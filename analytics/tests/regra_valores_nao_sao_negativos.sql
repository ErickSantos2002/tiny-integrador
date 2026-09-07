{#
  Regra de negócio (6.1): dinheiro e quantidade não são negativos nos fatos.

  Medido em 2026-09-06: **zero ocorrências hoje** nos dois fatos. O teste existe para o dia
  em que deixar de ser verdade — devolução lançada como valor negativo em vez de nota
  própria é o jeito clássico de isso acontecer, e some no meio da soma do faturamento sem
  mudar nada visivelmente.

  ⚠️ `dias_de_atraso` PODE ser negativo (pagou adiantado) e não entra aqui — negativo lá é
  informação, não defeito. Confundir os dois é o motivo de este teste listar as colunas em
  vez de varrer todas.

  `severity: error`: valor negativo em fato é defeito estrutural, não dívida conhecida.
#}

{{ config(severity = 'error') }}

select 'fato_vendas' as fato, sk_venda_item::text as chave, 'valor_nota_rateado' as coluna, valor_nota_rateado as valor
from {{ ref('fato_vendas') }} where valor_nota_rateado < 0

union all
select 'fato_vendas', sk_venda_item::text, 'valor_unitario', valor_unitario
from {{ ref('fato_vendas') }} where valor_unitario < 0

union all
select 'fato_vendas', sk_venda_item::text, 'quantidade', quantidade
from {{ ref('fato_vendas') }} where quantidade <= 0

union all
select 'fato_contas_receber', sk_conta::text, 'valor', valor
from {{ ref('fato_contas_receber') }} where valor < 0

union all
select 'fato_contas_receber', sk_conta::text, 'saldo', saldo
from {{ ref('fato_contas_receber') }} where saldo < 0

union all
-- saldo maior que o valor da conta significa que se deve mais do que foi cobrado
select 'fato_contas_receber', sk_conta::text, 'saldo > valor', saldo
from {{ ref('fato_contas_receber') }} where saldo > valor
