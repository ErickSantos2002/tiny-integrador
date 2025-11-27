"""
Serviço para consulta de NFSe na Prefeitura do Recife
"""
import requests
from datetime import datetime, timedelta, date
from xml.sax.saxutils import escape
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional
from html import unescape


class NFSeRecifeService:
    """Serviço para integração com NFSe Recife"""

    def __init__(self, cert_path: str, key_path: str, cnpj: str, inscricao_municipal: str):
        self.cert_path = cert_path
        self.key_path = key_path
        self.cnpj = cnpj
        self.inscricao_municipal = inscricao_municipal
        self.wsdl_url = "https://nfse.recife.pe.gov.br/WSNacional/nfse_v01.asmx"
        self.namespace = "http://www.abrasf.org.br/ABRASF/arquivos/nfse.xsd"

    def consultar_nfse(self, data_inicial: date, data_final: date) -> List[Dict]:
        """
        Consulta NFSe por período

        Args:
            data_inicial: Data inicial da consulta
            data_final: Data final da consulta

        Returns:
            Lista de dicionários com dados das NFSe encontradas
        """
        # Formata datas
        data_ini_str = data_inicial.strftime("%Y-%m-%d")
        data_fim_str = data_final.strftime("%Y-%m-%d")

        # XML de consulta ABRASF
        xml_consulta = f"""<?xml version="1.0" encoding="utf-8"?>
<ConsultarNfseEnvio xmlns="{self.namespace}">
    <Prestador>
        <Cnpj>{self.cnpj}</Cnpj>
        <InscricaoMunicipal>{self.inscricao_municipal}</InscricaoMunicipal>
    </Prestador>
    <PeriodoEmissao>
        <DataInicial>{data_ini_str}</DataInicial>
        <DataFinal>{data_fim_str}</DataFinal>
    </PeriodoEmissao>
</ConsultarNfseEnvio>"""

        # Escapa o XML para colocar dentro do inputXML
        xml_consulta_escaped = escape(xml_consulta)

        # Envelope SOAP
        soap_body = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
               xmlns:nfse="http://nfse.recife.pe.gov.br/">
    <soap:Body>
        <nfse:ConsultarNfseRequest>
            <nfse:inputXML>{xml_consulta_escaped}</nfse:inputXML>
        </nfse:ConsultarNfseRequest>
    </soap:Body>
