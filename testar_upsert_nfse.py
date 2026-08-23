"""
Prova de que o upsert de NFS-e casa por CHAVE DE ACESSO e não por número.

Cenário reproduzido (o que aconteceu de verdade no banco de produção):
  - existe no banco a NFS-e nº 749 emitida em 2019 (série antiga, Recife);
  - chega do ADN a NFS-e nº 749 emitida em 2026 (série nacional, numeração reiniciada);
  - as duas são notas DIFERENTES e devem coexistir.

Roda contra um Postgres DESCARTÁVEL. Nunca aponte para produção.

    docker run -d --rm --name nfse-teste -e POSTGRES_PASSWORD=teste \
        -e POSTGRES_DB=testdb -p 55432:5432 postgres:17
    python testar_upsert_nfse.py
    docker rm -f nfse-teste

O script recria o schema `tiny` do zero (DROP SCHEMA CASCADE) a cada execução.
"""
import json
import os
import sys
from datetime import date

# Forçado de propósito: este script faz DROP SCHEMA, então nunca herda a
# DATABASE_URL do ambiente (que em dev/prod aponta para o banco de verdade).
os.environ["DATABASE_URL"] = (
    "postgresql+psycopg2://postgres:teste@localhost:55432/testdb"
)
os.environ.setdefault("NFSE_CERT_PATH", "/dev/null")
os.environ.setdefault("NFSE_KEY_PATH", "/dev/null")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402
from app.models.database import Base, engine, SessionLocal  # noqa: E402
from app.models.nota_servico import NotaServico  # noqa: E402
import importlib  # noqa: E402

# import direto: o __init__ do pacote reexporta o router com o mesmo nome do módulo
ep = importlib.import_module("app.api.endpoints.nota_servico")

CHAVE_NOVA = "26116062208857492000148000000000074926061510050294"
CHAVE_OUTRA = "26116062208857492000148000000000075026061510050295"

falhas = []


def checa(descricao, condicao, detalhe=""):
    marca = "ok  " if condicao else "FALHA"
    print(f"  [{marca}] {descricao}{(' -> ' + detalhe) if detalhe else ''}")
    if not condicao:
        falhas.append(descricao)


def prepara_banco(com_migration=True):
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS tiny CASCADE"))
        conn.execute(text("CREATE SCHEMA tiny"))
    Base.metadata.create_all(engine, tables=[NotaServico.__table__])
    # A constraint abaixo existe no banco REAL mas não é declarada no model — sem
    # recriá-la aqui, o teste roda contra um schema mais permissivo que a produção
    # e deixa passar exatamente o defeito que ela causa.
    with engine.begin() as conn:
        conn.execute(text(
            'ALTER TABLE tiny.servicos ADD CONSTRAINT servicos_numero_nf_unique '
            'UNIQUE ("nº_da_nota_fiscal_eletrônica")'
        ))
        if com_migration:
            # migrations/002 — a identidade passa a ser a chave de acesso
            conn.execute(text(
                "ALTER TABLE tiny.servicos DROP CONSTRAINT servicos_numero_nf_unique"
            ))
            conn.execute(text(
                'CREATE UNIQUE INDEX servicos_chave_acesso_unique '
                'ON tiny.servicos ("código_de_verificação_nf") '
                "WHERE \"código_de_verificação_nf\" ~ '^[0-9]{50}$'"
            ))
    db = SessionLocal()
    db.add(
        NotaServico(
            numero_nfse=749,
            codigo_verificacao="CDVA-LZFV",       # código curto da série antiga
            data_emissao=date(2019, 8, 16),
            valor_servico="1000.00",
            razao_social_tomador="CLIENTE DE 2019",
        )
    )
    db.commit()
    db.close()


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


def roda_importacao(notas):
    """Executa o endpoint real, com o serviço do ADN substituído por um dublê."""

    class ServicoFalso:
        def __init__(self, **kwargs):
            pass

        def consultar_nfse(self, data_inicial, data_final):
            return notas

    original = ep.NFSeRecifeNacionalService
    ep.NFSeRecifeNacionalService = ServicoFalso
    db = SessionLocal()
    try:
        resposta = ep.importar_nfse_recife(
            data_inicial=date(2026, 6, 1), data_final=date(2026, 6, 30), db=db
        )
        return json.loads(resposta.body)
    finally:
        db.close()
        ep.NFSeRecifeNacionalService = original


def linhas():
    db = SessionLocal()
    try:
        return db.query(NotaServico).order_by(NotaServico.data_emissao).all()
    finally:
        db.close()


print("\n=== 0. SEM a migration 002, o banco rejeita a nota nova (justifica a migration) ===")
print("    (o traceback de UniqueViolation abaixo é ESPERADO: é o endpoint logando a falha)")
prepara_banco(com_migration=False)
try:
    r = roda_importacao(
        [nota_adn(749, CHAVE_NOVA, date(2026, 6, 30), "CLIENTE DE 2026", "475.00")]
    )
    rejeitou = r.get("success") is False
except Exception:
    rejeitou = True
checa("com a constraint antiga (UNIQUE no número) a importação falha", rejeitou,
      "é exatamente o que a migration 002 remove")
checa("e a nota de 2019 continua intacta (falhou sem destruir)",
      len(linhas()) == 1 and linhas()[0].razao_social_tomador == "CLIENTE DE 2019")

