from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional

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
    db: Session = Depends(get_db),
):
    query = db.query(ContasReceberModel)

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
