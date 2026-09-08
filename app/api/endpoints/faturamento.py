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
