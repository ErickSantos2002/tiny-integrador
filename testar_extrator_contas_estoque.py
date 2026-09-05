"""Prova dos extratores de contas (pagar/receber) e de estoque.

Os defeitos do n8n que estes testes cobrem, medidos em 2026-09-03:

  * contas: a pesquisa partia de uma data ESCRITA À MÃO no nó, então conta emitida antes
    dela nunca mais era reconferida — conta paga continuava `aberto` para sempre. O banco
    dizia 226 contas a pagar em aberto (R$ 962.071,57), o Tiny dizia 3;
  * estoque: a paginação era três blocos copiados (páginas 1, 2 e 3) e só o primeiro
    inseria produto novo — 270 produtos no banco contra 300 na origem.

Roda contra um Postgres DESCARTÁVEL. Nunca aponte para produção.

    docker run -d --rm --name extrator-teste -e POSTGRES_PASSWORD=teste \
        -e POSTGRES_DB=testdb -p 55433:5432 postgres:17
    python testar_extrator_contas_estoque.py
    docker rm -f extrator-teste
"""
import os
import sys
from datetime import date, datetime
from decimal import Decimal

os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:teste@localhost:55433/testdb"
os.environ.setdefault("TINY_TOKEN", "token-de-teste")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from app.models.database import Base, SessionLocal, engine  # noqa: E402
from app.models.contas_pagar import ContasPagar  # noqa: E402
from app.models.contas_receber import ContasReceber  # noqa: E402
from app.models.estoque import Estoque  # noqa: E402
from app.services.tiny_api import (TinyAPI, TinyAPIError, TinyNaoLocalizado,  # noqa: E402
                                   TinySemRegistros)
from app.services.tiny_contas import (marcar_excluida_na_origem,  # noqa: E402
                                      normalizar_conta, salvar_conta)
from app.services.tiny_estoque import normalizar_produto, salvar_produto  # noqa: E402
from app.jobs.extrair_contas import ids_em_aberto_no_banco  # noqa: E402

falhas = []


def checa(descricao, condicao, detalhe=""):
    marca = "ok  " if condicao else "FALHA"
    print(f"  [{marca}] {descricao}{(' -> ' + detalhe) if detalhe else ''}")
    if not condicao:
        falhas.append(descricao)


def conta_exemplo(**sobrescreve):
    """Uma conta no formato que `conta.pagar.obter.php?formato=json` devolve."""
    conta = {
        "id": "617037668",
        "data": "25/08/2026",
        "vencimento": "15/07/2026",
        "competencia": "07/2026",          # MM/yyyy, não dd/MM/yyyy
        "valor": "50389.30",
        "saldo": "50389.30",
        "nro_documento": "",
        "historico": "SEFAZ/DAE-10 (ICMS)",
        "categoria": "7.4 - ICMS",
        "situacao": "aberto",
        "ocorrencia": "U",
        "liquidacao": "",
        "cliente": {"nome": "Secretaria da Fazenda", "cpf_cnpj": "11111111000191",
                    "tipo_pessoa": "J", "cidade": "Recife", "uf": "PE", "codigo": "123"},
    }
    conta.update(sobrescreve)
    return conta


def produto_exemplo(**sobrescreve):
    produto = {
        "id": "613852626", "data_criacao": "24/01/2025 10:11:34", "nome": " VIDRO - PHOEBUS ",
        "codigo": "331", "preco": 300, "preco_promocional": 0, "unidade": "Pç", "gtin": "",
        "tipoVariacao": "N", "localizacao": "", "preco_custo": 0, "preco_custo_medio": 0,
        "situacao": "A",
    }
    produto.update(sobrescreve)
    return produto


