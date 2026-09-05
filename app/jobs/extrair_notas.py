"""Carga de notas fiscais do Tiny — o que o fluxo `[DATACORE] Puxar_Notas` do n8n fazia.

Uso:

    python -m app.jobs.extrair_notas --dias 14 --dry-run   # mostra, não escreve
    python -m app.jobs.extrair_notas --dias 14             # a carga de rotina
    python -m app.jobs.extrair_notas --desde 2018-01-01    # backfill
    python -m app.jobs.extrair_notas --id 617079728        # uma nota específica

A janela padrão de 14 dias é a mesma do n8n, e não é folga à toa: nota é alterada depois
de emitida (cancelamento, marcador, mudança de situação), então a carga precisa reolhar
o passado recente, não só o que foi emitido hoje.

Idempotente: rodar duas vezes seguidas não muda nada na segunda.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta

from app.core.config import settings
from app.models.database import SessionLocal
from app.services.execucao import registrar_execucao
from app.services.tiny_api import TinyAPI, TinyAPIError, TinySemRegistros, ESPERA_PADRAO
from app.services.tiny_notas import salvar_nota

logger = logging.getLogger("extrair_notas")


def montar_argumentos(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Extrai notas fiscais do Tiny para o schema bronze.")
    janela = p.add_mutually_exclusive_group()
    janela.add_argument("--dias", type=int, default=14,
                        help="quantos dias para trás olhar (padrão: 14, igual ao n8n)")
    janela.add_argument("--desde", type=date.fromisoformat, metavar="AAAA-MM-DD",
                        help="data inicial explícita")
    janela.add_argument("--id", dest="ids", action="append", metavar="ID_TINY",
                        help="processa só esta nota (pode repetir)")
    p.add_argument("--ate", type=date.fromisoformat, metavar="AAAA-MM-DD",
                   help="data final (padrão: hoje)")
    p.add_argument("--dry-run", action="store_true",
                   help="mostra o que faria, sem escrever nada no banco")
    p.add_argument("--espera", type=float, default=ESPERA_PADRAO,
                   help=f"segundos entre chamadas à API (padrão: {ESPERA_PADRAO})")
    p.add_argument("--limite", type=int, help="para depois de N notas (para testar)")
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
    with registrar_execucao("extrair_notas", " ".join(argv if argv is not None else sys.argv[1:])) as registro:
        codigo = _carregar(args, registro)
        registro.falhou = codigo != 0
        return codigo


def _carregar(args, registro) -> int:

    api = TinyAPI(settings.TINY_TOKEN, espera=args.espera)

    if args.ids:
        ids = list(args.ids)
        logger.info("== Notas avulsas: %d ==", len(ids))
    else:
        inicio = args.desde or (date.today() - timedelta(days=args.dias))
        fim = args.ate or date.today()
        logger.info("== Carga de %s a %s%s ==", inicio.strftime("%d/%m/%Y"),
                    fim.strftime("%d/%m/%Y"), "  (DRY-RUN, não escreve)" if args.dry_run else "")
        try:
            ids = list(api.pesquisar_ids(inicio, fim))
        except TinyAPIError as erro:
            logger.error("falha na pesquisa: %s", erro)
            return 1
        logger.info("   notas no período: %d", len(ids))

    if args.limite:
        ids = ids[:args.limite]

    contagem: dict[str, int] = {}
    erros = 0
    db = SessionLocal()
    try:
        for i, id_tiny in enumerate(ids, 1):
            try:
                nf = api.obter_nota(id_tiny)
                relato = salvar_nota(db, nf, dry_run=args.dry_run)
            except (TinyAPIError, TinySemRegistros) as erro:
                logger.warning("  ! nota %s: %s", id_tiny, erro)
                erros += 1
                continue
            except Exception as erro:  # falha de banco numa nota não derruba o lote
                logger.exception("  ! nota %s falhou ao gravar: %s", id_tiny, erro)
                erros += 1
                continue

            contagem[relato["acao"]] = contagem.get(relato["acao"], 0) + 1
            if relato["acao"] != "inalterada":
                detalhe = []
                if relato["mudancas"]:
                    detalhe.append("campos: " + ", ".join(sorted(relato["mudancas"])))
                if relato["filhos"]:
                    detalhe.append("filhos: " + ", ".join(
                        f"{nome} {antes}->{depois}" for nome, (antes, depois) in relato["filhos"].items()))
                if relato["marcadores"]:
                    detalhe.append("marcadores: " + " + ".join(relato["marcadores"]))
                logger.info("  NF %-8s %s  %s", relato["numero"] or "?", relato["acao"],
                            " | ".join(detalhe))
            if i % 100 == 0:
                logger.info("  [%d/%d] %s", i, len(ids), contagem)
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
