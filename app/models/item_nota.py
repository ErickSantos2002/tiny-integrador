from sqlalchemy import Column, Integer, String, Text, Numeric, ForeignKey
from sqlalchemy.orm import relationship
from app.models.database import Base

class ItemNota(Base):
    __tablename__ = "itens_nota"
    __table_args__ = {"schema": "tiny"}

    id = Column(Integer, primary_key=True, index=True)
    id_nota = Column(Integer, ForeignKey("tiny.notas_fiscais.id"), nullable=True)
    id_produto = Column(String(20), nullable=True)
    codigo = Column(String(20), nullable=True)
    descricao = Column(Text, nullable=True)
    unidade = Column(String(10), nullable=True)
    ncm = Column(String(20), nullable=True)
    quantidade = Column(Numeric, nullable=True)
    valor_unitario = Column(Numeric, nullable=True)
    valor_total = Column(Numeric, nullable=True)
    cfop = Column(String(10), nullable=True)
    natureza = Column(Text, nullable=True)

    # Relacionamento com nota fiscal
    nota_fiscal = relationship("NotaFiscal", back_populates="itens")
