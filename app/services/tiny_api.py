"""Cliente da API do Tiny (api2) para notas fiscais.

Existe para substituir o fluxo `[DATACORE] Puxar_Notas` do n8n, que gravava marcador
errado e nunca atualizava marcador posto depois da carga. Duas escolhas aqui são
resposta direta àqueles defeitos:

1. **`formato=json`, nunca XML.** No XML, `marcadores` vira objeto quando a nota tem um
   marcador e vira lista quando tem dois ou mais. O n8n lia sempre `marcadores.marcador
   .descricao`, o que dá `undefined` no caso da lista — e o `undefined` virava NULL no
   banco. Em JSON o campo é sempre lista, inclusive vazia.
2. **Erro da API não é HTTP.** O Tiny responde 200 com `retorno.status = "Erro"` no corpo.
   Quem só olha o código HTTP acha que deu certo e grava lixo.

Limite de chamadas: a própria API informa o teto do plano no cabeçalho **`x-limit-api`**
(20 por minuto no plano da empresa, medido em 2026-09-03). O cliente lê esse cabeçalho e
ajusta o ritmo sozinho, com folga — não adianta acertar o limite na régua, porque a conta
é por janela de minuto e qualquer atraso de rede empurra duas chamadas para o mesmo
minuto. Foi exatamente assim que a carga levou "API Bloqueada" na primeira tentativa:
3s entre chamadas dá 20/min cravado, sem margem.
"""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any, Iterator, Optional

import requests

logger = logging.getLogger(__name__)

URL_BASE = "https://api.tiny.com.br/api2"
ESPERA_PADRAO = 3.0
TIMEOUT = 30

# Quanto do teto informado por `x-limit-api` a gente se permite usar. 0.85 = 17 chamadas
# por minuto num limite de 20, o que deixa espaço para a variação de latência.
FOLGA_DO_LIMITE = 0.85

# Quando a API responde "API Bloqueada", ela pede para aguardar *alguns minutos*. Esperar
# os mesmos 3s de sempre e tentar de novo só gasta tentativa: o bloqueio é por janela.
ESPERA_APOS_BLOQUEIO = 60.0

# `status_processamento` da api2: 1 = erro na consulta, 2 = a consulta funcionou e não
# achou nada, 3 = achou. O 2 não é falha — é resposta vazia legítima.
PROC_ERRO, PROC_VAZIO, PROC_OK = "1", "2", "3"

# Códigos que significam "você está batendo demais" ou "a API caiu agora". Valem nova
# tentativa; qualquer outro erro é definitivo e tentar de novo só gasta tempo.
CODIGOS_TEMPORARIOS = {"6"}

# A api2 não tem uma resposta vazia só: às vezes devolve `status_processamento = 2`, e
# às vezes devolve **erro** com este código e a mensagem "A consulta não retornou
# registros". Nada disso é falha — é a pesquisa dizendo que não achou nada. Tratar como
# erro faria a carga abortar sempre que um filtro viesse vazio (descoberto em 2026-09-03,
# procurando contas com situação "parcial", que naquele dia não existiam).
CODIGO_SEM_REGISTROS = "20"


class TinySemRegistros(Exception):
    """A pesquisa funcionou e não achou nada. Não é erro."""


class TinyAPIError(Exception):
    """Erro devolvido pela API do Tiny (HTTP 200 com `status: Erro` no corpo)."""

    def __init__(self, mensagem: str, codigo: Optional[str] = None):
        super().__init__(mensagem)
        self.codigo = codigo

    @property
    def temporario(self) -> bool:
        return self.codigo in CODIGOS_TEMPORARIOS


