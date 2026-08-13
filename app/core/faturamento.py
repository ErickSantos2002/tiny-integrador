"""Régua de o que conta como venda no faturamento.

Ficava duplicada entre `endpoints/nota_fiscal.py` e `endpoints/centro_custo.py`, e as
duas cópias divergiram: a de nota_fiscal comparava o marcador sem normalizar o caixa,
então "NF cancelada" (que é como o Tiny grava) não casava com "nf cancelada" da lista e
a nota entrava no faturamento. Aqui é a fonte única — quem for filtrar venda importa
daqui e usa `sem_marcador_ruim()`.
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
