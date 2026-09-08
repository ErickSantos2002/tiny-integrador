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

from fastapi import APIRouter, Depends, Query
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


# Doze linhas sempre, mesmo nos meses sem nenhuma nota: `generate_series` cria os meses e o
# `left join` preenche com zero. Sem isso o gráfico teria buracos onde houve mês parado, e
# quem monta a tela precisaria saber disso para não desenhar dezembro no lugar de outubro.
SQL_MENSAL = """
WITH meses AS (
    SELECT generate_series(1, 12) AS mes
),
produto AS (
    SELECT EXTRACT(MONTH FROM data_venda)::int AS mes,
           SUM(valor_nota_rateado) AS valor
    FROM gold.fato_vendas
    WHERE EXTRACT(YEAR FROM data_venda) = :ano
    GROUP BY 1
),
servico AS (
    SELECT EXTRACT(MONTH FROM data_servico)::int AS mes,
           SUM(valor_servicos) AS valor
    FROM gold.fato_servicos
    WHERE EXTRACT(YEAR FROM data_servico) = :ano
    GROUP BY 1
)
SELECT
    :ano                                                    AS ano,
    m.mes,
    COALESCE(p.valor, 0)                                    AS produto,
    COALESCE(s.valor, 0)                                    AS servico,
    COALESCE(p.valor, 0) + COALESCE(s.valor, 0)             AS total
FROM meses m
LEFT JOIN produto p ON p.mes = m.mes
LEFT JOIN servico s ON s.mes = m.mes
ORDER BY m.mes
"""


@router.get("/mensal", response_model=List[FaturamentoMensal])
def faturamento_mensal(
    ano: int = Query(..., ge=2015, le=2100, description="Ano de referência (4 dígitos)"),
    db: Session = Depends(get_db),
):
    """Faturamento mês a mês de um ano, separado entre produto (NF-e) e serviço (NFS-e).

    Devolve sempre doze linhas. `total` é a soma dos dois — que é o número que o dashboard
    mostra como faturamento da empresa.

    ⚠️ `produto` e `servico` vêm de fatos com grãos diferentes (item da nota × nota). Somar
    os dois no mesmo total é correto porque cada um já está agregado por mês; o que não se
    pode fazer é juntar as linhas dos dois fatos numa tabela só, que dupla-contaria.
    """
    linhas = db.execute(text(SQL_MENSAL), {"ano": ano}).mappings().all()
    return [FaturamentoMensal(**dict(linha)) for linha in linhas]
