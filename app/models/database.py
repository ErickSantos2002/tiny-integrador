from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

# Cria a engine com a URL do banco de dados
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,  # detecta conexões mortas
)

# Cria a classe base para os modelos
Base = declarative_base()

# SessionLocal será usada em todo o projeto para obter sessões do banco
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)
