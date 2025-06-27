from pydantic import BaseModel
from typing import Optional

class FormaEnvioBase(BaseModel):
    id_nota: Optional[int]
    id_forma: Optional[str]
    descricao: Optional[str]

    class Config:
        orm_mode = True

class FormaEnvio(FormaEnvioBase):
    id: int
