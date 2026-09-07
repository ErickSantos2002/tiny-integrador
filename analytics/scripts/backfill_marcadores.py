#!/usr/bin/env python3
"""Reconcilia tiny.marcadores com a origem (API do Tiny).

Contexto: o fluxo do n8n grava no máximo UMA linha de marcador por nota e, quando a
nota tem dois ou mais, grava tudo NULL (lê `marcadores.marcador.descricao` como se
fosse objeto único, sem dividir a lista). Além disso, o ramo de atualização só roda
quando um dos 31 campos da nota muda — e marcador não está entre eles, então marcador
posto depois da carga inicial nunca entra. Resultado medido em 2026-09-01: 7.709 de
8.156 linhas (94,5%) com descricao NULL.

Este script NÃO conserta o n8n. Ele mede e (com --aplicar) corrige o histórico.

Roda na VPS, nunca na máquina de casa: a resposta da API traz PII (cliente, CPF,
endereço) e a Regra 6 do projeto diz que PII não sai do servidor. Aqui só marcador é
guardado; o resto da resposta é descartado na memória.

Uso:
    python3 backfill_marcadores.py                 # dry-run: só relata, não escreve
    python3 backfill_marcadores.py --aplicar       # escreve no banco
    python3 backfill_marcadores.py --limite 50     # amostra, para testar

Variáveis de ambiente obrigatórias:
    TINY_TOKEN   token da API do Tiny
    PGPASSWORD   senha do usuário do Postgres
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

import psycopg
import requests

API_URL = "https://api.tiny.com.br/api2/nota.fiscal.obter.php"

# Espera entre chamadas. O n8n usa 3s e nunca foi bloqueado — mantido por prudência,
# não por medição. Se um dia o limite real for conhecido, baixar aqui.
ESPERA_PADRAO = 3.0

# A régua de faturamento de hoje, copiada de app/core/faturamento.py do tiny-integrador.
# Existe aqui só para MEDIR o impacto da correção — não é a definição nova (essa vai
# nascer na silver, Fase 4). Se a de lá mudar, esta fica velha: é cópia, e cópia diverge.
MARCADORES_RUINS = {
    "cancelar",
    "cliente não quis o produto",
    "nf devolvida",
    "nf cancelada",
    "nf recusada",
    "nf recusada. cliente solicitou frete",
    "inutilizada",
}
CFOPS_VENDA = ("5102", "6102", "5108", "6108")
SITUACAO_EMITIDA = "Emitida DANFE"


def e_venda_pela_regua(natureza: str | None, situacao: str | None, marcadores: set[str]) -> bool:
    """Reproduz o filtro do endpoint /notas_fiscais/vendas/."""
    if situacao != SITUACAO_EMITIDA:
        return False
    nat = natureza or ""
    if not any(c in nat for c in CFOPS_VENDA):
        return False
    return not (marcadores & MARCADORES_RUINS)


def buscar_notas(conn, limite: int | None):
    """Notas do banco com os marcadores que hoje estão gravados."""
    sql = """
        SELECT nf.id, nf.id_tiny, nf.numero, nf.data_emissao, nf.valor_nota,
               nf.natureza_operacao, nf.descricao_situacao,
               coalesce(
                 array_agg(m.descricao) FILTER (WHERE btrim(coalesce(m.descricao,'')) <> ''),
                 '{}'
               ) AS marcadores_banco
        FROM tiny.notas_fiscais nf
        LEFT JOIN tiny.marcadores m ON m.id_nota = nf.id
        WHERE nf.id_tiny IS NOT NULL AND btrim(nf.id_tiny) <> ''
        GROUP BY nf.id
        ORDER BY nf.data_emissao DESC NULLS LAST
    """
    if limite:
        sql += f" LIMIT {int(limite)}"
    with conn.cursor() as cur:
        cur.execute(sql)
        colunas = [d.name for d in cur.description]
        return [dict(zip(colunas, linha)) for linha in cur.fetchall()]


def marcadores_da_api(sessao: requests.Session, token: str, id_tiny: str) -> list[dict] | None:
    """Devolve [{id, descricao, cor}] ou None se a chamada falhou.

    Com formato=json a API sempre devolve `marcadores` como lista — inclusive vazia.
    A ambiguidade objeto-vs-array que quebra o n8n só existe no XML. Verificado em
    2026-09-01 nas NF 005725 (2 marcadores), 008630 e 008651 (nenhum).
    """
    try:
        r = sessao.get(
            API_URL,
            params={"token": token, "id": id_tiny, "formato": "json"},
            timeout=30,
        )
        r.raise_for_status()
        corpo = r.json()
    except (requests.RequestException, ValueError) as erro:
        print(f"  ! falha na API para id_tiny={id_tiny}: {erro}", file=sys.stderr)
        return None

    retorno = corpo.get("retorno", {})
    if retorno.get("status") != "OK":
        print(f"  ! retorno não-OK para id_tiny={id_tiny}: {retorno.get('status')}", file=sys.stderr)
        return None

    nota = retorno.get("nota_fiscal", {})
    saida = []
    for item in nota.get("marcadores", []) or []:
        m = item.get("marcador", item)
        if not isinstance(m, dict):
            continue
        desc = (m.get("descricao") or "").strip()
        if desc:
            saida.append({"id": m.get("id"), "descricao": desc, "cor": m.get("cor")})
    return saida


def aplicar_no_banco(conn, id_nota: int, marcadores: list[dict]) -> None:
    """Sincroniza: apaga o que existe e grava o estado atual da origem.

    O Tiny é a fonte da verdade — marcador removido lá deixa de valer aqui. O histórico
    de 'já esteve marcada' não se perde: quem preserva isso é o snapshot do dbt
    (Fase 5.4), não a tabela bronze.
    """
    with conn.cursor() as cur:
        cur.execute("DELETE FROM tiny.marcadores WHERE id_nota = %s", (id_nota,))
        for m in marcadores:
            cur.execute(
                "INSERT INTO tiny.marcadores (id_nota, id_marcador, descricao, cor) "
                "VALUES (%s, %s, %s, %s)",
                (id_nota, m["id"], m["descricao"], m["cor"]),
            )


def aplicar_do_relatorio(conn, sessao, token, caminho: str, reconferir: bool, espera: float) -> int:
    """Aplica o que o dry-run já descobriu, sem reler as 8 mil notas.

    A leitura completa leva ~7h; a aplicação toca só as notas que mudam, que são poucas.
    Por padrão cada uma dessas é reconferida na API antes de gravar — entre o dry-run e a
    aplicação alguém pode ter mexido no marcador, e o custo de conferir algumas centenas
    de notas é minutos, não horas.
    """
    if not os.path.exists(caminho):
        print(f"ERRO: relatório não encontrado: {caminho}", file=sys.stderr)
        return 2

    pendentes = []
    with open(caminho, encoding="utf-8") as f:
        for linha in f:
            try:
                reg = json.loads(linha)
            except json.JSONDecodeError:
                continue
            if reg.get("situacao") != "iguais":
                pendentes.append(reg)

    print(f"== Aplicação a partir do relatório ==")
    print(f"   arquivo: {caminho}")
    print(f"   notas que mudam: {len(pendentes)}")
    if reconferir:
        print(f"   reconferindo cada uma na API ({espera}s cada, ~{len(pendentes)*espera/60:.0f} min)\n")
    else:
        print("   SEM reconferência — gravando o que o relatório diz\n")

    gravadas = divergiu = erros = 0
    for i, reg in enumerate(pendentes, 1):
        marcadores = reg.get("origem_completa") or []

        if reconferir:
            atual = marcadores_da_api(sessao, token, reg["id_tiny"])
            time.sleep(espera)
            if atual is None:
                erros += 1
                continue
            if {m["descricao"] for m in atual} != set(reg.get("na_origem") or []):
                print(f"  ~ NF {reg['numero']}: mudou desde o dry-run — gravando o valor de agora")
                divergiu += 1
            marcadores = atual

        aplicar_no_banco(conn, reg["id_nota"], marcadores)
        conn.commit()
        gravadas += 1
        if i % 50 == 0:
            print(f"  [{i}/{len(pendentes)}] gravadas: {gravadas}")

    print(f"\n== Resumo da aplicação ==")
    print(f"   notas gravadas: {gravadas}")
    print(f"   mudaram desde o dry-run: {divergiu}")
    print(f"   erros de API: {erros}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--aplicar", action="store_true", help="escreve no banco durante a leitura (padrão é dry-run)")
    ap.add_argument("--aplicar-do-relatorio", metavar="ARQUIVO",
                    help="aplica o que um dry-run anterior descobriu, sem reler tudo (minutos, não horas)")
    ap.add_argument("--sem-reconferir", action="store_true",
                    help="com --aplicar-do-relatorio: grava sem reconsultar a API")
    ap.add_argument("--limite", type=int, help="processa só as N notas mais recentes")
    ap.add_argument("--espera", type=float, default=ESPERA_PADRAO, help=f"segundos entre chamadas (padrão {ESPERA_PADRAO})")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--porta", default="5555")
    ap.add_argument("--banco", default="datacore-banco")
    ap.add_argument("--usuario", default="dbt")
    ap.add_argument("--saida", default="/opt/datacore-jobs/relatorio-marcadores.jsonl")
    args = ap.parse_args()

    token = os.environ.get("TINY_TOKEN")
    if not token:
        print("ERRO: variável TINY_TOKEN não definida.", file=sys.stderr)
        return 2
    if not os.environ.get("PGPASSWORD"):
        print("ERRO: variável PGPASSWORD não definida.", file=sys.stderr)
        return 2

    escreve = args.aplicar or args.aplicar_do_relatorio
    modo = "APLICAR (escreve no banco)" if escreve else "DRY-RUN (não escreve nada)"
    print(f"== Reconciliação de marcadores — {modo} ==")
    print(f"   início: {datetime.now(timezone.utc).isoformat(timespec='seconds')}")

    conn = psycopg.connect(
        host=args.host, port=args.porta, dbname=args.banco,
        user=args.usuario, password=os.environ["PGPASSWORD"], autocommit=False,
    )
    if not escreve:
        conn.execute("SET default_transaction_read_only = on")

    if args.aplicar_do_relatorio:
        codigo = aplicar_do_relatorio(
            conn, requests.Session(), token, args.aplicar_do_relatorio,
            reconferir=not args.sem_reconferir, espera=args.espera,
        )
        conn.close()
        return codigo

    notas = buscar_notas(conn, args.limite)
    total = len(notas)
    print(f"   notas a conferir: {total}")
    print(f"   espera entre chamadas: {args.espera}s  (~{total * args.espera / 3600:.1f}h)\n")

    # Já processadas numa execução anterior — o arquivo de saída é o próprio checkpoint.
    ja_feitas = set()
    if os.path.exists(args.saida):
        with open(args.saida, encoding="utf-8") as f:
            for linha in f:
                try:
                    ja_feitas.add(json.loads(linha)["id_nota"])
                except (json.JSONDecodeError, KeyError):
                    pass
        if ja_feitas:
            print(f"   retomando: {len(ja_feitas)} notas já conferidas antes\n")

    sessao = requests.Session()
    contagem = {"iguais": 0, "ganha": 0, "perde": 0, "muda": 0, "erro": 0, "pulos": 0}
    impacto = {"sai_do_faturamento": [], "entra_no_faturamento": []}

    with open(args.saida, "a", encoding="utf-8") as saida:
        for i, nota in enumerate(notas, 1):
            if nota["id"] in ja_feitas:
                contagem["pulos"] += 1
                continue

            da_api = marcadores_da_api(sessao, token, nota["id_tiny"])
            if da_api is None:
                contagem["erro"] += 1
                time.sleep(args.espera)
                continue

            no_banco = set(nota["marcadores_banco"] or [])
            na_origem = {m["descricao"] for m in da_api}

            if no_banco == na_origem:
                situacao = "iguais"
            elif not no_banco and na_origem:
                situacao = "ganha"
            elif no_banco and not na_origem:
                situacao = "perde"
            else:
                situacao = "muda"
            contagem[situacao] += 1

            # Impacto na régua de faturamento: a nota entra ou sai?
            era = e_venda_pela_regua(nota["natureza_operacao"], nota["descricao_situacao"],
                                    {m.lower() for m in no_banco})
            fica = e_venda_pela_regua(nota["natureza_operacao"], nota["descricao_situacao"],
                                     {m.lower() for m in na_origem})
            mudou_faturamento = None
            if era and not fica:
                mudou_faturamento = "sai_do_faturamento"
                impacto["sai_do_faturamento"].append(float(nota["valor_nota"] or 0))
            elif fica and not era:
                mudou_faturamento = "entra_no_faturamento"
                impacto["entra_no_faturamento"].append(float(nota["valor_nota"] or 0))

            registro = {
                "id_nota": nota["id"], "id_tiny": nota["id_tiny"], "numero": nota["numero"],
                "data_emissao": str(nota["data_emissao"]), "valor_nota": float(nota["valor_nota"] or 0),
                "situacao": situacao, "no_banco": sorted(no_banco), "na_origem": sorted(na_origem),
                # guardado com id e cor para a aplicação não precisar chamar a API de novo
                "origem_completa": da_api,
                "impacto_faturamento": mudou_faturamento,
            }
            saida.write(json.dumps(registro, ensure_ascii=False) + "\n")
            saida.flush()

            if args.aplicar and situacao != "iguais":
                aplicar_no_banco(conn, nota["id"], da_api)
                conn.commit()

            if mudou_faturamento:
                print(f"  [{i}/{total}] NF {nota['numero']} R$ {float(nota['valor_nota'] or 0):,.2f} "
                      f"-> {mudou_faturamento}  banco={sorted(no_banco)} origem={sorted(na_origem)}")
            elif i % 100 == 0:
                print(f"  [{i}/{total}] ... {contagem}")

            time.sleep(args.espera)

    conn.close()

    print("\n== Resumo ==")
    for chave, valor in contagem.items():
        print(f"   {chave:8s}: {valor}")
    sai = sum(impacto["sai_do_faturamento"])
    entra = sum(impacto["entra_no_faturamento"])
    print(f"\n   notas que SAEM do faturamento: {len(impacto['sai_do_faturamento'])} "
          f"— R$ {sai:,.2f}")
    print(f"   notas que ENTRAM no faturamento: {len(impacto['entra_no_faturamento'])} "
          f"— R$ {entra:,.2f}")
    print(f"   efeito líquido no faturamento: R$ {entra - sai:,.2f}")
    print(f"\n   detalhe nota a nota em: {args.saida}")
    if not args.aplicar:
        print("\n   (dry-run — nada foi escrito no banco)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
