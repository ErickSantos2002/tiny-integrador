from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, text
from typing import List, Optional
from app.core.faturamento import SITUACAO_EMITIDA, filtro_cfop_venda, sem_marcador_ruim
from app.core.paginacao import Pagina, limite_query, offset_query, paginar
from app.models.database import SessionLocal
from app.models.nota_fiscal import NotaFiscal as NotaFiscalModel
from app.schemas.nota_fiscal import NotaFiscal
from app.schemas.nota_fiscal import NotaFiscalUpdateTipo

router = APIRouter(prefix="/notas_fiscais", tags=["Notas Fiscais"])

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/", response_model=Pagina[NotaFiscal])
def listar_notas_fiscais(
    id_cliente: Optional[int] = Query(None),
    data_emissao: Optional[str] = Query(None),
    data_inicio: Optional[str] = Query(None),
    data_fim: Optional[str] = Query(None),
    natureza_operacao: Optional[List[str]] = Query(None),
    descricao_situacao: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    limite: int = limite_query(),
    offset: int = offset_query(),
    db: Session = Depends(get_db),
):
    query = db.query(NotaFiscalModel).options(
        joinedload(NotaFiscalModel.cliente),
        joinedload(NotaFiscalModel.enderecos_entrega),
        joinedload(NotaFiscalModel.formas_envio),
        joinedload(NotaFiscalModel.marcadores),
        joinedload(NotaFiscalModel.itens)
    )

    if id_cliente:
        query = query.filter(NotaFiscalModel.id_cliente == id_cliente)

    if data_inicio and data_fim:
        query = query.filter(NotaFiscalModel.data_emissao.between(data_inicio, data_fim))
    elif data_inicio:
        query = query.filter(NotaFiscalModel.data_emissao >= data_inicio)
    elif data_fim:
        query = query.filter(NotaFiscalModel.data_emissao <= data_fim)
    elif data_emissao:
        query = query.filter(NotaFiscalModel.data_emissao == data_emissao)

    if natureza_operacao:
        filtros = [
            NotaFiscalModel.natureza_operacao.ilike(f"%{valor}%")
            for valor in natureza_operacao
        ]
        query = query.filter(or_(*filtros))

    if descricao_situacao:
        query = query.filter(NotaFiscalModel.descricao_situacao == descricao_situacao)

    if tipo:   # <-- Filtro do novo campo
        query = query.filter(NotaFiscalModel.tipo == tipo)

    return paginar(query, limite, offset)

