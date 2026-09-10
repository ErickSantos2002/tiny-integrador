"""Os recortes agregados das duas telas de Contas, somados no banco.

## Por que existe

As telas de Contas a Pagar e a Receber baixavam a tabela inteira para calcular
KPI, evolução, pizza de categorias e ranking de contraparte no navegador.
Medido em 2026-09-09: **7,9 MB** e **11,2 MB** por abertura de tela — as duas
respostas mais pesadas do sistema, maiores que a lista de notas de venda que
motivou toda a Fase 9.

E a maior parte disso nem é lida: a linha de conta carrega endereço, CEP,
e-mail e telefone da contraparte, e a tela mostra nome, cidade e UF.

## As regras, e onde elas ficam

As três grandezas de uma conta — decisão do Erick em 31/08/2026, documentada em
`pages/contas/contas.ts` — são reproduzidas aqui *exatamente*:

    quitado = valor - saldo            (de TODAS as contas, quitadas ou não:
                                        recebimento parcial é dinheiro que entrou)
    aberto  = 0 se quitada, senão saldo
    faturado = quitado + aberto        (a base dos três gráficos)

É por causa delas que o topo da tela fecha com o gráfico logo abaixo. Somar
valor cheio nas quitadas e saldo nas abertas — que era o defeito 1.1 — fazia
uma conta de mil com novecentos já recebidos aparecer como cem em "aberto",
com os novecentos em lugar nenhum.

⚠️ O que decide se uma conta está QUITADA muda entre as duas telas (`pago` em
Contas a Pagar; `pago` ou `recebido` em Contas a Receber), e por isso entra
como parâmetro. Já `vencida` **não** usa esse dialeto: as duas telas sempre a
calcularam com a mesma lista fixa (`pago`, `recebido`). Está preservado como
está — mudar isso mudaria o KPI de contas vencidas de uma das telas, e é
decisão de negócio, não de migração.

## O que NÃO está aqui

A escolha entre evolução anual e mensal, o corte da pizza em sete fatias mais
"Outros" e o top dez do ranking. Isso é desenho: continuam na tela, agora
operando sobre dezenas de linhas agregadas em vez de dez mil contas.
"""

from datetime import date
from typing import List, Optional

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

# As situações que contam como quitada, por tela. Lista fechada e no código —
# não vem do pedido.
QUITADAS_A_PAGAR = ["pago"]
QUITADAS_A_RECEBER = ["recebido", "pago"]

# `vencida` é a mesma conta nas duas telas, e não a do dialeto. Ver o aviso no
# topo deste módulo.
SITUACOES_QUE_NAO_VENCEM = ["pago", "recebido"]


class KpisDeContas(BaseModel):
    total_aberto: float
    total_quitado: float
    contas_vencidas: int
    a_vencer_30: int
    media_mensal: float
    #: Quantas contas o recorte tem — a tela mostra a contagem junto da tabela.
    contas: int


class AnoDeContas(BaseModel):
    ano: int
    quitado: float
    aberto: float


class MesDeContas(BaseModel):
    ano: int
    mes: int
    quitado: float
    aberto: float


class LinhaAgregada(BaseModel):
    nome: str
    valor: float


class OpcoesDeContas(BaseModel):
    situacao: List[str]
    categoria: List[str]
    contraparte: List[str]


class ResumoDeContas(BaseModel):
    kpis: KpisDeContas
    #: As duas séries vêm juntas: qual delas o gráfico desenha (anual quando a
    #: base tem mais de um ano) é decisão da tela, e é lá que ela é testada.
    por_ano: List[AnoDeContas]
    por_mes: List[MesDeContas]
    por_categoria: List[LinhaAgregada]
    por_contraparte: List[LinhaAgregada]
    opcoes: OpcoesDeContas


