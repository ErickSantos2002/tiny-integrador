# Equivalente do env.fish para bash/zsh.  Uso:  source env.sh
raiz="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
. "$raiz/.venv/bin/activate"
DBT_PG_PASSWORD="$(grep -m1 ':datacore-banco:dbt:' ~/.pgpass | cut -d: -f5)"
export DBT_PG_PASSWORD
[ -z "$DBT_PG_PASSWORD" ] && echo "AVISO: senha do usuario dbt nao encontrada em ~/.pgpass"
