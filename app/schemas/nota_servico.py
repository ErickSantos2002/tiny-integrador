from pydantic import BaseModel
from typing import Optional
from decimal import Decimal
from datetime import date

class NotaServicoBase(BaseModel):
    tipo_de_registro: Optional[str] = None
    numero_nfse: Optional[int] = None
    status_nfse: Optional[Decimal] = None
    codigo_verificacao: Optional[str] = None
    data_emissao: Optional[date] = None
    tipo_rps: Optional[Decimal] = None
    serie_rps: Optional[Decimal] = None
    numero_rps: Optional[Decimal] = None
    data_emissao_rps: Optional[str] = None

    cpf_cnpj_prestador: Optional[str] = None
    inscricao_municipal_prestador: Optional[str] = None
    razao_social_prestador: Optional[str] = None
    endereco_prestador: Optional[str] = None
    cidade_prestador: Optional[str] = None
    uf_prestador: Optional[str] = None
    email_prestador: Optional[str] = None

    cpf_cnpj_tomador: Optional[str] = None
    inscricao_municipal_tomador: Optional[str] = None
    razao_social_tomador: Optional[str] = None
    endereco_tomador: Optional[str] = None
    cidade_tomador: Optional[str] = None
    uf_tomador: Optional[str] = None
    email_tomador: Optional[str] = None

    tipo_tributacao: Optional[Decimal] = None
    cidade_servico: Optional[str] = None
    uf_servico: Optional[str] = None
    regime_especial: Optional[Decimal] = None
    simples_nacional: Optional[Decimal] = None
    incentivo_cultural: Optional[Decimal] = None
    codigo_atividade_municipal: Optional[Decimal] = None

    aliquota: Optional[str] = None
    valor_servico: Optional[str] = None
    valor_deducoes: Optional[str] = None
    valor_iss: Optional[str] = None
    valor_outros: Optional[str] = None
    iss_retido: Optional[Decimal] = None

    discriminacao_servico: Optional[str] = None
    competencia: Optional[str] = None
    valor_total_recebido: Optional[str] = None

    model_config = {
        "from_attributes": True
    }

class NotaServico(NotaServicoBase):
    id: int
