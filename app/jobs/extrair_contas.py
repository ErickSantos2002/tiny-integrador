"""Carga de contas a pagar e a receber — os fluxos `Puxar_Contas_*` do n8n.

    python -m app.jobs.extrair_contas --dry-run           # as duas, mostrando o que faria
    python -m app.jobs.extrair_contas --tipo pagar
    python -m app.jobs.extrair_contas --desde 2018-01-01  # backfill
    python -m app.jobs.extrair_contas --sem-reconferir    # só a janela, sem as em aberto

A carga tem duas partes, e a segunda é a que o n8n não tinha:

1. **janela por emissão** (padrão 14 dias) — traz conta nova;
2. **reconferência do que está em aberto**, de qualquer data — é o que percebe que uma
   conta antiga foi paga. Sem isso o banco acumula passivo fantasma: em 2026-09-03 ele
   dizia 226 contas a pagar em aberto (R$ 962 mil) contra 3 no Tiny.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta

from app.core.config import settings
from app.models.database import SessionLocal
from app.services.tiny_api import ESPERA_PADRAO, TinyAPI, TinyAPIError, TinySemRegistros
from app.services.tiny_contas import salvar_conta

logger = logging.getLogger("extrair_contas")


def montar_argumentos(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Extrai contas a pagar/receber do Tiny.")
    p.add_argument("--tipo", choices=["pagar", "receber", "ambos"], default="ambos")
    janela = p.add_mutually_exclusive_group()
    janela.add_argument("--dias", type=int, default=14, help="dias para trás (padrão: 14)")
    janela.add_argument("--desde", type=date.fromisoformat, metavar="AAAA-MM-DD")
    p.add_argument("--ate", type=date.fromisoformat, metavar="AAAA-MM-DD")
    p.add_argument("--sem-reconferir", action="store_true",
                   help="não reconfere as contas em aberto (mais rápido, mas cego a pagamento)")
    p.add_argument("--dry-run", action="store_true", help="mostra o que faria, sem escrever")
    p.add_argument("--espera", type=float, default=ESPERA_PADRAO)
    p.add_argument("--limite", type=int, help="para depois de N contas (para testar)")
    return p.parse_args(argv)


def processar(api: TinyAPI, db, tipo: str, args) -> tuple[dict, int]:
    inicio = args.desde or (date.today() - timedelta(days=args.dias))
    fim = args.ate or date.today()

    ids: list[str] = []
    vistos: set[str] = set()
    for origem, gerador in (
        ("emitidas no período", api.pesquisar_ids_de_contas(tipo, inicio, fim)),
        ("em aberto (qualquer data)",
         iter(()) if args.sem_reconferir else api.pesquisar_ids_de_contas_em_aberto(tipo)),
    ):
        try:
            novos = [i for i in gerador if i not in vistos]
        except TinyAPIError as erro:
            logger.error("  falha na pesquisa (%s): %s", origem, erro)
            return {}, 1
        vistos.update(novos)
        ids.extend(novos)
        logger.info("   %-28s %d", origem + ":", len(novos))

    if args.limite:
        ids = ids[:args.limite]

    contagem: dict[str, int] = {}
    erros = 0
    for i, id_tiny in enumerate(ids, 1):
        try:
            conta = api.obter_conta(tipo, id_tiny)
            relato = salvar_conta(db, tipo, conta, dry_run=args.dry_run)
        except (TinyAPIError, TinySemRegistros, ValueError) as erro:
            logger.warning("  ! conta %s: %s", id_tiny, erro)
            erros += 1
            continue
        except Exception as erro:
            db.rollback()
            logger.exception("  ! conta %s falhou ao gravar: %s", id_tiny, erro)
            erros += 1
            continue

        contagem[relato["acao"]] = contagem.get(relato["acao"], 0) + 1
        if relato["acao"] not in ("inalterada",):
            campos = ", ".join(sorted(relato["mudancas"])) if relato["mudancas"] else ""
            logger.info("  conta %-10s %-12s %s %s", relato["id_tiny"], relato["acao"],
                        relato["situacao"] or "", ("| " + campos) if campos else "")
        if i % 100 == 0:
            logger.info("  [%d/%d] %s", i, len(ids), contagem)
    return contagem, erros


def main(argv=None) -> int:
    args = montar_argumentos(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s",
                        datefmt="%H:%M:%S", stream=sys.stdout)

    if not settings.TINY_TOKEN:
        logger.error("TINY_TOKEN não configurado — defina no .env ou no ambiente.")
        return 2

    api = TinyAPI(settings.TINY_TOKEN, espera=args.espera)
    tipos = ["pagar", "receber"] if args.tipo == "ambos" else [args.tipo]
    total_erros = 0
    db = SessionLocal()
    try:
        for tipo in tipos:
            logger.info("== Contas a %s%s ==", tipo, "  (DRY-RUN)" if args.dry_run else "")
            contagem, erros = processar(api, db, tipo, args)
            total_erros += erros
            for acao, quantas in sorted(contagem.items()):
                logger.info("   %-20s %d", acao, quantas)
            if erros:
                logger.warning("   %-20s %d", "erros", erros)
    finally:
        db.close()
    return 1 if total_erros else 0


if __name__ == "__main__":
    raise SystemExit(main())
