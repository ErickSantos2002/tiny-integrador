"""Faz o dado da origem caber nas colunas do banco, sem perder a linha inteira.

O Tiny não conhece o tamanho das nossas colunas. Em 2026-09-04 uma conta a receber de
R$ 23.520 foi perdida porque o número do endereço do cliente vinha como `NAO INFORMADO`
— 13 caracteres numa coluna `varchar(10)`. O `IntegrityError` derruba a conta toda por
causa de um campo de endereço que ninguém usa para nada.

Truncar não é a solução bonita: a bonita é a coluna caber. Mas entre perder dois
caracteres de um campo secundário e perder a conta, o certo é guardar a conta e avisar
alto no log, para a coluna ser ampliada depois com calma.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import String

logger = logging.getLogger(__name__)


def caber_no_schema(modelo, dados: dict[str, Any]) -> dict[str, Any]:
    """Corta os textos que não cabem na coluna, avisando quais foram."""
    colunas = modelo.__table__.columns
    ajustados = {}
    for campo, valor in dados.items():
        coluna = colunas.get(campo)
        limite = getattr(coluna.type, "length", None) if coluna is not None else None
        if isinstance(valor, str) and isinstance(getattr(coluna, "type", None), String) \
                and limite and len(valor) > limite:
            logger.warning(
                "%s.%s: %d caracteres não cabem em varchar(%d), truncado — valor era %r",
                modelo.__tablename__, campo, len(valor), limite, valor)
            valor = valor[:limite]
        ajustados[campo] = valor
    return ajustados
