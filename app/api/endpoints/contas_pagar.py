from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.models.contas_pagar import ContasPagar as ContasPagarModel
from app.schemas.contas_pagar import ContasPagar
from app.models.database import SessionLocal

router = APIRouter(prefix="/contas_pagar", tags=["Contas a Pagar"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/", response_model=List[ContasPagar])
def listar_contas_pagar(
    situacao: Optional[str] = Query(None),
    data_inicio: Optional[str] = Query(None),
    data_fim: Optional[str] = Query(None),
    vencimento_inicio: Optional[str] = Query(None),
    vencimento_fim: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(ContasPagarModel)

    if situacao:
        query = query.filter(ContasPagarModel.situacao == situacao)

    if data_inicio and data_fim:
        query = query.filter(ContasPagarModel.data_emissao.between(data_inicio, data_fim))
    elif data_inicio:
        query = query.filter(ContasPagarModel.data_emissao >= data_inicio)
    elif data_fim:
        query = query.filter(ContasPagarModel.data_emissao <= data_fim)

    if vencimento_inicio and vencimento_fim:
        query = query.filter(ContasPagarModel.vencimento.between(vencimento_inicio, vencimento_fim))
    elif vencimento_inicio:
        query = query.filter(ContasPagarModel.vencimento >= vencimento_inicio)
    elif vencimento_fim:
        query = query.filter(ContasPagarModel.vencimento <= vencimento_fim)

    return query.order_by(ContasPagarModel.vencimento).all()
