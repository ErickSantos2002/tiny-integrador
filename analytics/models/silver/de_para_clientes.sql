{#
  De-para de cliente: id do cadastro → cliente canônico (item 4.4).

  Existe porque a fusão não pode se limitar a escolher uma linha: em 19 dos 20 documentos
  duplicados, os DOIS cadastros têm nota emitida. Sem este mapa, 34 notas apontariam para
  um id que a silver deixou de reconhecer — e o cliente "sumiria" da análise sem erro
  nenhum, que é a forma silenciosa de errar que este projeto já viu várias vezes.

  Uso: `join de_para_clientes d on d.id_cadastro = n.id_cliente`, e depois `chave_cliente`
  para chegar em `clientes`. Serve igual para as fontes que só têm o documento em texto
  (`servicos`, `contas_*`, item 4.8) — lá o caminho é pelo próprio documento.
#}

with canonico as (

    select chave_cliente, id_canonico, documento, ids_originais
    from {{ ref('clientes') }}

)

select
    id_cadastro,
    chave_cliente,
    id_canonico,
    documento,
    id_cadastro = id_canonico   as e_o_canonico

from canonico,
     unnest(ids_originais) as id_cadastro
