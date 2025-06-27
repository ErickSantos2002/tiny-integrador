from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.endpoints.nota_fiscal import router as nota_fiscal_router
from app.api.endpoints.cliente import router as cliente_router
from app.api.endpoints.item_nota import router as item_nota_router
from app.api.endpoints.endereco_entrega import router as endereco_entrega_router
from app.api.endpoints.forma_envio import router as forma_envio_router
from app.api.endpoints.marcador import router as marcador_router

app = FastAPI(
    title="Tiny Integrador API",
    description="API para visualização de dados das notas fiscais do Tiny ERP",
    version="1.0.0"
)

# CORS (se acessar por frontend externo)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ajuste em produção
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.api import endpoints

# Registrar endpoints
app.include_router(endpoints.nota_fiscal, prefix="/notas", tags=["Notas Fiscais"])
app.include_router(endpoints.cliente, prefix="/clientes", tags=["Clientes"])
app.include_router(endpoints.item_nota, prefix="/itens", tags=["Itens da Nota"])
app.include_router(endpoints.endereco_entrega, prefix="/enderecos", tags=["Endereços de Entrega"])
app.include_router(endpoints.forma_envio, prefix="/formas", tags=["Formas de Envio"])
app.include_router(endpoints.marcador, prefix="/marcadores", tags=["Marcadores"])

# Health check
@app.get("/")
def read_root():
    return {"status": "ok", "message": "Tiny Integrador API está no ar 🚀"}
