from sqlalchemy import (
    Column, Integer, String, Text, Date, Numeric
)
from app.models.database import Base

class NotaServico(Base):
    __tablename__ = "servicos"
    __table_args__ = {"schema": "tiny"}

    id = Column(Integer, primary_key=True, index=True)
    tipo_de_registro = Column(Text, nullable=True)
    numero_nfse = Column(Integer, nullable=True)
    status_nfse = Column(Numeric, nullable=True)
    codigo_verificacao = Column(Text, nullable=True)
    data_emissao = Column(Text, nullable=True)
    tipo_rps = Column(Numeric, nullable=True)
    serie_rps = Column(Numeric, nullable=True)
    numero_rps = Column(Numeric, nullable=True)
    data_emissao_rps = Column(Text, nullable=True)
    cpf_cnpj_prestador = Column(Text, nullable=True)
    inscricao_municipal_prestador = Column(Text, nullable=True)
    razao_social_prestador = Column(Text, nullable=True)
    endereco_prestador = Column(Text, nullable=True)
    cidade_prestador = Column(Text, nullable=True)
    uf_prestador = Column(Text, nullable=True)
    email_prestador = Column(Text, nullable=True)

    cpf_cnpj_tomador = Column(Text, nullable=True)
    inscricao_municipal_tomador = Column(Text, nullable=True)
    razao_social_tomador = Column(Text, nullable=True)
    endereco_tomador = Column(Text, nullable=True)
    cidade_tomador = Column(Text, nullable=True)
    uf_tomador = Column(Text, nullable=True)
    email_tomador = Column(Text, nullable=True)

    tipo_tributacao = Column(Numeric, nullable=True)
    cidade_servico = Column(Text, nullable=True)
    uf_servico = Column(Text, nullable=True)
    regime_especial = Column(Numeric, nullable=True)
    simples_nacional = Column(Numeric, nullable=True)
    incentivo_cultural = Column(Numeric, nullable=True)
    codigo_atividade_municipal = Column(Numeric, nullable=True)

    aliquota = Column(Text, nullable=True)
    valor_servico = Column(Text, nullable=True)
    valor_deducoes = Column(Text, nullable=True)
    valor_iss = Column(Text, nullable=True)
    valor_outros = Column(Text, nullable=True)
    iss_retido = Column(Numeric, nullable=True)

    discriminacao_servico = Column(Text, nullable=True)
    competencia = Column(Text, nullable=True)
    valor_total_recebido = Column(Text, nullable=True)
