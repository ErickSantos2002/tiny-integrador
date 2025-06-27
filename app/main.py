from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.endpoints import (
    nota_fiscal,
    cliente,
    item_nota,
    endereco_entrega,
    forma_envio,
    marcador
)

app = FastAPI(
    title="Tiny Integrador API",
    description="API para visualização de dados das notas fiscais do Tiny ERP",
    version="1.0.0"
)

# (Opcional) Configurar CORS se for acessar via frontend externo
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ajuste para domínios específicos em produção
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Incluir routers/endpoints
app.include_router(nota_fiscal.router)
app.include_router(cliente.router)
app.include_router(item_nota.router)
app.include_router(endereco_entrega.router)
app.include_router(forma_envio.router)
app.include_router(marcador.router)

# Health check básico
@app.get("/")
def read_root():
    return {"status": "ok", "message": "Tiny Integrador API está no ar 🚀"}
