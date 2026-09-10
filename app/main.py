import logging
import sys
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from app.api import endpoints
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware

app = FastAPI(
    title="Tiny Integrador API",
    description="API para visualização de dados das notas fiscais do Tiny ERP",
    version="1.0.0"
)

# CORS (se acessar por frontend externo)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://datacorehs.healthsafetytech.com",
        "http://localhost:5174"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------- log de acesso
#
# Antes disto a API não registrava requisição NENHUMA: no dia em que alguém dissesse "o
# dashboard está lento" ou "deu erro", não havia o que consultar. Descoberto em 2026-09-08,
# tentando confirmar se uma tela recém-migrada estava chamando o endpoint novo.
#
# ⚠️ POR QUE UM MIDDLEWARE, E NÃO `--access-logfile` NO GUNICORN:
# com o UvicornWorker, quem escreve o access log é o uvicorn, e ele IGNORA o
# `--access-logformat` do gunicorn — registra a linha de requisição inteira, com query
# string. Como várias rotas recebem documento como parâmetro
# (`/notas_servico/?cpf_cnpj_tomador=...`), aquilo colocava CPF e CNPJ de clientes no log.
# Medido: o CNPJ apareceu no log na primeira tentativa. Aqui só entra `request.url.path`,
# que é o caminho SEM os parâmetros.
#
# Para "qual endpoint" e "quanto demorou" — as duas perguntas que o log precisa responder —
# o caminho basta.
log_acesso = logging.getLogger("acesso")

# O handler é montado explicitamente porque um logger sem handler não emite INFO — o
# Python cai no `lastResort`, que só deixa passar WARNING para cima, e a linha de acesso
# sumiria em silêncio. Foi o que aconteceu na primeira versão disto.
# `propagate = False` para a linha não sair duplicada quando o gunicorn também configura
# o root logger.
if not log_acesso.handlers:
    _saida = logging.StreamHandler(sys.stdout)
    _saida.setFormatter(logging.Formatter("%(asctime)s [acesso] %(message)s"))
    log_acesso.addHandler(_saida)
    log_acesso.setLevel(logging.INFO)
    log_acesso.propagate = False


@app.middleware("http")
async def registrar_acesso(request: Request, call_next):
    inicio = time.perf_counter()
    resposta = await call_next(request)
    ms = (time.perf_counter() - inicio) * 1000

    # `request.url.path` e não `request.url`: o segundo traria a query string de volta.
    log_acesso.info(
        "%s %s %s %.0fms",
        request.method,
        request.url.path,
        resposta.status_code,
        ms,
    )
    return resposta


# Registrar endpoints
app.include_router(endpoints.nota_fiscal)
app.include_router(endpoints.nota_servico)  # <-- novo endpoint
app.include_router(endpoints.cliente)
app.include_router(endpoints.item_nota)
app.include_router(endpoints.endereco_entrega)
app.include_router(endpoints.forma_envio)
app.include_router(endpoints.marcador)
app.include_router(endpoints.configuracoes)
app.include_router(endpoints.estoque)
app.include_router(endpoints.contas_pagar)
app.include_router(endpoints.contas_receber)
app.include_router(endpoints.centro_custo)
# saúde da ingestão: o DataCoreHS mostra aqui quando uma carga deu errado
app.include_router(endpoints.operacao)
# Faturamento lido do gold — a regra unica, ja aplicada (Fase 9).
app.include_router(endpoints.faturamento)
# Os recortes agregados das quatro telas do Comercial, somados no banco (item 9.4).
app.include_router(endpoints.comercial)

# Health check
@app.get("/")
def read_root():
    return {"status": "ok", "message": "Tiny Integrador API está no ar 🚀"}
