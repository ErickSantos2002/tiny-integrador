from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from typing import List, Optional

from app.models.database import SessionLocal
from app.models.centro_custo_config import CentroCustoConfig as CentroCustoConfigModel
from app.models.item_nota import ItemNota as ItemNotaModel
from app.models.nota_fiscal import NotaFiscal
from app.schemas.centro_custo_config import CentroCustoConfig, CentroCustoConfigCreate

router = APIRouter(prefix="/centro_custo", tags=["Centro de Custo"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# As notas que contam são as que `gold.fato_vendas` aprova. Antes esta linha era três
# filtros escritos aqui — situação por texto, CFOP procurado como substring dentro de
# `natureza_operacao` (campo livre) e uma subquery de marcadores comparados contra uma
# lista fixa de sete descrições. Eram uma terceira cópia da régua, e divergiam das outras
# duas sem que nada acusasse.
NOTAS_DE_VENDA = "SELECT DISTINCT id_nota FROM gold.fato_vendas"


@router.get("/resumo_produto/")
def resumo_produto(
    ano: int = Query(...),
    produto: str = Query(...),
    exato: bool = Query(False),
    db: Session = Depends(get_db),
):
    """Quantidade e receita de um produto, mês a mês, dentro de um ano.

    O produto é procurado pela DESCRIÇÃO do item na origem, e não pelo nome canônico de
    `gold.dim_produto`, de propósito: é o texto que a tela oferece na busca, e o
    dicionário do gold consolida 433 descrições em 291. Trocar isso mudaria o que a busca
    encontra — é melhoria, e merece ser feita medindo, não de carona nesta migração.
    """
    if exato:
        desc_filter = func.upper(ItemNotaModel.descricao) == produto.upper()
    else:
        desc_filter = ItemNotaModel.descricao.ilike(f"%{produto}%")

    rows = (
        db.query(
            func.extract("month", NotaFiscal.data_emissao).label("mes"),
            func.sum(ItemNotaModel.quantidade).label("quantidade"),
            func.sum(ItemNotaModel.quantidade * ItemNotaModel.valor_unitario).label("receita"),
        )
        .join(NotaFiscal, ItemNotaModel.id_nota == NotaFiscal.id)
        .filter(
            func.extract("year", NotaFiscal.data_emissao) == ano,
            NotaFiscal.id.in_(text(NOTAS_DE_VENDA)),
            desc_filter,
        )
        .group_by(func.extract("month", NotaFiscal.data_emissao))
        .order_by("mes")
        .all()
    )

    return [
        {
            "mes": int(r.mes),
            "quantidade": float(r.quantidade or 0),
            "receita": float(r.receita or 0),
        }
        for r in rows
    ]


@router.get("/config/")
def get_config(
    produto: str = Query(...),
    ano: int = Query(...),
    db: Session = Depends(get_db),
):
    cfg = (
        db.query(CentroCustoConfigModel)
        .filter(
            CentroCustoConfigModel.produto == produto,
            CentroCustoConfigModel.ano == ano,
        )
        .first()
    )
    if not cfg:
        return {"produto": produto, "ano": ano, "cmv_unitario": None, "frete_unitario": None, "outros_custos_unitario": None}
    return cfg


@router.post("/config/", response_model=CentroCustoConfig)
def salvar_config(
    payload: CentroCustoConfigCreate,
    db: Session = Depends(get_db),
):
    cfg = (
        db.query(CentroCustoConfigModel)
        .filter(
            CentroCustoConfigModel.produto == payload.produto,
            CentroCustoConfigModel.ano == payload.ano,
        )
        .first()
    )
    if cfg:
        cfg.cmv_unitario = payload.cmv_unitario
        cfg.frete_unitario = payload.frete_unitario
        cfg.outros_custos_unitario = payload.outros_custos_unitario
        cfg.config_json = payload.config_json
    else:
        cfg = CentroCustoConfigModel(**payload.model_dump())
        db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return cfg
