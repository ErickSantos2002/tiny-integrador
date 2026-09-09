"""Paginação das listagens da API.

## Por que existe

As listagens nasceram devolvendo `query.all()` — a tabela inteira, sem teto. Hoje isso são
alguns milhares de linhas e funciona; o problema é que não há nada entre "funciona" e "a
API cai", e a fronteira se move sozinha conforme a base cresce.

## Por que nem toda listagem pode ser paginada ainda

Paginar um endpoint cujo consumidor desenha **gráfico agregado** não conserta nada: quebra
o número, e em silêncio — a tela soma o que recebeu, e a primeira página passa a ser lida
como o total. Não haveria erro, só um faturamento menor.

Por isso a paginação entra primeiro onde é inofensiva: nas listagens que nenhuma tela
consome hoje. As demais entram quando a agregação delas mudar para o banco (itens 9.2/9.3
do roadmap), e essa é a ordem — não o contrário.

## O formato

Envelope, e não lista pelada. Uma lista de 100 itens não diz se existem 100 ou 10.000, e
quem consome acaba adivinhando pelo tamanho da resposta — que é o que se faz quando a
informação não está lá. Com `total` no corpo, a tela sabe quantas páginas existem antes de
pedir a segunda.
"""

from typing import Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy.orm import Query as OrmQuery

T = TypeVar("T")

# 100 por página é o suficiente para uma tela de tabela, e 1.000 é o teto do que se aceita
# pedir de uma vez. O teto é o ponto: sem ele, `limite=999999999` reinventa o `query.all()`
# que este módulo existe para aposentar.
LIMITE_PADRAO = 100
LIMITE_MAXIMO = 1000


def limite_query(padrao: int = LIMITE_PADRAO) -> int:
    return Query(padrao, ge=1, le=LIMITE_MAXIMO, description="Itens por página")


def offset_query() -> int:
    return Query(0, ge=0, description="Quantos itens pular")


class Pagina(BaseModel, Generic[T]):
    """Uma fatia de uma listagem, com o tamanho do todo junto."""

    itens: list[T]
    #: Quantas linhas o filtro encontrou — não quantas vieram nesta página.
    total: int
    limite: int
    offset: int


def paginar(query: OrmQuery, limite: int, offset: int) -> dict:
    """Conta o total e devolve a fatia pedida.

    A contagem sai do banco, e não de `len(query.all())` — contar em Python exigiria
    trazer tudo, que é exatamente o que se está evitando.

    ⚠️ **`query.count()`, e não `with_entities(func.count())`.** O segundo parece o mesmo
    e não é: `func.count()` não referencia coluna nenhuma, então o SQLAlchemy não tem de
    onde inferir o `FROM` e emite `SELECT count(*)` **solto**. O Postgres aceita — é uma
    consulta válida sobre nenhuma linha — e devolve **1**. Sem erro, sem aviso, e uma
    listagem de oito mil marcadores dizendo `total: 1`. Medido aqui antes de virar bug.

    `order_by(None)` porque ordenar para contar é trabalho jogado fora.
    """
    total = query.order_by(None).count()
    itens = query.limit(limite).offset(offset).all()
    return {"itens": itens, "total": total or 0, "limite": limite, "offset": offset}
