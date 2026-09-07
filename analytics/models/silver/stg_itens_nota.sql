{#
  Itens da nota, tipados (item 4.1, cobrado pela Fase 5).

  Ficou de fora até agora de propósito: staging sem consumidor é código morto. A
  `dim_produto` (5.3) pediu, então entra.

  ⚠️ **Os tipos da FK não batem entre as tabelas.** `itens_nota.id_produto` e
  `itens_nota.codigo` são `varchar`; em `tiny.estoque` os equivalentes (`id` e `codigo`)
  são `integer`. Um join ingênuo entre as duas nem compila — devolve
  `operator does not exist: integer = character varying`. O cast fica concentrado aqui
  para que nenhum modelo acima tenha que lembrar disso.

  ⚠️ **`id_produto` é a chave boa, `codigo` não.** Medido em 2026-09-06 sobre as 9.542
  linhas: por `id_produto` casam **9.078 (95,1%)** com o estoque; por `codigo`, apenas
  **5.297 (55,5%)**. O item 5.3 do roadmap dizia "dedupe de código" — o star schema, que
  dizia `id_produto`, é que estava certo.
#}

with bronze as (

    select * from {{ source('tiny', 'itens_nota') }}

),

limpo as (

    select
        id                                              as id_item,
        id_nota,

        -- a chave que casa com `estoque.id` (que é integer do outro lado)
        nullif(btrim(id_produto), '')                   as id_produto,
        nullif(btrim(codigo), '')                       as codigo_produto,
        {{ normalizar_texto('descricao') }}             as descricao,
        descricao                                       as descricao_original,

        nullif(btrim(unidade), '')                      as unidade,
        nullif(btrim(ncm), '')                          as ncm,

        -- ⚠️ CFOP pelo campo estruturado — é ele que decide o que é venda (decisão D1),
        -- não a natureza da operação, que é texto livre.
        cfop,
        {{ normalizar_texto('natureza') }}              as natureza,

        coalesce(quantidade, 0)                         as quantidade,
        coalesce(valor_unitario, 0)                     as valor_unitario,
        coalesce(valor_total, 0)                        as valor_total

    from bronze

)

select * from limpo