</soap:Envelope>"""

        # Faz a requisição
        response = requests.post(
            self.wsdl_url,
            data=soap_body.encode('utf-8'),
            headers={
                'Content-Type': 'text/xml; charset=utf-8',
                'SOAPAction': 'http://nfse.recife.pe.gov.br/ConsultarNfse'
            },
            cert=(self.cert_path, self.key_path),
            timeout=30
        )

        if response.status_code != 200:
            raise Exception(f"Erro HTTP {response.status_code}: {response.text}")

        # Parse do XML de resposta
        return self._parse_response(response.text)

    def _parse_response(self, xml_response: str) -> List[Dict]:
        """
        Faz o parsing da resposta SOAP

        Args:
            xml_response: XML de resposta do Web Service

        Returns:
            Lista de dicionários com dados das NFSe
        """
        # Remove namespaces para facilitar parsing
        root = ET.fromstring(xml_response)

        # Busca o outputXML dentro do SOAP
        output_xml = None
        for elem in root.iter():
            if 'outputXML' in elem.tag:
                output_xml = elem.text
                break

        if not output_xml:
            return []

        # Decodifica o XML escapado
        output_xml = unescape(output_xml)

        # Parse do XML de resposta ABRASF
        nfse_root = ET.fromstring(output_xml)

        # Define namespace ABRASF
        ns = {'nfse': self.namespace}

        notas = []

        # Busca todas as CompNfse
        for comp_nfse in nfse_root.findall('.//nfse:CompNfse', ns):
            try:
                nfse = comp_nfse.find('nfse:Nfse', ns)
                if nfse is None:
                    continue

                inf_nfse = nfse.find('nfse:InfNfse', ns)
                if inf_nfse is None:
                    continue

                # Extrai dados da NFSe
                nota = self._extrair_dados_nfse(inf_nfse, ns)
                notas.append(nota)

            except Exception as e:
                print(f"Erro ao processar NFSe: {e}")
                continue

        return notas

    def _extrair_dados_nfse(self, inf_nfse: ET.Element, ns: dict) -> Dict:
        """
        Extrai dados de uma NFSe do XML

        Args:
            inf_nfse: Elemento XML InfNfse
            ns: Namespaces

        Returns:
            Dicionário com dados da NFSe
        """
        def get_text(elem, path, default=None):
            """Helper para extrair texto de elemento XML"""
            found = elem.find(path, ns)
            return found.text if found is not None and found.text else default

        # Dados básicos da NFSe
        numero = get_text(inf_nfse, 'nfse:Numero')
        codigo_verificacao = get_text(inf_nfse, 'nfse:CodigoVerificacao')
        data_emissao = get_text(inf_nfse, 'nfse:DataEmissao')

        # RPS
        id_rps = inf_nfse.find('nfse:IdentificacaoRps', ns)
        numero_rps = get_text(id_rps, 'nfse:Numero') if id_rps is not None else None
        serie_rps = get_text(id_rps, 'nfse:Serie') if id_rps is not None else None
        tipo_rps = get_text(id_rps, 'nfse:Tipo') if id_rps is not None else None

        data_emissao_rps = get_text(inf_nfse, 'nfse:DataEmissaoRps')

        # Informações gerais
        natureza_operacao = get_text(inf_nfse, 'nfse:NaturezaOperacao')
        simples_nacional = get_text(inf_nfse, 'nfse:OptanteSimplesNacional')
        incentivo_cultural = get_text(inf_nfse, 'nfse:IncentivadorCultural')
        competencia = get_text(inf_nfse, 'nfse:Competencia')

        # Serviço
        servico = inf_nfse.find('nfse:Servico', ns)
        valores = servico.find('nfse:Valores', ns) if servico is not None else None

        valor_servicos = get_text(valores, 'nfse:ValorServicos') if valores is not None else None
        iss_retido = get_text(valores, 'nfse:IssRetido') if valores is not None else None
        valor_iss = get_text(valores, 'nfse:ValorIss') if valores is not None else None
        base_calculo = get_text(valores, 'nfse:BaseCalculo') if valores is not None else None
        aliquota = get_text(valores, 'nfse:Aliquota') if valores is not None else None
        valor_liquido = get_text(valores, 'nfse:ValorLiquidoNfse') if valores is not None else None
        valor_deducoes = get_text(valores, 'nfse:ValorDeducoes') if valores is not None else None
        valor_pis = get_text(valores, 'nfse:ValorPis') if valores is not None else None
        valor_cofins = get_text(valores, 'nfse:ValorCofins') if valores is not None else None
        valor_inss = get_text(valores, 'nfse:ValorInss') if valores is not None else None
        valor_ir = get_text(valores, 'nfse:ValorIr') if valores is not None else None
        valor_csll = get_text(valores, 'nfse:ValorCsll') if valores is not None else None

        item_lista = get_text(servico, 'nfse:ItemListaServico') if servico is not None else None
        codigo_tributacao = get_text(servico, 'nfse:CodigoTributacaoMunicipio') if servico is not None else None
        discriminacao = get_text(servico, 'nfse:Discriminacao') if servico is not None else None
        codigo_municipio = get_text(servico, 'nfse:CodigoMunicipio') if servico is not None else None

        # Prestador
        prestador = inf_nfse.find('nfse:PrestadorServico', ns)
        id_prestador = prestador.find('nfse:IdentificacaoPrestador', ns) if prestador is not None else None

        cnpj_prestador = get_text(id_prestador, 'nfse:Cnpj') if id_prestador is not None else None
        inscricao_municipal_prestador = get_text(id_prestador, 'nfse:InscricaoMunicipal') if id_prestador is not None else None
        razao_social_prestador = get_text(prestador, 'nfse:RazaoSocial') if prestador is not None else None

        endereco_prestador = prestador.find('nfse:Endereco', ns) if prestador is not None else None
        endereco_prest = get_text(endereco_prestador, 'nfse:Endereco') if endereco_prestador is not None else None
        numero_prest = get_text(endereco_prestador, 'nfse:Numero') if endereco_prestador is not None else None
        complemento_prest = get_text(endereco_prestador, 'nfse:Complemento') if endereco_prestador is not None else None
        bairro_prest = get_text(endereco_prestador, 'nfse:Bairro') if endereco_prestador is not None else None
        cod_municipio_prest = get_text(endereco_prestador, 'nfse:CodigoMunicipio') if endereco_prestador is not None else None
        uf_prest = get_text(endereco_prestador, 'nfse:Uf') if endereco_prestador is not None else None
        cep_prest = get_text(endereco_prestador, 'nfse:Cep') if endereco_prestador is not None else None

        contato_prestador = prestador.find('nfse:Contato', ns) if prestador is not None else None
        telefone_prest = get_text(contato_prestador, 'nfse:Telefone') if contato_prestador is not None else None
        email_prest = get_text(contato_prestador, 'nfse:Email') if contato_prestador is not None else None

        # Tomador
        tomador = inf_nfse.find('nfse:TomadorServico', ns)
        id_tomador = tomador.find('nfse:IdentificacaoTomador', ns) if tomador is not None else None
        cpf_cnpj_elem = id_tomador.find('nfse:CpfCnpj', ns) if id_tomador is not None else None

        cnpj_tomador = get_text(cpf_cnpj_elem, 'nfse:Cnpj') if cpf_cnpj_elem is not None else None
        if not cnpj_tomador:
            cnpj_tomador = get_text(cpf_cnpj_elem, 'nfse:Cpf') if cpf_cnpj_elem is not None else None

        inscricao_municipal_tomador = get_text(id_tomador, 'nfse:InscricaoMunicipal') if id_tomador is not None else None
        razao_social_tomador = get_text(tomador, 'nfse:RazaoSocial') if tomador is not None else None

        endereco_tomador = tomador.find('nfse:Endereco', ns) if tomador is not None else None
        endereco_tom = get_text(endereco_tomador, 'nfse:Endereco') if endereco_tomador is not None else None
        numero_tom = get_text(endereco_tomador, 'nfse:Numero') if endereco_tomador is not None else None
        complemento_tom = get_text(endereco_tomador, 'nfse:Complemento') if endereco_tomador is not None else None
        bairro_tom = get_text(endereco_tomador, 'nfse:Bairro') if endereco_tomador is not None else None
        cod_municipio_tom = get_text(endereco_tomador, 'nfse:CodigoMunicipio') if endereco_tomador is not None else None
        uf_tom = get_text(endereco_tomador, 'nfse:Uf') if endereco_tomador is not None else None
        cep_tom = get_text(endereco_tomador, 'nfse:Cep') if endereco_tomador is not None else None

        # Retorna dicionário com todos os dados
        return {
            'numero_nfse': int(numero) if numero else None,
            'codigo_verificacao': codigo_verificacao,
            'data_emissao': self._parse_date(data_emissao),
            'numero_rps': int(numero_rps) if numero_rps else None,
            'serie_rps': int(serie_rps) if serie_rps else None,
            'tipo_rps': int(tipo_rps) if tipo_rps else None,
            'data_emissao_rps': data_emissao_rps,
            'simples_nacional': int(simples_nacional) if simples_nacional else None,
            'incentivo_cultural': int(incentivo_cultural) if incentivo_cultural else None,
            'data_competencia': competencia,
            'valor_servico': valor_servicos,
            'iss_retido': int(iss_retido) if iss_retido else None,
            'valor_iss': valor_iss,
            'aliquota': aliquota,
            'valor_deducoes': valor_deducoes,
            'valor_pis': valor_pis,
            'valor_cofins': valor_cofins,
            'valor_inss': valor_inss,
            'valor_irpj': valor_ir,
            'valor_csll': valor_csll,
            'codigo_atividade_municipal': int(codigo_tributacao) if codigo_tributacao else None,
            'discriminacao_servico': discriminacao,
            'cpf_cnpj_prestador': cnpj_prestador,
            'inscricao_municipal_prestador': inscricao_municipal_prestador,
            'razao_social_prestador': razao_social_prestador,
            'endereco_prestador': endereco_prest,
            'numero_endereco_prestador': numero_prest,
            'complemento_endereco_prestador': complemento_prest,
            'bairro_prestador': bairro_prest,
            'uf_prestador': uf_prest,
            'cep_prestador': cep_prest,
            'telefone_prestador': telefone_prest,
            'email_prestador': email_prest,
            'cpf_cnpj_tomador': cnpj_tomador,
            'inscricao_municipal_tomador': inscricao_municipal_tomador,
            'razao_social_tomador': razao_social_tomador,
            'endereco_tomador': endereco_tom,
            'numero_endereco_tomador': numero_tom,
            'complemento_endereco_tomador': complemento_tom,
            'bairro_tomador': bairro_tom,
            'uf_tomador': uf_tom,
            'cep_tomador': cep_tom,
        }

    def _parse_date(self, date_str: Optional[str]) -> Optional[date]:
        """Converte string de data para objeto date"""
        if not date_str:
            return None

        try:
            # Tenta formato com hora
            if 'T' in date_str:
                return datetime.fromisoformat(date_str.replace('Z', '+00:00')).date()
            else:
                return datetime.strptime(date_str, '%Y-%m-%d').date()
        except:
            return None
