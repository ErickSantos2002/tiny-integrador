from sqlalchemy import Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.models.database import Base

class FormaEnvio(Base):
    __tablename__ = "formas_envio"

    id = Column(Integer, primary_key=True, index=True)
    id_nota = Column(Integer, ForeignKey("notas_fiscais.id"), nullable=True)
    id_forma = Column(String(20), nullable=True)
    descricao = Column(Text, nullable=True)

    # Relacionamento (opcional se quiser acessar a nota diretamente)
    nota_fiscal = relationship("NotaFiscal", back_populates="formas_envio")
