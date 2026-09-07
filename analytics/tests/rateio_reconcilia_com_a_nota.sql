{#
  FALHA se a soma do faturamento rateado não bater com a soma das notas.

  É o teste de reconciliação (item 5.10 do roadmap), antecipado para cá porque o
  rateio nasce aqui e é a peça mais fácil de quebrar sem ninguém notar.

  O risco concreto: `valor_nota` pertence à NOTA e o grão de `vendas` é ITEM. Qualquer
  erro no rateio — um `join` que duplica linha, uma nota cujo peso não fecha 100%, uma
  divisão que vira NULL — muda o faturamento sem gerar erro nenhum. Medido em
  2026-09-05: repetir o valor cheio em cada item inflaria o faturamento em 28%.
  Um número 28% maior é grande demais para passar despercebido, e pequeno demais para
  alguém desconfiar só de olhar.

  Tolerância de R$ 0,01 por causa de arredondamento de ponto flutuante na divisão —
  não é folga para erro de lógica, é o resíduo aritmético de somar 5 mil frações.

  `error` de propósito, ao contrário do teste de grafia nova: grafia nova é evento
  rotineiro do negócio, rateio que não fecha é defeito de código.
#}

with rateado as (
    select sum(valor_nota_rateado) as total from {{ ref('vendas') }}
),

notas as (
    select sum(valor_nota) as total
    from (
        select distinct id_nota, valor_nota_cheio as valor_nota
        from {{ ref('vendas') }}
    ) n
)

select
    r.total   as total_rateado,
    n.total   as total_das_notas,
    r.total - n.total as diferenca
from rateado r
cross join notas n
where abs(coalesce(r.total, 0) - coalesce(n.total, 0)) > 0.01
