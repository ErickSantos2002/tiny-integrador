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

E "em aberto" tem que ser perguntado aos **dois lados**, não só à origem:

* o que o Tiny diz estar em aberto pega a conta que o banco nunca viu (eram 194 contas a
  receber, R$ 1.105.358,23, ausentes do banco);
* o que o **banco** diz estar em aberto pega o caso oposto, que é o mais comum: a conta
  foi paga no Tiny e por isso *sumiu* da lista de abertas de lá. Perguntando só à origem,
  aquelas 223 contas a pagar (R$ 955.296,09) ficariam abertas para sempre — o que ficou
  claro na primeira execução real, em 2026-09-04, quando a reconferência voltou vazia.

E há um terceiro caso, que não é pagamento: a conta **deixou de existir** na origem. O
financeiro confirmou em 2026-09-05 que conta atrasada é excluída no Tiny e reemitida com
id novo. A API responde `codigo_erro 32` ("não localizada") e a linha aqui ficaria em
aberto para sempre. Isso vira `excluida_na_origem_em` na tabela — não erro, não `DELETE`:
a linha é a prova de que o atraso existiu, e a silver é quem filtra.

Enquanto isso era contado como erro, o job terminava `exit 1` **todo dia** — 226 contas a
pagar e 41 a receber em 2026-09-05. O estrago não era o código de saída feio: era o alarme
queimado, porque uma falha nova ficava indistinguível do barulho de sempre.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta

from app.core.config import settings
from app.models.database import SessionLocal
from app.services.execucao import registrar_execucao
from app.services.tiny_api import (ESPERA_PADRAO, TinyAPI, TinyAPIError,
                                   TinyNaoLocalizado, TinySemRegistros)
from app.services.tiny_contas import CONFIG, marcar_excluida_na_origem, salvar_conta

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


def ids_em_aberto_no_banco(db, tipo: str) -> list[str]:
    """O que o banco ainda considera não quitado.

    É a metade da reconferência que a origem não consegue dar: conta paga sai da lista de
    abertas do Tiny, então perguntar só a ele deixa o banco desatualizado para sempre.
    """
    modelo = CONFIG[tipo]["modelo"]
    linhas = (db.query(modelo.id_tiny)
              .filter(modelo.situacao.in_(("aberto", "parcial")))
              # Conta que a origem já negou não volta a existir: perguntar de novo só
              # gasta chamada. Eram 267 por dia — a maior parte dos 52 min do job.
              .filter(modelo.excluida_na_origem_em.is_(None))
              .all())
    return [str(linha[0]) for linha in linhas if linha[0] is not None]


def processar(api: TinyAPI, db, tipo: str, args) -> tuple[dict, int]:
    inicio = args.desde or (date.today() - timedelta(days=args.dias))
    fim = args.ate or date.today()

    ids: list[str] = []
    vistos: set[str] = set()
    for origem, gerador in (
        ("emitidas no período", api.pesquisar_ids_de_contas(tipo, inicio, fim)),
        ("em aberto no Tiny",
         iter(()) if args.sem_reconferir else api.pesquisar_ids_de_contas_em_aberto(tipo)),
        ("em aberto no banco",
         iter(()) if args.sem_reconferir else iter(ids_em_aberto_no_banco(db, tipo))),
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
        except TinyNaoLocalizado:
            # A conta sumiu da origem — o financeiro exclui a vencida e reemite com id
            # novo. Fato conhecido, não falha: marcar e seguir, sem sujar o exit code.
            resultado = marcar_excluida_na_origem(db, tipo, id_tiny, dry_run=args.dry_run)
            chave = {None: "sumida (não estava no banco)",
                     "ja_marcada": "sumida (já marcada)"}.get(resultado, "excluída na origem")
            contagem[chave] = contagem.get(chave, 0) + 1
            if resultado in ("marcada", "marcaria"):
                logger.info("  conta %-10s %s", id_tiny, chave)
            continue
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

    # O registro em `operacao.execucoes_job` é o que faz a falha chegar até alguém: o
    # código de saída sozinho morre no journal da VPS. Ver migration 005.
    with registrar_execucao("extrair_contas",
                            " ".join(argv if argv is not None else sys.argv[1:])) as registro:
        codigo = _carregar(args, registro)
        registro.falhou = codigo != 0
        return codigo


def _carregar(args, registro) -> int:
    api = TinyAPI(settings.TINY_TOKEN, espera=args.espera)
    tipos = ["pagar", "receber"] if args.tipo == "ambos" else [args.tipo]
    total_erros = 0
    tudo: dict[str, int] = {}
    db = SessionLocal()
    try:
        for tipo in tipos:
            logger.info("== Contas a %s%s ==", tipo, "  (DRY-RUN)" if args.dry_run else "")
            contagem, erros = processar(api, db, tipo, args)
            total_erros += erros
            # as duas contas viram um resumo só, prefixado, senão "criada" de pagar e de
            # receber se somariam e o histórico perderia de qual metade veio o volume
            for acao, quantas in contagem.items():
                tudo[f"{tipo}: {acao}"] = quantas
            for acao, quantas in sorted(contagem.items()):
                logger.info("   %-20s %d", acao, quantas)
            if erros:
                logger.warning("   %-20s %d", "erros", erros)
    finally:
        db.close()
    registro.contagens = tudo
    registro.erros = total_erros
    return 1 if total_erros else 0


if __name__ == "__main__":
    raise SystemExit(main())
