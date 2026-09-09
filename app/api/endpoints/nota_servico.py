from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date, timedelta
from app.models.database import SessionLocal
from app.models.nota_servico import NotaServico as NotaServicoModel
from app.schemas.nota_servico import NotaServico
from fastapi.responses import JSONResponse
from app.services.nfse_recife_nacional import NFSeRecifeNacionalService
from app.core.config import settings
import traceback

router = APIRouter(prefix="/notas_servico", tags=["Notas de Serviço"])

# Campos que são curadoria NOSSA, não dado da origem: a importação nunca os
# sobrescreve numa atualização. Hoje só `cancelada`, que é marcada à mão porque o
# leiaute nacional entrega o cancelamento como Evento separado, ainda não tratado.
# Sem esta proteção, cada reimportação da nota devolvia a marcação para o padrão.
CAMPOS_DE_CURADORIA_LOCAL = {"cancelada"}

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

        # Processa cada nota
        importadas = 0
        atualizadas = 0
        erros = []

        for nota_data in notas_encontradas:
            try:
                # Identidade da nota = CHAVE DE ACESSO (50 dígitos), nunca o número.
                #
                # O número da NFS-e NÃO é único: em 18/06/2026 a emissão migrou para o
                # Emissor Nacional e a numeração REINICIOU (a série do Recife estava em
                # 5.723; a nacional recomeçou em 725). Casar por número fazia a nota nova
                # nº 749 encontrar a nota de 2019 nº 749 e sobrescrevê-la, em silêncio.
                # Impacto medido em 23/08/2026: ~280 notas de 2018-2021 já foram perdidas
                # dessa forma (faixa 725-1058), e outras 4.405 estavam na fila.
                # A chave de acesso (doc["ChaveAcesso"]) é única por documento fiscal.
                chave = nota_data.get('codigo_verificacao')
                if not chave:
                    # Sem chave não há identidade confiável. Não inserir às cegas nem
                    # cair de volta no número: pular e reportar.
                    erros.append({
                        "nfse": nota_data.get('numero_nfse'),
                        "erro": "NFS-e sem chave de acesso; ignorada para não arriscar "
                                "sobrescrever outra nota"
                    })
                    continue

                nota_existente = db.query(NotaServicoModel).filter(
                    NotaServicoModel.codigo_verificacao == chave
                ).first()

                if nota_existente:
                    # Atualiza nota existente, preservando os campos de curadoria nossa
                    for key, value in nota_data.items():
                        if key in CAMPOS_DE_CURADORIA_LOCAL:
                            continue
                        if hasattr(nota_existente, key):
                            setattr(nota_existente, key, value)
                    atualizadas += 1
                else:
                    # Cria nova nota. Os campos de curadoria começam no padrão do
                    # modelo (cancelada=False) e só mudam por ação nossa.
                    nova_nota = NotaServicoModel(**{
                        k: v for k, v in nota_data.items()
                        if k not in CAMPOS_DE_CURADORIA_LOCAL
                    })
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