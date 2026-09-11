"""Prova do job diário de NFS-e (`app.jobs.importar_nfse`).

O defeito que ele corrige, medido em 2026-09-11: a importação só existia como endpoint, e
ninguém o chamava — 31 notas de 04/09 a 10/09 fora do banco, sem aviso nenhum. Estes
testes cobrem o que o timer precisa garantir:

  * a carga grava, é idempotente e não desfaz a curadoria (`cancelada`);
  * ela aparece em `operacao.execucoes_job` — é o que faz a falha chegar a alguém;
  * falha do ADN vira `falha` registrada e código 1, sem nada gravado pela metade;
  * dry-run não escreve e NÃO se registra como carga.

A regra de identidade (casar pela chave de acesso) é provada em `testar_upsert_nfse.py`,
que exercita a mesma função de gravação pelo caminho do endpoint.

Roda contra um Postgres DESCARTÁVEL. Nunca aponte para produção.

    docker run -d --rm --name extrator-teste -e POSTGRES_PASSWORD=teste \
        -e POSTGRES_DB=testdb -p 55433:5432 postgres:17
    python testar_job_importar_nfse.py
    docker rm -f extrator-teste

O script recria os schemas `tiny` e `operacao` do zero (DROP SCHEMA CASCADE).
"""
import os
import sys
from datetime import date, timedelta

# Forçado de propósito: este script faz DROP SCHEMA, então nunca herda a
# DATABASE_URL do ambiente (que em dev/prod aponta para o banco de verdade).
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:teste@localhost:55433/testdb"
os.environ.setdefault("TINY_TOKEN", "token-de-teste")
os.environ["NFSE_CERT_PATH"] = "/dev/null"
os.environ["NFSE_KEY_PATH"] = "/dev/null"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from app.jobs import importar_nfse as job  # noqa: E402
from app.models.database import Base, SessionLocal, engine  # noqa: E402
from app.models.nota_servico import NotaServico  # noqa: E402
from app.services.execucao import ExecucaoJob  # noqa: E402

CHAVE_A = "26116062208857492000148000000000074926061510050294"
CHAVE_B = "26116062208857492000148000000000075026061510050295"
CHAVE_C = "26116062208857492000148000000000075126061510050296"

falhas = []


def checa(descricao, condicao, detalhe=""):
    marca = "ok  " if condicao else "FALHA"
    print(f"  [{marca}] {descricao}{(' -> ' + detalhe) if detalhe else ''}")
    if not condicao:
        falhas.append(descricao)


def prepara_banco():
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS tiny CASCADE"))
        conn.execute(text("DROP SCHEMA IF EXISTS operacao CASCADE"))
        conn.execute(text("CREATE SCHEMA tiny"))
        conn.execute(text("CREATE SCHEMA operacao"))
    Base.metadata.create_all(engine, tables=[NotaServico.__table__, ExecucaoJob.__table__])
    with engine.begin() as conn:
        # migrations/002 — o banco real tem este índice; sem ele o teste roda contra um
        # schema mais permissivo que a produção
        conn.execute(text(
            'CREATE UNIQUE INDEX servicos_chave_acesso_unique '
            'ON tiny.servicos ("código_de_verificação_nf") '
            "WHERE \"código_de_verificação_nf\" ~ '^[0-9]{50}$'"
        ))


def nota_adn(numero, chave, dia, tomador, valor):
    """Dicionário no mesmo formato que NFSeRecifeNacionalService.consultar_nfse devolve."""
    return {
        "numero_nfse": numero,
        "codigo_verificacao": chave,
        "data_emissao": dia,
        "razao_social_tomador": tomador,
        "valor_servico": valor,
        "cancelada": False,
    }


class ADNFalso:
    """Dublê do serviço do ADN: devolve `notas`, ou levanta se `falhar` estiver definido."""
    notas = []
    falhar = None
    chamadas = []

    def __init__(self, **kwargs):
        pass

    def consultar_nfse(self, data_inicial, data_final):
        ADNFalso.chamadas.append((data_inicial, data_final))
        if ADNFalso.falhar:
            raise Exception(ADNFalso.falhar)
        return list(ADNFalso.notas)


job.NFSeRecifeNacionalService = ADNFalso


def roda(*argv, notas=(), falhar=None):
    ADNFalso.notas = list(notas)
    ADNFalso.falhar = falhar
    ADNFalso.chamadas = []
    return job.main(list(argv))


def linhas():
    db = SessionLocal()
    try:
        return db.query(NotaServico).order_by(NotaServico.id).all()
    finally:
        db.close()


def execucoes():
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(text(
            "SELECT job, resultado, erros, contagens, detalhe FROM operacao.execucoes_job "
            "ORDER BY id"))]


A = nota_adn(749, CHAVE_A, date(2026, 9, 4), "CLIENTE A", "475.00")
B = nota_adn(750, CHAVE_B, date(2026, 9, 8), "CLIENTE B", "300.00")
C = nota_adn(751, CHAVE_C, date(2026, 9, 10), "CLIENTE C", "120.00")
SEM_CHAVE = nota_adn(900, None, date(2026, 9, 9), "SEM CHAVE", "100.00")


print("\n=== 1. A janela: 30 dias por padrão, e `--dias 0` não vira 'sem janela' ===")
hoje = date(2026, 9, 11)
checa("padrão = os 30 dias até hoje",
      job.periodo(job.montar_argumentos([]), hoje) == (date(2026, 8, 12), hoje))
checa("--desde/--ate são respeitados",
      job.periodo(job.montar_argumentos(["--desde", "2026-06-18", "--ate", "2026-09-11"]), hoje)
      == (date(2026, 6, 18), date(2026, 9, 11)))
