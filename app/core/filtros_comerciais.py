"""Os filtros que recortam o conjunto de vendas — um lugar só, dois consumidores.

`/faturamento/resumo` (os gráficos) e `/faturamento/vendas` (a tabela) precisam recortar
exatamente o mesmo conjunto: a tela mostra os dois lado a lado, e um KPI somado sobre um
recorte com a tabela mostrando outro é o tipo de divergência que ninguém percebe olhando.
Por isso a cláusula mora aqui, e não copiada nos dois módulos.

O que este módulo NÃO é: régua de faturamento. Quem decide o que é venda é
`gold.fato_vendas`; aqui só se recorta o que já foi decidido.
"""

from datetime import date
from typing import List

from fastapi import HTTPException, Query


class FiltrosComerciais:
    """Os quatro filtros que as telas do Comercial cruzam, lidos da query string.

    Lista vazia e ausência são a mesma coisa — "sem filtro" —, e as duas viram `None`, que
    é o que o SQL testa. A tela manda `cliente_id=1&cliente_id=2`; a ausência do parâmetro
    não pode virar `[]` no SQL, porque `= ANY('{}')` não casa com nada e a tela ficaria
    vazia em vez de completa.
    """

    def __init__(
        self,
        data_inicio: date | None = Query(None, description="Emissão a partir de (inclusive)"),
        data_fim: date | None = Query(None, description="Emissão até (inclusive)"),
        cliente_id: List[int] | None = Query(None, description="Ids de cliente (repetível)"),
        vendedor: List[str] | None = Query(None, description="Nomes de vendedor (repetível)"),
        produto: List[str] | None = Query(
            None,
            description="Códigos de produto (repetível). Item sem código entra como '#' + descrição.",
        ),
    ):
        if data_inicio and data_fim and data_fim < data_inicio:
            raise HTTPException(
                status_code=422,
                detail="`data_fim` não pode ser anterior a `data_inicio`.",
            )
        self.params = {
            "data_inicio": data_inicio,
            "data_fim": data_fim,
            "clientes": cliente_id or None,
            "vendedores": vendedor or None,
            "produtos": produto or None,
        }


# A chave de produto: o código quando existe, e a descrição prefixada por '#' quando não.
# Sem isso os 36 itens sem código cairiam todos no mesmo balde (`NULL`) e apareceriam como
# um produto só — ou sumiriam, que é o que a tela de Produtos fazia.
CHAVE_PRODUTO = "COALESCE(NULLIF(i.codigo, ''), '#' || COALESCE(i.descricao, ''))"

# As notas que passam pelos filtros. `gold.fato_vendas` decide quais notas existem; os
# quatro filtros recortam esse conjunto. O filtro de produto seleciona a NOTA INTEIRA —
# é a semântica que a tela sempre teve: "as vendas em que esse produto aparece", e o valor
# somado é o da nota, não o do item.
CTE_NOTAS = f"""
WITH notas AS (
    SELECT n.id, n.data_emissao, n.valor_nota, n.valor_produtos,
           n.nome_vendedor, n.id_cliente
    FROM tiny.notas_fiscais n
    WHERE n.id IN (SELECT DISTINCT id_nota FROM gold.fato_vendas)
      AND (CAST(:data_inicio AS date) IS NULL
           OR n.data_emissao >= CAST(:data_inicio AS date))
      AND (CAST(:data_fim AS date) IS NULL
           OR n.data_emissao <= CAST(:data_fim AS date))
      AND (CAST(:clientes AS int[]) IS NULL
           OR n.id_cliente = ANY(CAST(:clientes AS int[])))
      -- O mesmo COALESCE do agrupamento, e não a coluna crua: 74% do faturamento não tem
      -- vendedor, então o ranking mostra 'Não informado' como a maior linha. Filtrar por
      -- `nome_vendedor` direto faria clicar nessa linha devolver zero — silenciosamente,
      -- porque zero é uma resposta válida para um filtro.
      AND (CAST(:vendedores AS text[]) IS NULL
           OR COALESCE(NULLIF(n.nome_vendedor, ''), 'Não informado')
              = ANY(CAST(:vendedores AS text[])))
      AND (CAST(:produtos AS text[]) IS NULL
           OR EXISTS (SELECT 1 FROM tiny.itens_nota i
                      WHERE i.id_nota = n.id
                        AND {CHAVE_PRODUTO} = ANY(CAST(:produtos AS text[]))))
)
"""
