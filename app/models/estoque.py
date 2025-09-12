from sqlalchemy import Column, Integer, String, Numeric, DateTime, CHAR
from app.models.database import Base

class Estoque(Base):
    __tablename__ = "estoque"
    __table_args__ = {"schema": "tiny"}

    id = Column(Integer, primary_key=True, index=True)
    data_criacao = Column(DateTime, nullable=True)
    nome = Column(String(255), nullable=True)
    codigo = Column(Integer, nullable=True)
    preco = Column(Numeric(10, 2), nullable=True, default=0)
    preco_promocional = Column(Numeric(10, 2), nullable=True, default=0)
    unidade = Column(String(10), nullable=True)
    gtin = Column(String(50), nullable=True)
    tipovariacao = Column(CHAR(1), nullable=True)
    localizacao = Column(String(100), nullable=True)
    preco_custo = Column(Numeric(10, 2), nullable=True, default=0)
    preco_custo_medio = Column(Numeric(10, 2), nullable=True, default=0)
    situacao = Column(CHAR(1), nullable=True)
    saldo = Column(Numeric(10, 2), nullable=False, default=0)
