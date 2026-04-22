from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, not_
from typing import List, Optional

from app.models.database import SessionLocal
from app.models.centro_custo_config import CentroCustoConfig as CentroCustoConfigModel
from app.models.item_nota import ItemNota as ItemNotaModel
from app.models.nota_fiscal import NotaFiscal
from app.models.marcador import Marcador
from app.schemas.centro_custo_config import CentroCustoConfig, CentroCustoConfigCreate

router = APIRouter(prefix="/centro_custo", tags=["Centro de Custo"])

MARCADORES_RUINS = [
    "cancelar", "cliente não quis o produto", "nf devolvida",
    "nf cancelada", "nf recusada",
    "nf recusada. cliente solicitou frete", "inutilizada",
]

CFOPS = ["%5102%", "%6102%", "%5108%", "%6108%"]


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/resumo_produto/")
def resumo_produto(
    ano: int = Query(...),
    produto: str = Query(...),
    exato: bool = Query(False),
    db: Session = Depends(get_db),
):
    bad_markers = (
        db.query(Marcador.id_nota)
        .filter(func.lower(Marcador.descricao).in_(MARCADORES_RUINS))
        .subquery()
    )

    cfop_filter = or_(*[NotaFiscal.natureza_operacao.ilike(c) for c in CFOPS])

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
            NotaFiscal.descricao_situacao == "Emitida DANFE",
            cfop_filter,
            desc_filter,
            not_(NotaFiscal.id.in_(bad_markers)),
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
    else:
        cfg = CentroCustoConfigModel(**payload.model_dump())
        db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return cfg
