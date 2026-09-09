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
    query = db.query(ContasPagarModel)

    # Conta que sumiu da origem sai por padrão. Não é limpeza de dado: a linha fica no
    # banco porque o compromisso existiu, e o job a marca em `excluida_na_origem_em` ao
    # reconferir. O que estava errado era contá-la como se ainda estivesse aberta.
    if not incluir_excluidas:
        query = query.filter(ContasPagarModel.excluida_na_origem_em.is_(None))

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
