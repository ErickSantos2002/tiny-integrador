"""Prova de que o extrator de notas do Tiny corrige o que o n8n errava.

Os dois defeitos medidos em 2026-09-01, que custaram R$ 226.685 de faturamento inflado:

  1. nota com DOIS marcadores chegava com a descrição em branco (no XML, dois marcadores
     viram uma lista e o n8n lia `.descricao` da lista);
  2. marcador posto DEPOIS da carga nunca entrava, porque o ramo de atualização só
     disparava quando um dos 31 campos da nota mudava — e marcador não era nenhum deles.

Roda contra um Postgres DESCARTÁVEL. Nunca aponte para produção.

    docker run -d --rm --name extrator-teste -e POSTGRES_PASSWORD=teste \
        -e POSTGRES_DB=testdb -p 55433:5432 postgres:17
    python testar_extrator_notas.py
    docker rm -f extrator-teste

A API do Tiny não é chamada: as notas são dicionários no formato que a api2 devolve.
O script recria o schema `tiny` do zero (DROP SCHEMA CASCADE) a cada execução.
"""
import os
import sys
from decimal import Decimal

# Forçado de propósito: este script faz DROP SCHEMA, então nunca herda a DATABASE_URL
# do ambiente (que em dev/prod aponta para o banco de verdade).
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:teste@localhost:55433/testdb"
os.environ.setdefault("TINY_TOKEN", "token-de-teste")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from app.models.database import Base, SessionLocal, engine  # noqa: E402
from app.models.cliente import Cliente  # noqa: E402
from app.models.item_nota import ItemNota  # noqa: E402
from app.models.marcador import Marcador  # noqa: E402
from app.models.nota_fiscal import NotaFiscal  # noqa: E402
from app.services.tiny_notas import _diferencas, salvar_nota  # noqa: E402

falhas = []


def checa(descricao, condicao, detalhe=""):
    marca = "ok  " if condicao else "FALHA"
    print(f"  [{marca}] {descricao}{(' -> ' + detalhe) if detalhe else ''}")
    if not condicao:
        falhas.append(descricao)


def nota_exemplo(**sobrescreve):
    """Uma nota no formato que `nota.fiscal.obter.php?formato=json` devolve."""
    nota = {
        "id": "617079728",
        "tipo_nota": "S",
        "natureza_operacao": "CFOP 6102 - Venda de mercadoria ",  # espaço no fim, como a origem manda
        "serie": "1",
        "numero": "008652",
        "numero_ecommerce": "",
        "data_emissao": "01/09/2026",
        "data_saida": "01/09/2026",
        "hora_saida": "11:56",
        "valor_produtos": "3306.00",
        "valor_nota": "3306.00",
        "valor_frete": "0.00",
        "situacao": "7",
        "descricao_situacao": "Emitida DANFE",
        "chave_acesso": "26260908857492000148550010000086521234567890",
        "obs": "observação qualquer\n\r\n",
        "cliente": {"nome": "CLIENTE TESTE LTDA", "cpf_cnpj": "12345678000199",
                    "tipo_pessoa": "J", "cidade": "Recife", "uf": "PE"},
        "endereco_entrega": {"nome_destinatario": "CLIENTE TESTE LTDA", "cidade": "Recife", "uf": "PE"},
        "forma_envio": None,
        "marcadores": [],
        "itens": [{"item": {"id_produto": "223536711", "codigo": "001",
                            "descricao": "BAFOMETRO - MARK X", "unidade": "Pc",
                            "quantidade": "1.0000", "valor_unitario": "3306.0000",
                            "valor_total": "3306.0000", "cfop": "6102",
                            "natureza": "CFOP 6102 - Venda"}}],
    }
    nota.update(sobrescreve)
    return nota


def marcador(id_marcador, descricao, cor="#808080"):
    return {"id": id_marcador, "descricao": descricao, "cor": cor}


def recriar_schema():
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS tiny CASCADE"))
        conn.execute(text("CREATE SCHEMA tiny"))
    Base.metadata.create_all(engine, tables=[
        t for t in Base.metadata.sorted_tables if t.schema == "tiny"])


def marcadores_no_banco(db, id_tiny):
    nota = db.query(NotaFiscal).filter(NotaFiscal.id_tiny == id_tiny).one()
    return sorted(m.descricao for m in db.query(Marcador).filter(Marcador.id_nota == nota.id))


