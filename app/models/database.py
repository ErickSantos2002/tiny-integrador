from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# Cria a engine com a URL do banco de dados
engine = create_engine(settings.DATABASE_URL)

# Cria a classe base para os modelos
Base = declarative_base()

# SessionLocal será usada em todo o projeto para obter sessões do banco
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