class APIFalsa(TinyAPI):
    """Responde no lugar da api2, para testar a paginação sem rede."""

    def __init__(self, paginas):
        self.paginas = paginas
        self.chamadas = []

    def _get(self, caminho, params):
        self.chamadas.append((caminho, params.get("pagina")))
        pagina = int(params.get("pagina") or 1)
        if pagina > len(self.paginas):
            return {"status_processamento": "2"}
        return {"status_processamento": "3", "numero_paginas": len(self.paginas),
                "produtos": [{"produto": p} for p in self.paginas[pagina - 1]]}


class RespostaFalsa:
    """Uma resposta HTTP 200 com o corpo que a api2 devolve — erro vem no corpo, não no
    código HTTP, e é exatamente essa a pegadinha que o cliente precisa tratar."""

    status_code = 200
    headers: dict = {}

    def __init__(self, corpo):
        self._corpo = corpo

    def raise_for_status(self):
        return None

    def json(self):
        return self._corpo


class SessaoFalsa:
    def __init__(self, corpo):
        self._corpo = corpo

    def get(self, url, params=None, timeout=None):
        return RespostaFalsa(self._corpo)


def recriar_schema():
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS tiny CASCADE"))
        conn.execute(text("CREATE SCHEMA tiny"))
    Base.metadata.create_all(engine, tables=[
        t for t in Base.metadata.sorted_tables if t.schema == "tiny"])


