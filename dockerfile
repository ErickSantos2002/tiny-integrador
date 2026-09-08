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
#
# ⚠️ SEM --access-logfile de propósito. Passá-lo faz o UvicornWorker ligar o access log
# DELE, que ignora o --access-logformat do gunicorn e registra a linha de requisição
# inteira — com query string. Várias rotas daqui recebem documento como parâmetro
# (/notas_servico/?cpf_cnpj_tomador=...), então isso jogaria CPF e CNPJ de clientes no log.
# Medido em 2026-09-08: o CNPJ apareceu no log na primeira tentativa.
# Quem registra acesso aqui é o middleware em app/main.py, que loga o caminho sem os
# parâmetros.
CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--forwarded-allow-ips=*"]
