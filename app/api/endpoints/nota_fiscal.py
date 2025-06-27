from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from app.models.database import SessionLocal
from app.models.nota_fiscal import NotaFiscal as NotaFiscalModel
from app.schemas.nota_fiscal import NotaFiscal

router = APIRouter(prefix="/notas_fiscais", tags=["Notas Fiscais"])

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# GET /notas_fiscais - listar todas com filtros opcionais
@router.get("/", response_model=List[NotaFiscal])
def listar_notas_fiscais(
    id_cliente: Optional[int] = Query(None),
    data_emissao: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    query = db.query(NotaFiscalModel).options(
        joinedload(NotaFiscalModel.cliente),
        joinedload(NotaFiscalModel.enderecos_entrega),
        joinedload(NotaFiscalModel.formas_envio),
        joinedload(NotaFiscalModel.marcadores),
        joinedload(NotaFiscalModel.itens)
    )

    if id_cliente:
        query = query.filter(NotaFiscalModel.id_cliente == id_cliente)

    if data_emissao:
        query = query.filter(NotaFiscalModel.data_emissao == data_emissao)

    return query.all()

# GET /notas_fiscais/{id} - buscar uma nota específica
@router.get("/{id}", response_model=NotaFiscal)
def obter_nota_fiscal(id: int, db: Session = Depends(get_db)):
    nota = db.query(NotaFiscalModel).options(
        joinedload(NotaFiscalModel.cliente),
        joinedload(NotaFiscalModel.enderecos_entrega),
        joinedload(NotaFiscalModel.formas_envio),
        joinedload(NotaFiscalModel.marcadores),
        joinedload(NotaFiscalModel.itens)
    ).filter(NotaFiscalModel.id == id).first()

    if not nota:
        raise HTTPException(status_code=404, detail="Nota fiscal não encontrada")
    
    return nota
