#!/usr/bin/env bash
# Compila o código com a versão de Python que RODA EM PRODUÇÃO.
#
# POR QUE EXISTE: em 2026-09-09 a API não subiu depois de um deploy. O gunicorn
# morreu no boot com
#
#     File "/app/app/core/contas_agregado.py", line 364
#     SyntaxError: f-string expression part cannot include a backslash
#
# O código tinha passado por `import app.main` na máquina de desenvolvimento e
# pelas verificações contra o banco. Nada acusou: a `.venv` local é Python
# **3.14** e a imagem do EasyPanel é **3.11**. A PEP 701, que chegou no 3.12,
# passou a permitir backslash e aspas repetidas dentro da expressão de uma
# f-string — o que é código válido aqui é erro de SINTAXE lá.
#
# ⚠️ Erro de sintaxe derruba o processo INTEIRO no boot, não só a rota que o
# contém, e não aparece em teste nenhum: o módulo nem chega a importar.
#
# ⚠️ E não adianta usar `ast.parse(..., feature_version=(3, 11))`: o
# `feature_version` serve para sintaxe que foi ACRESCENTADA em versões novas,
# e não reverte uma restrição que foi REMOVIDA. Testado — ele aceita a f-string
# com backslash e não acusa nada. A única checagem que responde pela sintaxe de
# lá é compilar com um interpretador de lá.
#
# Uso:  ./scripts/verificar_sintaxe.sh
set -euo pipefail

VERSAO="3.11"
raiz="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"

checador='
import pathlib, sys
erros = []
for f in sorted(pathlib.Path("app").rglob("*.py")):
    try:
        compile(f.read_text(encoding="utf-8"), str(f), "exec")
    except SyntaxError as e:
        erros.append("  %s:%s  %s" % (f, e.lineno, e.msg))
if erros:
    print("ERRO: nao compila no Python " + sys.version.split()[0] + ":")
    print("\n".join(erros))
    print("\nIsto derrubaria o processo no boot, e nenhum teste acusaria.")
    sys.exit(1)
print("ok: o app/ compila na sintaxe do Python " + sys.version.split()[0] + ".")
'

if command -v "python$VERSAO" >/dev/null 2>&1; then
    cd "$raiz" && exec "python$VERSAO" -c "$checador"
fi

if command -v docker >/dev/null 2>&1; then
    # `:ro` e sem bytecode: o container não escreve nada no repositório.
    exec docker run --rm \
        -v "$raiz":/src:ro -w /src \
        -e PYTHONDONTWRITEBYTECODE=1 \
        "python:$VERSAO-slim" python -c "$checador"
fi

echo "AVISO: sem python$VERSAO e sem docker — a sintaxe de producao NAO foi conferida." >&2
echo "  Instale um dos dois:  sudo pacman -S python311" >&2
exit 2
