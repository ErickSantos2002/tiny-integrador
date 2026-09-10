"""Os recortes agregados que as quatro telas do Comercial desenham.

## Por que existe

Clientes, Vendas, Produtos e Vendedores baixavam as 4.330 notas com os itens dentro e
calculavam tudo no navegador: KPI, evolução mensal, ranking de produto, de vendedor, de
cliente. As quatro fazem a mesma coisa sobre o mesmo conjunto, cruzando os mesmos quatro
filtros — cliente × vendedor × produto × período.

Aqui esses cruzamentos acontecem onde os dados estão. A resposta deixa de crescer com o
número de notas e passa a ter o tamanho do que a tela desenha: alguns milhares de linhas
de ranking em vez do histórico inteiro. É o que destrava paginar a listagem (item 9.4) —
enquanto o gráfico era desenhado a partir da lista, paginar teria feito a primeira página
ser lida como o total, sem erro nenhum.

## Onde está a régua

Em lugar nenhum daqui. `gold.fato_vendas` decide o que é venda; este módulo só filtra e
soma. Os campos de exibição continuam vindo da origem (`tiny.notas_fiscais`,
`tiny.itens_nota`, `tiny.clientes`), e não das dimensões do `gold` — a mesma decisão de
`/faturamento/vendas`: trocar a identidade de cliente, produto e vendedor muda o que a
tela ESCREVE, e merece fase própria com medição por ranking.

## Os dois valores, e por que são dois

`valor_nota` é o total da nota; `valor_produtos` é só a mercadoria. As telas usam os dois:
Vendas e Clientes somam `valor_nota`, Vendedores soma `valor_produtos`. Os dois vêm juntos
em `kpis` para que nenhuma tela precise escolher — e para que a diferença entre elas
continue sendo a que sempre foi, e não uma que esta migração inventou.

## O filtro de produto é por CÓDIGO, e isso conserta um defeito medido

A tela montava a lista do multiselect com um `Map` chaveado pelo código — só a última
descrição de cada código sobrevivia — mas filtrava comparando `descrição (código)`. Quem
selecionasse um produto recebia apenas a fatia daquela grafia exata.

Medido em 2026-09-09: existem 184 grafias para 127 produtos, e o multiselect oferecia 97
opções. Somando o que essas 97 opções alcançavam, **35,5% do valor dos itens estava fora
do alcance de quem filtrava por produto** — sem erro, sem aviso, e com o gráfico desenhado
como se fosse o total. Filtrando por código o problema não existe, e o rótulo mostrado
passa a ser a descrição de maior faturamento dentro do código.

Item sem código (36 itens, 0,12% do valor) entra pela descrição, em vez de ser descartado
como a tela de Produtos fazia.
"""

from datetime import date
from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.filtros_comerciais import CHAVE_PRODUTO, CTE_NOTAS, FiltrosComerciais
from app.models.database import SessionLocal

