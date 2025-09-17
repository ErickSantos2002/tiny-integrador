from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_
from typing import List, Optional
from app.models.database import SessionLocal
from app.models.nota_fiscal import NotaFiscal as NotaFiscalModel
from app.models.marcador import Marcador
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

@router.get("/", response_model=List[NotaFiscal])
def listar_notas_fiscais(
    id_cliente: Optional[int] = Query(None),
    data_emissao: Optional[str] = Query(None),
    data_inicio: Optional[str] = Query(None),
    data_fim: Optional[str] = Query(None),
    natureza_operacao: Optional[List[str]] = Query(None),
    descricao_situacao: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    db: Session = Depends(get_db)
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

    return query.all()

# Novo endpoint: /vendas/
@router.get("/vendas/", response_model=List[NotaFiscal])
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
    query = query.filter(
        (NotaFiscalModel.natureza_operacao.ilike("%6102%")) |
        (NotaFiscalModel.natureza_operacao.ilike("%5102%")) |
        (NotaFiscalModel.natureza_operacao.ilike("%6108%")) |
        (NotaFiscalModel.natureza_operacao.ilike("%5108%"))
    )

    # 🔹 Apenas notas emitidas
    query = query.filter(NotaFiscalModel.descricao_situacao == "Emitida DANFE")

    # 🔹 Excluir notas com marcadores problemáticos
    query = query.filter(
        ~NotaFiscalModel.marcadores.any(
            Marcador.descricao.in_([
                "cancelar",
                "cliente não quis o produto",
                "nf devolvida",
                "nf cancelada",
                "nf recusada",
                "nf recusada. cliente solicitou frete",
                "inutilizada"
            ])
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

    return query.all()

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