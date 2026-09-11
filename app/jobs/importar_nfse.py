"""Importação diária das NFS-e emitidas, do Ambiente de Dados Nacional (ADN).

    python -m app.jobs.importar_nfse --dry-run
    python -m app.jobs.importar_nfse                      # a rotina: últimos 30 dias
    python -m app.jobs.importar_nfse --desde 2026-06-18   # desde o Emissor Nacional

POR QUE EXISTE: até 2026-09-11 a única porta de entrada das NFS-e era o endpoint
`POST /notas_servico/importar`, e ninguém o chamava — nem timer, nem tela. Medido no dia:
31 notas de 04/09 a 10/09 fora do banco, e o gold de serviços parado no mesmo número
desde 08/09 sem que nada acusasse. Era a única ingestão do DataCore sem agendamento.

POR QUE 30 DIAS E NÃO 1: o ADN só se consulta por NSU, não por data. O serviço varre a
distribuição inteira e filtra a data depois, então a janela larga custa as mesmas chamadas
que a estreita. O que ela compra é tolerância: nota que chega atrasada ao ADN, ou um dia
em que o timer não rodou, entram na passagem seguinte. Reimportar é seguro — a nota casa
pela chave de acesso e a curadoria (`cancelada`) nunca é sobrescrita.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta

from app.core.config import settings
from app.models.database import SessionLocal
from app.services.execucao import registrar_execucao
from app.services.nfse_importacao import gravar_notas
from app.services.nfse_recife_nacional import NFSeRecifeNacionalService

logger = logging.getLogger("importar_nfse")

JANELA_PADRAO_DIAS = 30


def montar_argumentos(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Importa do ADN as NFS-e emitidas pela empresa.")
    janela = p.add_mutually_exclusive_group()
    janela.add_argument("--dias", type=int, default=JANELA_PADRAO_DIAS,
                        help=f"quantos dias antes de --ate (padrão: {JANELA_PADRAO_DIAS})")
    janela.add_argument("--desde", type=date.fromisoformat, metavar="AAAA-MM-DD",
                        help="data inicial explícita, no lugar de --dias")
    p.add_argument("--ate", type=date.fromisoformat, metavar="AAAA-MM-DD",
                   help="data final (padrão: hoje)")
    p.add_argument("--dry-run", action="store_true", help="mostra o que faria, sem escrever")
    return p.parse_args(argv)


def periodo(args, hoje: date | None = None) -> tuple[date, date]:
    fim = args.ate or (hoje or date.today())
    # `is not None`, não truthiness: foi assim que `--limite 0` do extrator de notas
    # passou a significar "sem limite". Aqui `--dias 0` quer dizer "só o dia de --ate".
    inicio = args.desde if args.desde is not None else fim - timedelta(days=args.dias)
    return inicio, fim


def main(argv=None) -> int:
    args = montar_argumentos(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s",
                        datefmt="%H:%M:%S", stream=sys.stdout)

    inicio, fim = periodo(args)
    if inicio > fim:
        logger.error("período invertido: %s é depois de %s", inicio, fim)
        return 2

    if args.dry_run:
        # Dry-run NÃO entra em `operacao.execucoes_job`. Nos extratores do Tiny ele entra, e
        # em 2026-09-06 11 das 20 "execuções" registradas eram teste — o monitor precisou
        # aprender a filtrá-las. Aqui o conserto é na raiz: ensaio não é carga.
        return _importar(args, inicio, fim, registro=None)

    argumentos = " ".join(argv if argv is not None else sys.argv[1:])
    with registrar_execucao("importar_nfse", argumentos) as registro:
        codigo = _importar(args, inicio, fim, registro)
        registro.falhou = codigo != 0
        return codigo


def _importar(args, inicio: date, fim: date, registro) -> int:
    logger.info("== NFS-e emitidas de %s a %s%s ==", inicio.strftime("%d/%m/%Y"),
                fim.strftime("%d/%m/%Y"), "  (DRY-RUN, não escreve)" if args.dry_run else "")

    cert_path, key_path = settings.get_cert_paths()
    servico = NFSeRecifeNacionalService(
        cert_path=cert_path,
        key_path=key_path,
        cnpj=settings.NFSE_CNPJ,
        inscricao_municipal=settings.NFSE_INSCRICAO_MUNICIPAL,
    )

    try:
        notas = servico.consultar_nfse(inicio, fim)
    except Exception as erro:                                  # noqa: BLE001
        # O serviço já retentou cada página 4 vezes (o ADN dá 504 sob carga). Chegar aqui
        # é falha de verdade — e ele levanta em vez de devolver meia lista, então nada foi
        # gravado pela metade.
        logger.error("falha ao consultar o ADN: %s", erro)
        if registro is not None:
            registro.erros = 1
            registro.detalhe = f"ADN: {erro}"
        return 1
    logger.info("   notas no período: %d", len(notas))

    db = SessionLocal()
    try:
        resultado = gravar_notas(db, notas, dry_run=args.dry_run)
        if args.dry_run:
            db.rollback()
        else:
            db.commit()
    finally:
        db.close()

    for erro in resultado.erros:
        logger.warning("  ! NFS-e %s: %s", erro["nfse"], erro["erro"])

    if registro is not None:
        registro.contagens = {"no_periodo": len(notas), "criada": resultado.importadas,
                              "reconferida": resultado.atualizadas}
        registro.erros = len(resultado.erros)

    logger.info("== Resumo ==")
    logger.info("   %-20s %d", "criadas", resultado.importadas)
    logger.info("   %-20s %d", "reconferidas", resultado.atualizadas)
    if resultado.erros:
        logger.warning("   %-20s %d", "erros", len(resultado.erros))

    # Mesmo critério dos extratores: erro em algumas notas não reprova a carga que trouxe o
    # resto; erro sem nada gravado, sim.
    gravadas = resultado.importadas + resultado.atualizadas
    return 1 if resultado.erros and not gravadas else 0


if __name__ == "__main__":
    raise SystemExit(main())
