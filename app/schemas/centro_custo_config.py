from pydantic import BaseModel
from typing import Optional, Any
from decimal import Decimal

class CentroCustoConfigBase(BaseModel):
    produto: str
    ano: int
    cmv_unitario: Optional[Decimal] = None
    frete_unitario: Optional[Decimal] = None
    outros_custos_unitario: Optional[Decimal] = None
    config_json: Optional[Any] = None

    model_config = {"from_attributes": True}

class CentroCustoConfigCreate(CentroCustoConfigBase):
    pass

class CentroCustoConfig(CentroCustoConfigBase):
    id: int