print("\n=== 1. Nota nova nº 749 (2026) não pode sobrescrever a nº 749 de 2019 ===")
prepara_banco()
r = roda_importacao(
    [nota_adn(749, CHAVE_NOVA, date(2026, 6, 30), "CLIENTE DE 2026", "475.00")]
)
todas = linhas()
checa("as duas notas coexistem", len(todas) == 2, f"{len(todas)} linhas")
antiga = [n for n in todas if n.data_emissao == date(2019, 8, 16)]
checa("a nota de 2019 continua no banco", len(antiga) == 1)
if antiga:
    checa(
        "a nota de 2019 está intacta",
        antiga[0].razao_social_tomador == "CLIENTE DE 2019"
        and antiga[0].valor_servico == "1000.00",
        f"tomador={antiga[0].razao_social_tomador!r} valor={antiga[0].valor_servico!r}",
    )
checa("contabilizou como importada, não atualizada",
      r["total_importadas"] == 1 and r["total_atualizadas"] == 0,
      f"importadas={r['total_importadas']} atualizadas={r['total_atualizadas']}")

print("\n=== 2. Reimportar a MESMA nota atualiza, não duplica (idempotência) ===")
r = roda_importacao(
    [nota_adn(749, CHAVE_NOVA, date(2026, 6, 30), "CLIENTE DE 2026 CORRIGIDO", "480.00")]
)
todas = linhas()
checa("continua com 2 linhas", len(todas) == 2, f"{len(todas)} linhas")
checa("contabilizou como atualizada",
      r["total_atualizadas"] == 1 and r["total_importadas"] == 0,
      f"importadas={r['total_importadas']} atualizadas={r['total_atualizadas']}")
nova = [n for n in linhas() if n.codigo_verificacao == CHAVE_NOVA][0]
checa("os dados da nota nova foram atualizados",
      nova.razao_social_tomador == "CLIENTE DE 2026 CORRIGIDO")
antiga = [n for n in linhas() if n.data_emissao == date(2019, 8, 16)][0]
checa("a nota de 2019 segue intacta depois da reimportação",
      antiga.valor_servico == "1000.00")

print("\n=== 3. Nota sem chave de acesso é recusada, não inserida às cegas ===")
r = roda_importacao(
    [nota_adn(900, None, date(2026, 6, 25), "SEM CHAVE", "100.00")]
)
checa("nada foi gravado", r["total_importadas"] == 0 and r["total_atualizadas"] == 0)
checa("o erro foi reportado na resposta", bool(r.get("erros")),
      json.dumps(r.get("erros"), ensure_ascii=False))
checa("o banco continua com 2 linhas", len(linhas()) == 2, f"{len(linhas())} linhas")

print("\n=== 4. Reimportar NÃO desfaz a marcação manual de cancelada ===")
prepara_banco()
roda_importacao(
    [nota_adn(749, CHAVE_NOVA, date(2026, 6, 30), "CLIENTE DE 2026", "475.00")]
)
db = SessionLocal()
nova = db.query(NotaServico).filter(NotaServico.codigo_verificacao == CHAVE_NOVA).first()
checa("nota criada pela importação nasce com cancelada=False (não NULL)",
      nova.cancelada is False, f"cancelada={nova.cancelada!r}")
nova.cancelada = True          # a equipe marca à mão, como faz hoje
db.commit()
db.close()

r = roda_importacao(
    [nota_adn(749, CHAVE_NOVA, date(2026, 6, 30), "CLIENTE DE 2026", "475.00")]
)
checa("a nota foi de fato reimportada", r["total_atualizadas"] == 1)
nova = [n for n in linhas() if n.codigo_verificacao == CHAVE_NOVA][0]
checa("a marcação de cancelada sobreviveu à reimportação",
      nova.cancelada is True, f"cancelada={nova.cancelada!r}")

print("\n=== 5. Nota com cancelada NULL não some da listagem ===")
db = SessionLocal()
db.execute(
    text('UPDATE tiny.servicos SET cancelada = NULL WHERE "código_de_verificação_nf" = :c'),
    {"c": CHAVE_NOVA},
)
db.commit()
db.close()
db = SessionLocal()
try:
    listadas = ep.listar_notas_servico(
        cpf_cnpj_tomador=None, cpf_cnpj_prestador=None, data_emissao=None,
        data_inicio=None, data_fim=None, cidade_servico=None, uf_servico=None,
        incluir_canceladas=False, db=db,
    )
    chaves = {n.codigo_verificacao for n in listadas}
finally:
    db.close()
checa("a nota com cancelada NULL aparece na listagem", CHAVE_NOVA in chaves,
      f"{len(chaves)} nota(s) listada(s)")

print("\n=== 6. Controle: o comportamento ANTIGO (casar por número) destrói a nota ===")
prepara_banco()
db = SessionLocal()
alvo = db.query(NotaServico).filter(NotaServico.numero_nfse == 749).first()
for k, v in nota_adn(749, CHAVE_NOVA, date(2026, 6, 30), "CLIENTE DE 2026", "475.00").items():
    setattr(alvo, k, v)
db.commit()
db.close()
sobrou = linhas()
checa("com a lógica antiga sobra só 1 linha (a de 2019 foi sobrescrita)",
      len(sobrou) == 1, f"{len(sobrou)} linha(s)")
checa("com a lógica antiga o cliente de 2019 desapareceu",
      sobrou[0].razao_social_tomador == "CLIENTE DE 2026",
      f"tomador={sobrou[0].razao_social_tomador!r}")

print()
if falhas:
    print(f"RESULTADO: {len(falhas)} verificação(ões) falharam:")
    for f in falhas:
        print(f"  - {f}")
    sys.exit(1)
print("RESULTADO: todas as verificações passaram.")
