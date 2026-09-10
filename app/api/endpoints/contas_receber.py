from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.core.contas_agregado import (
    ORDENACOES_DE_CONTAS,
    PaginaDeContas,
    QUITADAS_A_RECEBER,
    ResumoDeContas,
    pagina_de_contas,
    resumo_de_contas,
)
from app.core.paginacao import Pagina, limite_query, offset_query, paginar

from app.models.contas_receber import ContasReceber as ContasReceberModel
from app.schemas.contas_receber import ContasReceber
from app.models.database import SessionLocal

router = APIRouter(prefix="/contas_receber", tags=["Contas a Receber"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/", response_model=List[ContasReceber])
def listar_contas_receber(
    situacao: Optional[str] = Query(None),
    data_inicio: Optional[str] = Query(None),
    data_fim: Optional[str] = Query(None),
    vencimento_inicio: Optional[str] = Query(None),
    vencimento_fim: Optional[str] = Query(None),
    incluir_excluidas: bool = Query(
        False,
        description=(
            "Incluir contas que o Tiny não reconhece mais. Fora por padrão: quando uma "
            "conta atrasa, o financeiro exclui a antiga e emite outra com id novo — a "
            "antiga fica no banco em aberto e é dívida que já foi substituída."
        ),
    ),
    db: Session = Depends(get_db),
):
    query = db.query(ContasReceberModel)

    # Conta que sumiu da origem sai por padrão. Não é limpeza de dado: a linha fica no
    # banco porque o compromisso existiu, e o job a marca em `excluida_na_origem_em` ao
    # reconferir. O que estava errado era contá-la como se ainda estivesse aberta.
    if not incluir_excluidas:
        query = query.filter(ContasReceberModel.excluida_na_origem_em.is_(None))

    if situacao:
        query = query.filter(ContasReceberModel.situacao == situacao)

    if data_inicio and data_fim:
        query = query.filter(ContasReceberModel.data.between(data_inicio, data_fim))
    elif data_inicio:
        query = query.filter(ContasReceberModel.data >= data_inicio)
    elif data_fim:
        query = query.filter(ContasReceberModel.data <= data_fim)

    if vencimento_inicio and vencimento_fim:
        query = query.filter(ContasReceberModel.vencimento.between(vencimento_inicio, vencimento_fim))
    elif vencimento_inicio:
        query = query.filter(ContasReceberModel.vencimento >= vencimento_inicio)
    elif vencimento_fim:
        query = query.filter(ContasReceberModel.vencimento <= vencimento_fim)

    return query.order_by(ContasReceberModel.vencimento).all()


# ─────────────────────────────────────────────────────────────────────────────
# O que a tela desenha, somado no banco (item 9.4)
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/resumo", response_model=ResumoDeContas)
def resumo_contas_receber(
    situacao: Optional[List[str]] = Query(None, description="Situações (repetível)"),
    categoria: Optional[List[str]] = Query(None, description="Categorias (repetível)"),
    contraparte: Optional[List[str]] = Query(None, description="Clientes (repetível)"),
    data_inicio: Optional[date] = Query(None, description="Emissão a partir de (inclusive)"),
    data_fim: Optional[date] = Query(None, description="Emissão até (inclusive)"),
    db: Session = Depends(get_db),
):
    """KPIs, evolução, categorias e ranking de cliente — do recorte inteiro.

    A tela baixava a tabela toda para calcular isto no navegador: 11,2 MB por
    abertura, medido em 2026-09-09. As regras que decidem o que é *quitado*, o que
    é *aberto* e o que é *faturado* estão em `core/contas_agregado.py`, escritas
    uma vez para as duas telas.
    """
    if data_inicio and data_fim and data_fim < data_inicio:
        raise HTTPException(
            status_code=422,
            detail="`data_fim` não pode ser anterior a `data_inicio`.",
        )

    return resumo_de_contas(
        db,
        tabela="contas_receber",
        campo_emissao="data",
        quitadas=QUITADAS_A_RECEBER,
        situacoes=situacao,
        categorias=categoria,
        contrapartes=contraparte,
        data_inicio=data_inicio,
        data_fim=data_fim,
        hoje=date.today(),
    )


@router.get("/pagina", response_model=PaginaDeContas)
def pagina_contas_receber(
    situacao: Optional[List[str]] = Query(None),
    categoria: Optional[List[str]] = Query(None),
    contraparte: Optional[List[str]] = Query(None),
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
    busca: Optional[str] = Query(
        None, max_length=120, description="Procura em cliente, categoria, documento e histórico"
    ),
    ordenar_por: str = Query("vencimento"),
    direcao: str = Query("asc", pattern="^(asc|desc)$"),
    limite: int = limite_query(),
    offset: int = offset_query(),
    db: Session = Depends(get_db),
):
    """A tabela da tela, uma página por vez.

    Só pôde ser paginada agora: enquanto os KPIs e os três gráficos eram
    desenhados a partir desta lista, uma primeira página teria sido lida como o
    total — sem erro nenhum. Os agregados saíram para `/resumo` (item 9.4).

    Devolve treze colunas, e não as trinta e poucas da linha de conta: endereço,
    CEP, e-mail e telefone da contraparte não aparecem na tela e não têm por que
    trafegar.
    """
    if ordenar_por not in ORDENACOES_DE_CONTAS:
        raise HTTPException(
            status_code=422,
            detail=f"`ordenar_por` deve ser um de: {', '.join(ORDENACOES_DE_CONTAS)}.",
        )
    if data_inicio and data_fim and data_fim < data_inicio:
        raise HTTPException(
            status_code=422,
            detail="`data_fim` não pode ser anterior a `data_inicio`.",
        )

    return pagina_de_contas(
        db,
        tabela="contas_receber",
        campo_emissao="data",
        quitadas=QUITADAS_A_RECEBER,
        situacoes=situacao,
        categorias=categoria,
        contrapartes=contraparte,
        data_inicio=data_inicio,
        data_fim=data_fim,
        busca=busca,
        ordenar_por=ordenar_por,
        direcao=direcao,
        limite=limite,
        offset=offset,
        hoje=date.today(),
        colunas_extras=["forma_pagamento", "portador", "ocorrencia"],
    )
