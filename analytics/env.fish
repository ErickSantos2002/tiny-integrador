# Prepara o shell pra trabalhar no projeto.  Uso:  source env.fish
#
# Faz duas coisas: ativa o .venv e exporta a senha do usuario dbt.
# A senha e LIDA do ~/.pgpass — ela existe em um lugar so na maquina,
# e este arquivo (que vai pro Git) nao contem segredo nenhum.

set -l raiz (dirname (status --current-filename))
source $raiz/.venv/bin/activate.fish

set -gx DBT_PG_PASSWORD (grep -m1 ':datacore-banco:dbt:' ~/.pgpass | cut -d: -f5)

if test -z "$DBT_PG_PASSWORD"
    echo "⚠  senha do usuario dbt nao encontrada em ~/.pgpass — o dbt nao vai conectar"
else
    echo "✓ ambiente pronto (dbt "(dbt --version 2>/dev/null | grep -m1 installed | string trim)")"
end
