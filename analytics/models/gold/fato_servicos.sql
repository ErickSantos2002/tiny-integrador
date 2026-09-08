{#
  `fato_servicos` — o faturamento de serviço (NFS-e).

  **Grão: A NOTA**, como a matriz de barramento (2.3) decidiu. Diferente do `fato_vendas`,
  que é grão de item: a NFS-e não tem itens, tem uma discriminação em texto livre. Grão de
  nota aqui não é simplificação, é o grão que o documento tem.

  ## Por que ele existe agora, e não antes

  Ficou de fora das Fases 5 e 6 de propósito — o star schema desenhava, mas nenhum
  consumidor pedia, e modelo sem consumidor é código morto que ainda assim quebra quando a
  origem muda. O consumidor apareceu na Fase 9: o dashboard soma **NF-e mais NFS-e** no
  faturamento, então um endpoint lendo só `fato_vendas` responderia metade da tela.

  ## O que este modelo NÃO decide

  Que NFS-e cancelada não é faturamento já estava decidido em dois lugares antes daqui: a
  curadoria de 223 notas (item 4.9) e o endpoint da API, que já filtra por padrão. Aqui a
  regra só é aplicada — `cancelada` vem tratada da `stg_servicos`.

  ## Dimensões: as três que se aplicam

  - **cliente** — ligado pelo documento do tomador. É a mesma `dim_cliente` do
    `fato_vendas`, e é o que torna possível perguntar "quanto este cliente comprou de
    produto E de serviço" numa consulta só. Foi para isso que a dimensão nasceu unindo as
    três fontes (5.2): 119 tomadores de NFS-e não existem em `tiny.clientes`.
  - **geografia** — vem da CIDADE DO CLIENTE, não da cidade do tomador gravada na nota.
    A nota traz a sua própria, mas usar a do cliente é o que faz "faturamento por região"
    somar igual nos dois fatos. Duas geografias para o mesmo cliente fariam o total por
    região divergir do total geral sem ninguém achar o motivo.
  - **tempo** — pela data de emissão, igual ao `fato_vendas`.

  Produto e vendedor NÃO se aplicam: a NFS-e não tem produto, e não tem campo de vendedor
  (⚠️ registrado na matriz de barramento — só existiria por ligação com a venda que
  originou o serviço, o que hoje não é rastreável).

  ⚠️ **`linha de negócio` (Calibração × Plataforma × Manutenção) fica como atributo
  degenerado**, no `codigo_atividade`, e não como dimensão. A matriz previa a dimensão, mas
  o `fato_vendas` também não tem uma, e criá-la só aqui deixaria a régua de linha de
  negócio existindo de um lado e não do outro. Entra quando os dois fatos a pedirem.
#}

{{ config(materialized = 'table') }}

with servicos as (

    select * from {{ ref('stg_servicos') }}
    -- A régua: nota cancelada não é faturamento. Ver o cabeçalho.
    where not coalesce(cancelada, false)

),

cliente as (

    select chave_cliente, sk_cliente, cidade, uf from {{ ref('dim_cliente') }}

),

geografia as (

    select sk_geografia, cidade, uf from {{ ref('dim_geografia') }}

)

select
    -- ------------------------------------------------------------------ chaves
    s.id                                                          as sk_servico,

    s.data_emissao                                                as data_servico,

    -- `left join` e nunca `inner`: linha sem dimensão SOME do fato e o total encolhe sem
    -- ninguém ver. Tomador sem documento cai no membro próprio, do mesmo jeito que o
    -- `fato_contas_receber` trata o sacado sem documento.
    coalesce(cl.sk_cliente, md5('sem-documento:desconhecido'))    as sk_cliente,
    coalesce(g.sk_geografia, md5('nao informada' || '|' || '--')) as sk_geografia,

    -- ------------------------------------------- dimensões degeneradas (ficam no fato)
    s.numero_nfse,
    s.codigo_atividade,
    s.data_competencia,
    s.iss_retido,
    s.documento_tomador is null                                   as tomador_sem_documento,

    -- ------------------------------------------------------------------ métricas
    -- `valor_servicos` é o faturamento. As outras vêm ao lado, cada uma na sua coluna, em
    -- vez de um "valor" polivalente que muda de significado conforme o filtro.
    s.valor_servicos,
    s.valor_iss,
    s.valor_deducoes,
    s.valor_total_recebido

from servicos s
left join cliente   cl on cl.chave_cliente = s.documento_tomador
left join geografia g  on g.cidade = cl.cidade and g.uf = cl.uf
