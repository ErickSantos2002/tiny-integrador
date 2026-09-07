{#
  Contas a receber, tipadas e com o sacado identificável (itens 4.1 e 4.8).

  A segunda ILHA da 1.4: como a NFS-e, esta tabela não tem `id_cliente` — só o CPF/CNPJ do
  sacado em texto. Com o documento em dígitos, "quanto este cliente já pagou" passa a ser
  um join, e não uma planilha.

  ⚠️ **A série só virou confiável em 2026-09-06.** Antes do backfill (itens 0.13 e 0.15) a
  tabela tinha 1.606 linhas, 1.516 delas de 2026: o fluxo do n8n nunca funcionou aqui. Hoje
  são 9.634, começando em 2015. Análise feita sobre um dump anterior a essa data está
  medindo o vazio, não a empresa.

  ⚠️ **`excluida_na_origem_em` preenchido = o Tiny não reconhece mais esta conta.** O
  financeiro exclui a conta vencida e reemite com id novo, então a linha ficaria `aberto`
  para sempre. NÃO somar essas em "em aberto" — eram 41 em 2026-09-05.
#}

with bronze as (

    select * from {{ source('tiny', 'contas_receber') }}

),

limpo as (

    select
        id,
        id_tiny,

        data                                             as data_emissao,
        vencimento,
        liquidacao,
        competencia,

        coalesce(valor, 0)                               as valor,
        coalesce(saldo, 0)                               as saldo,

        {{ normalizar_texto('situacao') }}               as situacao,
        {{ normalizar_texto('categoria') }}              as categoria,
        {{ normalizar_texto('historico') }}              as historico,
        {{ normalizar_texto('forma_pagamento') }}        as forma_pagamento,
        {{ normalizar_texto('portador') }}               as portador,
        nro_documento                                    as numero_documento,
        ocorrencia,

        -- ---------------------------------------------------------------- sacado
        -- A chave que tira a tabela do isolamento — a mesma de `clientes.chave_cliente`.
        {{ so_digitos('cliente_cpf_cnpj') }}             as documento_sacado,
        {{ normalizar_texto('cliente_nome') }}           as nome_sacado,
        {{ normalizar_texto('cliente_cidade') }}         as cidade_sacado,
        upper(nullif(btrim(cliente_uf), ''))             as uf_sacado,
        cliente_codigo                                   as codigo_sacado,

        -- Ver o aviso do cabeçalho: conta marcada aqui não existe mais na origem.
        excluida_na_origem_em,
        excluida_na_origem_em is not null                as excluida_na_origem,

        -- Data de carga. Só passou a existir de verdade em 2026-09-06: até então o
        -- extrator mandava NULL explícito e desligava o DEFAULT da coluna, o que deixava
        -- o `freshness` cego. Ver item 0.13.
        created_at,
        updated_at

    from bronze

)

select * from limpo