def _clausulas(campo_emissao: str) -> str:
    """Os cinco filtros da tela, na mesma ordem em que ela os aplica.

    `CAST()` e nunca o operador de cast com dois-pontos: em `text()` do
    SQLAlchemy os dois-pontos iniciam um bind param, e o cast viraria um
    parâmetro fantasma obrigatório — inclusive dentro de comentário, que o
    parser não ignora.
    """
    return f"""
    WHERE excluida_na_origem_em IS NULL
      AND (CAST(:situacoes AS text[]) IS NULL
           OR situacao = ANY(CAST(:situacoes AS text[])))
      -- `trim` nos dois lados, e não só na lista de opções. A opção que a tela
      -- oferece já vinha aparada; a linha do banco, não. Uma categoria gravada
      -- com espaço no fim ficava inalcançável — a pessoa marcava a opção e via
      -- menos contas, sem nada indicando o porquê. Medido em 2026-09-09: são
      -- 108 contas da Receita Federal em duas grafias que diferem só por
      -- espaço, e mais 66 de outra.
      AND (CAST(:categorias AS text[]) IS NULL
           OR trim(categoria) = ANY(CAST(:categorias AS text[])))
      AND (CAST(:contrapartes AS text[]) IS NULL
           OR trim(cliente_nome) = ANY(CAST(:contrapartes AS text[])))
      AND (CAST(:data_inicio AS date) IS NULL
           OR {campo_emissao} >= CAST(:data_inicio AS date))
      AND (CAST(:data_fim AS date) IS NULL
           OR {campo_emissao} <= CAST(:data_fim AS date))
    """


def _base(tabela: str, campo_emissao: str) -> str:
    """As contas do recorte, já com `quitado` e `aberto` calculados.

    Duas CTEs porque `quitada` não pode ser referenciada no mesmo `SELECT` que a
    define — repetir a expressão convidaria as duas cópias a divergirem.
    """
    return f"""
WITH filtradas AS (
    SELECT id,
           {campo_emissao} AS emissao,
           vencimento,
           situacao,
           categoria,
           cliente_nome,
           -- Os dois campos de texto que só a busca da tabela usa. Entram na
           -- CTE porque é ela que os agregados e a listagem compartilham, e
           -- duas CTEs quase iguais divergem no primeiro filtro que mudar.
           nro_documento,
           historico,
           COALESCE(valor, 0) AS valor,
           COALESCE(saldo, 0) AS saldo,
           lower(COALESCE(situacao, '')) = ANY(CAST(:quitadas AS text[])) AS quitada
    FROM tiny.{tabela}
    {_clausulas(campo_emissao)}
),
contas AS (
    SELECT *,
           valor - saldo                              AS quitado,
           CASE WHEN quitada THEN 0 ELSE saldo END    AS aberto
    FROM filtradas
)
"""


SQL_KPIS = """
SELECT COALESCE(SUM(quitado), 0) AS total_quitado,
       COALESCE(SUM(aberto), 0)  AS total_aberto,
       COUNT(*)                  AS contas,
       COUNT(*) FILTER (
           WHERE vencimento < CAST(:hoje AS date)
             AND lower(COALESCE(situacao, '')) <> ALL(CAST(:nao_vencem AS text[]))
       )                         AS contas_vencidas,
       COUNT(*) FILTER (
           WHERE vencimento >= CAST(:hoje AS date)
             AND vencimento <= CAST(:hoje AS date) + 30
             AND NOT quitada
       )                         AS a_vencer_30,
       -- O divisor é o número de meses DISTINTOS de emissão, como sempre foi:
       -- a média mensal faturada, coerente com o divisor ser mês de emissão.
       COUNT(DISTINCT to_char(emissao, 'YYYY-MM')) AS meses
FROM contas
"""

SQL_POR_ANO = """
SELECT EXTRACT(YEAR FROM emissao)::int AS ano,
       COALESCE(SUM(quitado), 0)       AS quitado,
       COALESCE(SUM(aberto), 0)        AS aberto
FROM contas
GROUP BY 1
ORDER BY 1
"""

SQL_POR_MES = """
SELECT EXTRACT(YEAR  FROM emissao)::int AS ano,
       EXTRACT(MONTH FROM emissao)::int AS mes,
       COALESCE(SUM(quitado), 0)        AS quitado,
       COALESCE(SUM(aberto), 0)         AS aberto
FROM contas
GROUP BY 1, 2
ORDER BY 1, 2
"""

