{#
  Monitor de volume (item 6.4) — "hoje chegaram 3 notas em vez de 300".

  **Nenhum teste tradicional pega isso, porque o job termina feliz.** A carga roda, não dá
  erro, registra sucesso — e traz um centésimo do que deveria. O `freshness` (0.14) também
  não pega: para ele a carga rodou, e rodou mesmo.

  ⚠️ **Filtra dry-run, e isso não é detalhe.** Medido em 2026-09-06: **11 das 20 execuções
  registradas eram dry-run** de investigação (58% do histórico), incluindo cargas de 1
  registro. Comparar volume real com esse ruído produziria alarme todo dia.
  🔧 **O conserto de raiz é no extrator**, que não deveria registrar dry-run em
  `execucoes_job` — dry-run não é carga. Enquanto isso não muda, o filtro mora aqui.

  ## A regra, e por que ela se recusa a julgar

  Compara o volume da execução com a **mediana das últimas execuções do mesmo job no mesmo
  dia da semana** — sábado trazer 1 nota é normal, terça não. Mediana e não média porque um
  backfill (7.442 contas numa noite) arrastaria a média por semanas.

  🔴 **Com menos de `{{ var('minimo_execucoes_para_julgar', 5) }}` execuções comparáveis, o
  veredito é `sem base de comparacao` — não `ok`.** Isso é deliberado: em 2026-09-06 o
  histórico tem 2 dias, e um monitor que julgasse com duas amostras produziria alarme
  falso na primeira segunda-feira. Monitor que erra no começo é desligado antes de ficar
  útil. Ele passa a valer sozinho, conforme o histórico cresce.
#}

{{ config(materialized = 'view') }}

with execucoes as (

    select
        id,
        job,
        inicio,
        fim,
        resultado,
        erros,
        argumentos,
        -- volume = soma de todas as contagens; a chave varia por job
        (select coalesce(sum(value::numeric), 0)
           from jsonb_each_text(contagens)) as volume

    from {{ source('operacao', 'execucoes_job') }}
    where resultado = 'sucesso'
      and fim is not null
      -- ver aviso do cabeçalho
      and coalesce(argumentos, '') not like '%--dry-run%'
      and coalesce(argumentos, '') not like '%--limite%'

),

com_referencia as (

    select
        e.*,
        extract(isodow from e.inicio)::int as dia_da_semana,

        -- mediana e contagem das OUTRAS execuções do mesmo job e dia da semana
        (select percentile_cont(0.5) within group (order by o.volume)
           from execucoes o
          where o.job = e.job
            and extract(isodow from o.inicio) = extract(isodow from e.inicio)
            and o.id <> e.id)                                       as volume_mediano,

        (select count(*)
           from execucoes o
          where o.job = e.job
            and extract(isodow from o.inicio) = extract(isodow from e.inicio)
            and o.id <> e.id)                                       as execucoes_comparaveis

    from execucoes e

)

select
    id,
    job,
    inicio,
    dia_da_semana,
    volume,
    volume_mediano,
    execucoes_comparaveis,

    case
        when execucoes_comparaveis < {{ var('minimo_execucoes_para_julgar', 5) }}
            then 'sem base de comparacao'
        when volume_mediano is null or volume_mediano = 0
            then 'sem base de comparacao'
        when volume < volume_mediano * 0.25
            then 'volume MUITO abaixo do normal'
        when volume < volume_mediano * 0.5
            then 'volume abaixo do normal'
        when volume > volume_mediano * 4
            then 'volume muito acima do normal'
        else 'ok'
    end                                                             as veredito

from com_referencia
