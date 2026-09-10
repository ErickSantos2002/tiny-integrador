from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.core.paginacao import Pagina, limite_query, offset_query, paginar
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
@router.get("/", response_model=Pagina[Cliente])
def listar_clientes(
    cpf_cnpj: Optional[str] = Query(None),
    nome: Optional[str] = Query(None),
    limite: int = limite_query(),
    offset: int = offset_query(),
    db: Session = Depends(get_db),
):
    """Os clientes cadastrados, uma página por vez.

    Paginado em 2026-09-09, quando o último consumidor da lista completa deixou
    de existir: as quatro telas do Comercial baixavam os 2.084 cadastros para
    cruzar com as notas no navegador, e esse cruzamento passou a ser do banco
    (`/faturamento/resumo`, item 9.4). Enquanto elas desenhavam gráfico a partir
    desta lista, paginar teria feito a primeira página ser lida como o total.

    A ordem é por `id` porque paginação sem ordem definida não é paginação: o
    Postgres não promete ordem estável entre duas consultas, e a mesma linha
    pode aparecer em duas páginas — ou em nenhuma.
    """
    query = db.query(ClienteModel)

    if cpf_cnpj:
        query = query.filter(ClienteModel.cpf_cnpj == cpf_cnpj)

    if nome:
        query = query.filter(ClienteModel.nome.ilike(f"%{nome}%"))

    return paginar(query.order_by(ClienteModel.id), limite, offset)

# GET /clientes/{id} - buscar por ID
@router.get("/{id}", response_model=Cliente)
def obter_cliente(id: int, db: Session = Depends(get_db)):
    cliente = db.query(ClienteModel).filter(ClienteModel.id == id).first()

    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    return cliente
