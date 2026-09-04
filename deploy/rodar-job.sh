#!/usr/bin/env bash
# Roda um job do extrator dentro do container da API, na VPS.
#
# Uso:  ./rodar-job.sh extrair_notas --dias 14
#
# Por que resolver o container pelo PREFIXO do nome: o EasyPanel/Swarm troca o sufixo do
# nome a cada redeploy (erick_datacore-api.1.<hash>), então um nome fixo quebra na
# primeira publicação. Mesmo cuidado que o backup do Postgres já toma.
set -euo pipefail

PREFIXO="${CONTAINER_PREFIXO:-erick_datacore-api}"
JOB="${1:?uso: rodar-job.sh <extrair_notas|extrair_contas|extrair_estoque> [argumentos]}"
shift

CONTAINER="$(docker ps --format '{{.Names}}' | grep -m1 "^${PREFIXO}" || true)"
if [ -z "$CONTAINER" ]; then
    echo "ERRO: nenhum container começando com '${PREFIXO}' está rodando." >&2
    exit 1
fi

echo "== $(date -Is) | ${JOB} em ${CONTAINER} =="
docker exec "$CONTAINER" python -m "app.jobs.${JOB}" "$@"
