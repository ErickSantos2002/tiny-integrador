from sqlalchemy import Column, Integer, String
from app.models.database import Base

class Configuracao(Base):
    __tablename__ = "configuracoes"
    __table_args__ = {"schema": "tiny"}

    id = Column(Integer, primary_key=True, index=True)
    chave = Column(String, unique=True, nullable=False, index=True)
    valor = Column(String, nullable=False)
