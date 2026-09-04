"""Extrator de contas a pagar e a receber do Tiny para o schema `tiny` (bronze).

Substitui os fluxos `[DATACORE] Puxar_Contas_Pagar` e `Puxar_Contas_Receber` do n8n.
As duas contas têm a mesma forma na origem e quase a mesma tabela aqui, então o código é
um só, parametrizado por `tipo` ("pagar" ou "receber").

O defeito que motivou a troca, medido em 2026-09-03: o n8n pesquisava a partir de uma
**data escrita à mão dentro do nó** (30/06/2026 nas contas a pagar). Conta emitida antes
disso nunca mais era reconferida — então conta antiga que fosse paga continuava `aberto`
no banco para sempre. O banco dizia **226 contas a pagar em aberto, R$ 962.071,57**, a
mais antiga de 2021; o Tiny dizia **3**.

A correção não é só trocar a data por uma janela móvel: janela nenhuma resolve isso,
porque a conta muda de situação muito depois de emitida. Por isso a carga tem duas
partes — a janela por emissão, que traz conta nova, e a **reconferência de tudo que
ainda está em aberto**, sem limite de data, que é o que percebe pagamento.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.contas_pagar import ContasPagar
from app.models.contas_receber import ContasReceber

logger = logging.getLogger(__name__)

# Campos que as duas tabelas têm com o mesmo nome e o mesmo significado.
CAMPOS_TEXTO_COMUNS = [
    "nro_documento", "historico", "categoria", "situacao", "ocorrencia",
]
CAMPOS_CLIENTE = [
    "codigo", "nome", "tipo_pessoa", "cpf_cnpj", "ie", "rg", "endereco", "numero",
    "complemento", "bairro", "cep", "cidade", "uf", "pais", "fone", "email",
]
CAMPOS_INTEIROS = ["dia_vencimento", "numero_parcelas"]

# O que só existe em contas a receber.
CAMPOS_TEXTO_RECEBER = [
    "link_boleto", "serie_documento", "nro_banco", "forma_pagamento", "portador",
]

CONFIG = {
    "pagar": {
        "modelo": ContasPagar,
        "coluna_data_emissao": "data_emissao",   # a tabela de pagar chama de data_emissao
        "coluna_dia_semana": "dia_semana_vencimento",
        "campos_texto": CAMPOS_TEXTO_COMUNS,
    },
    "receber": {
        "modelo": ContasReceber,
        "coluna_data_emissao": "data",           # a de receber chama de data
        "coluna_dia_semana": "dia_vencimento_semanal",
        "campos_texto": CAMPOS_TEXTO_COMUNS + CAMPOS_TEXTO_RECEBER,
    },
}


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


def _inteiro(valor: Any) -> Optional[int]:
    texto = _txt(valor)
    if texto is None:
        return None
    try:
        return int(Decimal(texto))
    except (InvalidOperation, ValueError):
        return None


def _data(valor: Any) -> Optional[date]:
    texto = _txt(valor)
    if texto is None:
        return None
    try:
        return datetime.strptime(texto, "%d/%m/%Y").date()
    except ValueError:
        logger.warning("data não reconhecida: %r", valor)
        return None


def _competencia(valor: Any) -> Optional[date]:
    """A origem manda competência como `MM/yyyy`; a coluna é `date`.

    Vira o primeiro dia do mês — mesma conversão que o n8n fazia. Guardar como data (e
    não como texto) é o que deixa agrupar por mês sem gambiarra.
    """
    texto = _txt(valor)
    if texto is None:
        return None
    try:
        return datetime.strptime(texto, "%m/%Y").date()
    except ValueError:
        return _data(valor)  # algumas contas mandam a data cheia


def normalizar_conta(tipo: str, conta: dict) -> dict:
    config = CONFIG[tipo]
    cliente = conta.get("cliente") or {}

    dados: dict[str, Any] = {"id_tiny": _inteiro(conta.get("id"))}
    for campo in config["campos_texto"]:
        dados[campo] = _txt(conta.get(campo))
    for campo in CAMPOS_INTEIROS:
        dados[campo] = _inteiro(conta.get(campo))
    dados[config["coluna_dia_semana"]] = _inteiro(conta.get("dia_semana_vencimento"))

    dados[config["coluna_data_emissao"]] = _data(conta.get("data"))
    dados["vencimento"] = _data(conta.get("vencimento"))
    dados["liquidacao"] = _data(conta.get("liquidacao"))
    dados["competencia"] = _competencia(conta.get("competencia"))
    dados["valor"] = _num(conta.get("valor"))
    dados["saldo"] = _num(conta.get("saldo"))

    for campo in CAMPOS_CLIENTE:
        dados[f"cliente_{campo}"] = _txt(cliente.get(campo))
    return dados


# Colunas `NOT NULL` na tabela: sem elas o INSERT quebra. Conferir antes deixa o erro
# legível ("faltou vencimento") em vez de um IntegrityError cru no meio do lote.
OBRIGATORIOS = {
    "pagar": ["id_tiny", "data_emissao", "vencimento", "valor", "saldo", "ocorrencia", "cliente_nome"],
    "receber": ["id_tiny", "data", "vencimento", "valor", "saldo", "ocorrencia", "cliente_nome"],
}


def _equivalente(atual: Any, novo: Any) -> bool:
    """Mesma tolerância do extrator de notas: `''` e NULL são a mesma ausência."""
    if isinstance(atual, str) or isinstance(novo, str):
        a = (atual or "").strip() if isinstance(atual, str) else ("" if atual is None else atual)
        b = (novo or "").strip() if isinstance(novo, str) else ("" if novo is None else novo)
        return a == b
    if isinstance(atual, Decimal) and isinstance(novo, Decimal):
        return atual == novo
    if atual is None or novo is None:
        return atual is None and novo is None
    return atual == novo


def salvar_conta(db: Session, tipo: str, conta: dict, *, dry_run: bool = False) -> dict:
    """Grava uma conta. Uma transação por conta."""
    modelo = CONFIG[tipo]["modelo"]
    dados = normalizar_conta(tipo, conta)

    relato = {
        "id_tiny": dados["id_tiny"],
        "documento": dados.get("nro_documento"),
        "situacao": dados.get("situacao"),
        "valor": dados.get("valor"),
        "mudancas": {},
    }

    faltando = [c for c in OBRIGATORIOS[tipo] if dados.get(c) is None]
    if faltando:
        raise ValueError(f"conta {dados['id_tiny']}: campo obrigatório vazio: {', '.join(faltando)}")

    registro = db.query(modelo).filter(modelo.id_tiny == dados["id_tiny"]).one_or_none()

    if registro is None:
        relato["acao"] = "criaria" if dry_run else "criada"
        if dry_run:
            return relato
        db.add(modelo(**dados))
        db.commit()
        return relato

    mudancas = {c: (getattr(registro, c), v) for c, v in dados.items()
                if not _equivalente(getattr(registro, c, None), v)}
    relato["mudancas"] = mudancas
    relato["acao"] = ("atualizaria" if dry_run else "atualizada") if mudancas else "inalterada"

    if mudancas and not dry_run:
        for campo, (_, novo) in mudancas.items():
            setattr(registro, campo, novo)
        registro.updated_at = datetime.now()  # a coluna existe e o n8n nunca a tocava
        db.commit()
    return relato
