{#
  `notas` tem que ter exatamente uma linha por nota do staging.

  O item 4.7 achata três tabelas satélite de volta para a nota, e duas delas são 1:1 —
  mas `marcadores` NÃO é: 43 notas têm mais de um (até 3). Se alguém trocar a agregação
  por um `left join` inocente, essas 43 viram 90 e ninguém percebe olhando a tela: a
  contagem de notas quase não muda. O estrago aparece no dinheiro, porque marcador é o
  que abate faturamento (decisão D8), e a nota duplicada soma duas vezes.

  `severity: error` de propósito, e é dos poucos que merecem: o efeito é silencioso e
  contamina o número que a empresa olha.
#}

{{ config(severity = 'error') }}

select
    (select count(*) from {{ ref('stg_notas_fiscais') }})  as no_staging,
    (select count(*) from {{ ref('notas') }})              as no_achatado

where (select count(*) from {{ ref('stg_notas_fiscais') }})
   <> (select count(*) from {{ ref('notas') }})
