{#
  O `fato_vendas` tem que somar exatamente o mesmo que `silver.vendas` (item 5.10).

  O fato não aplica régua nenhuma — só troca chave natural por chave de dimensão. Então
  qualquer diferença de total significa que uma linha se perdeu ou se multiplicou num join,
  e é o erro mais perigoso de um star schema: `inner join` que engole a linha sem dimensão,
  ou dimensão com chave duplicada que multiplica o valor. Os dois mudam o faturamento sem
  levantar nenhum erro.

  **Tolerância: ZERO.** Não é rigor excessivo — as duas somas vêm da mesma coluna, sem
  conta no meio. Aqui não há arredondamento a perdoar (o rateio, esse sim, tem tolerância
  de R$ 0,01, e está em `rateio_reconcilia_com_a_nota.sql`).
#}

{{ config(severity = 'error') }}

with silver as (

    select count(*) as linhas, sum(valor_nota_rateado) as total
    from {{ ref('vendas') }}

),

fato as (

    select count(*) as linhas, sum(valor_nota_rateado) as total
    from {{ ref('fato_vendas') }}

)

select
    s.linhas as linhas_silver,
    f.linhas as linhas_fato,
    s.total  as total_silver,
    f.total  as total_fato

from silver s, fato f
where s.linhas <> f.linhas
   or s.total  is distinct from f.total
