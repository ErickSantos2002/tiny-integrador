from pydantic import BaseModel

class ConfiguracaoBase(BaseModel):
    chave: str
    valor: str

class ConfiguracaoCreate(ConfiguracaoBase):
    pass

class ConfiguracaoUpdate(BaseModel):
    valor: str

class Configuracao(ConfiguracaoBase):
    class Config:
        orm_mode = True
