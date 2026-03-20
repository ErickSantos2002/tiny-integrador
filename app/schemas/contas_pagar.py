from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime
from decimal import Decimal


class ContasPagarBase(BaseModel):
    id_tiny: int
    data_emissao: date
    vencimento: date
    competencia: Optional[date] = None
    valor: Decimal
    saldo: Decimal
    nro_documento: Optional[str] = None
    historico: Optional[str] = None
    categoria: Optional[str] = None
    situacao: Optional[str] = None
    ocorrencia: str
    dia_vencimento: Optional[int] = None
    numero_parcelas: Optional[int] = None
    dia_semana_vencimento: Optional[int] = None
    cliente_codigo: Optional[str] = None
    cliente_nome: str
    cliente_tipo_pessoa: Optional[str] = None
    cliente_cpf_cnpj: Optional[str] = None
    cliente_ie: Optional[str] = None
    cliente_rg: Optional[str] = None
    cliente_fone: Optional[str] = None
    cliente_email: Optional[str] = None
    cliente_endereco: Optional[str] = None
    cliente_numero: Optional[str] = None
    cliente_complemento: Optional[str] = None
    cliente_bairro: Optional[str] = None
    cliente_cep: Optional[str] = None
    cliente_cidade: Optional[str] = None
    cliente_uf: Optional[str] = None
    cliente_pais: Optional[str] = None
    liquidacao: Optional[date] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {
        "from_attributes": True
    }


class ContasPagar(ContasPagarBase):
    id: int
