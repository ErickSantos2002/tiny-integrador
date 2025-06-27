from pydantic import BaseModel
from typing import Optional, List
from datetime import date, time
from decimal import Decimal

from app.schemas.cliente import Cliente
from app.schemas.endereco_entrega import EnderecoEntrega
from app.schemas.forma_envio import FormaEnvio
from app.schemas.marcador import Marcador
from app.schemas.item_nota import ItemNota

class NotaFiscalBase(BaseModel):
    id_tiny: Optional[str]
    tipo_nota: Optional[str]
    natureza_operacao: Optional[str]
    regime_tributario: Optional[str]
    finalidade: Optional[str]
    serie: Optional[str]
    numero: Optional[str]
    numero_ecommerce: Optional[str]
    data_emissao: Optional[date]
    data_saida: Optional[date]
    hora_saida: Optional[time]
    base_icms: Optional[Decimal]
    valor_icms: Optional[Decimal]
    base_icms_st: Optional[Decimal]
    valor_icms_st: Optional[Decimal]
    valor_produtos: Optional[Decimal]
    valor_servicos: Optional[Decimal]
    valor_frete: Optional[Decimal]
    valor_seguro: Optional[Decimal]
    valor_outras: Optional[Decimal]
    valor_ipi: Optional[Decimal]
    valor_issqn: Optional[Decimal]
    valor_nota: Optional[Decimal]
    valor_desconto: Optional[Decimal]
    valor_faturado: Optional[Decimal]
    frete_por_conta: Optional[str]
    condicao_pagamento: Optional[str]
    forma_pagamento: Optional[str]
    meio_pagamento: Optional[str]
    id_vendedor: Optional[str]
    nome_vendedor: Optional[str]
    situacao: Optional[str]
    descricao_situacao: Optional[str]
    chave_acesso: Optional[str]
    observacoes: Optional[str]
    id_cliente: Optional[int]

    class Config:
        orm_mode = True

class NotaFiscal(NotaFiscalBase):
    id: int

    # Relacionamentos (opcionais na resposta)
    cliente: Optional[Cliente]
    enderecos_entrega: Optional[EnderecoEntrega]
    formas_envio: Optional[List[FormaEnvio]]
    marcadores: Optional[List[Marcador]]
    itens: Optional[List[ItemNota]]
