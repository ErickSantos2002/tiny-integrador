{#
  O `fato_servicos` tem que somar exatamente o mesmo que a `stg_servicos` NAO CANCELADA.

  Mesmo raciocinio do `fato_vendas_reconcilia_com_a_silver`: o fato so troca chave natural
  por chave de dimensao, entao diferenca de total significa linha perdida ou multiplicada
  num join — `inner join` que engole a linha sem dimensao, ou dimensao com chave duplicada
  que multiplica o valor. Os dois mudam o faturamento sem levantar erro nenhum.

  ⚠️ O risco concreto aqui e a `dim_cliente`: o join e por DOCUMENTO, e documento repetido
  na dimensao multiplicaria a nota de servico. A dimensao tem teste de unicidade, mas este
  teste e quem percebe se ela deixar de ter.

  **Tolerancia: ZERO.** As duas somas vem da mesma coluna, sem conta no meio.
#}

{{ config(severity = 'error') }}

with silver as (

    select count(*) as linhas, sum(valor_servicos) as total
    from {{ ref('stg_servicos') }}
    where not coalesce(cancelada, false)

),

fato as (

    select count(*) as linhas, sum(valor_servicos) as total
    from {{ ref('fato_servicos') }}

)

select
    s.linhas as linhas_silver,
    f.linhas as linhas_fato,
    s.total  as total_silver,
    f.total  as total_fato

from silver s, fato f
where s.linhas <> f.linhas
   or s.total  is distinct from f.total