router = APIRouter(prefix="/faturamento", tags=["Faturamento"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Maior, menor e desvio padrão entram aqui porque a tela os mostra — e porque são
# exatamente o tipo de número que não sobrevive à paginação: `Math.max` sobre a página é o
# máximo dos cem primeiros, e continua parecendo o máximo.
#
# `STDDEV_POP`, e não `STDDEV`: a tela divide a soma dos quadrados por N, que é o desvio
# POPULACIONAL. O `STDDEV` do Postgres é o amostral, que divide por N-1 — daria um número
# diferente, pouco, o bastante para ninguém notar e o suficiente para estar errado.
SQL_KPIS = CTE_NOTAS + """
, itens_das_notas AS (
    SELECT COUNT(*) AS total_itens
    FROM notas n
    JOIN tiny.itens_nota i ON i.id_nota = n.id
)
SELECT COALESCE(SUM(valor_nota), 0)     AS faturamento,
       COALESCE(SUM(valor_produtos), 0) AS faturamento_produtos,
       COUNT(*)                         AS notas,
       COALESCE(MAX(valor_nota), 0)     AS maior_venda,
       COALESCE(MIN(valor_nota), 0)     AS menor_venda,
       COALESCE(STDDEV_POP(valor_nota), 0) AS desvio_padrao_venda,
       (SELECT total_itens FROM itens_das_notas) AS itens
FROM notas
"""

# Só os meses que tiveram venda, como a tela sempre desenhou — quem monta a grade de doze
# meses é `/faturamento/mensal`, que serve o Dashboard. Aqui o eixo acompanha o filtro:
# com período de dois meses o gráfico tem dois pontos, não vinte e quatro.
SQL_EVOLUCAO = CTE_NOTAS + f"""
, mensal_nota AS (
    SELECT EXTRACT(YEAR  FROM data_emissao)::int AS ano,
           EXTRACT(MONTH FROM data_emissao)::int AS mes,
           COALESCE(SUM(valor_nota), 0)          AS total,
           -- A tela de Vendedores desenha a evolução sobre a MERCADORIA, não
           -- sobre o total da nota. Os dois vêm juntos para que a escolha
           -- continue sendo de cada tela, como sempre foi, e não uma que a
           -- migração arbitrou.
           COALESCE(SUM(valor_produtos), 0)      AS total_produtos,
           COUNT(*)                              AS notas
    FROM notas
    GROUP BY 1, 2
),
-- A quantidade de itens é do grão de ITEM, então sai de uma agregação própria e
-- entra por join. Juntar itens na consulta acima multiplicaria as linhas e faria
-- `SUM(valor_nota)` contar a mesma nota uma vez por item — o erro de rateio que
-- o `tests/rateio_reconcilia_com_a_nota.sql` do dbt existe para travar.
mensal_item AS (
    SELECT EXTRACT(YEAR  FROM n.data_emissao)::int AS ano,
           EXTRACT(MONTH FROM n.data_emissao)::int AS mes,
           COALESCE(SUM(i.quantidade), 0)          AS quantidade
    FROM notas n
    JOIN tiny.itens_nota i ON i.id_nota = n.id
    WHERE CAST(:produtos AS text[]) IS NULL
       OR {CHAVE_PRODUTO} = ANY(CAST(:produtos AS text[]))
    GROUP BY 1, 2
)
SELECT mn.ano,
       mn.mes,
       mn.total,
       mn.total_produtos,
       mn.notas,
       COALESCE(mi.quantidade, 0) AS quantidade
FROM mensal_nota mn
LEFT JOIN mensal_item mi ON mi.ano = mn.ano AND mi.mes = mn.mes
ORDER BY 1, 2
"""

# Dois agrupamentos porque `COUNT(DISTINCT nota)` só é verdade no nível do código: somar a
# contagem das descrições contaria duas vezes a nota que tem o mesmo código escrito de
# dois jeitos. O rótulo sai por `DISTINCT ON`, a descrição que mais fatura dentro do
# código.
SQL_POR_PRODUTO = CTE_NOTAS + f"""
, itens AS (
    SELECT {CHAVE_PRODUTO}          AS chave,
           NULLIF(i.codigo, '')     AS codigo,
           i.descricao,
           i.quantidade,
           i.valor_total,
           i.id_nota
    FROM notas n
    JOIN tiny.itens_nota i ON i.id_nota = n.id
    WHERE CAST(:produtos AS text[]) IS NULL
       OR {CHAVE_PRODUTO} = ANY(CAST(:produtos AS text[]))
),
por_chave AS (
    SELECT chave,
           MAX(codigo)                          AS codigo,
           COALESCE(SUM(quantidade), 0)         AS quantidade,
           COALESCE(SUM(valor_total), 0)        AS valor,
           COUNT(DISTINCT id_nota)              AS notas
    FROM itens
    GROUP BY chave
),
rotulo AS (
    SELECT DISTINCT ON (chave) chave, descricao
    FROM (
        SELECT chave, descricao, COALESCE(SUM(valor_total), 0) AS valor
        FROM itens
        GROUP BY 1, 2
    ) t
    ORDER BY chave, valor DESC, descricao
)
SELECT p.chave, p.codigo, r.descricao, p.quantidade, p.valor, p.notas
FROM por_chave p
JOIN rotulo r ON r.chave = p.chave
ORDER BY p.valor DESC, p.chave
"""

SQL_POR_VENDEDOR = CTE_NOTAS + """
SELECT COALESCE(NULLIF(nome_vendedor, ''), 'Não informado') AS nome,
       COALESCE(SUM(valor_nota), 0)                         AS valor,
       COALESCE(SUM(valor_produtos), 0)                     AS valor_produtos,
       COUNT(*)                                             AS notas
FROM notas
GROUP BY 1
ORDER BY valor DESC, nome
"""

# Agrupado pelo documento em dígitos, e não pelo id: é o que a tela de Clientes já fazia,
# e é o que faz os 18 cadastros duplicados aparecerem como um cliente só. O filtro, esse
# sim, continua por id — trocá-lo mudaria em silêncio o que o multiselect seleciona.
SQL_POR_CLIENTE = CTE_NOTAS + """
SELECT regexp_replace(COALESCE(c.cpf_cnpj, ''), '[^0-9]', '', 'g') AS documento,
       (array_agg(c.nome ORDER BY c.id DESC))[1]                   AS nome,
       -- Documento, e-mail e telefone do cadastro MAIS RECENTE do documento: é
       -- a mesma regra do canônico construído da `dim_cliente` (item 4.4), e é
       -- o que a tela de Clientes mostra na linha da tabela.
       (array_agg(c.cpf_cnpj ORDER BY c.id DESC))[1]               AS cpf_cnpj,
       (array_agg(c.email ORDER BY c.id DESC))[1]                  AS email,
       (array_agg(c.fone ORDER BY c.id DESC))[1]                   AS fone,
       COALESCE(SUM(n.valor_nota), 0)                              AS valor,
       COALESCE(SUM(n.valor_produtos), 0)                          AS valor_produtos,
       COUNT(*)                                                    AS notas,
       MAX(n.data_emissao)                                         AS ultima_compra
FROM notas n
LEFT JOIN tiny.clientes c ON c.id = n.id_cliente
GROUP BY 1
-- Pelo NOME da coluna, e nunca pela posição: acrescentar um campo no SELECT
-- muda o que "3" significa, e a lista passa a sair ordenada por outra coisa sem
-- erro nenhum. Aconteceu aqui em 2026-09-09, ao incluir o contato do cliente —
-- o ranking passou a vir por CNPJ e só o teste de soma acusou.
ORDER BY valor DESC, nome
"""


# A evolução mensal dos CINCO maiores clientes do recorte, uma série por cliente.
#
# Não sai de `por_cliente` nem de `evolucao_mensal`: aquele soma o período todo e
# este soma todos os clientes. O gráfico da tela de Clientes precisa do cruzamento
# dos dois, e cruzamento de dois agregados não se remonta a partir das margens.
#
# Cinco é o que a tela desenha. Fica fixo aqui de propósito: um parâmetro `top`
# convidaria alguém a pedir mil séries e chamar isso de gráfico.
SQL_EVOLUCAO_POR_CLIENTE = CTE_NOTAS + """
, notas_com_documento AS (
    SELECT n.data_emissao,
           n.valor_nota,
           regexp_replace(COALESCE(c.cpf_cnpj, ''), '[^0-9]', '', 'g') AS documento
    FROM notas n
    LEFT JOIN tiny.clientes c ON c.id = n.id_cliente
),
maiores AS (
    SELECT documento
    FROM notas_com_documento
    GROUP BY documento
    ORDER BY COALESCE(SUM(valor_nota), 0) DESC, documento
    LIMIT 5
)
SELECT d.documento,
       EXTRACT(YEAR  FROM d.data_emissao)::int AS ano,
       EXTRACT(MONTH FROM d.data_emissao)::int AS mes,
       COALESCE(SUM(d.valor_nota), 0)          AS total
FROM notas_com_documento d
JOIN maiores m ON m.documento = d.documento
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3
"""


class Kpis(BaseModel):
    faturamento: float
    faturamento_produtos: float
    notas: int
    ticket_medio: float
    maior_venda: float
    menor_venda: float
    desvio_padrao_venda: float
    #: Quantas linhas de item as notas do recorte têm somadas — a tela divide pelo número
    #: de notas para mostrar "itens por nota".
    itens: int


class MesDaEvolucao(BaseModel):
    ano: int
    mes: int
    #: Soma de `valor_nota` — o que Vendas e Clientes desenham.
    total: float
    #: Soma de `valor_produtos` — o que Vendedores desenha.
    total_produtos: float
    notas: int
    #: Itens vendidos no mês — o que a tela de Produtos desenha. Respeita o
    #: filtro de produto no nível do ITEM, e não da nota.
    quantidade: float


class LinhaDeProduto(BaseModel):
    #: A chave de agrupamento — o código, ou '#' + descrição quando o item não tem código.
    chave: str
    codigo: str | None = None
    descricao: str | None = None
    quantidade: float
    valor: float
    notas: int


class LinhaDeVendedor(BaseModel):
    nome: str
    valor: float
    valor_produtos: float
    notas: int


class LinhaDeCliente(BaseModel):
    documento: str
    nome: str | None = None
    #: Como está no cadastro, com máscara — o documento em dígitos é a `documento`.
    cpf_cnpj: str | None = None
    email: str | None = None
    fone: str | None = None
    valor: float
    valor_produtos: float
    notas: int
    ultima_compra: date | None = None


class MesDeUmCliente(BaseModel):
    documento: str
    ano: int
    mes: int
    total: float


class ResumoComercial(BaseModel):
    kpis: Kpis
    evolucao_mensal: List[MesDaEvolucao]
    #: Uma série por cliente, só para os cinco maiores do recorte.
    evolucao_por_cliente: List[MesDeUmCliente]
    por_produto: List[LinhaDeProduto]
    por_vendedor: List[LinhaDeVendedor]
    por_cliente: List[LinhaDeCliente]


@router.get("/resumo", response_model=ResumoComercial)
def resumo(filtros: FiltrosComerciais = Depends(), db: Session = Depends(get_db)):
    """Tudo que as quatro telas do Comercial desenham, para um mesmo recorte.

    Um payload só, e não cinco endpoints, porque as telas mostram os cinco recortes ao
    mesmo tempo: cinco chamadas por mudança de filtro seriam cinco vezes a latência e
    cinco chances de a tela desenhar KPI de um filtro com ranking de outro.

    Os rankings vêm inteiros e ordenados por valor. Quem mostra "top 10" corta os dez
    primeiros; quem mostra "outros" soma o resto — nenhuma das duas coisas é decisão da
    API, e o total continua batendo com `kpis.faturamento` linha a linha.
    """
    p = filtros.params

    linha_kpis = db.execute(text(SQL_KPIS), p).mappings().first()
    notas = int(linha_kpis["notas"] or 0)
    faturamento = float(linha_kpis["faturamento"] or 0)

    return ResumoComercial(
        kpis=Kpis(
            faturamento=faturamento,
            faturamento_produtos=float(linha_kpis["faturamento_produtos"] or 0),
            notas=notas,
            ticket_medio=(faturamento / notas) if notas else 0.0,
            maior_venda=float(linha_kpis["maior_venda"] or 0),
            menor_venda=float(linha_kpis["menor_venda"] or 0),
            desvio_padrao_venda=float(linha_kpis["desvio_padrao_venda"] or 0),
            itens=int(linha_kpis["itens"] or 0),
        ),
        evolucao_mensal=[
            MesDaEvolucao(**dict(l)) for l in db.execute(text(SQL_EVOLUCAO), p).mappings()
        ],
        por_produto=[
            LinhaDeProduto(**dict(l)) for l in db.execute(text(SQL_POR_PRODUTO), p).mappings()
        ],
        por_vendedor=[
            LinhaDeVendedor(**dict(l)) for l in db.execute(text(SQL_POR_VENDEDOR), p).mappings()
        ],
        por_cliente=[
            LinhaDeCliente(**dict(l)) for l in db.execute(text(SQL_POR_CLIENTE), p).mappings()
        ],
        evolucao_por_cliente=[
            MesDeUmCliente(**dict(l))
            for l in db.execute(text(SQL_EVOLUCAO_POR_CLIENTE), p).mappings()
        ],
    )


# ─────────────────────────────────────────────────────────────────────────────
# As listas dos multiselects
# ─────────────────────────────────────────────────────────────────────────────
#
# Vinham de percorrer as 4.330 notas no navegador, que é metade do motivo de a lista
# inteira ser baixada. São três listas curtas — 1.831 clientes, 6 vendedores e ~130
# produtos — e nenhuma delas depende dos filtros escolhidos: o multiselect de vendedor
# não pode encolher porque alguém escolheu um cliente, senão desmarcar o filtro vira uma
# opção que sumiu da lista.

SQL_FILTROS_CLIENTES = """
SELECT DISTINCT c.id, c.nome, c.cpf_cnpj
FROM tiny.notas_fiscais n
JOIN tiny.clientes c ON c.id = n.id_cliente
WHERE n.id IN (SELECT DISTINCT id_nota FROM gold.fato_vendas)
ORDER BY c.nome, c.id
"""

SQL_FILTROS_VENDEDORES = """
SELECT DISTINCT COALESCE(NULLIF(n.nome_vendedor, ''), 'Não informado') AS nome
FROM tiny.notas_fiscais n
WHERE n.id IN (SELECT DISTINCT id_nota FROM gold.fato_vendas)
ORDER BY 1
"""

SQL_FILTROS_PRODUTOS = f"""
WITH itens AS (
    SELECT {CHAVE_PRODUTO}      AS chave,
           NULLIF(i.codigo, '') AS codigo,
           i.descricao,
           i.valor_total
    FROM tiny.itens_nota i
    WHERE i.id_nota IN (SELECT DISTINCT id_nota FROM gold.fato_vendas)
)
SELECT DISTINCT ON (chave)
       chave,
       codigo,
       descricao,
       SUM(COALESCE(valor_total, 0)) OVER (PARTITION BY chave) AS valor
FROM (
    SELECT chave, codigo, descricao, COALESCE(SUM(valor_total), 0) AS valor_total
    FROM itens
    GROUP BY 1, 2, 3
) t
ORDER BY chave, valor_total DESC, descricao
"""


class ClienteDoFiltro(BaseModel):
    id: int
    nome: str | None = None
    cpf_cnpj: str | None = None


class ProdutoDoFiltro(BaseModel):
    chave: str
    codigo: str | None = None
    descricao: str | None = None
    valor: float


class Filtros(BaseModel):
    clientes: List[ClienteDoFiltro]
    vendedores: List[str]
    produtos: List[ProdutoDoFiltro]


@router.get("/filtros", response_model=Filtros)
def filtros(db: Session = Depends(get_db)):
    """As opções dos multiselects, montadas pelo banco.

    Sempre o universo inteiro das vendas, sem recorte de período: a lista existe para
    escolher o filtro, então encolher com o filtro escolhido esconderia justamente a opção
    que a pessoa quer marcar em seguida.

    A lista de produtos tem uma linha por código — não uma por grafia. É a correção do
    defeito descrito no topo deste módulo: eram 184 grafias para 97 códigos, e a tela
    mostrava uma grafia por código enquanto filtrava pela grafia.
    """
    return Filtros(
        clientes=[
            ClienteDoFiltro(**dict(l))
            for l in db.execute(text(SQL_FILTROS_CLIENTES)).mappings()
        ],
        vendedores=[l["nome"] for l in db.execute(text(SQL_FILTROS_VENDEDORES)).mappings()],
        produtos=[
            ProdutoDoFiltro(**dict(l))
            for l in db.execute(text(SQL_FILTROS_PRODUTOS)).mappings()
        ],
    )
