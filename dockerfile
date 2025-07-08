# Imagem base
FROM python:3.11-slim

# Diretório de trabalho dentro do container
WORKDIR /app

# Copia a pasta app/ corretamente para dentro do container
COPY app/ app/

# Copia o requirements.txt e instala dependências
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Expor a porta padrão
EXPOSE 8000

# Comando para rodar a aplicação FastAPI
CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--forwarded-allow-ips=*"]