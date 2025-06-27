from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.models.database import SessionLocal
from app.models.cliente import Cliente as ClienteModel
from app.schemas.cliente import Cliente

router = APIRouter(prefix="/clientes", tags=["Clientes"])

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# GET /clientes - listar com filtros opcionais
@router.get("/", response_model=List[Cliente])
def listar_clientes(
    cpf_cnpj: Optional[str] = Query(None),
    nome: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    query = db.query(ClienteModel)

    if cpf_cnpj:
        query = query.filter(ClienteModel.cpf_cnpj == cpf_cnpj)
    
    if nome:
        query = query.filter(ClienteModel.nome.ilike(f"%{nome}%"))

    return query.all()

# GET /clientes/{id} - buscar por ID
@router.get("/{id}", response_model=Cliente)
def obter_cliente(id: int, db: Session = Depends(get_db)):
    cliente = db.query(ClienteModel).filter(ClienteModel.id == id).first()

    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    return cliente
