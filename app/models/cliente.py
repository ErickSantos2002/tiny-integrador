from sqlalchemy import Column, Integer, String, CHAR, Text
from sqlalchemy.orm import relationship
from app.models.database import Base

class Cliente(Base):
    __tablename__ = "clientes"
    __table_args__ = {"schema": "tiny"}

    id = Column(Integer, primary_key=True, index=True)
    cpf_cnpj = Column(String(20), nullable=False, unique=True)
    nome = Column(Text, nullable=True)
    tipo_pessoa = Column(CHAR(1), nullable=True)
    ie = Column(String(30), nullable=True)
    endereco = Column(Text, nullable=True)
    numero = Column(String(10), nullable=True)
    complemento = Column(Text, nullable=True)
    bairro = Column(Text, nullable=True)
    cep = Column(String(10), nullable=True)
    cidade = Column(Text, nullable=True)
    uf = Column(CHAR(2), nullable=True)
    fone = Column(String(20), nullable=True)
    email = Column(String(100), nullable=True)

    notas_fiscais = relationship("NotaFiscal", back_populates="cliente")
