from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.models import estoque as models
from app.schemas import estoque as schemas
from app.models.database import get_db

router = APIRouter()

@router.get("/", response_model=List[schemas.Estoque])
def listar_estoque(db: Session = Depends(get_db)):
    return db.query(models.Estoque).all()

@router.get("/{estoque_id}", response_model=schemas.Estoque)
def obter_estoque(estoque_id: int, db: Session = Depends(get_db)):
    estoque = db.query(models.Estoque).filter(models.Estoque.id == estoque_id).first()
    if not estoque:
        raise HTTPException(status_code=404, detail="Estoque não encontrado")
    return estoque

@router.post("/", response_model=schemas.Estoque)
def criar_estoque(item: schemas.EstoqueCreate, db: Session = Depends(get_db)):
    db_item = models.Estoque(**item.dict())
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item

@router.put("/{estoque_id}", response_model=schemas.Estoque)
def atualizar_estoque(estoque_id: int, item: schemas.EstoqueUpdate, db: Session = Depends(get_db)):
    db_item = db.query(models.Estoque).filter(models.Estoque.id == estoque_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Estoque não encontrado")
    for key, value in item.dict(exclude_unset=True).items():
        setattr(db_item, key, value)
    db.commit()
    db.refresh(db_item)
    return db_item

@router.delete("/{estoque_id}")
def deletar_estoque(estoque_id: int, db: Session = Depends(get_db)):
    db_item = db.query(models.Estoque).filter(models.Estoque.id == estoque_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Estoque não encontrado")
    db.delete(db_item)
    db.commit()
    return {"detail": "Estoque removido com sucesso"}
