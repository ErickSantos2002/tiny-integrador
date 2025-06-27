from pydantic import BaseModel
from typing import Optional

class FormaEnvioBase(BaseModel):
    id_nota: Optional[int]
    id_forma: Optional[str]
    descricao: Optional[str]

    model_config = {
        "from_attributes": True
    }

class FormaEnvio(FormaEnvioBase):
    id: int
