{#
  NFS-e marcada como cancelada na bronze e ausente do CSV.

  Vale mais que a de `tipo`: são 223 notas que NÃO podem contar como
  faturamento. Perder essa marca numa recarga não quebra nada visivelmente — só infla o
  número, que é a forma de errar que este projeto mais viu.

  `severity: warn`, mesmo motivo do teste irmão: é lembrete de exportar, não defeito.
#}

{{ config(severity = 'warn') }}

with bronze as (

    select id from {{ source('tiny', 'servicos') }} where cancelada

),

seed as (

    select id from {{ ref('nfse_cancelada_curada') }}

)

select b.id
from bronze b
left join seed s on s.id = b.id
where s.id is null
