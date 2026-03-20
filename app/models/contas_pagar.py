from sqlalchemy import Column, Integer, String, Date, Numeric, DateTime, SmallInteger, CHAR, Text
from app.models.database import Base


class ContasPagar(Base):
    __tablename__ = "contas_pagar"
    __table_args__ = {"schema": "tiny"}

    id = Column(Integer, primary_key=True, index=True)
    id_tiny = Column(Integer, unique=True, nullable=False)
    data_emissao = Column(Date, nullable=False)
    vencimento = Column(Date, nullable=False)
    competencia = Column(Date, nullable=True)
    valor = Column(Numeric(15, 2), nullable=False)
    saldo = Column(Numeric(15, 2), nullable=False)
    nro_documento = Column(String(30), nullable=True)
    historico = Column(String(300), nullable=True)
    categoria = Column(String(100), nullable=True)
    situacao = Column(String(50), nullable=True)
    ocorrencia = Column(CHAR(1), nullable=False)
    dia_vencimento = Column(SmallInteger, nullable=True)
    numero_parcelas = Column(SmallInteger, nullable=True)
    dia_semana_vencimento = Column(SmallInteger, nullable=True)
    cliente_codigo = Column(String(30), nullable=True)
    cliente_nome = Column(String(150), nullable=False)
    cliente_tipo_pessoa = Column(CHAR(1), nullable=True)
    cliente_cpf_cnpj = Column(String(18), nullable=True)
    cliente_ie = Column(String(18), nullable=True)
    cliente_rg = Column(String(10), nullable=True)
    cliente_fone = Column(String(40), nullable=True)
    cliente_email = Column(String(150), nullable=True)
    cliente_endereco = Column(String(150), nullable=True)
    cliente_numero = Column(String(10), nullable=True)
    cliente_complemento = Column(String(150), nullable=True)
    cliente_bairro = Column(String(100), nullable=True)
    cliente_cep = Column(String(10), nullable=True)
    cliente_cidade = Column(String(100), nullable=True)
    cliente_uf = Column(CHAR(2), nullable=True)
    cliente_pais = Column(String(100), nullable=True)
    liquidacao = Column(Date, nullable=True)
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)
