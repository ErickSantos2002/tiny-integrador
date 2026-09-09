"""Régua de o que conta como venda no faturamento. ⚠️ DEPRECADA.

**Não use este módulo em código novo.** A régua de verdade vive em `gold.fato_vendas`,
construída e testada pelo dbt, e chega pronta por `GET /faturamento/vendas`. O que está
aqui é a versão que se procura CFOP dentro de texto livre e compara marcador contra uma
lista fixa — os dois defeitos medidos no item 9.1.

Sobrou um consumidor: `/notas_fiscais/vendas/`, também deprecado. Quando aquele endpoint
sair, este arquivo sai junto. O critério para decidir isso está escrito em
`endpoints/nota_fiscal.py`, acima da rota.

## Como este arquivo chegou aqui

A régua ficava duplicada entre `endpoints/nota_fiscal.py` e `endpoints/centro_custo.py`,
e as duas cópias divergiram: a de nota_fiscal comparava o marcador sem normalizar o
caixa, então "NF cancelada" (que é como o Tiny grava) não casava com "nf cancelada" da
lista e a nota entrava no faturamento. Este módulo nasceu para ser a fonte única.

Foi o passo certo, e durou pouco: unificar as cópias mostrou que o lugar de uma
definição de negócio não é o código que serve a requisição. O `centro_custo` migrou para
o `gold` em 2026-09-08 e parou de importar daqui.
"""

from sqlalchemy import func, or_

from app.models.marcador import Marcador
from app.models.nota_fiscal import NotaFiscal

# Comparar sempre em minúsculo: no banco convivem "NF cancelada", "CANCELAR",
# "NF DEVOLVIDA" e "inutilizada". Manter esta lista toda em minúsculo.
MARCADORES_RUINS = [
    "cancelar",
    "cliente não quis o produto",
    "nf devolvida",
    "nf cancelada",
    "nf recusada",
    "nf recusada. cliente solicitou frete",
    "inutilizada",
]

CFOPS_VENDA = ["%5102%", "%6102%", "%5108%", "%6108%"]

SITUACAO_EMITIDA = "Emitida DANFE"


def filtro_cfop_venda():
    """CFOP de venda, procurado dentro da natureza de operação da nota."""
    return or_(*[NotaFiscal.natureza_operacao.ilike(c) for c in CFOPS_VENDA])


def sem_marcador_ruim():
    """Exclui nota marcada como cancelada, devolvida, recusada ou inutilizada."""
    return ~NotaFiscal.marcadores.any(
        func.lower(Marcador.descricao).in_(MARCADORES_RUINS)
    )
