#!/usr/bin/env bash
# Roda o dbt dentro do container do analytics, na VPS.
#
# Uso:  ./rodar-dbt.sh              # o job diario: dbt build, com retry
#       ./rodar-dbt.sh test         # so os testes, sem retry (uso interativo)
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

# Backoff entre tentativas, em segundos. Sao tres tentativas ao todo.
# Por que 2 e 8 minutos: o que o retry resolve e falha PASSAGEIRA — banco reiniciando,
# container subindo depois de um redeploy, rede oscilando. Isso passa em minutos. Erro de
# modelo nao passa: vai falhar as tres vezes, gastar dez minutos de madrugada e registrar
# falha, que e exatamente o desfecho certo. Nao vale complicar para distinguir os dois.
ESPERAS=(120 480)

achar_container() {
    docker ps --format '{{.Names}}' | grep -m1 "^${PREFIXO}" || true
}

CONTAINER="$(achar_container)"
if [ -z "$CONTAINER" ]; then
    echo "ERRO: nenhum container começando com '${PREFIXO}' está rodando." >&2
    exit 1
fi

# Chamada com argumentos = alguem operando na mao. Roda uma vez e devolve o resultado
# cru: quem esta olhando decide se tenta de novo.
if [ $# -gt 0 ]; then
    echo "== $(date -Is) | dbt $* em ${CONTAINER} =="
    exec docker exec "$CONTAINER" dbt "$@"
fi

# ---------------------------------------------------------------- o job diario
tentativa=1
total=$(( ${#ESPERAS[@]} + 1 ))

while :; do
    echo "== $(date -Is) | dbt build em ${CONTAINER} (tentativa ${tentativa}/${total}) =="

    # `codigo=$?` depois de um `if cmd; then ... fi` devolveria 0 mesmo com o comando
    # falhando — um `if` sem `else` termina com status 0. Por isso o codigo e capturado
    # no proprio comando, com o `||` protegendo do `set -e`.
    codigo=0
    docker exec "$CONTAINER" dbt build || codigo=$?

    if [ "$codigo" -eq 0 ]; then
        echo "== $(date -Is) | dbt build OK na tentativa ${tentativa} =="
        exit 0
    fi

    if [ "$tentativa" -gt "${#ESPERAS[@]}" ]; then
        echo "== $(date -Is) | dbt build FALHOU nas ${total} tentativas (codigo ${codigo}) ==" >&2
        echo "   O resultado ja esta em operacao.execucoes_job se o dbt chegou a rodar;" >&2
        echo "   se nem isso, o aviso vem do atraso: GET /operacao/avisos." >&2
        exit "$codigo"
    fi

    espera="${ESPERAS[$((tentativa - 1))]}"
    echo "   falhou (codigo ${codigo}); nova tentativa em ${espera}s" >&2
    sleep "$espera"

    # O container pode ter trocado de nome nesse meio tempo (redeploy durante a espera).
    novo="$(achar_container)"
    if [ -n "$novo" ]; then
        CONTAINER="$novo"
    fi

    tentativa=$(( tentativa + 1 ))
done
