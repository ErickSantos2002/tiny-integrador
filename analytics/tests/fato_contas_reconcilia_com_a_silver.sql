{#
  O `fato_contas_receber` tem que ter a mesma contagem e o mesmo valor da silver (5.10).

  Mesma lógica do teste irmão do `fato_vendas`: o fato não aplica regra, só troca chave
  natural por chave de dimensão. Diferença de total = linha perdida ou multiplicada num
  join, que é o erro que não levanta erro.
#}

{{ config(severity = 'error') }}

with silver as (
    select count(*) as linhas, sum(valor) as total, sum(saldo) as saldo
    from {{ ref('stg_contas_receber') }}
),
fato as (
    select count(*) as linhas, sum(valor) as total, sum(saldo) as saldo
    from {{ ref('fato_contas_receber') }}
)
select s.linhas as linhas_silver, f.linhas as linhas_fato,
       s.total as total_silver, f.total as total_fato
from silver s, fato f
where s.linhas <> f.linhas
   or s.total is distinct from f.total
   or s.saldo is distinct from f.saldo
