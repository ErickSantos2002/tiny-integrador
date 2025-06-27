from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.models.database import SessionLocal
from app.models.forma_envio import FormaEnvio as FormaEnvioModel
from app.schemas.forma_envio import FormaEnvio

router = APIRouter(prefix="/formas_envio", tags=["Formas de Envio"])

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# GET /formas_envio - listar com filtros
@router.get("/", response_model=List[FormaEnvio])
def listar_formas_envio(
    id_nota: Optional[int] = Query(None),
    id_forma: Optional[str] = Query(None),
    descricao: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    query = db.query(FormaEnvioModel)

    if id_nota:
        query = query.filter(FormaEnvioModel.id_nota == id_nota)
    if id_forma:
        query = query.filter(FormaEnvioModel.id_forma == id_forma)
    if descricao:
        query = query.filter(FormaEnvioModel.descricao.ilike(f"%{descricao}%"))

    return query.all()

# GET /formas_envio/{id}
@router.get("/{id}", response_model=FormaEnvio)
def obter_forma_envio(id: int, db: Session = Depends(get_db)):
    forma = db.query(FormaEnvioModel).filter(FormaEnvioModel.id == id).first()

    if not forma:
        raise HTTPException(status_code=404, detail="Forma de envio não encontrada")

    return forma
