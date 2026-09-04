"""Extrator de produtos e saldo de estoque do Tiny para o schema `tiny` (bronze).

Substitui o fluxo `[DATACORE] Atualizar estoque` do n8n, que tinha dois defeitos de
construção — os dois por paginação escrita à mão:

* **três blocos copiados**, um para a página 1, outro para a 2 e outro para a 3. Hoje a
  origem tem exatamente 3 páginas de produto; a quarta não seria lida, e sem erro nenhum
  para avisar. Aqui a paginação segue o `numero_paginas` que a própria API devolve.
* **só a página 1 inseria produto novo** — as outras duas só atualizavam saldo. Produto
  das páginas 2 e 3 que ainda não estivesse no banco nunca entrava: 270 produtos no
  banco contra 300 na origem, medido em 2026-09-03.

O saldo não vem na pesquisa: é uma chamada por produto (`produto.obter.estoque.php`).
São 300 chamadas a 3s — cerca de 15 minutos, uma vez por dia, como já era.
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.services.tiny_schema import caber_no_schema

from app.models.estoque import Estoque

logger = logging.getLogger(__name__)

CAMPOS_TEXTO = ["nome", "unidade", "gtin", "localizacao", "situacao"]
CAMPOS_VALOR = ["preco", "preco_promocional", "preco_custo", "preco_custo_medio"]


def _txt(valor: Any) -> Optional[str]:
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto or None


def _num(valor: Any) -> Optional[Decimal]:
    texto = _txt(valor)
    if texto is None:
        return None
    try:
        return Decimal(texto.replace(",", "."))
    except InvalidOperation:
        logger.warning("valor numérico não reconhecido: %r", valor)
        return None


def _codigo(valor: Any) -> Optional[int]:
    """A coluna `codigo` é inteira, mas a origem manda texto — e nem todo código é número.

    Código como `001` vira 1, o que já é o que estava gravado. Código alfanumérico (que
    hoje não existe: os 270 do banco vão de 1 a 373) vira NULL com aviso, em vez de
    derrubar a carga inteira do produto por causa de um campo.
    """
    texto = _txt(valor)
    if texto is None:
        return None
    try:
        return int(texto)
    except ValueError:
        logger.warning("código de produto não numérico, gravado como nulo: %r", valor)
        return None


def _data_criacao(valor: Any) -> Optional[datetime]:
    texto = _txt(valor)
    if texto is None:
        return None
    for formato in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y"):
        try:
            return datetime.strptime(texto, formato)
        except ValueError:
            continue
    logger.warning("data de criação não reconhecida: %r", valor)
    return None


def normalizar_produto(produto: dict, saldo: Any = None) -> dict:
    dados: dict[str, Any] = {"id": int(produto["id"])}  # a PK é o próprio id do Tiny
    for campo in CAMPOS_TEXTO:
        dados[campo] = _txt(produto.get(campo))
    for campo in CAMPOS_VALOR:
        dados[campo] = _num(produto.get(campo))
    dados["codigo"] = _codigo(produto.get("codigo"))
    dados["tipovariacao"] = _txt(produto.get("tipoVariacao"))  # a origem usa camelCase
    dados["data_criacao"] = _data_criacao(produto.get("data_criacao"))
    if saldo is not None:
        dados["saldo"] = _num(saldo) or Decimal(0)
    return dados


def _equivalente(atual: Any, novo: Any) -> bool:
    if isinstance(atual, str) or isinstance(novo, str):
        a = (atual or "").strip() if isinstance(atual, str) else ("" if atual is None else atual)
        b = (novo or "").strip() if isinstance(novo, str) else ("" if novo is None else novo)
        return a == b
    if isinstance(atual, Decimal) and isinstance(novo, Decimal):
        return atual == novo
    if atual is None or novo is None:
        return atual is None and novo is None
    return atual == novo


def salvar_produto(db: Session, produto: dict, saldo: Any = None, *,
                   dry_run: bool = False) -> dict:
    """Grava produto e saldo. Produto que ainda não existe é criado — inclusive o das
    páginas que o n8n nunca inseria."""
    dados = normalizar_produto(produto, saldo)
    relato = {"id": dados["id"], "codigo": dados.get("codigo"), "nome": dados.get("nome"),
              "saldo": dados.get("saldo"), "mudancas": {}}

    dados = caber_no_schema(Estoque, dados)
    registro = db.query(Estoque).filter(Estoque.id == dados["id"]).one_or_none()

    if registro is None:
        relato["acao"] = "criaria" if dry_run else "criado"
        if dry_run:
            return relato
        dados.setdefault("saldo", Decimal(0))  # a coluna é NOT NULL
        db.add(Estoque(**dados))
        db.commit()
        return relato

    mudancas = {c: (getattr(registro, c), v) for c, v in dados.items()
                if not _equivalente(getattr(registro, c, None), v)}
    relato["mudancas"] = mudancas
    relato["acao"] = ("atualizaria" if dry_run else "atualizado") if mudancas else "inalterado"

    if mudancas and not dry_run:
        for campo, (_, novo) in mudancas.items():
            setattr(registro, campo, novo)
        db.commit()
    return relato
