#!/usr/bin/env bash
# Barra valor absoluto em real dentro de analytics/.
#
# POR QUE EXISTE: este repositorio e publico, porque o codigo e da empresa e ela precisa
# continuar rodando sem depender de ninguem. A regra que torna isso seguro e uma so:
#
#     o repositorio carrega a REGUA, nao o RESULTADO.
#
# Proporcao pode ("74,1% do faturamento nao tem vendedor"); valor absoluto nao. Sem esta
# checagem a regra depende de alguem lembrar dela a cada commit — e regra assim nao
# sobrevive a um dia corrido. Os numeros medidos vivem no repositorio interno, na VPS.
#
# ⚠️ Isto pega dinheiro, nao pega TUDO. Nome de cliente, CNPJ e chave de acesso de NF-e
# tambem nao entram aqui, e disso nao existe deteccao automatica confiavel — ao escrever
# um comentario, cite a nota pelo numero e pela data, nunca pela parte que a identifica.
#
# Uso:  ./scripts/verificar_sem_valores.sh
set -euo pipefail

raiz="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"

# Toleradas: R$ 0,01 (tolerancia de arredondamento do rateio) e R$ 0.
achados="$(grep -rnE 'R\$ ?[0-9]' "$raiz" \
    --exclude-dir=target --exclude-dir=logs --exclude-dir=dbt_packages \
    --exclude-dir=.venv --exclude-dir=.git \
    | grep -vE 'R\$ ?0,01|R\$ 0 ' || true)"

if [ -n "$achados" ]; then
    echo "ERRO: valor absoluto em real no repositorio publico. Troque por proporcao." >&2
    echo "$achados" >&2
    exit 1
fi

echo "ok: nenhum valor absoluto em real."
