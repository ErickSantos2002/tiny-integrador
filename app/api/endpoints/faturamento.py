"""Faturamento lido da camada `gold` — a régua única, já aplicada.

## Por que este módulo existe, se `/notas_fiscais/vendas/` já responde faturamento

Porque aquele endpoint **reimplementa a régua**. Ele filtra CFOP procurando a substring
dentro de `natureza_operacao`, que é campo de texto livre, e compara o marcador contra uma
lista fixa de sete descrições. Isso tem dois defeitos medidos (item 9.1):

- **24 notas canceladas contam como faturamento.** O Tiny grava `NF cancelada`, a lista tem
  `nf cancelada`, e a comparação é sensível a maiúscula — a nota passa direto.
- **Exportação some.** A lista tem quatro CFOPs e o 7102 não está lá; cinco vendas ao
  exterior nunca apareceram na tela, sem erro nenhum.

E o frontend filtra **de novo** por cima, com regras vindas da tabela `configuracoes`. São
três cópias da mesma régua que ninguém sincroniza.

Aqui não há régua: o `gold` já decidiu o que é venda (`silver.vendas`, item 4.6) e o que é
serviço faturado (`gold.fato_servicos`). Este módulo só agrega e serve.

## Por que agregado, e não a lista de notas

A tela do dashboard busca o ano inteiro para mostrar doze barras: hoje isso trafega
milhares de notas com cliente, itens e marcadores dentro, e a soma acontece no navegador.
Aqui a soma acontece no banco, que é onde os dados já estão, e a resposta são **doze
linhas**. Quem precisa da lista de notas continua tendo `/notas_fiscais/`.
"""

from datetime import date
from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.filtros_comerciais import CTE_NOTAS, FiltrosComerciais
from app.core.paginacao import LIMITE_MAXIMO, LIMITE_PADRAO
from app.models.database import SessionLocal

