# Equivalente do env.fish para bash/zsh.  Uso:  source env.sh
raiz="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
. "$raiz/.venv/bin/activate"
DBT_PG_PASSWORD="$(grep -m1 ':datacore-banco:dbt:' ~/.pgpass | cut -d: -f5)"
export DBT_PG_PASSWORD
# if/fi, nao "[ ... ] && echo": com && a linha devolve 1 quando a senha EXISTE,
# e como e a ultima linha do arquivo o `source` inteiro sai 1. Ai
# `source ./env.sh && dbt build` nunca roda o dbt, sem imprimir nada.
if [ -z "$DBT_PG_PASSWORD" ]; then
    echo "AVISO: senha do usuario dbt nao encontrada em ~/.pgpass"
fi
