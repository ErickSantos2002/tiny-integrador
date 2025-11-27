from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date, timedelta
from app.models.database import SessionLocal
from app.models.nota_servico import NotaServico as NotaServicoModel
from app.schemas.nota_servico import NotaServico
from fastapi.responses import JSONResponse
from app.services.nfse_recife import NFSeRecifeService
from app.core.config import settings
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


@router.post("/importar")
def importar_nfse_recife(
    data_inicial: Optional[date] = Query(None, description="Data inicial (padrão: ontem)"),
    data_final: Optional[date] = Query(None, description="Data final (padrão: hoje)"),
    db: Session = Depends(get_db)
):
    """
    Importa NFSe da Prefeitura do Recife para o banco de dados

    Se não informar datas, busca NFSe de ontem até hoje.
    """
    try:
        # Define período padrão (ontem até hoje)
        if not data_inicial:
            data_inicial = date.today() - timedelta(days=1)
        if not data_final:
            data_final = date.today()

        # Inicializa serviço NFSe
        cert_path, key_path = settings.get_cert_paths()
        nfse_service = NFSeRecifeService(
            cert_path=cert_path,
            key_path=key_path,
            cnpj=settings.NFSE_CNPJ,
            inscricao_municipal=settings.NFSE_INSCRICAO_MUNICIPAL
        )

        # Consulta NFSe na Prefeitura
        print(f"Consultando NFSe de {data_inicial} até {data_final}...")
        notas_encontradas = nfse_service.consultar_nfse(data_inicial, data_final)

        if not notas_encontradas:
            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "message": "Nenhuma NFSe encontrada no período",
                    "periodo": {
                        "data_inicial": str(data_inicial),
                        "data_final": str(data_final)
                    },
                    "total_encontradas": 0,
                    "total_importadas": 0,
                    "total_atualizadas": 0
                }
            )

        # Processa cada nota
        importadas = 0
        atualizadas = 0
        erros = []

        for nota_data in notas_encontradas:
            try:
                # Verifica se nota já existe (busca por número)
                nota_existente = db.query(NotaServicoModel).filter(
                    NotaServicoModel.numero_nfse == nota_data['numero_nfse']
                ).first()

                if nota_existente:
                    # Atualiza nota existente
                    for key, value in nota_data.items():
                        if hasattr(nota_existente, key):
                            setattr(nota_existente, key, value)
                    atualizadas += 1
                else:
                    # Cria nova nota
                    nova_nota = NotaServicoModel(**nota_data)
                    db.add(nova_nota)
                    importadas += 1

            except Exception as e:
                erros.append({
                    "nfse": nota_data.get('numero_nfse'),
                    "erro": str(e)
                })
                print(f"Erro ao processar NFSe {nota_data.get('numero_nfse')}: {e}")
                traceback.print_exc()

        # Commit das alterações
        db.commit()

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": f"Importação concluída com sucesso",
                "periodo": {
                    "data_inicial": str(data_inicial),
                    "data_final": str(data_final)
                },
                "total_encontradas": len(notas_encontradas),
                "total_importadas": importadas,
                "total_atualizadas": atualizadas,
                "erros": erros if erros else None
            }
        )

    except Exception as e:
        print("ERRO NA IMPORTAÇÃO:")
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "erro": str(e),
                "message": "Erro ao importar NFSe"
            }
        )