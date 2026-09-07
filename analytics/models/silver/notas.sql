{#
  A nota fiscal completa, uma linha por nota (item 4.7).

  A normalização do Tiny espalha a nota em tabelas satélite. Isso serve ao ERP e atrapalha
  a análise: quem quiser "faturamento por transportadora" ou "venda com entrega em outro
  estado" hoje precisa lembrar de três joins e acertar a cardinalidade de cada um. Achatar
  aqui é o que faz esse conhecimento existir UMA vez.

  ⚠️ **A cardinalidade não é a que o roadmap dizia.** Medida em 2026-09-06:

    | tabela              | linhas | notas | máx por nota |
    |---------------------|--------|-------|--------------|
    | `enderecos_entrega` | 8.176  | 8.176 | **1**        |
    | `formas_envio`      | 8.149  | 8.149 | **1**        |
    | `marcadores`        | 8.162  | 8.113 | **3**        |

  `marcadores` **NÃO é 1:1** — são 43 notas com mais de um. Achatar as três com o mesmo
  `left join` duplicaria essas 43 notas, e como o marcador é o que abate faturamento
  (decisão D8), a duplicata **inflaria o valor** sem quebrar nada visível. Por isso
  marcador entra AGREGADO, não por join.

  Grão: **uma linha por nota**. Quem precisa do grão de item usa `vendas`.
  Nenhuma regra de negócio aqui — quem decide o que é venda continua sendo `vendas.sql`.
#}

with notas as (

    select * from {{ ref('stg_notas_fiscais') }}

),

entrega as (

    -- 1:1 verificado, e o teste `unique` em `id_nota` no schema.yml é o que mantém isso
    -- verdadeiro: se a origem passar a mandar dois endereços, o build acusa em vez de
    -- duplicar a nota em silêncio.
    select
        id_nota,
        {{ normalizar_texto('nome_destinatario') }}  as entrega_destinatario,
        {{ so_digitos('cpf_cnpj') }}                 as entrega_documento,
        {{ normalizar_texto('cidade') }}             as entrega_cidade,
        upper(nullif(btrim(uf), ''))                 as entrega_uf,
        {{ so_digitos('cep') }}                      as entrega_cep

    from {{ source('tiny', 'enderecos_entrega') }}

),

envio as (

    select
        id_nota,
        id_forma                             as forma_envio_id,
        {{ normalizar_texto('descricao') }}  as forma_envio

    from {{ source('tiny', 'formas_envio') }}

),

marcadores as (

    -- AGREGADO, não join: ver o aviso do cabeçalho. `bool_or` responde a pergunta que a
    -- régua faz ("esta nota tem algum marcador que exclui?") sem multiplicar linha.
    select
        id_nota,
        count(*)                                                   as qtd_marcadores,
        bool_or(exclui_do_faturamento)                             as tem_marcador_que_exclui,
        string_agg(descricao, ' | ' order by descricao)            as marcadores,
        string_agg(distinct conceito, ' | ' order by conceito)     as conceitos_marcador

    from {{ ref('stg_marcadores') }}
    group by id_nota

)

select
    n.*,

    e.entrega_destinatario,
    e.entrega_documento,
    e.entrega_cidade,
    e.entrega_uf,
    e.entrega_cep,

    -- entrega em UF diferente da do cliente é o começo da análise de logística, e só é
    -- barato de perguntar depois que a nota está achatada
    v.forma_envio_id,
    v.forma_envio,

    coalesce(m.qtd_marcadores, 0)               as qtd_marcadores,
    coalesce(m.tem_marcador_que_exclui, false)  as tem_marcador_que_exclui,
    m.marcadores,
    m.conceitos_marcador

from notas n
left join entrega    e on e.id_nota = n.id
left join envio      v on v.id_nota = n.id
left join marcadores m on m.id_nota = n.id
