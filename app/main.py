from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import endpoints

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
