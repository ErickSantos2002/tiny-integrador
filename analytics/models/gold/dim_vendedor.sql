{#
  Dimensão de vendedor (item 5.5). Tipo 1 — só existe em NF-e.

  🔴 **O número que muda o que esta dimensão pode prometer:** medido em 2026-09-06,
  **74,1% do faturamento NÃO tem vendedor atribuído.** Só os 25,9% restantes
  (908 notas) têm. A pergunta "faturamento por vendedor" da 1.7 continua respondível,
  mas **sobre um quarto do faturamento** — e quem olhar o gráfico sem esse aviso vai concluir
  que a equipe vende muito menos do que vende.

  ⚠️ **`id_vendedor = 0` NÃO é um vendedor.** São 6.946 notas (85% da base) com id zero e
  nome vazio: é "sem atribuição" gravado como número. Tratar zero como vendedor real criaria
  um fantasma no topo de qualquer ranking, com mais notas que a equipe inteira somada. O
  mesmo vale para o id vazio (190 notas).

  **Membro "não informado":** a dimensão traz uma linha própria para isso, em vez de deixar
  o fato com chave nula. É o padrão dimensional, e a razão é prática: `left join` que não
  acha vira NULL silencioso, e NULL some de `GROUP BY` — a nota sem vendedor desapareceria
  do total em vez de aparecer como "não informado". O total tem que fechar sempre.

  Os 7 vendedores reais têm id e nome estáveis: nenhum id com dois nomes, nenhum nome com
  dois ids (verificado). Não há dedupe a fazer aqui.
#}

{{ config(materialized = 'table') }}

with das_notas as (

    select
        id_vendedor::text                as id_vendedor,
        {{ normalizar_texto('vendedor') }}  as nome
    from {{ ref('stg_notas_fiscais') }}
    where id_vendedor is not null
      and btrim(id_vendedor::text) not in ('', '0')   -- ver aviso do cabeçalho
      and {{ normalizar_texto('vendedor') }} is not null

),

vendedores as (

    select distinct on (id_vendedor)
        id_vendedor,
        nome
    from das_notas
    order by id_vendedor, nome

),

com_nao_informado as (

    select
        id_vendedor,
        nome,
        true    as vendedor_identificado
    from vendedores

    union all

    -- o membro que faz o total fechar
    select
        'nao-informado'  as id_vendedor,
        'sem vendedor atribuido' as nome,
        false            as vendedor_identificado

)

select
    md5(id_vendedor)    as sk_vendedor,
    id_vendedor,
    nome,
    vendedor_identificado

from com_nao_informado