class TinyAPI:
    def __init__(self, token: str, espera: float = ESPERA_PADRAO,
                 sessao: Optional[requests.Session] = None, tentativas: int = 3):
        if not token:
            raise ValueError("token do Tiny não informado")
        self.token = token
        self.espera = espera
        self.tentativas = tentativas
        self.sessao = sessao or requests.Session()
        self._ultima_chamada = 0.0
        self._espera_minima = espera  # o que o header impuser nunca fica abaixo disto

    # ------------------------------------------------------------------ interno

    def _aguardar(self) -> None:
        """Segura o ritmo sem dormir mais do que o necessário.

        Dormir `espera` a cada chamada ignora o tempo que a própria requisição levou.
        Aqui o intervalo é medido de partida a partida: se a API demorou 2s para
        responder e a espera é 3s, dorme 1s.
        """
        falta = self.espera - (time.monotonic() - self._ultima_chamada)
        if falta > 0:
            time.sleep(falta)

    def _ajustar_ritmo(self, resposta) -> None:
        """Obedece ao teto que a API declara em `x-limit-api` (chamadas por minuto)."""
        try:
            limite = int(resposta.headers.get("x-limit-api", ""))
        except ValueError:
            return
        if limite <= 0:
            return
        nova = 60.0 / (limite * FOLGA_DO_LIMITE)
        if nova > self.espera:
            logger.info("ritmo ajustado para %.1fs entre chamadas (x-limit-api = %d/min)",
                        nova, limite)
            self.espera = nova

    def _get(self, caminho: str, params: dict[str, Any]) -> dict:
        params = {**params, "token": self.token, "formato": "json"}
        ultimo_erro: Optional[Exception] = None

        for tentativa in range(1, self.tentativas + 1):
            self._aguardar()
            self._ultima_chamada = time.monotonic()
            try:
                r = self.sessao.get(f"{URL_BASE}/{caminho}", params=params, timeout=TIMEOUT)
                r.raise_for_status()
                self._ajustar_ritmo(r)
                corpo = r.json()
            except (requests.RequestException, ValueError) as e:
                ultimo_erro = e
                logger.warning("%s: falha de rede (tentativa %d/%d): %s",
                               caminho, tentativa, self.tentativas, e)
                time.sleep(self.espera * tentativa)
                continue

            retorno = corpo.get("retorno") or {}
            if retorno.get("status") == "Erro":
                codigo = str(retorno.get("codigo_erro") or "")
                texto = _texto_do_erro(retorno)
                if codigo == CODIGO_SEM_REGISTROS or "não retornou registros" in texto:
                    raise TinySemRegistros(texto)
                erro = TinyAPIError(texto, codigo)
                if erro.temporario and tentativa < self.tentativas:
                    ultimo_erro = erro
                    pausa = ESPERA_APOS_BLOQUEIO * tentativa
                    logger.warning("%s: %s — aguardando %.0fs (tentativa %d/%d)",
                                   caminho, erro, pausa, tentativa, self.tentativas)
                    time.sleep(pausa)
                    continue
                raise erro
            return retorno

        raise TinyAPIError(f"{caminho}: falhou em {self.tentativas} tentativas: {ultimo_erro}")

    # ------------------------------------------------------------------ público

    def pesquisar_ids(self, data_inicial: date, data_final: Optional[date] = None) -> Iterator[str]:
        """Devolve os ids do Tiny das notas emitidas no período, página por página.

        A pesquisa é por data de emissão e vem paginada. O n8n descobria o número de
        páginas numa chamada e depois montava a lista à mão com dois nós de código e um
        acumulador; aqui é um laço que para quando `pagina == numero_paginas`.
        """
        pagina = 1
        while True:
            params = {
                "dataInicial": data_inicial.strftime("%d/%m/%Y"),
                "pagina": pagina,
            }
            if data_final:
                params["dataFinal"] = data_final.strftime("%d/%m/%Y")

            try:
                retorno = self._get("notas.fiscais.pesquisa.php", params)
            except TinySemRegistros:
                return  # período sem nota nenhuma: não é erro

            if str(retorno.get("status_processamento")) == PROC_VAZIO:
                return

            for item in retorno.get("notas_fiscais") or []:
                nota = item.get("nota_fiscal") or {}
                if nota.get("id"):
                    yield str(nota["id"])

            total = int(retorno.get("numero_paginas") or 1)
            if pagina >= total:
                return
            pagina += 1

    # --- contas a pagar e a receber -------------------------------------------
    #
    # As duas têm a mesma API com nome trocado, então `tipo` é "pagar" ou "receber".
    # O fluxo do n8n pesquisava por emissão a partir de uma data ESCRITA À MÃO no nó
    # (30/06/2026 nas contas a pagar, 14/03/2026 nas a receber). Isso envelhece sozinho:
    # conta emitida antes daquele dia nunca mais era reconferida, então conta antiga que
    # fosse paga continuava "aberto" no banco para sempre — 226 contas a pagar,
    # R$ 962 mil, contra 3 realmente em aberto no Tiny (medido em 2026-09-03).
    #
    # Por isso existe `pesquisar_contas_por_situacao`: além da janela por emissão, a
    # carga reconfere tudo que ainda está em aberto, sem limite de data.

    def pesquisar_ids_de_contas(self, tipo: str, data_inicial: date,
                                data_final: Optional[date] = None) -> Iterator[str]:
        """Ids das contas emitidas no período."""
        yield from self._pesquisar_contas(tipo, {
            "data_ini_emissao": data_inicial.strftime("%d/%m/%Y"),
            **({"data_fim_emissao": data_final.strftime("%d/%m/%Y")} if data_final else {}),
        })

    def pesquisar_ids_de_contas_em_aberto(self, tipo: str) -> Iterator[str]:
        """Ids de tudo que o Tiny ainda considera não quitado, de qualquer data."""
        for situacao in ("aberto", "parcial"):
            yield from self._pesquisar_contas(tipo, {"situacao": situacao})

    def _pesquisar_contas(self, tipo: str, filtros: dict) -> Iterator[str]:
        pagina = 1
        while True:
            try:
                retorno = self._get(f"contas.{tipo}.pesquisa.php", {**filtros, "pagina": pagina})
            except TinySemRegistros:
                return
            if str(retorno.get("status_processamento")) == PROC_VAZIO:
                return
            for item in retorno.get("contas") or []:
                conta = item.get("conta") or item
                if conta.get("id"):
                    yield str(conta["id"])
            total = int(retorno.get("numero_paginas") or 1)
            if pagina >= total:
                return
            pagina += 1

    def obter_conta(self, tipo: str, id_tiny: str) -> dict:
        retorno = self._get(f"conta.{tipo}.obter.php", {"id": id_tiny})
        return retorno.get("conta") or {}

    # --- produtos e saldo -----------------------------------------------------
    #
    # O fluxo do n8n tinha TRÊS blocos copiados, um para a página 1, outro para a 2 e
    # outro para a 3 — paginação escrita à mão. Hoje existem exatamente 3 páginas de
    # produto; a quarta simplesmente não seria vista, sem erro nenhum. E só a página 1
    # tinha o passo de inserir produto novo: produto das páginas 2 e 3 que ainda não
    # estivesse no banco nunca entrava (270 no banco contra 300 na origem).

    def pesquisar_produtos(self) -> Iterator[dict]:
        """Todos os produtos, seguindo a paginação até onde ela for."""
        pagina = 1
        while True:
            try:
                retorno = self._get("produtos.pesquisa.php", {"pagina": pagina})
            except TinySemRegistros:
                return
            if str(retorno.get("status_processamento")) == PROC_VAZIO:
                return
            for item in retorno.get("produtos") or []:
                produto = item.get("produto") or item
                if produto.get("id"):
                    yield produto
            total = int(retorno.get("numero_paginas") or 1)
            if pagina >= total:
                return
            pagina += 1

    def obter_saldo(self, id_produto: str) -> dict:
        """O saldo em estoque não vem na pesquisa: é uma chamada por produto."""
        retorno = self._get("produto.obter.estoque.php", {"id": id_produto})
        return retorno.get("produto") or {}

    def obter_nota(self, id_tiny: str) -> dict:
        """A nota completa: cliente, endereço de entrega, itens, marcadores e forma de envio."""
        retorno = self._get("nota.fiscal.obter.php", {"id": id_tiny})
        return retorno.get("nota_fiscal") or {}


def _texto_do_erro(retorno: dict) -> str:
    """A api2 devolve os erros em `erros: [{erro: "..."}]`, às vezes só em `erro`."""
    erros = retorno.get("erros")
    if isinstance(erros, list):
        partes = [str(e.get("erro") if isinstance(e, dict) else e) for e in erros]
        if partes:
            return "; ".join(partes)
    return str(retorno.get("erro") or "erro sem descrição")
