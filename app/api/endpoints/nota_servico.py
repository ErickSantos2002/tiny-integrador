from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date, timedelta
from app.models.database import SessionLocal
from app.models.nota_servico import NotaServico as NotaServicoModel
from app.schemas.nota_servico import NotaServico
from fastapi.responses import JSONResponse
from app.services.nfse_recife_nacional import NFSeRecifeNacionalService
from app.services.nfse_importacao import gravar_notas
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

# ⚠️ DEPRECADO em 2026-09-08 — substituído por `GET /faturamento/servicos`.
#
# Não é o conjunto que muda: os dois devolvem as mesmas 5.004 notas, conferido. O que muda
# é de onde vem o VALOR. Aqui `valor_dos_serviços` sai como TEXTO, do jeito que a origem
# grava — e a origem grava em duas convenções, `1.234,56` e `1234.56`. Cada consumidor
# precisava converter, e foi assim que uma cópia antiga da conversão sobreviveu dentro do
# `ServicosContext` do DataCoreHS, sem o teste de ponto-de-milhar: nela `"1.234"` viraria
# R$ 1,23. O substituto lê `gold.fato_servicos`, onde o valor já é `numeric`.
#
# Continua no ar pelo mesmo motivo do `/notas_fiscais/vendas/`: é rota pública, o
# DataCoreHS parou de chamá-la hoje, e o log de acesso só existe desde 08/09. O critério
# de remoção é o mesmo, e está escrito em `endpoints/nota_fiscal.py`.
@router.get("/", response_model=List[NotaServico], deprecated=True)
def listar_notas_servico(
    cpf_cnpj_tomador: Optional[str] = Query(None),
    cpf_cnpj_prestador: Optional[str] = Query(None),
    data_emissao: Optional[date] = Query(None),
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
    cidade_servico: Optional[str] = Query(None),
    uf_servico: Optional[str] = Query(None),
    incluir_canceladas: bool = Query(False, description="Incluir notas canceladas na listagem"),
    db: Session = Depends(get_db)
):
    try:
        query = db.query(NotaServicoModel)

        # Filtro padrão: apenas notas NÃO canceladas (a menos que explicitamente solicitado).
        # `is_not(True)` em vez de `!= True`: em SQL, `cancelada != TRUE` é NULL quando a
        # coluna é NULL, e a linha fica de fora — uma nota sumiria do relatório só por
        # estar com o campo em branco. `IS NOT TRUE` trata NULL como "não cancelada".
        if not incluir_canceladas:
            query = query.filter(NotaServicoModel.cancelada.is_not(True))

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

        # Inicializa serviço NFSe (agora via Ambiente de Dados Nacional / ADN)
        cert_path, key_path = settings.get_cert_paths()
        nfse_service = NFSeRecifeNacionalService(
            cert_path=cert_path,
            key_path=key_path,
            cnpj=settings.NFSE_CNPJ,
            inscricao_municipal=settings.NFSE_INSCRICAO_MUNICIPAL
        )

        # Consulta NFSe no ambiente nacional (ADN)
        print(f"Consultando NFSe (ADN nacional) de {data_inicial} até {data_final}...")
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

        # A gravação (casar pela chave de acesso, preservar a curadoria) mora em
        # `app/services/nfse_importacao.py`, compartilhada com o job diário
        # `app.jobs.importar_nfse` — uma regra só, dois caminhos de entrada.
        resultado = gravar_notas(db, notas_encontradas)

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
                "total_importadas": resultado.importadas,
                "total_atualizadas": resultado.atualizadas,
                "erros": resultado.erros if resultado.erros else None
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