checa("--dias 0 = só o dia de --ate",
      job.periodo(job.montar_argumentos(["--dias", "0", "--ate", "2026-09-10"]), hoje)
      == (date(2026, 9, 10), date(2026, 9, 10)))

prepara_banco()
codigo = roda("--desde", "2026-09-12", "--ate", "2026-09-11", notas=[A])
checa("período invertido sai 2", codigo == 2, f"código {codigo}")
checa("... sem consultar o ADN", ADNFalso.chamadas == [])
checa("... e sem registrar execução", execucoes() == [])

print("\n=== 2. A carga de rotina grava e se registra ===")
codigo = roda(notas=[A, B])
checa("sai 0", codigo == 0, f"código {codigo}")
checa("pediu ao ADN os 30 dias até hoje",
      ADNFalso.chamadas == [(date.today() - timedelta(days=30), date.today())],
      str(ADNFalso.chamadas))
checa("as 2 notas estão no banco", len(linhas()) == 2, f"{len(linhas())} linhas")
ex = execucoes()
checa("uma execução registrada como importar_nfse / sucesso",
      len(ex) == 1 and ex[0]["job"] == "importar_nfse" and ex[0]["resultado"] == "sucesso",
      str(ex))
checa("as contagens dizem o que aconteceu",
      ex and ex[-1]["contagens"] == {"no_periodo": 2, "criada": 2, "reconferida": 0},
      str(ex[-1]["contagens"] if ex else None))

print("\n=== 3. Rodar de novo não duplica e não desfaz a curadoria ===")
db = SessionLocal()
db.query(NotaServico).filter(NotaServico.codigo_verificacao == CHAVE_A).first().cancelada = True
db.commit()
db.close()
A_corrigida = dict(A, razao_social_tomador="CLIENTE A CORRIGIDO")
codigo = roda(notas=[A_corrigida, B])
todas = linhas()
checa("sai 0", codigo == 0, f"código {codigo}")
checa("continua com 2 linhas", len(todas) == 2, f"{len(todas)} linhas")
nota_a = [n for n in todas if n.codigo_verificacao == CHAVE_A][0]
checa("o dado da origem foi atualizado", nota_a.razao_social_tomador == "CLIENTE A CORRIGIDO")
checa("a marcação manual de cancelada sobreviveu", nota_a.cancelada is True,
      f"cancelada={nota_a.cancelada!r}")
checa("contou como reconferida, não criada",
      execucoes()[-1]["contagens"] == {"no_periodo": 2, "criada": 0, "reconferida": 2},
      str(execucoes()[-1]["contagens"]))

print("\n=== 4. Dry-run não escreve e não se registra como carga ===")
antes = len(execucoes())
codigo = roda("--dry-run", notas=[A, C])
checa("sai 0", codigo == 0, f"código {codigo}")
checa("a nota C não foi gravada", len(linhas()) == 2, f"{len(linhas())} linhas")
checa("nenhuma execução nova registrada", len(execucoes()) == antes,
      f"{antes} -> {len(execucoes())}")

# O dry-run tem duas proteções: `gravar_notas` não toca na sessão E o job dá rollback.
# Pelo job, uma esconde a falha da outra — então a primeira é provada sozinha, com COMMIT.
from app.services.nfse_importacao import gravar_notas  # noqa: E402
db = SessionLocal()
r = gravar_notas(db, [dict(A_corrigida, razao_social_tomador="NÃO PODE GRAVAR"), C],
                 dry_run=True)
db.commit()
db.close()
checa("gravar_notas(dry_run=True) + commit não cria nota", len(linhas()) == 2,
      f"{len(linhas())} linhas")
nota_a = [n for n in linhas() if n.codigo_verificacao == CHAVE_A][0]
checa("... nem altera a que existe", nota_a.razao_social_tomador == "CLIENTE A CORRIGIDO",
      nota_a.razao_social_tomador)
checa("... mas conta o que faria", r.importadas == 1 and r.atualizadas == 1,
      f"importadas={r.importadas} atualizadas={r.atualizadas}")

print("\n=== 5. ADN fora do ar: falha registrada, código 1, nada gravado ===")
codigo = roda(notas=[C], falhar="Falha ao consultar ADN no NSU 1 (último erro: HTTP 504)")
checa("sai 1", codigo == 1, f"código {codigo}")
checa("nada foi gravado", len(linhas()) == 2, f"{len(linhas())} linhas")
ultima = execucoes()[-1]
checa("registrada como falha, com o motivo",
      ultima["resultado"] == "falha" and "504" in (ultima["detalhe"] or ""), str(ultima))

print("\n=== 6. Só erro e nada gravado reprova; erro no meio de uma carga boa, não ===")
codigo = roda(notas=[SEM_CHAVE])
checa("só nota sem chave: sai 1", codigo == 1, f"código {codigo}")
checa("... registrada como falha", execucoes()[-1]["resultado"] == "falha")

codigo = roda(notas=[SEM_CHAVE, C])
ultima = execucoes()[-1]
checa("nota sem chave junto de uma boa: sai 0", codigo == 0, f"código {codigo}")
checa("... a boa entrou", len(linhas()) == 3, f"{len(linhas())} linhas")
checa("... sucesso, mas o erro fica contado",
      ultima["resultado"] == "sucesso" and ultima["erros"] == 1, str(ultima))

print()
if falhas:
    print(f"RESULTADO: {len(falhas)} verificação(ões) falharam:")
    for f in falhas:
        print(f"  - {f}")
    sys.exit(1)
print("RESULTADO: todas as verificações passaram.")
