{#
  Nota que NÃO está em quarentena tem que ter data, situação e ao menos um item (6.1/6.3).

  Antes da 6.3 isto era um `warn` permanente de 22 linhas — e warn permanente é ruído: em
  duas semanas ninguém mais lê. Agora as 22 conhecidas estão registradas com motivo, e este
  teste vigia o que sobra. Se ele acusar, é problema NOVO, e por isso é `error`.

  É a diferença entre "temos 22 notas quebradas há meses" e "apareceu uma nota quebrada
  hoje": a primeira é dívida conhecida, a segunda é incidente.
#}

{{ config(severity = 'error') }}

with em_quarentena as (

    select id_nota from {{ ref('quarentena_notas') }}

),

com_item as (

    select distinct id_nota from {{ ref('stg_itens_nota') }}

)

select
    n.id,
    n.data_emissao,
    n.situacao_codigo,
    i.id_nota is null as sem_item

from {{ ref('stg_notas_fiscais') }} n
left join com_item i on i.id_nota = n.id
where n.id not in (select id_nota from em_quarentena)
  and (n.data_emissao is null or n.situacao_codigo is null or i.id_nota is null)
