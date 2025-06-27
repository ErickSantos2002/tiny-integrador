from pydantic import BaseModel
from typing import Optional

class MarcadorBase(BaseModel):
    id_nota: Optional[int]
    id_marcador: Optional[str]
    descricao: Optional[str]
    cor: Optional[str]

    model_config = {
        "from_attributes": True
    }

class Marcador(MarcadorBase):
    id: int