# `faturado` — quitado + aberto — nos dois gráficos, porque é o que faz a soma
# das fatias ser exatamente "Total em Aberto + Total Recebido" e o topo da tela
# fechar com o gráfico (defeito 1.1).
SQL_POR_CATEGORIA = """
SELECT COALESCE(NULLIF(trim(categoria), ''), 'Sem categoria') AS nome,
       COALESCE(SUM(quitado + aberto), 0)               AS valor
FROM contas
GROUP BY 1
ORDER BY valor DESC, nome
"""

SQL_POR_CONTRAPARTE = """
SELECT trim(COALESCE(cliente_nome, '')) AS nome,
       COALESCE(SUM(quitado + aberto), 0) AS valor
FROM contas
GROUP BY 1
ORDER BY valor DESC, nome
"""

# As opções saem da base INTEIRA, e não do recorte: uma lista que encolhe com o
# filtro escondia justamente a opção que a pessoa ia marcar em seguida. O vazio
# fica de fora — um `cliente_nome` em branco virava uma opção clicável que não
# filtrava nada de útil.
SQL_OPCOES = """
SELECT DISTINCT trim(coluna) AS valor
FROM (
    SELECT {coluna} AS coluna
    FROM tiny.{tabela}
    WHERE excluida_na_origem_em IS NULL
) t
WHERE coluna IS NOT NULL AND trim(coluna) <> ''
ORDER BY 1
"""


