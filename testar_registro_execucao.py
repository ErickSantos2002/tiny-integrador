"""Prova do registro de execução das cargas (`operacao.execucoes_job`).

O registro existe para que a falha de uma carga chegue até o Erick — hoje o código de
saída morre no journal da VPS. Por isso os testes aqui insistem em duas propriedades que
são fáceis de quebrar sem perceber:

  * o registro **sobrevive a rollback** da carga. Se ele morresse junto, sumiria
    exatamente na hora em que importa;
  * falha ao registrar **não derruba a carga**. O log de execução não pode impedir 8 mil
    notas de entrar.

Roda contra um Postgres DESCARTÁVEL. Nunca aponte para produção.

    docker run -d --rm --name extrator-teste -e POSTGRES_PASSWORD=teste \
        -e POSTGRES_DB=testdb -p 55433:5432 postgres:17
    python testar_registro_execucao.py
    docker rm -f extrator-teste
"""
import os
import sys

os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:teste@localhost:55433/testdb"
os.environ.setdefault("TINY_TOKEN", "token-de-teste")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from app.models.database import Base, SessionLocal, engine  # noqa: E402
from app.services.execucao import ExecucaoJob, registrar_execucao  # noqa: E402

falhas = []


def checa(descricao, condicao, detalhe=""):
    marca = "ok  " if condicao else "FALHA"
    print(f"  [{marca}] {descricao}{(' -> ' + detalhe) if detalhe else ''}")
    if not condicao:
        falhas.append(descricao)


def recriar_schema():
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS operacao CASCADE"))
        conn.execute(text("CREATE SCHEMA operacao"))
    Base.metadata.create_all(engine, tables=[ExecucaoJob.__table__])


def ultima(db, job):
    linha = (db.query(ExecucaoJob).filter(ExecucaoJob.job == job)
             .order_by(ExecucaoJob.id.desc()).first())
    if linha is not None:
        db.expunge(linha)      # desliga do ORM: sem isto o rollback abaixo apaga os campos
    # O SELECT abre transação e segura ACCESS SHARE na tabela. Sem soltar aqui, o
    # `DROP TABLE` do bloco 6 espera por um lock que só sairia no fim do teste — o
    # processo trava calado. Custou uma investigação; fica o comentário.
    db.rollback()
    return linha


def main():
    recriar_schema()
    db = SessionLocal()

    print("\n1. Carga que termina bem vira uma linha 'sucesso'")
    with registrar_execucao("teste_ok", "--dias 14") as registro:
        registro.contagens = {"criada": 3, "inalterada": 50}
    linha = ultima(db, "teste_ok")
    checa("a execução foi registrada", linha is not None)
    if linha is None:
        print("  (sem linha, pulando o resto do bloco)")
        return
    checa("resultado 'sucesso'", linha.resultado == "sucesso", str(linha.resultado))
    checa("guardou as contagens", linha.contagens == {"criada": 3, "inalterada": 50},
          str(linha.contagens))
    checa("guardou os argumentos", linha.argumentos == "--dias 14", str(linha.argumentos))
    checa("tem início e fim", linha.inicio is not None and linha.fim is not None)
    checa("o fim não é anterior ao início", linha.fim >= linha.inicio)

    print("\n2. Erros contados viram 'falha'")
    with registrar_execucao("teste_erro") as registro:
        registro.erros = 3
    linha = ultima(db, "teste_erro")
    checa("resultado 'falha'", linha.resultado == "falha", str(linha.resultado))
    checa("e o número de erros ficou guardado", linha.erros == 3, str(linha.erros))

    print("\n3. O resultado segue o CÓDIGO DE SAÍDA, não o número de erros")
    # `extrair_notas` sai 0 quando errou em alguns registros mas trouxe o resto. Se o
    # registro dissesse "falha" e o systemd dissesse "sucesso", o alarme contradiria o
    # journal — e aí ninguém confia em nenhum dos dois.
    with registrar_execucao("teste_parcial") as registro:
        registro.erros = 2
        registro.falhou = False          # o job saiu 0
    linha = ultima(db, "teste_parcial")
    checa("erro sem reprovação continua 'sucesso'", linha.resultado == "sucesso",
          str(linha.resultado))
    checa("mas os erros ficam visíveis no histórico", linha.erros == 2, str(linha.erros))

    print("\n4. Exceção no meio da carga é registrada como falha, e re-levantada")
    try:
        with registrar_execucao("teste_excecao") as registro:
            registro.contagens = {"criada": 1}
            raise RuntimeError("a API caiu")
        checa("a exceção continua subindo", False, "não levantou")
    except RuntimeError as erro:
        checa("a exceção continua subindo", "a API caiu" in str(erro), str(erro))
    linha = ultima(db, "teste_excecao")
    checa("ficou registrada como falha", linha.resultado == "falha", str(linha.resultado))
    checa("com o motivo no detalhe", "a API caiu" in (linha.detalhe or ""), str(linha.detalhe))
    checa("e o que já tinha sido feito não se perdeu",
          linha.contagens == {"criada": 1}, str(linha.contagens))

    print("\n5. O registro SOBREVIVE a rollback da carga")
    # Esta é a propriedade que faz o alarme existir: a carga que deu errado provavelmente
    # deixou a sessão dela suja. Se o registro compartilhasse a transação, ele sumiria
    # justamente quando é necessário.
    with registrar_execucao("teste_rollback") as registro:
        outra = SessionLocal()
        outra.execute(text("SELECT 1"))
        outra.rollback()
        outra.close()
        registro.erros = 1
    linha = ultima(db, "teste_rollback")
    checa("a linha continua lá depois do rollback alheio", linha is not None)
    checa("e está fechada como falha", linha is not None and linha.resultado == "falha",
          str(linha and linha.resultado))

    print("\n6. Falha ao REGISTRAR não derruba a carga")
    # Sem a tabela, gravar o registro é impossível. A carga tem que seguir mesmo assim.
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE operacao.execucoes_job"))
    rodou = False
    try:
        with registrar_execucao("teste_sem_tabela") as registro:
            rodou = True
            registro.contagens = {"criada": 9}
        checa("a carga rodou inteira mesmo sem conseguir registrar", rodou)
    except Exception as erro:                                  # noqa: BLE001
        checa("a carga rodou inteira mesmo sem conseguir registrar", False,
              f"{type(erro).__name__}: {erro}")

    print("\n7. Interrupção (SystemExit/Ctrl+C) também fica registrada")
    recriar_schema()
    try:
        with registrar_execucao("teste_interrompido"):
            raise KeyboardInterrupt()
    except KeyboardInterrupt:
        pass
    linha = ultima(db, "teste_interrompido")
    checa("ficou registrada", linha is not None)
    checa("como falha, com o tipo no detalhe",
          linha is not None and linha.resultado == "falha"
          and "KeyboardInterrupt" in (linha.detalhe or ""),
          str(linha and linha.detalhe))

    db.close()
    print("\n" + "=" * 60)
    if falhas:
        print(f"{len(falhas)} FALHA(S):")
        for f in falhas:
            print("  -", f)
        return 1
    print("todos os testes passaram")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
