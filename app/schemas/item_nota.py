from pydantic import BaseModel
from typing import Optional
from decimal import Decimal

class ItemNotaBase(BaseModel):
    id_nota: Optional[int]
    id_produto: Optional[str]
    codigo: Optional[str]
    descricao: Optional[str]
    unidade: Optional[str]
    ncm: Optional[str]
    quantidade: Optional[Decimal]
    valor_unitario: Optional[Decimal]
    valor_total: Optional[Decimal]
    cfop: Optional[str]
    natureza: Optional[str]

    class Config:
        orm_mode = True

class ItemNota(ItemNotaBase):
    id: int
