{#
  `fato_vendas` — o centro do star schema (item 5.7).

  **Grão: ITEM DA NOTA**, decidido na 2.4. É o grão que permite responder "quanto cada
  produto faturou"; no grão de nota essa pergunta é impossível, e no grão de item ela é uma
  soma.

  **Este modelo não decide o que é venda.** Quem decide é `silver.vendas` (item 4.6), a
  definição única — CFOP pelo campo estruturado, exportação 7102 incluída, cancelamento
  pelo de-para de marcadores. Aqui só se troca chave natural por chave de dimensão e se
  organizam as métricas. Colocar régua nos dois lugares é como o faturamento passou anos
  divergindo entre relatórios.

  ## Por que `left join` em toda dimensão, e nunca `inner`

  `inner join` num star schema é uma armadilha silenciosa: a linha que não encontra
  dimensão **some do fato**, e o total encolhe sem ninguém ver. Aqui cada dimensão tem
  membro "não informado" ou cobertura verificada, e o `coalesce` manda a linha para ele.
  O teste `fato_vendas_reconcilia_com_a_silver` existe justamente para provar que nenhum
  centavo se perdeu no caminho.

  ## As métricas ficam SEPARADAS (2.4)

  `valor_nota_rateado` é o faturamento (a régua). `valor_total_item`, `frete`, `desconto` e
  `icms` vêm ao lado, cada um na própria coluna, em vez de um "valor" polivalente que
  significa coisas diferentes conforme o filtro.
  ⚠️ **`valor_nota_cheio` NÃO entra no fato.** É o valor da NOTA repetido em cada item —
  somá-lo inflaria o faturamento em 28%. Ele existe na silver para conferir
  o rateio, e é exatamente o tipo de coluna que alguém soma por engano num BI. Fora daqui.
#}

{{ config(materialized = 'table') }}

with vendas as (

    select * from {{ ref('vendas') }}

),

-- id do cadastro → identidade canônica: sem esta ponte, as 34 notas dos cadastros
-- duplicados (item 4.4) apontariam para um cliente que a dimensão não reconhece
de_para as (

    select id_cadastro, chave_cliente from {{ ref('de_para_clientes') }}

),

cliente as (

    select chave_cliente, sk_cliente, cidade, uf from {{ ref('dim_cliente') }}

),

geografia as (

    select sk_geografia, cidade, uf from {{ ref('dim_geografia') }}

),

produto as (

    select id_produto, sk_produto from {{ ref('dim_produto') }}

),

vendedor as (

    select id_vendedor, sk_vendedor from {{ ref('dim_vendedor') }}

)

select
    -- ------------------------------------------------------------------ chaves
    v.id_item                                       as sk_venda_item,

    v.data_emissao                                  as data_venda,
    c.sk_cliente,
    p.sk_produto,

    -- Cliente sem cidade ou sem UF (18 e 12 na dimensão) faz o join por par cidade+UF
    -- falhar — NULL não casa com NULL. São 5 itens, e sem este coalesce eles ficariam com
    -- chave nula e sumiriam de qualquer análise por região: o total por região deixaria de
    -- fechar com o total geral, pela diferença mais difícil de explicar que existe.
    coalesce(g.sk_geografia, md5('nao informada' || '|' || '--'))  as sk_geografia,

    -- o vendedor não atribuído (74,1% do faturamento) cai no membro próprio, não em NULL
    coalesce(ven.sk_vendedor, md5('nao-informado')) as sk_vendedor,

    -- ------------------------------------------- dimensões degeneradas (ficam no fato)
    v.id_nota,
    v.numero_nota,
    v.chave_acesso,
    v.cfop,
    v.mercado,

    -- ------------------------------------------------------------------ métricas
    v.quantidade,
    v.valor_unitario,
    v.valor_total_item,
    v.valor_nota_rateado,
    v.valor_frete_rateado,
    v.valor_desconto_rateado,
    v.valor_icms_rateado

from vendas v
left join de_para    dp  on dp.id_cadastro  = v.id_cliente
left join cliente    c   on c.chave_cliente = dp.chave_cliente
left join geografia  g   on g.cidade = c.cidade and g.uf = c.uf
left join produto    p   on p.id_produto    = v.id_produto
left join vendedor   ven on ven.id_vendedor = v.id_vendedor::text
