from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.models.database import SessionLocal
from app.models.item_nota import ItemNota as ItemNotaModel
from app.schemas.item_nota import ItemNota

router = APIRouter(prefix="/itens_nota", tags=["Itens da Nota Fiscal"])

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# GET /itens_nota - listar com filtros opcionais
@router.get("/", response_model=List[ItemNota])
def listar_itens(
    id_nota: Optional[int] = Query(None),
    id_produto: Optional[str] = Query(None),
    descricao: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    query = db.query(ItemNotaModel)

    if id_nota:
        query = query.filter(ItemNotaModel.id_nota == id_nota)
    if id_produto:
        query = query.filter(ItemNotaModel.id_produto == id_produto)
    if descricao:
        query = query.filter(ItemNotaModel.descricao.ilike(f"%{descricao}%"))

    return query.all()

# GET /itens_nota/{id} - obter item específico
@router.get("/{id}", response_model=ItemNota)
def obter_item(id: int, db: Session = Depends(get_db)):
    item = db.query(ItemNotaModel).filter(ItemNotaModel.id == id).first()

    if not item:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    
    return item
