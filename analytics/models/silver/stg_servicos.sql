{#
  NFS-e (nota de serviço), tipada e com o tomador identificável (itens 4.1 e 4.8).

  Esta era uma das duas ILHAS descobertas na 1.4: a tabela não tem `id_cliente`, só o
  CPF/CNPJ do tomador em texto com máscara inconsistente. Sem o documento em dígitos não
  havia como perguntar "quanto este cliente comprou de produto E de serviço" — que é
  exatamente a pergunta de negócio da 1.7.

  ⚠️ **Os nomes das colunas vêm do leiaute da prefeitura**, com acento e espaço
  (`"data_da_emissão_nfs_e_dsr_e"`). Um erro de digitação num nome desses não dá erro de
  compilação óbvio, dá coluna faltando. Renomear aqui é o que impede esse nome de vazar
  para todo modelo daqui pra frente.

  ⚠️ **Todos os valores chegam como `text`.** Medido em 2026-09-06 nas 5.227 linhas: ponto
  decimal, nenhuma vírgula, nenhum vazio, 100% conversível — então o cast é seguro. Mas ele
  precisa estar em UM lugar só: `sum()` sobre texto não soma, concatena ou estoura, e o dia
  em que a prefeitura mandar `1.234,56` isto aqui é que quebra, não os cinco modelos abaixo.

  Nenhuma regra de negócio aqui: o que conta como faturamento de serviço é assunto da
  camada de cima, como em `vendas.sql`.
#}

with bronze as (

    select * from {{ source('tiny', 'servicos') }}

),

{#
  Curadoria humana em CSV versionado (item 4.9). `cancelada` NÃO vem da origem: o leiaute
  nacional entrega cancelamento como Evento separado, ainda não tratado na importação
  (defeito D11), então alguém marca à mão. São 223 NFS-e — e é isso que
  impede nota cancelada de contar como faturamento. Perder essa marca numa recarga
  INFLA o faturamento em silêncio, que é o defeito mais caro que este projeto já viu.
#}
cancelada_curada as (

    select id, cancelada from {{ ref('nfse_cancelada_curada') }}

),

limpo as (

    select
        bronze.id,
        "nº_da_nota_fiscal_eletrônica"                          as numero_nfse,
        -- ⚠️ É CÓDIGO NUMÉRICO, não texto — mesma armadilha do `situacao` das notas
        -- fiscais, que em 2026-09-05 custou uma investigação inteira. Nome explícito
        -- para ninguém filtrar por 'cancelada' aqui e receber zero linhas sem erro.
        status_da_nota_fiscal                                    as status_codigo,
        "data_da_emissão_nfs_e_dsr_e"::date                      as data_emissao,
        "data_de_competência"::date                              as data_competencia,
        nullif(btrim("data_de_cancelamento"), '')::date          as data_cancelamento,

        -- ⚠️ CURADORIA MANUAL, não vem da origem: o leiaute nacional entrega cancelamento
        -- como Evento separado, ainda não tratado na importação (defeito D11). NFS-e
        -- cancelada que ninguém marcou conta como faturamento até hoje.
        -- seed primeiro, bronze de reserva (item 4.9)
        coalesce(cancelada_curada.cancelada, bronze.cancelada, false)   as cancelada,

        -- ---------------------------------------------------------------- tomador
        -- A CHAVE que tira esta tabela do isolamento. `clientes.chave_cliente` é o mesmo
        -- documento em dígitos, então o join existe sem depender de `id_cliente`.
        {{ so_digitos('"cpf_cnpj_do_tomador"') }}                as documento_tomador,
        {{ normalizar_texto('"razão_social_do_tomador"') }}      as nome_tomador,
        {{ normalizar_texto('"cidade_do_tomador"') }}            as cidade_tomador,
        upper(nullif(btrim("uf_do_tomador"), ''))                as uf_tomador,

        -- --------------------------------------------------------------- serviço
        -- Candidato a separar as LINHAS DE SERVIÇO (defeito D10): 62* parece Plataforma,
        -- 33* parece calibração. ⚠️ O mesmo código aparece como `3312102` e `3312102.0`
        -- porque a COLUNA É `numeric` e a escala aparece no texto — não foi float na
        -- importação, como o glossário dizia até 2026-09-06. O cast + `split_part` no
        -- ponto é o que torna os dois comparáveis.
        nullif(split_part(btrim("código_de_atividade_municipal"::text), '.', 1), '')
                                                                 as codigo_atividade,
        {{ normalizar_texto('"discriminação_dos_serviços"') }}   as discriminacao,

        -- ---------------------------------------------------------------- valores
        -- Cast concentrado aqui (ver cabeçalho).
        coalesce(nullif(btrim("valor_dos_serviços"), '')::numeric, 0)   as valor_servicos,
        coalesce(nullif(btrim("valor_do_iss"), '')::numeric, 0)         as valor_iss,
        coalesce(nullif(btrim("valor_das_deduções"), '')::numeric, 0)   as valor_deducoes,
        coalesce(nullif(btrim("valor_total_recebido"), '')::numeric, 0) as valor_total_recebido,
        iss_retido

    from bronze
    left join cancelada_curada on cancelada_curada.id = bronze.id

)

select * from limpo