# ⚠️ DEPRECADO em 2026-09-08 — substituído por `GET /faturamento/vendas`.
#
# Este endpoint REIMPLEMENTA a régua de faturamento: CFOP procurado como substring dentro
# de `natureza_operacao`, que é campo de texto livre, e marcador comparado contra uma lista
# fixa de sete descrições. Os dois defeitos foram medidos (item 9.1): notas canceladas
# passavam por diferença de caixa, e exportação (CFOP 7102) nunca apareceu porque não está
# na lista. O substituto lê `gold.fato_vendas`, onde a régua é única e testada.
#
# Continua no ar de propósito, e não por esquecimento: o DataCoreHS parou de chamá-lo
# hoje, mas ele é uma rota pública de uma API que outros consumidores podem estar usando —
# e o log de acesso, que responderia isso, só existe desde ontem.
#
# COMO DECIDIR A REMOÇÃO, sem adivinhar: agora que o frontend migrou, toda chamada que
# aparecer no log é de outro consumidor. Rodar, depois de alguns dias de uso normal:
#
#     docker logs --since 168h <container-da-api> 2>&1 | grep "\[acesso\]" \
#         | grep "/notas_fiscais/vendas/"
#
# Zero linhas em uma semana que inclua fechamento de mês → pode sair, junto com
# `app/core/faturamento.py`, que existe só para servi-lo.
@router.get("/vendas/", response_model=List[NotaFiscal], deprecated=True)
def listar_vendas(
    id_cliente: Optional[int] = Query(None),
    data_emissao: Optional[str] = Query(None),
    data_inicio: Optional[str] = Query(None),
    data_fim: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    query = db.query(NotaFiscalModel).options(
        joinedload(NotaFiscalModel.cliente),
        joinedload(NotaFiscalModel.enderecos_entrega),
        joinedload(NotaFiscalModel.formas_envio),
        joinedload(NotaFiscalModel.marcadores),
        joinedload(NotaFiscalModel.itens),
    )

    # 🔹 Filtra CFOP de vendas
    query = query.filter(filtro_cfop_venda())

    # 🔹 Apenas notas emitidas
    query = query.filter(NotaFiscalModel.descricao_situacao == SITUACAO_EMITIDA)

    # 🔹 Excluir notas com marcadores problemáticos
    query = query.filter(sem_marcador_ruim())

    # 🔹 Filtros opcionais iguais ao /notas_fiscais
    if id_cliente:
        query = query.filter(NotaFiscalModel.id_cliente == id_cliente)

    if data_inicio and data_fim:
        query = query.filter(NotaFiscalModel.data_emissao.between(data_inicio, data_fim))
    elif data_inicio:
        query = query.filter(NotaFiscalModel.data_emissao >= data_inicio)
    elif data_fim:
        query = query.filter(NotaFiscalModel.data_emissao <= data_fim)
    elif data_emissao:
        query = query.filter(NotaFiscalModel.data_emissao == data_emissao)

    return query.all()

# Novo endpoint: /locacao/  → notas com o marcador "Locação"
@router.get("/locacao/", response_model=List[NotaFiscal])
def listar_locacao(
    id_cliente: Optional[int] = Query(None),
    data_emissao: Optional[str] = Query(None),
    data_inicio: Optional[str] = Query(None),
    data_fim: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    query = db.query(NotaFiscalModel).options(
        joinedload(NotaFiscalModel.cliente),
        joinedload(NotaFiscalModel.enderecos_entrega),
        joinedload(NotaFiscalModel.formas_envio),
        joinedload(NotaFiscalModel.marcadores),
        joinedload(NotaFiscalModel.itens),
    )

    # Quem decide o que é locação é a `silver.stg_marcadores`, pelo conceito — não um
    # `ilike("loca%")` sobre a descrição crua. O prefixo funcionava por sorte de grafia:
    # bastava alguém cadastrar "aluguel" ou "LOC." para a nota sumir da tela sem erro
    # nenhum. Na silver a classificação é por radical, com seed de exceções e teste.
    query = query.filter(
        NotaFiscalModel.id.in_(
            text("SELECT id_nota FROM silver.stg_marcadores WHERE conceito = 'locacao'")
        )
    )

    # 🔹 Filtros opcionais iguais ao /notas_fiscais
    if id_cliente:
        query = query.filter(NotaFiscalModel.id_cliente == id_cliente)

    if data_inicio and data_fim:
        query = query.filter(NotaFiscalModel.data_emissao.between(data_inicio, data_fim))
    elif data_inicio:
        query = query.filter(NotaFiscalModel.data_emissao >= data_inicio)
    elif data_fim:
        query = query.filter(NotaFiscalModel.data_emissao <= data_fim)
    elif data_emissao:
        query = query.filter(NotaFiscalModel.data_emissao == data_emissao)

    return query.order_by(NotaFiscalModel.data_emissao.desc()).all()

@router.patch("/{nota_id}/tipo", response_model=NotaFiscal)
def atualizar_tipo_nota(
    nota_id: int = Path(..., description="ID da nota fiscal"),
    payload: NotaFiscalUpdateTipo = None,
    db: Session = Depends(get_db)
):
    # 🔎 Busca a nota fiscal pelo ID
    nota = db.query(NotaFiscalModel).filter(NotaFiscalModel.id == nota_id).first()
    if not nota:
        raise HTTPException(status_code=404, detail="Nota fiscal não encontrada")

    # ✏️ Atualiza apenas o campo tipo
    nota.tipo = payload.tipo
    db.add(nota)
    db.commit()
    db.refresh(nota)

    return nota