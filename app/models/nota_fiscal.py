from sqlalchemy import (
    Column, Integer, String, Text, Date, Time, Numeric, ForeignKey
)
from sqlalchemy.orm import relationship
from app.models.database import Base

class NotaFiscal(Base):
    __tablename__ = "notas_fiscais"
    __table_args__ = {"schema": "tiny"}

    id = Column(Integer, primary_key=True, index=True)
    id_tiny = Column(String(20), unique=True, nullable=True)
    tipo_nota = Column(String(2), nullable=True)
    natureza_operacao = Column(Text, nullable=True)
    regime_tributario = Column(String(5), nullable=True)
    finalidade = Column(String(5), nullable=True)
    serie = Column(String(10), nullable=True)
    numero = Column(String(20), nullable=True)
    numero_ecommerce = Column(String(20), nullable=True)

    data_emissao = Column(Date, nullable=True)
    data_saida = Column(Date, nullable=True)
    hora_saida = Column(Time, nullable=True)

    base_icms = Column(Numeric, nullable=True)
    valor_icms = Column(Numeric, nullable=True)
    base_icms_st = Column(Numeric, nullable=True)
    valor_icms_st = Column(Numeric, nullable=True)
    valor_produtos = Column(Numeric, nullable=True)
    valor_servicos = Column(Numeric, nullable=True)
    valor_frete = Column(Numeric, nullable=True)
    valor_seguro = Column(Numeric, nullable=True)
    valor_outras = Column(Numeric, nullable=True)
    valor_ipi = Column(Numeric, nullable=True)
    valor_issqn = Column(Numeric, nullable=True)
    valor_nota = Column(Numeric, nullable=True)
    valor_desconto = Column(Numeric, nullable=True)
    valor_faturado = Column(Numeric, nullable=True)

    frete_por_conta = Column(String(1), nullable=True)
    condicao_pagamento = Column(String(30), nullable=True)
    forma_pagamento = Column(String(100), nullable=True)
    meio_pagamento = Column(String(100), nullable=True)

    id_vendedor = Column(String(20), nullable=True)
    nome_vendedor = Column(String(100), nullable=True)

    situacao = Column(String(10), nullable=True)
    descricao_situacao = Column(Text, nullable=True)
    chave_acesso = Column(String(60), nullable=True)
    observacoes = Column(Text, nullable=True)

    id_cliente = Column(Integer, ForeignKey("tiny.clientes.id"), nullable=True)
    cliente = relationship("ClienteModel", back_populates="notas_fiscais")

    # Relacionamentos com outras tabelas
    enderecos_entrega = relationship("EnderecoEntrega", back_populates="nota_fiscal", uselist=False)
    formas_envio = relationship("FormaEnvio", back_populates="nota_fiscal")
    marcadores = relationship("Marcador", back_populates="nota_fiscal")
    itens = relationship("ItemNota", back_populates="nota_fiscal")
