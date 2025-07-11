from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.models.database import SessionLocal
from app.models.configuracoes import Configuracao as ConfiguracaoModel
from app.schemas.configuracoes import Configuracao, ConfiguracaoCreate, ConfiguracaoUpdate

router = APIRouter(prefix="/configuracoes", tags=["Configurações"])

# Reutilizando a dependência como seu exemplo
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/", response_model=List[Configuracao])
def listar_configuracoes(db: Session = Depends(get_db)):
    return db.query(ConfiguracaoModel).all()

@router.get("/{chave}", response_model=Configuracao)
def obter_configuracao(chave: str, db: Session = Depends(get_db)):
    config = db.query(ConfiguracaoModel).filter_by(chave=chave).first()
    if not config:
        raise HTTPException(status_code=404, detail="Configuração não encontrada")
    return config

@router.put("/{chave}", response_model=Configuracao)
def atualizar_configuracao(chave: str, dados: ConfiguracaoUpdate, db: Session = Depends(get_db)):
    config = db.query(ConfiguracaoModel).filter_by(chave=chave).first()
    if not config:
        raise HTTPException(status_code=404, detail="Configuração não encontrada")
    config.valor = dados.valor
    db.commit()
    db.refresh(config)
    return config

@router.post("/", response_model=Configuracao)
def criar_configuracao(dados: ConfiguracaoCreate, db: Session = Depends(get_db)):
    existente = db.query(ConfiguracaoModel).filter_by(chave=dados.chave).first()
    if existente:
        raise HTTPException(status_code=400, detail="Chave já existente")
    nova = ConfiguracaoModel(chave=dados.chave, valor=dados.valor)
    db.add(nova)
    db.commit()
    db.refresh(nova)
    return nova
