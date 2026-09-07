{#
  `fato_contas_receber` — o segundo fato (item 5.8).

  **Existe para provar o *drill across*.** Um star schema com um fato só não prova nada: a
  pergunta que importa é "quanto este cliente comprou E quanto já pagou", e ela só é
  respondível se os dois fatos compartilharem a MESMA `dim_cliente`. É isso que este modelo
  demonstra — e por isso ele vale mais como prova de arquitetura do que como tabela.

  ⚠️ **Grão: a CONTA, não a nota.** Uma venda pode gerar várias parcelas, e uma conta pode
  não ter venda nenhuma (a série vai até 2015, antes de boa parte das notas). Somar este
  fato com `fato_vendas` numa tabela só dupla-contaria faturamento todo mês — eles se
  conversam pelas dimensões conformes, que é exatamente para isso que a matriz de barramento
  serve.

  ## Três datas, três papéis

  Conta tem emissão, vencimento e liquidação, e cada uma responde uma pergunta diferente
  ("quanto faturei em julho" × "quanto vence em julho" × "quanto entrou em julho"). As três
  apontam para `dim_tempo` — é a mesma dimensão em papéis diferentes, e trocar uma pela
  outra é como relatório financeiro fica errado sem parecer errado.

  ## `dias_de_atraso` é o realizado, não o de hoje

  `liquidacao - vencimento`: negativo = pagou adiantado, positivo = pagou atrasado. **É um
  fato histórico e determinístico.** O atraso de uma conta AINDA em aberto depende de "hoje"
  e por isso NÃO entra aqui: fato que muda de valor a cada build deixa de ser fato, e dois
  relatórios rodados em dias diferentes passariam a discordar sem ninguém ter mudado nada.
  Atraso corrente se calcula na consulta, contra a data de referência dela.

  ⚠️ **`excluida_na_origem` (41 contas):** o Tiny não reconhece mais essas
  contas — o financeiro exclui a vencida e reemite com id novo. Elas ficam no fato, porque
  aconteceram, mas com a flag: **somá-las em "em aberto" infla o passivo com dívida que não
  existe mais.**
#}

{{ config(materialized = 'table') }}

with contas as (

    select * from {{ ref('stg_contas_receber') }}

),

cliente as (

    select chave_cliente, sk_cliente, cidade, uf from {{ ref('dim_cliente') }}

),

geografia as (

    select sk_geografia, cidade, uf from {{ ref('dim_geografia') }}

)

select
    -- ------------------------------------------------------------------ chaves
    c.id                                            as sk_conta,
    c.id_tiny,

    -- a MESMA dimensão de cliente do `fato_vendas`: é isso que torna possível somar
    -- compra e pagamento do mesmo cliente
    coalesce(cl.sk_cliente, md5('sem-documento:desconhecido'))  as sk_cliente,
    coalesce(g.sk_geografia, md5('nao informada' || '|' || '--')) as sk_geografia,

    -- três papéis da dim_tempo — ver cabeçalho
    c.data_emissao                                  as data_emissao,
    c.vencimento                                    as data_vencimento,
    c.liquidacao                                    as data_liquidacao,

    -- ------------------------------------------- dimensões degeneradas
    -- `categoria` fica como atributo aqui em vez de virar dimensão própria: o star schema
    -- previa `dim_categoria_financeira`, mas ela só ganha o lugar quando o fato de contas a
    -- PAGAR existir e as duas compartilharem a categoria. Antes disso seria uma dimensão de
    -- um consumidor só, que é uma junção a mais sem nada em troca.
    c.categoria,
    c.forma_pagamento,
    c.portador,
    c.situacao,
    c.numero_documento,

    -- ------------------------------------------------------------------ estado
    c.situacao = 'aberto' and not c.excluida_na_origem   as em_aberto,
    c.situacao = 'cancelada'                             as cancelada,
    c.excluida_na_origem,
    c.documento_sacado is null                           as sacado_sem_documento,

    -- ------------------------------------------------------------------ métricas
    c.valor,
    c.saldo,

    -- realizado: negativo = pagou adiantado. NULL enquanto não liquidou (ver cabeçalho).
    case
        when c.liquidacao is not null then c.liquidacao - c.vencimento
    end                                             as dias_de_atraso

from contas c
left join cliente   cl on cl.chave_cliente = c.documento_sacado
left join geografia g  on g.cidade = cl.cidade and g.uf = cl.uf
