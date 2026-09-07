{#
  Regra de negócio (6.1): nada foi emitido ou liquidado no futuro.

  Medido em 2026-09-06: zero ocorrências. Data futura em emissão quase sempre é erro de
  digitação de ano (2062 em vez de 2026) e envenena qualquer série temporal — a linha vai
  para o fim do gráfico e distorce a escala inteira, fazendo os anos reais parecerem planos.

  ⚠️ **Vencimento futuro é NORMAL e não entra aqui** — são 189 contas hoje, e é assim que
  contas a receber funciona. Um teste que reclamasse disso seria desligado na primeira
  semana, com razão.

  `severity: error` para emissão e liquidação: são fatos passados por definição.
#}

{{ config(severity = 'error') }}

select 'nota' as origem, id::text as chave, 'data_emissao' as coluna, data_emissao as data
from {{ ref('stg_notas_fiscais') }} where data_emissao > current_date

union all
select 'conta', id::text, 'data_emissao', data_emissao
from {{ ref('stg_contas_receber') }} where data_emissao > current_date

union all
select 'conta', id::text, 'liquidacao', liquidacao
from {{ ref('stg_contas_receber') }} where liquidacao > current_date

union all
select 'nfse', id::text, 'data_emissao', data_emissao
from {{ ref('stg_servicos') }} where data_emissao > current_date
