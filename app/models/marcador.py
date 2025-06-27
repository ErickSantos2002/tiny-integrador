from sqlalchemy import Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.models.database import Base

class Marcador(Base):
    __tablename__ = "marcadores"

    id = Column(Integer, primary_key=True, index=True)
    id_nota = Column(Integer, ForeignKey("notas_fiscais.id"), nullable=True)
    id_marcador = Column(String(20), nullable=True)
    descricao = Column(Text, nullable=True)
    cor = Column(String(10), nullable=True)

    # Relacionamento (opcional)
    nota_fiscal = relationship("NotaFiscal", back_populates="marcadores")
