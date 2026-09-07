{#
  Documento que aparece em dois cadastros com nomes que nem parecidos são, e que ninguém
  revisou ainda.

  Por que "nem parecidos": divergência de grafia (pontuação, abreviação, razão social
  atualizada) é ruído e a fusão automática resolve — hoje são 4 casos assim. O que precisa
  de gente é o par cujos nomes começam com palavras diferentes, porque aí existe a hipótese
  ruim: **o documento foi digitado errado e a fusão juntaria dois clientes que não são o
  mesmo.** Foi assim que apareceu o cadastro 2016, cujo nome está corrompido por encoding.

  ⚠️ Este teste é o que impede o silêncio. Sem ele, um par novo entraria fundido sem
  ninguém decidir nada — exatamente como o marcador de grafia nova entrava como venda.

  `severity: warn`: par novo não pode derrubar a silver, mas tem que aparecer. Quando
  aparecer, a decisão vai para `seeds/clientes_revisados.csv`, datada e com motivo.
#}

{{ config(severity = 'warn') }}

with cadastros as (

    select c.documento, c.id, c.nome
    from {{ ref('stg_clientes') }} c
    where c.documento is not null

),

divergentes as (

    select
        documento,
        min(nome) as nome_a,
        max(nome) as nome_b

    from cadastros
    group by documento
    having count(distinct nome) > 1
       -- só o que não é variação de grafia: primeira palavra diferente
       and split_part(min(nome), ' ', 1) <> split_part(max(nome), ' ', 1)

),

ja_revisados as (

    select c.documento
    from cadastros c
    join {{ ref('clientes_revisados') }} r on r.id = c.id

)

select d.documento, d.nome_a, d.nome_b

from divergentes d
where d.documento not in (select documento from ja_revisados)
