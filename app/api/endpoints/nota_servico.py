from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date
from app.models.database import SessionLocal
from app.models.nota_servico import NotaServico as NotaServicoModel
from app.schemas.nota_servico import NotaServico
from fastapi.responses import JSONResponse
import traceback

router = APIRouter(prefix="/notas_servico", tags=["Notas de Serviço"])

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/", response_model=List[NotaServico])
def listar_notas_servico(
    cpf_cnpj_tomador: Optional[str] = Query(None),
    cpf_cnpj_prestador: Optional[str] = Query(None),
    data_emissao: Optional[date] = Query(None),
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
    cidade_servico: Optional[str] = Query(None),
    uf_servico: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    try:
        query = db.query(NotaServicoModel)

        if cpf_cnpj_tomador:
            query = query.filter(NotaServicoModel.cpf_cnpj_tomador.ilike(f"%{cpf_cnpj_tomador}%"))

        if cpf_cnpj_prestador:
            query = query.filter(NotaServicoModel.cpf_cnpj_prestador.ilike(f"%{cpf_cnpj_prestador}%"))

        if data_inicio and data_fim:
            query = query.filter(NotaServicoModel.data_emissao.between(data_inicio, data_fim))
        elif data_inicio:
            query = query.filter(NotaServicoModel.data_emissao >= data_inicio)
        elif data_fim:
            query = query.filter(NotaServicoModel.data_emissao <= data_fim)
        elif data_emissao:
            query = query.filter(NotaServicoModel.data_emissao == data_emissao)

        if cidade_servico:
            query = query.filter(NotaServicoModel.cidade_servico.ilike(f"%{cidade_servico}%"))

        if uf_servico:
            query = query.filter(NotaServicoModel.uf_servico == uf_servico)

        return query.all()

    except Exception as e:
        print("ERRO NA API:")
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"erro": str(e)}
        )