def main():
    recriar_schema()
    db = SessionLocal()

    print("\n1. Conta a pagar entra inteira, com as conversões certas")
    relato = salvar_conta(db, "pagar", conta_exemplo())
    conta = db.query(ContasPagar).filter(ContasPagar.id_tiny == 617037668).one()
    checa("a conta foi criada", relato["acao"] == "criada", relato["acao"])
    checa("valor é Decimal exato", conta.valor == Decimal("50389.30"), str(conta.valor))
    checa("competência MM/yyyy virou o 1º dia do mês",
          conta.competencia == date(2026, 7, 1), str(conta.competencia))
    checa("vencimento convertido", conta.vencimento == date(2026, 7, 15), str(conta.vencimento))
    checa("liquidação vazia virou NULL", conta.liquidacao is None, str(conta.liquidacao))
    checa("documento vazio virou NULL", conta.nro_documento is None, str(conta.nro_documento))

    print("\n2. O defeito do n8n: conta antiga que foi paga")
    # A conta já está no banco como 'aberto'. No Tiny ela foi quitada. O n8n não via,
    # porque só reconferia o que tinha sido emitido depois da data fixa do nó.
    relato = salvar_conta(db, "pagar", conta_exemplo(
        situacao="pago", saldo="0", liquidacao="13/07/2026"))
    db.refresh(conta)
    checa("a situação virou 'pago'", conta.situacao == "pago", str(conta.situacao))
    checa("o saldo zerou", conta.saldo == Decimal("0"), str(conta.saldo))
    checa("a data de liquidação entrou", conta.liquidacao == date(2026, 7, 13), str(conta.liquidacao))
    checa("e o relato aponta os três campos",
          set(relato["mudancas"]) == {"situacao", "saldo", "liquidacao"}, str(sorted(relato["mudancas"])))
    checa("updated_at foi tocado", conta.updated_at is not None)

    print("\n3. Idempotência das contas")
    relato = salvar_conta(db, "pagar", conta_exemplo(situacao="pago", saldo="0", liquidacao="13/07/2026"))
    checa("segunda passagem não altera", relato["acao"] == "inalterada", relato["acao"])
    checa("e não duplica", db.query(ContasPagar).count() == 1)

    print("\n4. Campo obrigatório vazio falha com mensagem legível")
    try:
        salvar_conta(db, "pagar", conta_exemplo(id="999", vencimento=""))
        checa("erro explicando o campo", False, "não levantou")
    except ValueError as erro:
        checa("erro explicando o campo", "vencimento" in str(erro), str(erro))

    print("\n5. Contas a receber usam a coluna `data` e os campos extras")
    receber = conta_exemplo(id="700000001", link_boleto="https://banco/boleto",
                            forma_pagamento="boleto", portador="Itaú", nro_banco="341",
                            serie_documento="1")
    salvar_conta(db, "receber", receber)
    cr = db.query(ContasReceber).filter(ContasReceber.id_tiny == 700000001).one()
    checa("gravou na coluna `data`", cr.data == date(2026, 8, 25), str(cr.data))
    checa("guardou o link do boleto", cr.link_boleto == "https://banco/boleto")
    checa("guardou o portador", cr.portador == "Itaú")
    dados = normalizar_conta("receber", receber)
    checa("usa `dia_vencimento_semanal` (nome só de receber)", "dia_vencimento_semanal" in dados)

    print("\n5b. A reconferência olha o que o BANCO acha em aberto, não só o Tiny")
    # Conta paga SOME da lista de abertas do Tiny. Se a carga só perguntasse à origem,
    # a conta que ficou `aberto` no banco nunca mais seria reconferida — eram 223 contas
    # a pagar, R$ 955.296,09, presas em aberto desde 2021.
    salvar_conta(db, "pagar", conta_exemplo(id="500000001", situacao="aberto"))
    salvar_conta(db, "pagar", conta_exemplo(id="500000002", situacao="pago", saldo="0"))
    em_aberto = ids_em_aberto_no_banco(db, "pagar")
    checa("a conta aberta no banco entra na reconferência", "500000001" in em_aberto, str(em_aberto))
    checa("a já paga não entra", "500000002" not in em_aberto, str(em_aberto))

    print("\n5c. Campo maior que a coluna não derruba a conta")
    # Em 2026-09-04 uma conta a receber de R$ 23.520 se perdeu porque o número do
    # endereço do cliente vinha como "NAO INFORMADO" — 13 caracteres num varchar(10).
    relato = salvar_conta(db, "receber", conta_exemplo(
        id="700000009",
        cliente={"nome": "ITUIUTABA BIOENERGIA LTDA.", "cpf_cnpj": "08164344000148",
                 "numero": "NAO INFORMADO", "tipo_pessoa": "J"}))
    salva = db.query(ContasReceber).filter(ContasReceber.id_tiny == 700000009).one_or_none()
    checa("a conta entrou apesar do campo grande", salva is not None, str(relato["acao"]))
    checa("o campo foi truncado no limite da coluna",
          salva is not None and salva.cliente_numero == "NAO INFORM", str(salva and salva.cliente_numero))

    print("\n5d. Conta que sumiu do Tiny é MARCADA, não contada como erro")
    # Confirmado com o financeiro em 2026-09-05: conta que atrasa é EXCLUÍDA no Tiny e
    # reemitida com id novo. O id some da origem e a linha ficaria `aberto` para sempre —
    # eram 226 contas a pagar (R$ 962.071,57) e 41 a receber (R$ 173.480,80).
    api_sumida = TinyAPI("token", espera=0, sessao=SessaoFalsa(
        {"retorno": {"status_processamento": "2", "status": "Erro", "codigo_erro": "32",
                     "erros": [{"erro": "Conta a pagar não localizada"}]}}))
    try:
        api_sumida._get("conta.pagar.obter.php", {"id": "1"})
        checa("codigo_erro 32 vira TinyNaoLocalizado", False, "não levantou")
    except TinyNaoLocalizado as erro:
        checa("codigo_erro 32 vira TinyNaoLocalizado", "não localizada" in str(erro), str(erro))
    except Exception as erro:                       # noqa: BLE001 — o ponto é o tipo
        checa("codigo_erro 32 vira TinyNaoLocalizado", False, type(erro).__name__)

    # e um erro de verdade continua sendo erro: sem isto, a "correção" viraria um
    # silenciador geral e o exit code continuaria sem significar nada.
    api_quebrada = TinyAPI("token", espera=0, tentativas=1, sessao=SessaoFalsa(
        {"retorno": {"status": "Erro", "codigo_erro": "1",
                     "erros": [{"erro": "Token inválido"}]}}))
    try:
        api_quebrada._get("conta.pagar.obter.php", {"id": "1"})
        checa("erro de verdade continua sendo TinyAPIError", False, "não levantou")
    except TinyNaoLocalizado:
        checa("erro de verdade continua sendo TinyAPIError", False, "virou não-localizado")
    except TinyAPIError as erro:
        checa("erro de verdade continua sendo TinyAPIError", "Token" in str(erro), str(erro))

    # 500000001 está no banco como 'aberto' desde o bloco 5b
    checa("antes: a conta entra na reconferência",
          "500000001" in ids_em_aberto_no_banco(db, "pagar"))
    resultado = marcar_excluida_na_origem(db, "pagar", "500000001")
    sumida = db.query(ContasPagar).filter(ContasPagar.id_tiny == 500000001).one()
    checa("a conta foi marcada", resultado == "marcada", str(resultado))
    checa("com a data em que sumiu", sumida.excluida_na_origem_em is not None)
    checa("a situação NÃO foi mexida (bronze registra, não reescreve)",
          sumida.situacao == "aberto", str(sumida.situacao))
    checa("depois: a conta sai da reconferência",
          "500000001" not in ids_em_aberto_no_banco(db, "pagar"),
          str(ids_em_aberto_no_banco(db, "pagar")))
    checa("marcar de novo é inócuo",
          marcar_excluida_na_origem(db, "pagar", "500000001") == "ja_marcada")
    checa("id que não está no banco não inventa linha",
          marcar_excluida_na_origem(db, "pagar", "999999999") is None)
    checa("e não criou linha nenhuma", db.query(ContasPagar).filter(
        ContasPagar.id_tiny == 999999999).count() == 0)
    checa("dry-run não escreve", marcar_excluida_na_origem(
        db, "pagar", "500000002", dry_run=True) == "marcaria")
    checa("  (e a conta continua sem marca)", db.query(ContasPagar).filter(
        ContasPagar.id_tiny == 500000002).one().excluida_na_origem_em is None)

    print("\n5e. Conta marcada que reaparece na origem é desmarcada sozinha")
    # A reversibilidade é o motivo de marcar em vez de apagar: se a API der um falso
    # "não localizada", a passagem seguinte conserta sem ninguém mexer no banco.
    relato = salvar_conta(db, "pagar", conta_exemplo(id="500000001", situacao="aberto"))
    db.refresh(sumida)
    checa("a marca foi limpa", sumida.excluida_na_origem_em is None,
          str(sumida.excluida_na_origem_em))
    checa("e o relato registra que ela voltou",
          "excluida_na_origem_em" in relato["mudancas"], str(sorted(relato["mudancas"])))
    checa("volta a entrar na reconferência",
          "500000001" in ids_em_aberto_no_banco(db, "pagar"))

    print("\n6. Produto novo entra — inclusive o das páginas que o n8n não inseria")
    relato = salvar_produto(db, produto_exemplo(), saldo="7")
    produto = db.query(Estoque).filter(Estoque.id == 613852626).one_or_none()
    checa("o produto foi criado", relato["acao"] == "criado", relato["acao"])
    checa("e está mesmo gravado", produto is not None)
    if produto is None:      # sem isto o resto do bloco estoura em vez de reportar
        print("  (pulando o resto do bloco 6: o produto não entrou)")
        produto = Estoque(id=0)
    checa("saldo gravado", produto.saldo == Decimal("7"), str(produto.saldo))
    checa("código virou inteiro", produto.codigo == 331, str(produto.codigo))
    checa("tipoVariacao virou tipovariacao", produto.tipovariacao == "N", str(produto.tipovariacao))
    checa("data_criacao com hora", produto.data_criacao == datetime(2025, 1, 24, 10, 11, 34),
          str(produto.data_criacao))

    print("\n7. Saldo que muda é atualizado; o resto fica quieto")
    relato = salvar_produto(db, produto_exemplo(), saldo="3")
    db.refresh(produto)
    checa("saldo novo entrou", produto.saldo == Decimal("3"), str(produto.saldo))
    checa("só o saldo mudou", set(relato["mudancas"]) == {"saldo"}, str(sorted(relato["mudancas"])))
    relato = salvar_produto(db, produto_exemplo(), saldo="3")
    checa("e roda de novo sem mexer em nada", relato["acao"] == "inalterado", relato["acao"])

    print("\n8. Código de produto não numérico não derruba a carga")
    relato = salvar_produto(db, produto_exemplo(id="700", codigo="AB-12"), saldo="1")
    checa("produto entrou mesmo assim", relato["acao"] == "criado", relato["acao"])
    checa("com código nulo", db.query(Estoque).filter(Estoque.id == 700).one().codigo is None)

    print("\n9. A paginação segue até a última página, não até a terceira")
    # O n8n tinha três blocos copiados: páginas 1, 2 e 3. Uma quarta página passaria batida.
    paginas = [[produto_exemplo(id=str(1000 + p * 100 + i), codigo=str(p * 100 + i))
                for i in range(3)] for p in range(5)]
    api = APIFalsa(paginas)
    encontrados = list(api.pesquisar_produtos())
    checa("leu as 5 páginas", len(encontrados) == 15, f"{len(encontrados)} produtos")
    checa("pediu página por página até o fim",
          [c[1] for c in api.chamadas] == [1, 2, 3, 4, 5], str([c[1] for c in api.chamadas]))

    print("\n9b. Pesquisa que não acha nada não é erro")
    # A api2 responde a filtro vazio com `status: Erro`, código 20, "A consulta não
    # retornou registros". Tratar isso como falha fazia a carga inteira abortar quando
    # não havia nenhuma conta com situação "parcial" (visto em produção em 2026-09-03).
    class APIVazia(APIFalsa):
        def _get(self, caminho, params):
            raise TinySemRegistros("A consulta não retornou registros")

    try:
        vazio = list(APIVazia([]).pesquisar_produtos())
        checa("devolve lista vazia em vez de estourar", vazio == [], str(vazio))
    except Exception as erro:
        checa("devolve lista vazia em vez de estourar", False, f"{type(erro).__name__}: {erro}")

    print("\n9c. O ritmo obedece ao limite que a API declara")
    # `x-limit-api` diz quantas chamadas por minuto o plano permite (20 no da empresa).
    # Andar no limite cravado é o que fez a carga levar "API Bloqueada" na 1ª tentativa.
    class RespostaFalsa:
        def __init__(self, limite):
            self.headers = {"x-limit-api": str(limite)}

    api = TinyAPI("t", espera=1.0)
    api._ajustar_ritmo(RespostaFalsa(20))
    checa("20/min vira mais de 3s entre chamadas", api.espera > 3.0, f"{api.espera:.2f}s")
    checa("e sobra folga (menos de 20 chamadas por minuto)", 60 / api.espera < 20,
          f"{60 / api.espera:.1f} chamadas/min")
    api._ajustar_ritmo(RespostaFalsa(120))
    checa("limite maior não acelera abaixo do configurado", api.espera > 3.0, f"{api.espera:.2f}s")
    api2 = TinyAPI("t", espera=1.0)
    api2._ajustar_ritmo(RespostaFalsa("lixo"))
    checa("cabeçalho inválido não quebra nada", api2.espera == 1.0, f"{api2.espera:.2f}s")

    print("\n10. Dry-run não escreve")
    antes_contas = db.query(ContasPagar).count()
    antes_produtos = db.query(Estoque).count()
    checa("conta: diz o que faria",
          salvar_conta(db, "pagar", conta_exemplo(id="888"), dry_run=True)["acao"] == "criaria")
    checa("produto: diz o que faria",
          salvar_produto(db, produto_exemplo(id="888"), saldo="1", dry_run=True)["acao"] == "criaria")
    checa("e nada foi criado", db.query(ContasPagar).count() == antes_contas
          and db.query(Estoque).count() == antes_produtos)

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
