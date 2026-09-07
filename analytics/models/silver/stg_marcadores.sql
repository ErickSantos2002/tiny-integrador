{#
  Marcadores da nota, normalizados e CLASSIFICADOS.

  Este é o model mais importante da silver, e o motivo está no glossário: a decisão D8
  é que devolução NÃO abate faturamento — a venda devolvida sai pelo marcador. Ou seja,
  todo o abatimento do faturamento depende desta classificação estar certa.

  Como classifica, decidido em 2026-09-05 (item 4.2b):

    1. RADICAL sobre o texto normalizado. Cobre a grafia livre sem precisar prever cada
       frase: `aparelho devolvido dia 14/07/2025` carrega a data dentro do texto, então
       nasce uma grafia nova a cada ocorrência — igualdade exata é inviável por construção.

    2. SEED de exceções (`marcadores_excecoes`), que vence o radical nos dois sentidos:
       força a exclusão de grafia que o radical não pega (erro de digitação, sinônimo) e
       impede a exclusão de grafia que ele pega por engano.

  ⚠️ O radical é `devol`, não `devolv`. "devolução" não contém "devolv" — perderia
  `devolução do equipamento` e `nota devolução de mercadoria`. Erro cometido e corrigido
  ao medir; fica anotado para não voltar.

  ⚠️ `carta de correção` é o marcador MAIS COMUM da base (316 notas) e NÃO é cancelamento.
  Radical mais largo mataria faturamento legítimo. É o motivo de a lista ser curta.
#}

with bronze as (

    select
        id,
        id_nota,
        descricao as descricao_original,
        -- Identificador numerico longo nao e categoria de marcador: a chave de acesso
        -- de NF-e tem 44 digitos e apareceu como descricao. Vira mascara para que a
        -- seed de curadoria possa ser versionada sem carregar o numero do documento
        -- fiscal (com a chave se consulta a nota inteira na SEFAZ).
        regexp_replace({{ normalizar_texto('descricao') }}, '[0-9]{20,}', 'identificador', 'g') as descricao
    from {{ source('tiny', 'marcadores') }}
    -- linha sem descrição é registro-fantasma da carga antiga do n8n: uma linha por nota
    -- mesmo quando não havia marcador nenhum. Não é marcador, não classifica.
    where descricao is not null

),

excecoes as (
    select
        regexp_replace({{ normalizar_texto('descricao') }}, '[0-9]{20,}', 'identificador', 'g') as descricao,
        conceito,
        exclui_do_faturamento
    from {{ ref('marcadores_excecoes') }}
),

classificado as (

    select
        b.id,
        b.id_nota,
        b.descricao_original,
        b.descricao,

        -- a seed vence o radical, nos dois sentidos
        coalesce(
            e.conceito,
            case
                when b.descricao ~ 'cancel'    then 'cancelamento'
                when b.descricao ~ 'devol'     then 'devolucao'
                when b.descricao ~ 'recusad'   then 'recusa'
                when b.descricao ~ 'rejeit'    then 'rejeicao'
                when b.descricao ~ 'inutiliz'  then 'inutilizacao'
                when b.descricao ~ 'nao quis'  then 'recusa'
                when b.descricao ~ '^loca'     then 'locacao'
                else 'neutro'
            end
        ) as conceito,

        coalesce(
            e.exclui_do_faturamento,
            b.descricao ~ '(cancel|devol|recusad|rejeit|inutiliz|nao quis)'
        ) as exclui_do_faturamento,

        (e.descricao is not null) as veio_da_seed

    from bronze b
    left join excecoes e on e.descricao = b.descricao

)

select * from classificado