def resumo_de_contas(
    db: Session,
    *,
    tabela: str,
    campo_emissao: str,
    quitadas: List[str],
    situacoes: Optional[List[str]],
    categorias: Optional[List[str]],
    contrapartes: Optional[List[str]],
    data_inicio: Optional[date],
    data_fim: Optional[date],
    hoje: date,
) -> ResumoDeContas:
    """Os quatro recortes que a tela desenha, para um mesmo filtro."""
    base = _base(tabela, campo_emissao)
    params = {
        "quitadas": quitadas,
        "nao_vencem": SITUACOES_QUE_NAO_VENCEM,
        "situacoes": situacoes or None,
        "categorias": categorias or None,
        "contrapartes": contrapartes or None,
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "hoje": hoje,
    }

    linha = db.execute(text(base + SQL_KPIS), params).mappings().first()
    total_aberto = float(linha["total_aberto"] or 0)
    total_quitado = float(linha["total_quitado"] or 0)
    meses = int(linha["meses"] or 0)

    def opcoes(coluna: str) -> List[str]:
        sql = SQL_OPCOES.format(coluna=coluna, tabela=tabela)
        return [l["valor"] for l in db.execute(text(sql)).mappings()]

    return ResumoDeContas(
        kpis=KpisDeContas(
            total_aberto=total_aberto,
            total_quitado=total_quitado,
            contas_vencidas=int(linha["contas_vencidas"] or 0),
            a_vencer_30=int(linha["a_vencer_30"] or 0),
            media_mensal=((total_aberto + total_quitado) / meses) if meses else 0.0,
            contas=int(linha["contas"] or 0),
        ),
        por_ano=[
            AnoDeContas(**dict(l)) for l in db.execute(text(base + SQL_POR_ANO), params).mappings()
        ],
        por_mes=[
            MesDeContas(**dict(l)) for l in db.execute(text(base + SQL_POR_MES), params).mappings()
        ],
        por_categoria=[
            LinhaAgregada(**dict(l))
            for l in db.execute(text(base + SQL_POR_CATEGORIA), params).mappings()
        ],
        por_contraparte=[
            LinhaAgregada(**dict(l))
            for l in db.execute(text(base + SQL_POR_CONTRAPARTE), params).mappings()
        ],
        opcoes=OpcoesDeContas(
            situacao=opcoes("situacao"),
            categoria=opcoes("categoria"),
            contraparte=opcoes("cliente_nome"),
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# A tabela: uma página, com as colunas que a tela lê
# ─────────────────────────────────────────────────────────────────────────────
#
# A linha de conta tem trinta e poucas colunas, e a tela mostra treze. Iam junto
# endereço, número, complemento, bairro, CEP, país, e-mail, telefone, IE e RG da
# contraparte — em dez mil linhas. Nada disso aparece na tela, e boa parte é dado
# pessoal que não tem por que trafegar.

COLUNAS_DA_TELA = """
    id,
    id_tiny,
    {campo_emissao} AS emissao,
    vencimento,
    situacao,
    categoria,
    cliente_nome,
    cliente_cpf_cnpj,
    cliente_cidade,
    cliente_uf,
    nro_documento,
    historico,
    liquidacao,
    COALESCE(valor, 0) AS valor,
    COALESCE(saldo, 0) AS saldo,
    -- As duas condições que a tabela usa para colorir o selo da situação.
    -- Vêm do banco, e não recalculadas no navegador, porque são as MESMAS
    -- regras que decidem os KPIs logo acima da tabela: um selo verde numa
    -- linha que o KPI conta como aberta é o tipo de divergência que ninguém
    -- percebe olhando.
    lower(COALESCE(situacao, '')) = ANY(CAST(:quitadas AS text[])) AS quitada,
    (vencimento < CAST(:hoje AS date)
     AND lower(COALESCE(situacao, '')) <> ALL(CAST(:nao_vencem AS text[]))) AS vencida
"""

# A busca da tabela: nome da contraparte, categoria, nº do documento e histórico —
# os mesmos quatro campos que o navegador procurava, e nenhum a mais. Situação,
# valor, saldo, id e data ficam de fora, como sempre ficaram.
#
# ⚠️ `unaccent` NÃO está instalado no servidor (o mesmo achado da macro
# `normalizar_texto` do dbt), então o acento cai por `translate`. Quem digita
# `servicos` acha `Serviços`, e quem digita `Serviços` continua achando.
_ACENTUADAS = "áàâãäéèêëíìîïóòôõöúùûüçÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ"
_SEM_ACENTO = "aaaaaeeeeiiiiooooouuuucAAAAAEEEEIIIIOOOOOUUUUC"


def _dobrado(expressao: str) -> str:
    return f"translate(lower({expressao}), '{_ACENTUADAS}', '{_SEM_ACENTO}')"


CAMPOS_DA_BUSCA = ["cliente_nome", "categoria", "nro_documento", "historico"]


def _clausula_de_busca() -> str:
    """A cláusula OR que procura o termo nos quatro campos.

    ⚠️ Montada por concatenação, e não por f-string aninhada. A imagem roda
    Python **3.11**, onde backslash dentro da expressão de uma f-string é erro
    de SINTAXE — o módulo nem importa, e o gunicorn morre no boot. No 3.11 o
    aspas-dentro-de-aspas também não vale. Isto passou despercebido porque a
    `.venv` local é 3.14, onde a PEP 701 permite as duas coisas: o
    `import app.main` daqui não reproduz o erro de lá.
    """
    vazio = "''"
    alvo = _dobrado("CAST(:busca AS text)")
    casa = [
        _dobrado("COALESCE(" + campo + ", " + vazio + ")")
        + " LIKE '%' || " + alvo + " || '%'"
        for campo in CAMPOS_DA_BUSCA
    ]
    return " AND (CAST(:busca AS text) IS NULL OR (" + " OR ".join(casa) + "))"


FILTRO_DE_BUSCA = _clausula_de_busca()

# Ordenação por lista fechada: o `ORDER BY` é a única parte da consulta que não
# pode ser bind param, então o que entra ali sai daqui e nunca do pedido.
ORDENACOES_DE_CONTAS = {
    "vencimento": "vencimento {d}, id {d}",
    "emissao": "emissao {d}, id {d}",
    "cliente_nome": "cliente_nome {d} NULLS LAST, id DESC",
    "categoria": "categoria {d} NULLS LAST, id DESC",
    "situacao": "situacao {d} NULLS LAST, id DESC",
    "valor_numero": "valor {d}, id DESC",
    "saldo_numero": "saldo {d}, id DESC",
    "nro_documento": "nro_documento {d} NULLS LAST, id DESC",
}


class ContaDaTela(BaseModel):
    id: int
    id_tiny: int | None = None
    #: `contas_receber.data` e `contas_pagar.data_emissao` sob um nome só — a
    #: coluna se chama "Emissão" nas duas telas.
    emissao: date | None = None
    vencimento: date | None = None
    situacao: str | None = None
    categoria: str | None = None
    cliente_nome: str | None = None
    cliente_cpf_cnpj: str | None = None
    cliente_cidade: str | None = None
    cliente_uf: str | None = None
    nro_documento: str | None = None
    historico: str | None = None
    #: `date`, e não texto: a coluna é `date` no banco. O schema antigo dizia
    #: `str` e o Pydantic entregava a data serializada — a tela sempre a tratou
    #: como string de calendário, e continua recebendo `AAAA-MM-DD`.
    liquidacao: date | None = None
    #: Número, e não o texto que o navegador convertia: as colunas são `numeric`
    #: na origem, e a conversão no front era uma cópia a mais para divergir.
    valor: float
    saldo: float
    quitada: bool
    #: Venceu e não foi paga. Usa a lista fixa (`pago`, `recebido`), e não o
    #: dialeto da tela — é como as duas telas sempre calcularam.
    vencida: bool
    # As três colunas que existem em uma das tabelas e não na outra, e que só a
    # PLANILHA usa. `None` na tela que não as tem — o schema é um só porque as
    # duas telas são a mesma tela com vocabulário diferente.
    forma_pagamento: str | None = None
    portador: str | None = None
    ocorrencia: str | None = None


class PaginaDeContas(BaseModel):
    itens: List[ContaDaTela]
    #: Do FILTRO, não da página — é o que impede a tela de somar o que recebeu.
    total: int
    total_aberto: float
    total_quitado: float
    limite: int
    offset: int


def pagina_de_contas(
    db: Session,
    *,
    tabela: str,
    campo_emissao: str,
    quitadas: List[str],
    situacoes: Optional[List[str]],
    categorias: Optional[List[str]],
    contrapartes: Optional[List[str]],
    data_inicio: Optional[date],
    data_fim: Optional[date],
    busca: Optional[str],
    ordenar_por: str,
    direcao: str,
    limite: int,
    offset: int,
    hoje: date,
    colunas_extras: Optional[List[str]] = None,
) -> PaginaDeContas:
    """Uma página da tabela, filtrada, buscada e ordenada pelo banco.

    `colunas_extras` são as que existem só numa das duas tabelas e vão para a
    planilha. Vêm do código da rota, nunca do pedido: entram concatenadas no
    `SELECT`, que é onde bind param não alcança.
    """
    base = _base(tabela, campo_emissao)
    params = {
        "quitadas": quitadas,
        "situacoes": situacoes or None,
        "categorias": categorias or None,
        "contrapartes": contrapartes or None,
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "busca": (busca or "").strip() or None,
        "nao_vencem": SITUACOES_QUE_NAO_VENCEM,
        "hoje": hoje,
    }

    contagem = db.execute(
        text(
            base
            + "SELECT COUNT(*) AS total, COALESCE(SUM(aberto), 0) AS aberto, "
            "COALESCE(SUM(quitado), 0) AS quitado FROM contas WHERE true"
            + FILTRO_DE_BUSCA
        ),
        params,
    ).mappings().first()

    permitidas = {"forma_pagamento", "portador", "ocorrencia"}
    escolhidas = [c for c in (colunas_extras or []) if c in permitidas]
    extras = "".join(f",\n    {coluna}" for coluna in escolhidas)

    ordem = ORDENACOES_DE_CONTAS[ordenar_por].format(d=direcao.upper())
    # Vírgula, e não um `WITH` novo: `base` já abriu as CTEs, e duas cláusulas
    # `WITH` na mesma consulta é erro de sintaxe.
    sql_itens = f"""
, pagina AS (
    SELECT id FROM contas WHERE true {FILTRO_DE_BUSCA}
    ORDER BY {ordem}
    LIMIT :limite OFFSET :offset
)
SELECT {COLUNAS_DA_TELA.format(campo_emissao=campo_emissao)}{extras}
FROM tiny.{tabela}
WHERE id IN (SELECT id FROM pagina)
ORDER BY {ordem}
"""
    linhas = db.execute(
        text(base + sql_itens), {**params, "limite": limite, "offset": offset}
    ).mappings()

    return PaginaDeContas(
        itens=[ContaDaTela(**dict(l)) for l in linhas],
        total=int(contagem["total"] or 0),
        total_aberto=float(contagem["aberto"] or 0),
        total_quitado=float(contagem["quitado"] or 0),
        limite=limite,
        offset=offset,
    )