def main():
    recriar_schema()
    db = SessionLocal()

    print("\n1. Nota nova entra inteira")
    relato = salvar_nota(db, nota_exemplo())
    nota = db.query(NotaFiscal).filter(NotaFiscal.id_tiny == "617079728").one()
    checa("a nota foi criada", relato["acao"] == "criada", relato["acao"])
    checa("valor_nota é Decimal exato", nota.valor_nota == Decimal("3306.00"), str(nota.valor_nota))
    checa("data virou date", str(nota.data_emissao) == "2026-09-01", str(nota.data_emissao))
    checa("hora virou time", str(nota.hora_saida) == "11:56:00", str(nota.hora_saida))
    checa("o item entrou", db.query(ItemNota).filter(ItemNota.id_nota == nota.id).count() == 1)
    checa("o cliente foi criado", db.query(Cliente).count() == 1)
    checa("nota amarrada ao cliente", nota.id_cliente is not None)

    print("\n2. O bug do n8n: DOIS marcadores na mesma nota")
    salvar_nota(db, nota_exemplo(marcadores=[
        marcador("311467", "NF cancelada"), marcador("300001", "NF recusada")]))
    descricoes = marcadores_no_banco(db, "617079728")
    checa("os dois marcadores chegaram com descrição",
          descricoes == ["NF cancelada", "NF recusada"], str(descricoes))

    print("\n3. Marcador posto depois, sem nenhum campo da nota mudar")
    # É o caso real: a nota é emitida, e dias depois alguém a marca como cancelada.
    # O n8n não via, porque comparava só os 31 campos da nota.
    salvar_nota(db, nota_exemplo(marcadores=[]))          # volta ao estado sem marcador
    checa("marcador removido na origem sumiu", marcadores_no_banco(db, "617079728") == [])
    relato = salvar_nota(db, nota_exemplo(marcadores=[marcador("311467", "NF cancelada")]))
    checa("marcador novo entrou mesmo com a nota igual",
          marcadores_no_banco(db, "617079728") == ["NF cancelada"])
    checa("e o relato conta que foram os filhos", "marcadores" in relato["filhos"], str(relato))

    print("\n4. Marcador sem descrição não vira linha-fantasma")
    # O n8n gravou 7.7 mil linhas com descricao NULL, uma por nota sem marcador.
    salvar_nota(db, nota_exemplo(marcadores=[marcador("999", "  ")]))
    nota = db.query(NotaFiscal).filter(NotaFiscal.id_tiny == "617079728").one()
    checa("nenhuma linha gravada", db.query(Marcador).filter(Marcador.id_nota == nota.id).count() == 0)

    print("\n5. Idempotência: rodar de novo não muda nada")
    igual = nota_exemplo(marcadores=[marcador("311467", "NF cancelada")])
    salvar_nota(db, igual)
    relato = salvar_nota(db, igual)
    checa("segunda passagem não altera", relato["acao"] == "inalterada", relato["acao"])
    checa("e não duplica item",
          db.query(ItemNota).filter(ItemNota.id_nota == nota.id).count() == 1)
    checa("nem duplica marcador",
          db.query(Marcador).filter(Marcador.id_nota == nota.id).count() == 1)
    checa("nem duplica cliente", db.query(Cliente).count() == 1)

    print("\n6. Diferença só cosmética não conta como mudança")
    # O n8n gravou '' onde deveria haver NULL e deixou espaço no fim do texto. Se isso
    # contasse como alteração, a primeira carga reescreveria as 8 mil notas do banco.
    nota.numero_ecommerce = ""
    nota.natureza_operacao = "CFOP 6102 - Venda de mercadoria "
    db.commit()
    relato = salvar_nota(db, nota_exemplo(marcadores=[marcador("311467", "NF cancelada")],
                                          natureza_operacao="CFOP 6102 - Venda de mercadoria"))
    checa("vazio e espaço sobrando são ignorados", relato["acao"] == "inalterada",
          f"{relato['acao']} {relato['mudancas']}")

    print("\n7. Mudança de verdade é vista")
    relato = salvar_nota(db, nota_exemplo(marcadores=[marcador("311467", "NF cancelada")],
                                          descricao_situacao="Cancelada", situacao="9"))
    checa("situação nova entrou", relato["acao"] == "atualizada", relato["acao"])
    checa("e diz quais campos", set(relato["mudancas"]) == {"situacao", "descricao_situacao"},
          str(sorted(relato["mudancas"])))

    print("\n8. Curadoria local sobrevive à reimportação")
    # `tipo` é preenchido à mão pelo pessoal (PATCH /notas_fiscais/{id}/tipo). A origem
    # não conhece esse campo; se a importação o escrevesse, apagaria a classificação.
    nota.tipo = "locacao"
    db.commit()
    salvar_nota(db, nota_exemplo(marcadores=[marcador("311467", "NF cancelada")]))
    db.refresh(nota)
    checa("o `tipo` marcado à mão continua lá", nota.tipo == "locacao", str(nota.tipo))
    # O de cima passa hoje por um motivo frágil: `tipo` nem é lido da origem, então a
    # proteção não chega a ser exercida (verificado por mutação). O de baixo testa a
    # proteção de verdade, para o dia em que alguém acrescentar o campo ao mapeamento.
    ignorou = _diferencas(nota, {"tipo": "venda", "situacao": nota.situacao})
    checa("`_diferencas` ignora campo de curadoria mesmo se ele vier nos dados",
          "tipo" not in ignorou, str(ignorou))

    print("\n9. Dry-run não escreve")
    antes = db.query(NotaFiscal).count()
    relato = salvar_nota(db, nota_exemplo(id="999999999", numero="009999"), dry_run=True)
    checa("diz o que faria", relato["acao"] == "criaria", relato["acao"])
    checa("mas não criou nada", db.query(NotaFiscal).count() == antes)

    db.close()

    print("\n" + "=" * 60)
    if falhas:
        print(f"{len(falhas)} FALHA(S):")
        for f in falhas:
            print(f"  - {f}")
        return 1
    print("todos os testes passaram")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
