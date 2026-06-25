"""
Serviço para consulta de NFS-e no Ambiente de Dados Nacional (ADN Contribuinte).

Substitui o caminho antigo (SOAP/ABRASF no WS da Prefeitura do Recife), que parou
de receber as notas emitidas pelo Emissor Nacional. Mantém EXATAMENTE a mesma
interface pública do NFSeRecifeService — `consultar_nfse(data_inicial, data_final)`
retornando uma lista de dicionários com as MESMAS CHAVES — para que o endpoint
de importação grave os mesmos valores, da mesma forma, no banco.

Como funciona o ADN (Ambiente de Dados Nacional):
  - Endpoint: GET https://adn.nfse.gov.br/contribuintes/DFe/{NSU}?cnpjConsulta={CNPJ}
  - Autenticação: mTLS (TLS 1.2+) com o e-CNPJ A1 (mesmo certificado já usado).
  - O cnpjConsulta é OBRIGATÓRIO na prática: sem ele o servidor varre tudo e dá 504.
  - Resposta JSON com LoteDFe[] (até 50 docs por lote); paginação por NSU incremental.
  - Cada documento traz ArquivoXml = GZip -> base64, no leiaute nacional
    (namespace http://www.sped.fazenda.gov.br/nfse), diferente do ABRASF.
  - A distribuição inclui TODO documento de interesse: como PRESTADOR (emitidas) e
    como TOMADOR (recebidas). Aqui filtramos só as emitidas pelo nosso CNPJ.
"""
import base64
import gzip
import time
from datetime import datetime, date
from typing import List, Dict, Optional
from xml.etree import ElementTree as ET

import requests


