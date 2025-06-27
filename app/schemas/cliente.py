from pydantic import BaseModel
from typing import Optional

class ClienteBase(BaseModel):
    cpf_cnpj: str
    nome: Optional[str]
    tipo_pessoa: Optional[str]
    ie: Optional[str]
    endereco: Optional[str]
    numero: Optional[str]
    complemento: Optional[str]
    bairro: Optional[str]
    cep: Optional[str]
    cidade: Optional[str]
    uf: Optional[str]
    fone: Optional[str]
    email: Optional[str]

    class Config:
        orm_mode = True

class Cliente(ClienteBase):
    id: int
