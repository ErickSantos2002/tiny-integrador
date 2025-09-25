from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class EstoqueBase(BaseModel):
    data_criacao: Optional[datetime]
    nome: Optional[str]
    codigo: Optional[int]
    preco: Optional[float] = 0
    preco_promocional: Optional[float] = 0
    unidade: Optional[str]
    gtin: Optional[str]
    tipovariacao: Optional[str]
    localizacao: Optional[str]
    preco_custo: Optional[float] = 0
    preco_custo_medio: Optional[float] = 0
    situacao: Optional[str]
    saldo: float = 0

class EstoqueCreate(EstoqueBase):
    id: int

class EstoqueUpdate(EstoqueBase):
    pass

class EstoqueInDBBase(EstoqueBase):
    id: int

    model_config = {
        "from_attributes": True
    }

class Estoque(EstoqueInDBBase):
    pass
