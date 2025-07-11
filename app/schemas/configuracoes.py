from pydantic import BaseModel

# Base para reuso
class ConfiguracaoBase(BaseModel):
    chave: str
    valor: str

# Schema para criação
class ConfiguracaoCreate(ConfiguracaoBase):
    pass

# Schema para atualização
class ConfiguracaoUpdate(BaseModel):
    valor: str

# Schema de resposta (com id e orm_mode configurado)
class Configuracao(ConfiguracaoBase):
    id: int

    model_config = {
        "from_attributes": True
    }
