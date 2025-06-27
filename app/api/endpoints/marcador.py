from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.models.database import SessionLocal
from app.models.marcador import Marcador as MarcadorModel
from app.schemas.marcador import Marcador

router = APIRouter(prefix="/marcadores", tags=["Marcadores"])

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# GET /marcadores - listar com filtros
@router.get("/", response_model=List[Marcador])
def listar_marcadores(
    id_nota: Optional[int] = Query(None),
    id_marcador: Optional[str] = Query(None),
    descricao: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    query = db.query(MarcadorModel)

    if id_nota:
        query = query.filter(MarcadorModel.id_nota == id_nota)
    if id_marcador:
        query = query.filter(MarcadorModel.id_marcador == id_marcador)
    if descricao:
        query = query.filter(MarcadorModel.descricao.ilike(f"%{descricao}%"))

    return query.all()

# GET /marcadores/{id}
@router.get("/{id}", response_model=Marcador)
def obter_marcador(id: int, db: Session = Depends(get_db)):
    marcador = db.query(MarcadorModel).filter(MarcadorModel.id == id).first()

    if not marcador:
        raise HTTPException(status_code=404, detail="Marcador não encontrado")

    return marcador
