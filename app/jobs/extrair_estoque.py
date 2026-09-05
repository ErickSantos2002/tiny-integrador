"""Carga de produtos e saldo — o fluxo `Atualizar estoque` do n8n.

    python -m app.jobs.extrair_estoque --dry-run
    python -m app.jobs.extrair_estoque
    python -m app.jobs.extrair_estoque --sem-saldo   # só o cadastro, sem 1 chamada por produto

O saldo exige uma chamada por produto (a pesquisa não o traz), então a carga completa
leva ~15 min para os 300 produtos, com a espera de 3s entre chamadas.
"""

from __future__ import annotations

import argparse
import logging
import sys

from app.core.config import settings
from app.models.database import SessionLocal
from app.services.execucao import registrar_execucao
from app.services.tiny_api import ESPERA_PADRAO, TinyAPI, TinyAPIError, TinySemRegistros
from app.services.tiny_estoque import salvar_produto

logger = logging.getLogger("extrair_estoque")


def montar_argumentos(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Extrai produtos e saldo de estoque do Tiny.")
    p.add_argument("--sem-saldo", action="store_true",
                   help="não consulta o saldo (uma chamada a menos por produto)")
    p.add_argument("--dry-run", action="store_true", help="mostra o que faria, sem escrever")
    p.add_argument("--espera", type=float, default=ESPERA_PADRAO)
    p.add_argument("--limite", type=int, help="para depois de N produtos (para testar)")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = montar_argumentos(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s",
                        datefmt="%H:%M:%S", stream=sys.stdout)

    if not settings.TINY_TOKEN:
        logger.error("TINY_TOKEN não configurado — defina no .env ou no ambiente.")
        return 2

    # O registro em `operacao.execucoes_job` é o que faz a falha chegar até alguém: o
    # código de saída sozinho morre no journal da VPS. Ver migration 005.
    with registrar_execucao("extrair_estoque", " ".join(argv if argv is not None else sys.argv[1:])) as registro:
        codigo = _carregar(args, registro)
        registro.falhou = codigo != 0
        return codigo


def _carregar(args, registro) -> int:

    api = TinyAPI(settings.TINY_TOKEN, espera=args.espera)
    logger.info("== Estoque%s ==", "  (DRY-RUN, não escreve)" if args.dry_run else "")

    try:
        produtos = list(api.pesquisar_produtos())
    except TinyAPIError as erro:
        logger.error("falha na pesquisa de produtos: %s", erro)
        return 1
    logger.info("   produtos na origem: %d", len(produtos))

    if args.limite:
        produtos = produtos[:args.limite]

    contagem: dict[str, int] = {}
    erros = 0
    db = SessionLocal()
    try:
        for i, produto in enumerate(produtos, 1):
            try:
                saldo = None if args.sem_saldo else api.obter_saldo(produto["id"]).get("saldo")
                relato = salvar_produto(db, produto, saldo, dry_run=args.dry_run)
            except (TinyAPIError, TinySemRegistros) as erro:
                logger.warning("  ! produto %s: %s", produto.get("id"), erro)
                erros += 1
                continue
            except Exception as erro:
                db.rollback()
                logger.exception("  ! produto %s falhou ao gravar: %s", produto.get("id"), erro)
                erros += 1
                continue

            contagem[relato["acao"]] = contagem.get(relato["acao"], 0) + 1
            if relato["acao"] not in ("inalterado",):
                campos = ", ".join(sorted(relato["mudancas"])) if relato["mudancas"] else ""
                logger.info("  %-8s %-10s %-38s %s", relato["codigo"] or "?", relato["acao"],
                            (relato["nome"] or "")[:38], ("| " + campos) if campos else "")
            if i % 50 == 0:
                logger.info("  [%d/%d] %s", i, len(produtos), contagem)
    finally:
        db.close()

    registro.contagens = dict(contagem)
    registro.erros = erros

    logger.info("== Resumo ==")
    for acao, quantas in sorted(contagem.items()):
        logger.info("   %-20s %d", acao, quantas)
    if erros:
        logger.warning("   %-20s %d", "erros", erros)
    return 1 if erros and not contagem else 0


if __name__ == "__main__":
    raise SystemExit(main())
