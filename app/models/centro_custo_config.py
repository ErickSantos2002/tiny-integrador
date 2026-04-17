from sqlalchemy import Column, Integer, String, Numeric, DateTime, func
from app.models.database import Base

class CentroCustoConfig(Base):
    __tablename__ = "centro_custo_config"
    __table_args__ = {"schema": "tiny"}

    id = Column(Integer, primary_key=True, index=True)
    produto = Column(String(50), nullable=False)
    ano = Column(Integer, nullable=False)
    cmv_unitario = Column(Numeric(12, 2), nullable=True)
    frete_unitario = Column(Numeric(12, 2), nullable=True)
    outros_custos_unitario = Column(Numeric(12, 2), nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
