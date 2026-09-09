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

SQL_VENDAS = """
SELECT
    n.id,
    n.numero,
    n.data_emissao,
    n.valor_nota,
    n.valor_produtos,
    n.nome_vendedor,
    n.tipo,
    (n.observacoes IS NOT NULL AND n.observacoes <> '') AS tem_observacoes,
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
FROM tiny.notas_fiscais n
LEFT JOIN tiny.clientes c ON c.id = n.id_cliente
-- O `gold` é quem decide o que é venda. Este IN é a régua inteira deste endpoint.
WHERE n.id IN (SELECT DISTINCT id_nota FROM gold.fato_vendas)
  -- CAST(), e nao o operador de cast com dois-pontos: em `text()` do SQLAlchemy os
  -- dois-pontos iniciam um bind param, entao o cast vira um parametro fantasma e a query
  -- quebra. E o parser NAO ignora comentario: escrever o operador aqui dentro tambem
  -- criaria o parametro. Por isso esta frase o descreve em vez de mostra-lo.
  AND (CAST(:data_inicio AS date) IS NULL OR n.data_emissao >= CAST(:data_inicio AS date))
  AND (CAST(:data_fim    AS date) IS NULL OR n.data_emissao <= CAST(:data_fim    AS date))
ORDER BY n.data_emissao DESC, n.id DESC
"""


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


@router.get("/vendas", response_model=List[NotaDeVenda])
def vendas(
    data_inicio: date | None = Query(None, description="Emissão a partir de (inclusive)"),
    data_fim: date | None = Query(None, description="Emissão até (inclusive)"),
    db: Session = Depends(get_db),
):
    """As notas que contam como faturamento, pela régua do `gold`.

    Sem filtro de data devolve o histórico inteiro — hoje 4.330 notas, ~1,8 MB. É o que as
    telas de Clientes, Vendas, Produtos e Vendedores precisam, porque cada uma desenha
    gráfico sobre o conjunto todo e filtra no navegador.

    ⚠️ **Não paginar antes de migrar essas agregações** (item 9.4): enquanto o gráfico for
    desenhado a partir desta resposta, uma primeira página seria lida como se fosse o
    total — e sem erro nenhum, que é o pior jeito de errar.
    """
    if data_inicio and data_fim and data_fim < data_inicio:
        raise HTTPException(
            status_code=422,
            detail="`data_fim` não pode ser anterior a `data_inicio`.",
        )

    linhas = db.execute(
        text(SQL_VENDAS), {"data_inicio": data_inicio, "data_fim": data_fim}
    ).mappings().all()
    return [NotaDeVenda(**dict(linha)) for linha in linhas]


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
