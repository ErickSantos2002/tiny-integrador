{#
  Dimensão de cliente — CONFORME, porque é a união das três fontes (item 5.2).

  A tentação é fazer a dimensão ser uma cópia de `tiny.clientes`. Medido em 2026-09-06, isso
  perderia gente de verdade: **119 tomadores de NFS-e e 143 sacados de contas não estão no
  cadastro do ERP** — quem só comprou serviço, e quem comprou antes de 2018. Sem eles, o
  serviço e o recebimento dessa gente ficariam pendurados em "cliente
  desconhecido".

  Conforme quer dizer: **a mesma dimensão serve aos três fatos** (venda de produto, venda de
  serviço, recebimento), então dá para perguntar "quanto este cliente comprou de tudo e
  quanto já pagou" — que é o *drill across* da 1.7. Isso só é possível porque a chave de
  negócio é a mesma nos três: o CPF/CNPJ em dígitos.

  ## Precedência dos atributos

  O ERP é a fonte rica (endereço, contato, IE); NFS-e e contas trazem só nome e praça. Então
  o atributo vem do ERP quando existe, e das outras fontes quando o cliente **só** existe
  lá. Não é escolha estética: sobrescrever o cadastro com o nome que veio numa nota avulsa
  degradaria o dado bom com o dado pobre.

  ## Chave

  `sk_cliente` é `md5(chave_cliente)` — determinística de propósito. `row_number()` mudaria a
  cada build e quebraria qualquer fato já gravado com a chave antiga; hash da chave de
  negócio é estável entre ambientes e reexecuções.

  🔒 **PII.** A dimensão concentra documento e nome — é o preço de ser a dimensão de
  cliente, e concentrar é melhor que espalhar. **Telefone e e-mail ficaram de fora de
  propósito**: são PII de contato sem uso analítico, e o que não está aqui não vaza daqui.
  ⚠️ Falta o acesso restrito de verdade (`grants` para uma role de analista) — depende de
  criar essa role no banco, que é trabalho de infra ainda não feito. Está anotado no 5.2.
#}

{{ config(materialized = 'table') }}

with erp as (

    select
        chave_cliente,
        documento,
        tipo_documento,
        nome,
        cidade,
        uf,
        id_canonico    as id_no_erp,
        qtd_cadastros  as qtd_cadastros_erp
    from {{ ref('clientes') }}

),

tomadores as (

    -- Cliente que aparece na NFS-e. `distinct on` para pegar UMA linha por documento, a
    -- mais recente, sem precisar de agregação por atributo.
    select distinct on (documento_tomador)
        documento_tomador   as chave_cliente,
        nome_tomador        as nome,
        cidade_tomador      as cidade,
        uf_tomador          as uf
    from {{ ref('stg_servicos') }}
    where documento_tomador is not null
    order by documento_tomador, data_emissao desc nulls last

),

sacados as (

    select distinct on (documento_sacado)
        documento_sacado    as chave_cliente,
        nome_sacado         as nome,
        cidade_sacado       as cidade,
        uf_sacado           as uf
    from {{ ref('stg_contas_receber') }}
    where documento_sacado is not null
    order by documento_sacado, data_emissao desc nulls last

),

todas_as_chaves as (

    select chave_cliente from erp
    union
    select chave_cliente from tomadores
    union
    select chave_cliente from sacados

),

unido as (

    select
        k.chave_cliente,

        -- de onde esta identidade é conhecida — responde "este cliente só existe na NFS-e?"
        e.chave_cliente is not null                          as existe_no_erp,
        t.chave_cliente is not null                          as existe_em_nfse,
        s.chave_cliente is not null                          as existe_em_contas,

        -- documento: a chave só NÃO é documento quando o cliente do ERP não tem nenhum
        coalesce(e.documento,
                 case when k.chave_cliente ~ '^[0-9]+$' then k.chave_cliente end
        )                                                    as documento,

        coalesce(
            e.tipo_documento,
            case length(nullif(regexp_replace(k.chave_cliente, '[^0-9]', '', 'g'), ''))
                when 11 then 'cpf' when 14 then 'cnpj'
            end
        )                                                    as tipo_documento,

        -- ERP primeiro; as outras fontes só quando o cliente não está cadastrado
        coalesce(e.nome,   t.nome,   s.nome)                 as nome,
        coalesce(e.cidade, t.cidade, s.cidade)               as cidade,
        coalesce(e.uf,     t.uf,     s.uf)                   as uf,

        e.id_no_erp,
        coalesce(e.qtd_cadastros_erp, 0)                     as qtd_cadastros_erp

    from todas_as_chaves k
    left join erp       e on e.chave_cliente = k.chave_cliente
    left join tomadores t on t.chave_cliente = k.chave_cliente
    left join sacados   s on s.chave_cliente = k.chave_cliente

),

com_nao_informado as (

    select * from unido

    union all

    -- Membro "não informado", pelo mesmo motivo da `dim_vendedor` e da `dim_geografia`:
    -- 197 contas a receber não trazem o documento do sacado (item 5.8). Sem esta linha
    -- elas ficariam com chave nula, e NULL some do `GROUP BY` — o recebimento por cliente
    -- deixaria de fechar com o recebimento total, pela diferença que ninguém explica.
    select
        'sem-documento:desconhecido' as chave_cliente,
        false as existe_no_erp, false as existe_em_nfse, false as existe_em_contas,
        null::text as documento, null::text as tipo_documento,
        'sacado sem documento na origem' as nome,
        null::text as cidade, null::text as uf,
        null::bigint as id_no_erp, 0 as qtd_cadastros_erp

)

select
    md5(chave_cliente)      as sk_cliente,
    chave_cliente,
    documento,
    tipo_documento,
    nome,
    cidade,
    uf,
    existe_no_erp,
    existe_em_nfse,
    existe_em_contas,
    id_no_erp,
    qtd_cadastros_erp,

    -- rótulo pronto para o gráfico não ter que repetir esta regra
    case
        when existe_no_erp then 'cadastrado no ERP'
        when existe_em_nfse and existe_em_contas then 'so em NFS-e e contas'
        when existe_em_nfse then 'so em NFS-e'
        else 'so em contas'
    end                     as procedencia

from com_nao_informado
