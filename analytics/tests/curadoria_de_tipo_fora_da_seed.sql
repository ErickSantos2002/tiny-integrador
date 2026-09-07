{#
  Nota classificada na tela (`PATCH /{id}/tipo`) cuja decisão ainda não foi para o CSV.

  A silver lê a seed primeiro e a bronze de reserva, então a classificação nova continua
  valendo — o risco não é agora, é na próxima recarga: o que só existe na bronze morre com
  ela. Este teste é o lembrete de exportar, e o que impede a diferença de crescer calada.

  Também acusa DIVERGÊNCIA: mesma nota com tipo diferente nos dois lugares, que significa
  que alguém reclassificou depois da última exportação.

  `severity: warn`: curadoria pendente de exportação não é motivo para derrubar a silver.
#}

{{ config(severity = 'warn') }}

with bronze as (

    select id, btrim(tipo) as tipo_bronze
    from {{ source('tiny', 'notas_fiscais') }}
    where tipo is not null and btrim(tipo) <> ''

),

seed as (

    select id, tipo as tipo_seed from {{ ref('notas_tipo_curado') }}

)

select
    b.id,
    b.tipo_bronze,
    s.tipo_seed,
    case when s.id is null then 'nao exportada' else 'divergente' end as situacao

from bronze b
left join seed s on s.id = b.id
where s.id is null
   or s.tipo_seed is distinct from b.tipo_bronze
