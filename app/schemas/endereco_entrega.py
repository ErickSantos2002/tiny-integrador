from pydantic import BaseModel
from typing import Optional

class EnderecoEntregaBase(BaseModel):
    cpf_cnpj: Optional[str]
    nome_destinatario: Optional[str]
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
    id_nota: Optional[int]

    model_config = {
        "from_attributes": True
    }

class EnderecoEntrega(EnderecoEntregaBase):
    id: int