router = APIRouter(prefix="/faturamento", tags=["Faturamento"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class FaturamentoMensal(BaseModel):
    ano: int
    mes: int
    produto: float
    servico: float
    total: float
    # Contagem de NOTAS, não de linhas do fato. `gold.fato_vendas` tem grão de item: um
    # `count(*)` ali devolveria 5.148 onde existem 4.352 notas. Já `gold.fato_servicos`
    # tem grão de nota, e aí `count(*)` é o número certo.
    quantidade_produto: int
    quantidade_servico: int


# Doze linhas por ano sempre, mesmo nos meses sem nenhuma nota: o produto cartesiano dos
# dois `generate_series` cria a grade ano × mês e o `left join` preenche com zero. Sem isso
# o gráfico teria buracos onde houve mês parado, e quem monta a tela precisaria saber disso
# para não desenhar dezembro no lugar de outubro.
SQL_MENSAL = """
WITH periodos AS (
    SELECT a.ano, m.mes
    FROM generate_series(:ano_inicio, :ano_fim) AS a(ano),
         generate_series(1, 12) AS m(mes)
),
produto AS (
    SELECT EXTRACT(YEAR FROM data_venda)::int  AS ano,
           EXTRACT(MONTH FROM data_venda)::int AS mes,
           SUM(valor_nota_rateado)             AS valor,
           COUNT(DISTINCT id_nota)             AS notas
    FROM gold.fato_vendas
    WHERE EXTRACT(YEAR FROM data_venda) BETWEEN :ano_inicio AND :ano_fim
    GROUP BY 1, 2
),
servico AS (
    SELECT EXTRACT(YEAR FROM data_servico)::int  AS ano,
           EXTRACT(MONTH FROM data_servico)::int AS mes,
           SUM(valor_servicos)                   AS valor,
           COUNT(*)                              AS notas
    FROM gold.fato_servicos
    WHERE EXTRACT(YEAR FROM data_servico) BETWEEN :ano_inicio AND :ano_fim
    GROUP BY 1, 2
)
SELECT
    p.ano,
    p.mes,
    COALESCE(pr.valor, 0)                        AS produto,
    COALESCE(sv.valor, 0)                        AS servico,
    COALESCE(pr.valor, 0) + COALESCE(sv.valor, 0) AS total,
    COALESCE(pr.notas, 0)                        AS quantidade_produto,
    COALESCE(sv.notas, 0)                        AS quantidade_servico
FROM periodos p
LEFT JOIN produto pr ON pr.ano = p.ano AND pr.mes = p.mes
LEFT JOIN servico sv ON sv.ano = p.ano AND sv.mes = p.mes
ORDER BY p.ano, p.mes
"""


@router.get("/mensal", response_model=List[FaturamentoMensal])
def faturamento_mensal(
    ano: int = Query(..., ge=2015, le=2100, description="Ano de referência (4 dígitos)"),
    ano_fim: int | None = Query(
        None,
        ge=2015,
        le=2100,
        description="Último ano da faixa. Ausente, devolve só o ano de `ano`.",
    ),
    db: Session = Depends(get_db),
):
    """Faturamento mês a mês, separado entre produto (NF-e) e serviço (NFS-e).

    Devolve sempre doze linhas por ano da faixa, com zero nos meses sem nota. `total` é a
    soma dos dois — que é o número que o dashboard mostra como faturamento da empresa.

    `ano_fim` existe porque a tela de Financeiro compara cinco anos lado a lado e calcula a
    variação de cada um contra o anterior. Sem a faixa, ela faria cinco chamadas para
    montar uma tabela só; e a variação do primeiro ano exige o ano anterior a ele, o que
    convidaria a tela a inventar a própria janela.

    ⚠️ `produto` e `servico` vêm de fatos com grãos diferentes (item da nota × nota). Somar
    os dois no mesmo total é correto porque cada um já está agregado por mês; o que não se
    pode fazer é juntar as linhas dos dois fatos numa tabela só, que dupla-contaria. Pelo
    mesmo motivo `quantidade_produto` conta notas distintas, não linhas do fato.
    """
    fim = ano if ano_fim is None else ano_fim
    if fim < ano:
        raise HTTPException(
            status_code=422,
            detail="`ano_fim` não pode ser anterior a `ano`.",
        )
    # Uma faixa aberta demais devolveria centenas de linhas e varreria o fato inteiro. O
    # limite é generoso para o uso real (a tela pede cinco anos) e fecha o caso de alguém
    # pedir 2015–2100 por engano de digitação.
    if fim - ano > 19:
        raise HTTPException(
            status_code=422,
            detail="A faixa de anos não pode passar de 20 anos.",
        )

    linhas = db.execute(
        text(SQL_MENSAL), {"ano_inicio": ano, "ano_fim": fim}
    ).mappings().all()
    return [FaturamentoMensal(**dict(linha)) for linha in linhas]


# ─────────────────────────────────────────────────────────────────────────────
# As notas que compõem o faturamento
# ─────────────────────────────────────────────────────────────────────────────
#
# Por que este endpoint existe, se `/notas_fiscais/vendas/` devolve o mesmo tipo de coisa:
#
# 1. **A régua.** Aquele reimplementa em Python o que é venda — CFOP procurado como
#    substring dentro de `natureza_operacao` (texto livre), lista fixa de sete marcadores
#    comparada sem normalizar. Aqui o conjunto de notas é decidido por `gold.fato_vendas`,
#    que é a régua única, testada a cada execução do dbt.
# 2. **O tamanho.** Aquele devolve a nota inteira com cliente, itens, marcadores, endereços
#    de entrega e formas de envio aninhados: ~9,7 MB medidos. Aqui vão só os campos que as
#    telas leem, e o texto das observações fica de fora — ~1,8 MB, 81% menos.
#
# O que este endpoint NÃO faz: trocar a identidade de cliente, produto e vendedor. Os
# campos de exibição continuam vindo da origem, e não das dimensões do `gold`. É de
# propósito — `dim_vendedor.nome` é normalizado em minúsculas para agrupar
# ("adriana oliveira"), e `dim_produto` consolida 433 descrições em 291. As duas coisas
# são melhorias, e nenhuma delas é "migrar a régua": elas mudam o que a tela ESCREVE, não
# o que ela CONTA. Entram numa fase própria, medindo o efeito em cada ranking.

# A busca da tabela, do jeito que a tela sempre fez: nome do cliente, documento com e sem
# pontuação, vendedor, descrição de item e o valor escrito. O documento entra duas vezes
# porque quem digita só números espera achar o CNPJ formatado — e quem copia o CNPJ
# formatado espera achar também.
#
# ⚠️ `CAST()`, e nunca o operador de cast com dois-pontos: em `text()` do SQLAlchemy os
# dois-pontos iniciam um bind param, então o cast vira um parâmetro fantasma obrigatório e
# a query quebra. E o parser NÃO ignora comentário — escrever o operador aqui dentro
# criaria o parâmetro do mesmo jeito. Por isso esta frase o descreve em vez de mostrá-lo.
FILTRO_BUSCA = """
  AND (CAST(:busca AS text) IS NULL OR (
        c.nome ILIKE '%' || CAST(:busca AS text) || '%'
     OR c.cpf_cnpj ILIKE '%' || CAST(:busca AS text) || '%'
     OR regexp_replace(COALESCE(c.cpf_cnpj, ''), '[^0-9]', '', 'g')
        ILIKE '%' || regexp_replace(CAST(:busca AS text), '[^0-9]', '', 'g') || '%'
        AND regexp_replace(CAST(:busca AS text), '[^0-9]', '', 'g') <> ''
     OR n.nome_vendedor ILIKE '%' || CAST(:busca AS text) || '%'
     OR CAST(n.valor_nota AS text) ILIKE '%' || CAST(:busca AS text) || '%'
     OR EXISTS (SELECT 1 FROM tiny.itens_nota i2
                WHERE i2.id_nota = n.id
                  AND i2.descricao ILIKE '%' || CAST(:busca AS text) || '%')
  ))
"""

# Ordenação por lista fechada, e não pelo texto que chega na query string: o `ORDER BY` é
# a única parte desta consulta que não pode ser bind param, então o que entra ali sai
# daqui — de um dicionário — e nunca do pedido.
ORDENACOES = {
    "data_emissao": "n.data_emissao {d}, n.id {d}",
    "cliente": "c.nome {d} NULLS LAST, n.id DESC",
    "valor": "n.valor_nota {d} NULLS LAST, n.id DESC",
    "vendedor": "n.nome_vendedor {d} NULLS LAST, n.id DESC",
    "numero": "nf.numero {d} NULLS LAST, n.id DESC",
    # A tela de Vendedores ordena por tipo (Outbound/Inbound/ReCompra), que é
    # curadoria local — a única coluna desta listagem que não veio do Tiny.
    "tipo": "nf.tipo {d} NULLS LAST, n.id DESC",
    # Vendedores mede a MERCADORIA, não o total da nota: ordenar pelos dois pela
    # mesma chave faria a tabela discordar do KPI que está logo acima dela.
    "valor_produtos": "n.valor_produtos {d} NULLS LAST, n.id DESC",
}

SQL_VENDAS = CTE_NOTAS + """
SELECT
    n.id,
    nf.numero,
    n.data_emissao,
    n.valor_nota,
    n.valor_produtos,
    n.nome_vendedor,
    nf.tipo,
    (nf.observacoes IS NOT NULL AND nf.observacoes <> '') AS tem_observacoes,
    CASE WHEN c.id IS NULL THEN NULL ELSE
        json_build_object('id', c.id, 'nome', c.nome, 'cpf_cnpj', c.cpf_cnpj)
    END AS cliente,
    COALESCE((
        SELECT json_agg(json_build_object(
                   'descricao',      i.descricao,
                   'codigo',         i.codigo,
                   'quantidade',     i.quantidade,
                   'valor_unitario', i.valor_unitario,
                   'valor_total',    i.valor_total)
               ORDER BY i.id)
        FROM tiny.itens_nota i
        WHERE i.id_nota = n.id
    ), CAST('[]' AS json)) AS itens
FROM notas n
JOIN tiny.notas_fiscais nf ON nf.id = n.id
LEFT JOIN tiny.clientes c ON c.id = n.id_cliente
WHERE true
""" + FILTRO_BUSCA + """
ORDER BY {ordem}
LIMIT :limite OFFSET :offset
"""

SQL_VENDAS_TOTAL = CTE_NOTAS + """
SELECT COUNT(*) AS total, COALESCE(SUM(n.valor_nota), 0) AS valor
FROM notas n
LEFT JOIN tiny.clientes c ON c.id = n.id_cliente
WHERE true
""" + FILTRO_BUSCA


class ItemDaVenda(BaseModel):
    descricao: str | None = None
    codigo: str | None = None
    # `Decimal`, como no schema de `/item_nota` — as três colunas são `numeric` na origem.
    # As telas envolvem cada uma em `Number(...)` antes de somar, o que funciona com o
    # número e com o texto; o contrato aqui segue o que a API já devolvia.
    quantidade: Decimal | None = None
    valor_unitario: Decimal | None = None
    valor_total: Decimal | None = None


class ClienteDaVenda(BaseModel):
    id: int
    nome: str | None = None
    cpf_cnpj: str | None = None


class NotaDeVenda(BaseModel):
    id: int
    numero: str | None = None
    data_emissao: date | None = None
    valor_nota: float | None = None
    valor_produtos: float | None = None
    nome_vendedor: str | None = None
    tipo: str | None = None
    # Só se HÁ observação, não o texto. O campo é livre e carrega número de série, chave
    # de acesso e nome de quem recebeu — mandar isso em toda listagem é gastar banda para
    # espalhar dado que quase ninguém abre. O texto vem por `/observacoes` quando o modal
    # é aberto.
    tem_observacoes: bool = False
    cliente: ClienteDaVenda | None = None
    itens: List[ItemDaVenda] = []


class PaginaDeVendas(BaseModel):
    """Uma página da tabela, com o tamanho e o valor do recorte inteiro junto.

    `total` e `valor_total` são do FILTRO, não da página — é o que impede a tela de somar
    o que recebeu e chamar aquilo de faturamento. Enquanto a resposta era a lista inteira
    isso era a mesma coisa; a partir da paginação, deixa de ser, e a diferença precisa
    estar escrita no corpo em vez de subentendida.
    """

    itens: List[NotaDeVenda]
    total: int
    valor_total: float
    limite: int
    offset: int


@router.get("/vendas", response_model=PaginaDeVendas)
def vendas(
    filtros: FiltrosComerciais = Depends(),
    busca: str | None = Query(
        None,
        max_length=120,
        description="Procura em cliente, documento, vendedor, produto e valor",
    ),
    ordenar_por: str = Query("data_emissao", description=f"Um de: {', '.join(ORDENACOES)}"),
    direcao: str = Query("desc", pattern="^(asc|desc)$"),
    limite: int = Query(LIMITE_PADRAO, ge=1, le=LIMITE_MAXIMO),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """As notas que contam como faturamento, pela régua do `gold` — uma página por vez.

    Filtra, busca, ordena e pagina no banco. Os gráficos que antes eram desenhados a partir
    desta lista saíram para `/faturamento/resumo` (item 9.4), e é isso que torna a
    paginação segura: enquanto a tela somava o que recebia, uma primeira página teria sido
    lida como o total — sem erro nenhum, que é o pior jeito de errar.

    O recorte é o mesmo de `/faturamento/resumo` para os mesmos parâmetros — a cláusula é
    literalmente a mesma, importada de um módulo só.
    """
    if ordenar_por not in ORDENACOES:
        raise HTTPException(
            status_code=422,
            detail=f"`ordenar_por` deve ser um de: {', '.join(ORDENACOES)}.",
        )

    termo = (busca or "").strip() or None
    params = {**filtros.params, "busca": termo}

    contagem = db.execute(text(SQL_VENDAS_TOTAL), params).mappings().first()

    ordem = ORDENACOES[ordenar_por].format(d=direcao.upper())
    linhas = db.execute(
        text(SQL_VENDAS.replace("{ordem}", ordem)),
        {**params, "limite": limite, "offset": offset},
    ).mappings().all()

    return PaginaDeVendas(
        itens=[NotaDeVenda(**dict(linha)) for linha in linhas],
        total=int(contagem["total"] or 0),
        valor_total=float(contagem["valor"] or 0),
        limite=limite,
        offset=offset,
    )


@router.get("/vendas/{id_nota}/observacoes")
def observacoes_da_venda(id_nota: int, db: Session = Depends(get_db)):
    """O texto das observações de uma nota, sob demanda.

    Fica fora da listagem de propósito: são ~1,7 MB de campo livre que só é lido quando
    alguém clica para abrir o modal, e o conteúdo é o mais sensível da nota — número de
    série, chave de acesso, nome de quem recebeu.

    Responde 404 para nota que não é venda pela régua do `gold`, e não o texto: quem não
    pode listar a nota também não pode ler a observação dela por id direto.
    """
    linha = db.execute(
        text(
            """
            SELECT n.observacoes
            FROM tiny.notas_fiscais n
            WHERE n.id = :id_nota
              AND n.id IN (SELECT DISTINCT id_nota FROM gold.fato_vendas)
            """
        ),
        {"id_nota": id_nota},
    ).mappings().first()

    if linha is None:
        raise HTTPException(status_code=404, detail="Nota de venda não encontrada.")
    return {"id": id_nota, "observacoes": linha["observacoes"]}


# ─────────────────────────────────────────────────────────────────────────────
# Serviços: o que a tela desenha, somado no banco (item 9.4)
# ─────────────────────────────────────────────────────────────────────────────
#
# A tela de Serviços baixava as 5.004 notas para calcular KPI, evolução mensal,
# ranking de cliente e distribuição por cidade no navegador. Mesmo desenho das
# telas do Comercial e de Contas: aqui se filtra e se soma; o corte do top dez e
# a escolha entre a série anual e a mensal continuam sendo da tela.
#
# O "tipo de serviço" são os primeiros 50 caracteres da discriminação. Não é
# regra de negócio nem classificação: é um agrupamento aproximado que a tela
# inventou para ter um terceiro filtro, e está reproduzido como está — mudá-lo
# mudaria as opções do multiselect sem que ninguém tivesse pedido.
TIPO_DO_SERVICO = "COALESCE(NULLIF(LEFT(s.\"discriminação_dos_serviços\", 50), ''), 'Não especificado')"

CLIENTE_DO_SERVICO = (
    "COALESCE(s.\"razão_social_do_tomador\", '') || ' (' "
    "|| COALESCE(s.\"cpf_cnpj_do_tomador\", '') || ')'"
)

CIDADE_DO_SERVICO = (
    "COALESCE(s.\"cidade_do_tomador\", '') || '/' || COALESCE(s.\"uf_do_tomador\", '')"
)

CTE_SERVICOS = f"""
WITH servicos AS (
    SELECT s.id,
           s."data_da_emissão_nfs_e_dsr_e"   AS data_emissao,
           s."razão_social_do_tomador"       AS cliente,
           {CIDADE_DO_SERVICO}               AS cidade,
           {TIPO_DO_SERVICO}                 AS tipo,
           f.valor_servicos                  AS valor
    FROM tiny.servicos s
    -- O `gold` é quem decide o que é serviço faturado. Este join é a régua.
    JOIN gold.fato_servicos f ON f.sk_servico = s.id
    WHERE (CAST(:data_inicio AS date) IS NULL
           OR s."data_da_emissão_nfs_e_dsr_e" >= CAST(:data_inicio AS date))
      AND (CAST(:data_fim AS date) IS NULL
           OR s."data_da_emissão_nfs_e_dsr_e" <= CAST(:data_fim AS date))
      AND (CAST(:clientes AS text[]) IS NULL
           OR {CLIENTE_DO_SERVICO} = ANY(CAST(:clientes AS text[])))
      AND (CAST(:cidades AS text[]) IS NULL
           OR {CIDADE_DO_SERVICO} = ANY(CAST(:cidades AS text[])))
      AND (CAST(:tipos AS text[]) IS NULL
           OR {TIPO_DO_SERVICO} = ANY(CAST(:tipos AS text[])))
)
"""

SQL_SERVICOS_KPIS = CTE_SERVICOS + """
SELECT COALESCE(SUM(valor), 0) AS faturamento,
       COUNT(*)                AS notas
FROM servicos
"""

SQL_SERVICOS_EVOLUCAO = CTE_SERVICOS + """
SELECT EXTRACT(YEAR  FROM data_emissao)::int AS ano,
       EXTRACT(MONTH FROM data_emissao)::int AS mes,
       COALESCE(SUM(valor), 0)               AS total,
       COUNT(*)                              AS notas
FROM servicos
GROUP BY 1, 2
ORDER BY 1, 2
"""

SQL_SERVICOS_POR_CLIENTE = CTE_SERVICOS + """
SELECT COALESCE(cliente, '')  AS nome,
       COALESCE(SUM(valor), 0) AS valor,
       COUNT(*)                AS notas
FROM servicos
GROUP BY 1
ORDER BY valor DESC, nome
"""

SQL_SERVICOS_POR_CIDADE = CTE_SERVICOS + """
SELECT cidade                  AS nome,
       COALESCE(SUM(valor), 0) AS valor,
       COUNT(*)                AS notas
FROM servicos
GROUP BY 1
ORDER BY valor DESC, nome
"""

# As opções saem do universo inteiro, sem recorte: uma lista que encolhe com o
# filtro esconde a opção que a pessoa ia marcar em seguida.
SQL_SERVICOS_OPCOES = f"""
SELECT DISTINCT
       {CLIENTE_DO_SERVICO} AS cliente,
       {CIDADE_DO_SERVICO}  AS cidade,
       {TIPO_DO_SERVICO}    AS tipo
FROM tiny.servicos s
JOIN gold.fato_servicos f ON f.sk_servico = s.id
"""


class FiltrosDeServicos:
    """Os quatro filtros da tela de Serviços, lidos da query string."""

    def __init__(
        self,
        data_inicio: date | None = Query(None, description="Emissão a partir de (inclusive)"),
        data_fim: date | None = Query(None, description="Emissão até (inclusive)"),
        cliente: List[str] | None = Query(None, description="'Razão social (documento)' (repetível)"),
        cidade: List[str] | None = Query(None, description="'Cidade/UF' (repetível)"),
        tipo: List[str] | None = Query(None, description="Tipo de serviço (repetível)"),
    ):
        if data_inicio and data_fim and data_fim < data_inicio:
            raise HTTPException(
                status_code=422,
                detail="`data_fim` não pode ser anterior a `data_inicio`.",
            )
        self.params = {
            "data_inicio": data_inicio,
            "data_fim": data_fim,
            "clientes": cliente or None,
            "cidades": cidade or None,
            "tipos": tipo or None,
        }


class KpisDeServicos(BaseModel):
    faturamento: float
    notas: int
    ticket_medio: float


class MesDeServicos(BaseModel):
    ano: int
    mes: int
    total: float
    notas: int


class LinhaDeServicos(BaseModel):
    nome: str
    valor: float
    notas: int


class OpcoesDeServicos(BaseModel):
    clientes: List[str]
    cidades: List[str]
    tipos: List[str]


class ResumoDeServicos(BaseModel):
    kpis: KpisDeServicos
    evolucao_mensal: List[MesDeServicos]
    por_cliente: List[LinhaDeServicos]
    por_cidade: List[LinhaDeServicos]
    opcoes: OpcoesDeServicos


# ─────────────────────────────────────────────────────────────────────────────
# As notas de serviço que compõem o faturamento
# ─────────────────────────────────────────────────────────────────────────────
#
# Mesmo desenho de `/faturamento/vendas`: `gold.fato_servicos` decide QUAIS notas contam,
# e os campos de exibição vêm da origem. `sk_servico` é o próprio `id` de `tiny.servicos`,
# então a ligação é direta.
#
# A diferença em relação a `/notas_servico/` não é o conjunto — os dois devolvem as mesmas
# 5.004 notas, conferido. É de onde vem o VALOR:
#
# Na origem, `valor_dos_serviços` é TEXTO, e em duas convenções (brasileira e americana).
# Quem consome converte, e o `ServicosContext` do DataCoreHS carrega uma cópia antiga
# dessa conversão, sem o teste de ponto-de-milhar — nela `"1.234"` vira R$ 1,23. Hoje
# nenhuma nota cai nesse caso (medido: zero), mas é bomba armada esperando um cadastro
# escrito de outro jeito. Aqui o valor sai de `gold.fato_servicos`, onde já é `numeric`
# convertido por macro testada, e a tela não precisa converter nada.

SQL_SERVICOS = """
SELECT
    s.id,
    s."nº_da_nota_fiscal_eletrônica"  AS numero_nfse,
    s."data_da_emissão_nfs_e_dsr_e"   AS data_emissao,
    s."razão_social_do_tomador"       AS razao_social_tomador,
    s."cpf_cnpj_do_tomador"           AS cpf_cnpj_tomador,
    s."cidade_do_tomador"             AS cidade_tomador,
    s."uf_do_tomador"                 AS uf_tomador,
    s."discriminação_dos_serviços"    AS discriminacao_servico,
    -- Numéricos, vindos do gold: a origem grava os três como texto em duas convenções.
    f.valor_servicos                  AS valor_servico,
    f.valor_iss,
    f.valor_total_recebido
FROM tiny.servicos s
-- O `gold` é quem decide o que é serviço faturado. Este join é a régua deste endpoint.
JOIN gold.fato_servicos f ON f.sk_servico = s.id
WHERE (CAST(:data_inicio AS date) IS NULL
       OR s."data_da_emissão_nfs_e_dsr_e" >= CAST(:data_inicio AS date))
  AND (CAST(:data_fim AS date) IS NULL
       OR s."data_da_emissão_nfs_e_dsr_e" <= CAST(:data_fim AS date))
ORDER BY s."data_da_emissão_nfs_e_dsr_e" DESC, s.id DESC
"""


class NotaDeServico(BaseModel):
    id: int
    numero_nfse: int | None = None
    data_emissao: date | None = None
    razao_social_tomador: str | None = None
    cpf_cnpj_tomador: str | None = None
    cidade_tomador: str | None = None
    uf_tomador: str | None = None
    discriminacao_servico: str | None = None
    valor_servico: Decimal | None = None
    valor_iss: Decimal | None = None
    valor_total_recebido: Decimal | None = None


# A busca da tabela de Serviços: número da NFS-e, razão social, documento (com e
# sem máscara), cidade e a discriminação. Os mesmos seis campos que o navegador
# procurava.
FILTRO_BUSCA_SERVICOS = """
  AND (CAST(:busca AS text) IS NULL OR (
        CAST(s."nº_da_nota_fiscal_eletrônica" AS text) ILIKE '%' || CAST(:busca AS text) || '%'
     OR s."razão_social_do_tomador" ILIKE '%' || CAST(:busca AS text) || '%'
     OR s."cpf_cnpj_do_tomador" ILIKE '%' || CAST(:busca AS text) || '%'
     OR (regexp_replace(CAST(:busca AS text), '[^0-9]', '', 'g') <> ''
         AND regexp_replace(COALESCE(s."cpf_cnpj_do_tomador", ''), '[^0-9]', '', 'g')
             ILIKE '%' || regexp_replace(CAST(:busca AS text), '[^0-9]', '', 'g') || '%')
     OR s."cidade_do_tomador" ILIKE '%' || CAST(:busca AS text) || '%'
     OR s."discriminação_dos_serviços" ILIKE '%' || CAST(:busca AS text) || '%'
  ))
"""

ORDENACOES_DE_SERVICOS = {
    "numero": 's."nº_da_nota_fiscal_eletrônica" {d} NULLS LAST, s.id DESC',
    "data_emissao": 's."data_da_emissão_nfs_e_dsr_e" {d}, s.id {d}',
    "cliente": 'lower(s."razão_social_do_tomador") {d} NULLS LAST, s.id DESC',
    "cidade": 'lower(s."cidade_do_tomador") {d} NULLS LAST, s.id DESC',
    "valor": "f.valor_servicos {d} NULLS LAST, s.id DESC",
}


class PaginaDeServicos(BaseModel):
    """Uma página da tabela, com o tamanho e o valor do recorte inteiro junto."""

    itens: List[NotaDeServico]
    total: int
    valor_total: float
    limite: int
    offset: int


@router.get("/servicos", response_model=PaginaDeServicos)
def servicos(
    filtros: FiltrosDeServicos = Depends(),
    busca: str | None = Query(
        None, max_length=120, description="Procura em número, tomador, documento, cidade e discriminação"
    ),
    ordenar_por: str = Query("data_emissao"),
    direcao: str = Query("desc", pattern="^(asc|desc)$"),
    limite: int = Query(LIMITE_PADRAO, ge=1, le=LIMITE_MAXIMO),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """As notas de serviço que contam como faturamento — uma página por vez.

    Os valores chegam como número, e não como o texto que a origem grava: é a
    diferença que importa aqui, porque a conversão desse texto tem duas
    convenções e já morou duplicada no navegador.

    Paginada desde 2026-09-09. Só pôde ser agora: enquanto os KPIs, a evolução e
    os dois rankings saíam desta lista, uma primeira página teria sido lida como
    o total. Eles saíram para `/faturamento/servicos/resumo` (item 9.4).
    """
    if ordenar_por not in ORDENACOES_DE_SERVICOS:
        raise HTTPException(
            status_code=422,
            detail=f"`ordenar_por` deve ser um de: {', '.join(ORDENACOES_DE_SERVICOS)}.",
        )

    params = {**filtros.params, "busca": (busca or "").strip() or None}

    contagem = db.execute(
        text(
            CTE_SERVICOS.replace("f.valor_servicos                  AS valor",
                                 "f.valor_servicos                  AS valor")
            + "SELECT COUNT(*) AS total, COALESCE(SUM(valor), 0) AS valor FROM servicos"
        ),
        params,
    ).mappings().first()

    # A contagem acima já respeita os filtros; a busca entra na consulta das
    # linhas, que é onde as colunas de texto estão disponíveis.
    total_com_busca = db.execute(
        text(
            """
            SELECT COUNT(*) AS total, COALESCE(SUM(f.valor_servicos), 0) AS valor
            FROM tiny.servicos s
            JOIN gold.fato_servicos f ON f.sk_servico = s.id
            WHERE (CAST(:data_inicio AS date) IS NULL
                   OR s."data_da_emissão_nfs_e_dsr_e" >= CAST(:data_inicio AS date))
              AND (CAST(:data_fim AS date) IS NULL
                   OR s."data_da_emissão_nfs_e_dsr_e" <= CAST(:data_fim AS date))
              AND (CAST(:clientes AS text[]) IS NULL
                   OR """ + CLIENTE_DO_SERVICO + """ = ANY(CAST(:clientes AS text[])))
              AND (CAST(:cidades AS text[]) IS NULL
                   OR """ + CIDADE_DO_SERVICO + """ = ANY(CAST(:cidades AS text[])))
              AND (CAST(:tipos AS text[]) IS NULL
                   OR """ + TIPO_DO_SERVICO + """ = ANY(CAST(:tipos AS text[])))
            """
            + FILTRO_BUSCA_SERVICOS
        ),
        params,
    ).mappings().first()

    ordem = ORDENACOES_DE_SERVICOS[ordenar_por].format(d=direcao.upper())
    linhas = db.execute(
        text(
            SQL_SERVICOS.replace(
                'ORDER BY s."data_da_emissão_nfs_e_dsr_e" DESC, s.id DESC',
                FILTRO_BUSCA_SERVICOS + f"ORDER BY {ordem}\nLIMIT :limite OFFSET :offset",
            )
        ),
        {**params, "limite": limite, "offset": offset},
    ).mappings().all()

    return PaginaDeServicos(
        itens=[NotaDeServico(**dict(linha)) for linha in linhas],
        total=int(total_com_busca["total"] or 0),
        valor_total=float(total_com_busca["valor"] or 0),
        limite=limite,
        offset=offset,
    )



@router.get("/servicos/resumo", response_model=ResumoDeServicos)
def resumo_de_servicos(
    filtros: FiltrosDeServicos = Depends(), db: Session = Depends(get_db)
):
    """Tudo que a tela de Serviços desenha, para um mesmo recorte.

    Os valores vêm de `gold.fato_servicos`, já como número. Na origem os três
    são TEXTO, em duas convenções — e o navegador carregava a conversão, que é
    exatamente o tipo de cópia que diverge da outra sem ninguém notar.
    """
    p = filtros.params

    linha = db.execute(text(SQL_SERVICOS_KPIS), p).mappings().first()
    notas = int(linha["notas"] or 0)
    faturamento = float(linha["faturamento"] or 0)

    opcoes = list(db.execute(text(SQL_SERVICOS_OPCOES)).mappings())

    def distintos(campo: str) -> List[str]:
        return sorted({l[campo] for l in opcoes if (l[campo] or "").strip()})

    return ResumoDeServicos(
        kpis=KpisDeServicos(
            faturamento=faturamento,
            notas=notas,
            ticket_medio=(faturamento / notas) if notas else 0.0,
        ),
        evolucao_mensal=[
            MesDeServicos(**dict(l))
            for l in db.execute(text(SQL_SERVICOS_EVOLUCAO), p).mappings()
        ],
        por_cliente=[
            LinhaDeServicos(**dict(l))
            for l in db.execute(text(SQL_SERVICOS_POR_CLIENTE), p).mappings()
        ],
        por_cidade=[
            LinhaDeServicos(**dict(l))
            for l in db.execute(text(SQL_SERVICOS_POR_CIDADE), p).mappings()
        ],
        opcoes=OpcoesDeServicos(
            clientes=distintos("cliente"),
            cidades=distintos("cidade"),
            tipos=distintos("tipo"),
        ),
    )
