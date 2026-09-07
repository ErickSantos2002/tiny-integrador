{#
  Dimensão de geografia (item 5.6) — conforme: serve aos três fatos.

  Cidade **não é chave sozinha**: medido em 2026-09-06, 9 nomes de cidade aparecem em mais
  de uma UF na base. A chave é o par `cidade + uf`, e são 688 pares hoje.

  ⚠️ **`EX` não é uma UF.** São 28 valores de dois caracteres na base, e o Brasil tem 27
  unidades federativas: o extra é `EX`, o código fiscal de **exterior** (2 clientes). Somar
  `EX` como se fosse estado colocaria exportação dentro de uma região brasileira — e a
  decisão D2 diz justamente que exportação conta como venda **marcada**, não diluída. Aqui
  ela vira `regiao = 'exterior'`, visível.

  **Região por UF é fato objetivo** (divisão do IBGE), então é `CASE`, não seed: não muda,
  não depende de opinião, e uma seed para isso seria manutenção sem motivo.

  **Membro "não informado"** pelo mesmo motivo da `dim_vendedor`: 18 clientes sem cidade e
  12 sem UF. Sem essa linha, eles sairiam do `GROUP BY` como NULL e o total por região não
  fecharia com o total geral — o tipo de diferença que ninguém consegue explicar depois.
#}

{{ config(materialized = 'table') }}

with pares as (

    -- A dimensão nasce de onde a geografia é usada: o cliente. Quando `fato_servicos` e
    -- `fato_contas` entrarem, a praça deles já cai aqui pela mesma chave.
    select distinct
        cidade,
        uf
    from {{ ref('dim_cliente') }}
    where cidade is not null and uf is not null

),

classificado as (

    select
        cidade,
        uf,
        case uf
            when 'EX' then 'exterior'
            when 'AC' then 'norte'    when 'AP' then 'norte'    when 'AM' then 'norte'
            when 'PA' then 'norte'    when 'RO' then 'norte'    when 'RR' then 'norte'
            when 'TO' then 'norte'
            when 'AL' then 'nordeste' when 'BA' then 'nordeste' when 'CE' then 'nordeste'
            when 'MA' then 'nordeste' when 'PB' then 'nordeste' when 'PE' then 'nordeste'
            when 'PI' then 'nordeste' when 'RN' then 'nordeste' when 'SE' then 'nordeste'
            when 'DF' then 'centro-oeste' when 'GO' then 'centro-oeste'
            when 'MT' then 'centro-oeste' when 'MS' then 'centro-oeste'
            when 'ES' then 'sudeste'  when 'MG' then 'sudeste'
            when 'RJ' then 'sudeste'  when 'SP' then 'sudeste'
            when 'PR' then 'sul'      when 'RS' then 'sul'      when 'SC' then 'sul'
        end as regiao
    from pares

),

com_nao_informado as (

    select
        cidade,
        uf,
        regiao,
        uf = 'PE'                       as e_pernambuco,
        uf = 'EX'                       as e_exterior,
        true                            as geografia_identificada
    from classificado

    union all

    select
        'nao informada'  as cidade,
        '--'             as uf,
        'nao informada'  as regiao,
        false            as e_pernambuco,
        false            as e_exterior,
        false            as geografia_identificada

)

select
    md5(cidade || '|' || uf)    as sk_geografia,
    cidade,
    uf,
    regiao,
    -- a praça da casa: a H&S é de Recife, e "quanto vendemos fora do estado" é a primeira
    -- pergunta que alguém faz olhando um mapa
    e_pernambuco,
    e_exterior,
    geografia_identificada

from com_nao_informado
