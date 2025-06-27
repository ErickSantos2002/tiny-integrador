from sqlalchemy import Column, Integer, String, Text, CHAR, ForeignKey
from sqlalchemy.orm import relationship
from app.models.database import Base

class EnderecoEntrega(Base):
    __tablename__ = "enderecos_entrega"
    __table_args__ = {"schema": "tiny"}

    id = Column(Integer, primary_key=True, index=True)
    cpf_cnpj = Column(String(20), nullable=True)
    nome_destinatario = Column(Text, nullable=True)
    tipo_pessoa = Column(CHAR(1), nullable=True)
    ie = Column(String(30), nullable=True)
    endereco = Column(Text, nullable=True)
    numero = Column(String(20), nullable=True)
    complemento = Column(Text, nullable=True)
    bairro = Column(Text, nullable=True)
    cep = Column(String(20), nullable=True)
    cidade = Column(Text, nullable=True)
    uf = Column(CHAR(2), nullable=True)
    fone = Column(String(20), nullable=True)

    id_nota = Column(Integer, ForeignKey("tiny.notas_fiscais.id"), nullable=True)

    # Relacionamento (opcional se for acessar nota diretamente)
    nota_fiscal = relationship("NotaFiscal", back_populates="enderecos_entrega")
