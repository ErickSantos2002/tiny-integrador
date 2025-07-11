from pydantic import BaseModel
from typing import Optional
from decimal import Decimal

class NotaServicoBase(BaseModel):
    tipo_de_registro: Optional[str]
    numero_nfse: Optional[int]
    status_nfse: Optional[Decimal]
    codigo_verificacao: Optional[str]
    data_emissao: Optional[str]
    tipo_rps: Optional[Decimal]
    serie_rps: Optional[Decimal]
    numero_rps: Optional[Decimal]
    data_emissao_rps: Optional[str]

    cpf_cnpj_prestador: Optional[str]
    inscricao_municipal_prestador: Optional[str]
    razao_social_prestador: Optional[str]
    endereco_prestador: Optional[str]
    cidade_prestador: Optional[str]
    uf_prestador: Optional[str]
    email_prestador: Optional[str]

    cpf_cnpj_tomador: Optional[str]
    inscricao_municipal_tomador: Optional[str]
    razao_social_tomador: Optional[str]
    endereco_tomador: Optional[str]
    cidade_tomador: Optional[str]
    uf_tomador: Optional[str]
    email_tomador: Optional[str]

    tipo_tributacao: Optional[Decimal]
    cidade_servico: Optional[str]
    uf_servico: Optional[str]
    regime_especial: Optional[Decimal]
    simples_nacional: Optional[Decimal]
    incentivo_cultural: Optional[Decimal]
    codigo_atividade_municipal: Optional[Decimal]

    aliquota: Optional[str]
    valor_servico: Optional[str]
    valor_deducoes: Optional[str]
    valor_iss: Optional[str]
    valor_outros: Optional[str]
    iss_retido: Optional[Decimal]

    discriminacao_servico: Optional[str]
    competencia: Optional[str]
    valor_total_recebido: Optional[str]

    model_config = {
        "from_attributes": True
    }

class NotaServico(NotaServicoBase):
    id: int
