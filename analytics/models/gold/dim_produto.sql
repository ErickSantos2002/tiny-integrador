{#
  Dimensão de produto (item 5.3).

  ⚠️ **O item 5.3 do roadmap está desatualizado e o star schema é que estava certo.**
  O item dizia "derivada de `itens_nota` por dedupe de `codigo`, não existe tabela de
  produto no Tiny". Passou a existir: `tiny.estoque` tem 280 produtos. E medido em
  2026-09-06, `codigo` é a chave errada:

    | chave        | itens que casam | % |
    |--------------|-----------------|---|
    | `id_produto` | 9.078           | **95,1%** |
    | `codigo`     | 5.297           | 55,5% |

  ## Por que o estoque sozinho não serve

  **15 produtos vendidos não estão no estoque** — e não são resíduo: carregam
  perto de **19% do faturamento** em itens. Uma dimensão feita só do
  cadastro deixaria esse valor apontando para "produto desconhecido", que é a mesma
  armadilha que a `dim_cliente` (5.2) evitou do outro lado.

  Na direção oposta, **115 produtos do estoque nunca foram vendidos**. Eles ENTRAM assim
  mesmo: produto existe independentemente de ter saído, e uma dimensão que só contém o que
  foi vendido não responde "o que temos em catálogo e não vende".

  ## Procedência, como na dim_cliente
  `procedencia` diz se o produto veio do cadastro, se é órfão (só aparece em nota) ou se é
  os dois. Sem isso, "produto sem preço de custo" parece defeito quando é só órfão.

  ⚠️ SCD Tipo 2 é o item 5.4 e ainda não está aqui: **esta dimensão é Tipo 1 hoje** e
  sobrescreve. O alerta do 5.4 é literal — histórico não se recupera depois.
#}

{{ config(materialized = 'table') }}

with estoque as (

    select
        id::text                                     as id_produto,
        {{ normalizar_texto('nome') }}               as nome,
        nome                                         as nome_original,
        codigo::text                                 as codigo_produto,
        nullif(btrim(unidade), '')                   as unidade,
        situacao,
        preco,
        preco_custo,
        preco_custo_medio,
        saldo,
        data_criacao
    from {{ source('tiny', 'estoque') }}

),

vendidos as (

    -- Um produto por id, com a descrição do item MAIS RECENTE: descrição de item muda ao
    -- longo do tempo (o vendedor reescreve), e a mais nova é a que as pessoas reconhecem.
    select distinct on (i.id_produto)
        i.id_produto,
        i.descricao          as descricao_no_item,
        i.codigo_produto     as codigo_no_item,
        i.unidade            as unidade_no_item
    from {{ ref('stg_itens_nota') }} i
    join {{ ref('stg_notas_fiscais') }} n on n.id = i.id_nota
    where i.id_produto is not null
    order by i.id_produto, n.data_emissao desc nulls last

),

todos as (

    select id_produto from estoque
    union
    select id_produto from vendidos

),

unido as (

    select
        t.id_produto,

        e.id_produto is not null                     as existe_no_estoque,
        v.id_produto is not null                     as ja_foi_vendido,

        -- cadastro primeiro; a descrição da nota entra quando o produto é órfão
        coalesce(e.nome, v.descricao_no_item)        as nome,
        coalesce(e.codigo_produto, v.codigo_no_item) as codigo_produto,
        coalesce(e.unidade, v.unidade_no_item)       as unidade,

        e.situacao,
        e.preco,
        e.preco_custo,
        e.preco_custo_medio,
        e.saldo,
        e.data_criacao

    from todos t
    left join estoque  e on e.id_produto = t.id_produto
    left join vendidos v on v.id_produto = t.id_produto

)

select
    md5(id_produto)     as sk_produto,
    id_produto,
    nome,
    codigo_produto,
    unidade,

    existe_no_estoque,
    ja_foi_vendido,
    case
        when existe_no_estoque and ja_foi_vendido then 'cadastrado e vendido'
        when existe_no_estoque                    then 'em catalogo, nunca vendido'
        else 'orfao: vendido sem cadastro'
    end                 as procedencia,

    -- ⚠️ `situacao` do Tiny: A = ativo, I = inativo. Nulo em órfão, porque órfão não tem
    -- cadastro para estar ativo ou não — não é "situação desconhecida", é ausência de
    -- cadastro, e as duas coisas se parecem num filtro descuidado.
    situacao,
    preco,
    preco_custo,
    preco_custo_medio,
    saldo,
    data_criacao

from unido
