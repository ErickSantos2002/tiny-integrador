from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.models.database import SessionLocal
from app.models.endereco_entrega import EnderecoEntrega as EnderecoEntregaModel
from app.schemas.endereco_entrega import EnderecoEntrega

router = APIRouter(prefix="/enderecos_entrega", tags=["Endereços de Entrega"])

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# GET /enderecos_entrega - listar todos com filtros opcionais
@router.get("/", response_model=List[EnderecoEntrega])
def listar_enderecos(
    id_nota: Optional[int] = Query(None),
    cpf_cnpj: Optional[str] = Query(None),
    nome_destinatario: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    query = db.query(EnderecoEntregaModel)

    if id_nota:
        query = query.filter(EnderecoEntregaModel.id_nota == id_nota)
    if cpf_cnpj:
        query = query.filter(EnderecoEntregaModel.cpf_cnpj == cpf_cnpj)
    if nome_destinatario:
        query = query.filter(EnderecoEntregaModel.nome_destinatario.ilike(f"%{nome_destinatario}%"))

    return query.all()

# GET /enderecos_entrega/{id}
@router.get("/{id}", response_model=EnderecoEntrega)
def obter_endereco(id: int, db: Session = Depends(get_db)):
    endereco = db.query(EnderecoEntregaModel).filter(EnderecoEntregaModel.id == id).first()

    if not endereco:
        raise HTTPException(status_code=404, detail="Endereço não encontrado")

    return endereco
