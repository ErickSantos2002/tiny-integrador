#!/usr/bin/env bash
# Roda o dbt dentro do container do analytics, na VPS.
#
# Uso:  ./rodar-dbt.sh              # o job diario: dbt build
#       ./rodar-dbt.sh test         # so os testes
#       ./rodar-dbt.sh run --select vendas+
#
# Por que resolver o container pelo PREFIXO do nome: o EasyPanel/Swarm troca o sufixo a
# cada redeploy (erick_datacore-dbt.1.<hash>), entao nome fixo quebra na primeira
# publicacao. Mesmo cuidado que o rodar-job.sh ja toma.
#
# ⚠️ POR QUE E SO `dbt build`, sem um `dbt snapshot` antes:
# os snapshots (scd_cliente, scd_produto) leem `ref('dim_cliente')` e `ref('dim_produto')`,
# que sao dimensoes do gold — nao a origem. Quem le o gold tem que rodar DEPOIS dele, e o
# `dbt build` ja poe cada um na posicao certa pelo DAG. Rodar `dbt snapshot` antes
# fotografaria a dimensao de ONTEM e deixaria o historico permanentemente um dia atrasado.
set -euo pipefail

PREFIXO="${CONTAINER_PREFIXO:-erick_datacore-dbt}"

CONTAINER="$(docker ps --format '{{.Names}}' | grep -m1 "^${PREFIXO}" || true)"
if [ -z "$CONTAINER" ]; then
    echo "ERRO: nenhum container começando com '${PREFIXO}' está rodando." >&2
    exit 1
fi

if [ $# -eq 0 ]; then
    set -- build
fi

echo "== $(date -Is) | dbt $* em ${CONTAINER} =="
docker exec "$CONTAINER" dbt "$@"