class NFSeRecifeNacionalService:
    """Consulta NFS-e do contribuinte no ADN (padrão nacional)."""

    NS = {"n": "http://www.sped.fazenda.gov.br/nfse"}
    BASE_URL = "https://adn.nfse.gov.br/contribuintes/DFe"

    def __init__(self, cert_path: str, key_path: str, cnpj: str,
                 inscricao_municipal: Optional[str] = None):
        self.cert = (cert_path, key_path)
        self.cnpj = cnpj
        self.inscricao_municipal = inscricao_municipal

    # ------------------------------------------------------------------ API
    def consultar_nfse(self, data_inicial: date, data_final: date,
                       desde_nsu: int = 1) -> List[Dict]:
        """
        Retorna as NFS-e EMITIDAS pelo nosso CNPJ cujo `dhEmi` cai no período.

        Mantém a assinatura do serviço antigo. O ADN só permite consulta por NSU
        (não por data), então paginamos a partir de `desde_nsu` e filtramos a data
        no cliente. `desde_nsu` é opcional: deixe 1 para varrer tudo (comportamento
        equivalente ao antigo) ou informe o último NSU já processado para busca
        incremental (mais leve e robusto contra instabilidade do ADN).
        """
        docs = self._paginar(desde_nsu)
        notas = []
        for doc in docs:
            xml = self._descompactar(doc.get("ArquivoXml"))
            if not xml:
                continue
            dados = self._extrair_dados_nfse(xml, doc)
            if not dados:
                continue
            # só notas em que SOMOS o prestador (emitidas) — espelha o WS antigo
            if dados["cpf_cnpj_prestador"] != self.cnpj:
                continue
            de = dados["data_emissao"]
            if de and (data_inicial <= de <= data_final):
                notas.append(dados)
        return notas

    # -------------------------------------------------------------- HTTP/ADN
    def _paginar(self, desde_nsu: int, max_paginas: int = 80) -> List[Dict]:
        """Pagina a distribuição por NSU. Levanta exceção se uma página falhar de
        vez (melhor falhar e reprocessar depois — o dedupe por número evita
        duplicar — do que importar parcial silenciosamente)."""
        docs: List[Dict] = []
        nsu = desde_nsu
        with requests.Session() as session:
            for _ in range(max_paginas):
                resp = self._buscar_lote(session, nsu)
                lote = resp.get("LoteDFe") or []
                if not lote:
                    break
                docs.extend(lote)
                max_nsu = max(d["NSU"] for d in lote)
                if len(lote) < 50:        # último lote
                    break
                nsu = max_nsu + 1
                time.sleep(0.3)
        return docs

    def _buscar_lote(self, session: requests.Session, nsu: int,
                     tentativas: int = 4) -> Dict:
        """GET /DFe/{nsu}?cnpjConsulta=CNPJ com retry/backoff (o ADN dá 504 sob carga)."""
        url = f"{self.BASE_URL}/{nsu}"
        params = {"cnpjConsulta": self.cnpj}
        ultimo_erro = None
        for t in range(tentativas):
            try:
                r = session.get(url, params=params, cert=self.cert,
                                headers={"Accept": "application/json"}, timeout=100)
                if r.status_code == 200:
                    return r.json()
                ultimo_erro = f"HTTP {r.status_code}"
            except requests.RequestException as e:
                ultimo_erro = f"{type(e).__name__}: {e}"
            time.sleep(1.5 * (t + 1))
        raise Exception(f"Falha ao consultar ADN no NSU {nsu} após {tentativas} "
                        f"tentativas (último erro: {ultimo_erro})")

    @staticmethod
    def _descompactar(arquivo_xml_b64: Optional[str]) -> Optional[str]:
        if not arquivo_xml_b64:
            return None
        raw = base64.b64decode(arquivo_xml_b64)
        try:
            return gzip.decompress(raw).decode("utf-8", "replace")
        except OSError:
            return raw.decode("utf-8", "replace")

    # ----------------------------------------------------------- XML -> dict
    def _txt(self, parent, path: str) -> Optional[str]:
        if parent is None:
            return None
        el = parent.find(path, self.NS)
        return el.text if (el is not None and el.text) else None

    @staticmethod
    def _to_int(v: Optional[str]) -> Optional[int]:
        try:
            return int(v) if v not in (None, "") else None
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_date(date_str: Optional[str]) -> Optional[date]:
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str).date()
        except ValueError:
            try:
                return datetime.strptime(date_str[:10], "%Y-%m-%d").date()
            except ValueError:
                return None

    def _extrair_dados_nfse(self, xml_str: str, doc: Dict) -> Optional[Dict]:
        """Mapeia o XML nacional para o MESMO dicionário do serviço antigo."""
        try:
            root = ET.fromstring(xml_str)
        except ET.ParseError:
            return None
        inf = root.find(".//n:infNFSe", self.NS)
        if inf is None:
            return None

        emit = inf.find(".//n:emit", self.NS)          # prestador (infNFSe)
        ender_p = emit.find("n:enderNac", self.NS) if emit is not None else None
        toma = inf.find(".//n:toma", self.NS)           # tomador (infDPS)
        end_t = toma.find("n:end", self.NS) if toma is not None else None
        endnac_t = end_t.find("n:endNac", self.NS) if end_t is not None else None

        # CNPJ/CPF do tomador
        cnpj_tomador = self._txt(toma, "n:CNPJ") or self._txt(toma, "n:CPF")

        # ISS retido: traduz o código nacional (tpRetISSQN: 1=Não retido,
        # 2/3=Retido) para o código ABRASF antigo (1=Sim, 2=Não), preservando o
        # sentido no banco. >>> CONFERIR se algum relatório depende deste código.
        tp_ret = self._to_int(self._txt(inf, ".//n:tpRetISSQN"))
        iss_retido = None
        if tp_ret is not None:
            iss_retido = 2 if tp_ret == 1 else 1

        return {
            # identificação
            "numero_nfse": self._to_int(self._txt(inf, "n:nNFSe")),
            "codigo_verificacao": doc.get("ChaveAcesso"),  # chave de acesso nacional
            "data_emissao": self._parse_date(self._txt(inf, ".//n:dhEmi")),
            "numero_rps": self._to_int(self._txt(inf, ".//n:nDPS")),  # DPS ~ RPS
            "serie_rps": self._to_int(self._txt(inf, ".//n:serie")),
            "tipo_rps": None,                              # sem equivalente nacional
            "data_emissao_rps": None,
            "simples_nacional": self._to_int(self._txt(inf, ".//n:opSimpNac")),
            "incentivo_cultural": None,
            "data_competencia": self._txt(inf, ".//n:dCompet"),
            # valores
            "valor_servico": self._txt(inf, ".//n:vServPrest/n:vServ"),
            "iss_retido": iss_retido,
            "valor_iss": self._txt(inf, ".//n:vISSQN"),
            "aliquota": self._txt(inf, ".//n:pAliqAplic"),
            "valor_deducoes": None,
            "valor_pis": None,
            "valor_cofins": None,
            "valor_inss": None,
            "valor_irpj": None,
            "valor_csll": None,
            # serviço
            "codigo_atividade_municipal": self._to_int(self._txt(inf, ".//n:cTribMun")),
            "discriminacao_servico": self._txt(inf, ".//n:xDescServ"),
            # prestador
            "cpf_cnpj_prestador": self._txt(emit, "n:CNPJ"),
            "inscricao_municipal_prestador": self._txt(emit, "n:IM"),
            "razao_social_prestador": self._txt(emit, "n:xNome"),
            "endereco_prestador": self._txt(ender_p, "n:xLgr"),
            "numero_endereco_prestador": self._txt(ender_p, "n:nro"),
            "complemento_endereco_prestador": self._txt(ender_p, "n:xCpl"),
            "bairro_prestador": self._txt(ender_p, "n:xBairro"),
            "uf_prestador": self._txt(ender_p, "n:UF"),
            "cep_prestador": self._txt(ender_p, "n:CEP"),
            "telefone_prestador": self._txt(emit, "n:fone"),
            "email_prestador": self._txt(emit, "n:email"),
            # tomador
            "cpf_cnpj_tomador": cnpj_tomador,
            "inscricao_municipal_tomador": self._txt(toma, "n:IM"),
            "razao_social_tomador": self._txt(toma, "n:xNome"),
            "endereco_tomador": self._txt(end_t, "n:xLgr"),
            "numero_endereco_tomador": self._txt(end_t, "n:nro"),
            "complemento_endereco_tomador": self._txt(end_t, "n:xCpl"),
            "bairro_tomador": self._txt(end_t, "n:xBairro"),
            "uf_tomador": self._txt(endnac_t, "n:UF"),     # geralmente ausente no leiaute
            "cep_tomador": self._txt(endnac_t, "n:CEP"),
            # status — cancelamento no nacional vem como Evento separado (não tratado aqui)
            "cancelada": False,
        }
