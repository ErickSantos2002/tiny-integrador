# Imagem do dbt do DataCore — analytics/ do tiny-integrador.
# No EasyPanel: servico proprio, Build Path /analytics/ (monorepo).
#
# Este container NAO e um servidor. O dbt roda, termina e sai. Mas o EasyPanel espera um
# servico de pe e reinicia o que morre, entao o container fica dormindo e o trabalho e
# disparado de fora, por `docker exec` a partir de um timer systemd — exatamente o padrao
# que os extratores do Tiny ja usam (deploy/rodar-job.sh).
FROM python:3.11-slim

WORKDIR /dbt

# git so serve para `dbt deps` (pacotes tipo dbt_utils, que vem de repositorio).
# Hoje nao ha nenhum, mas sem ele `dbt debug` acusa check falho e o dia que
# alguem adicionar um package a imagem quebra sem motivo aparente.
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# Versao fixada de proposito: `dbt build` tem que produzir o mesmo resultado daqui a um ano.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . /dbt/

# O profiles versionado se chama profiles.docker.yml porque o .gitignore bloqueia
# "profiles.yml" — regra que existe para nenhuma senha entrar no repositorio por descuido.
# Este arquivo nao guarda segredo: le tudo de variavel de ambiente.
RUN cp /dbt/docker/profiles.docker.yml /dbt/profiles.yml
ENV DBT_PROFILES_DIR=/dbt

CMD ["sleep", "infinity"]
