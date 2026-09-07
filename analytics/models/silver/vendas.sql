{#
  ============================================================================
  A DEFINIÇÃO ÚNICA DE VENDA.  (item 4.6 — o coração do projeto)
  ============================================================================

  Hoje essa definição existe em SEIS lugares: cinco arquivos `.py` e o navegador.
  Já divergiu uma vez, e inflou um relatório de 2025 em cerca de 1% do faturamento. Daqui
  para frente, quem quiser saber o que é venda lê ESTE arquivo.

  Grão: **ITEM DA NOTA** (decisão 2.4). Permite analisar produto; a nota se obtém
  somando. O caminho inverso seria impossível.

  A régua, conforme `docs/02-glossario.md`:

    1. CFOP DO ITEM é quem prova que é venda — não a natureza de operação, que é
       texto livre. 170 notas têm a natureza VAZIA (3,5% do faturamento) e nunca poderiam ser
       classificadas por lá; 15 notas divergem entre os dois caminhos (cerca de 1%).
    2. Situação "emitida danfe" — lida de `descricao_situacao`, nunca de `situacao`.
    3. Sem marcador que exclua, conforme a classificação de `stg_marcadores`.

  ⚠️ O RATEIO é o que faz o faturamento somar. `valor_nota` pertence à NOTA e o grão
  aqui é ITEM: repetir o valor cheio em cada linha conta a mesma nota várias vezes.
  Medido em 2026-09-05: o total correto contra um inflado em 28% —
  28% a mais, por causa de 588 notas com 2 ou mais itens (a maior tem 13).

  A decisão do Erick foi manter faturamento = valor da nota (continuidade com o
  histórico já reportado). O rateio respeita isso: somar `valor_nota_rateado` devolve
  exatamente o valor das notas.
#}

with itens as (

    select
        id          as id_item,
        id_nota,
        id_produto,
        codigo      as codigo_produto,
        {{ normalizar_texto('descricao') }} as descricao_produto,
        cfop,
        coalesce(quantidade, 0)     as quantidade,
        coalesce(valor_unitario, 0) as valor_unitario,
        coalesce(valor_total, 0)    as valor_total_item
    from {{ source('tiny', 'itens_nota') }}

),

notas as (

    select * from {{ ref('stg_notas_fiscais') }}

),

-- notas que têm ao menos um marcador que exclui do faturamento
notas_excluidas as (

    select distinct id_nota
    from {{ ref('stg_marcadores') }}
    where exclui_do_faturamento

),

-- peso de cada item dentro da sua nota, para ratear o valor da nota.
-- ⚠️ A nota sem item, ou com todos os itens zerados, quebraria a divisão. Nesses
-- casos o rateio cai para partes iguais entre os itens existentes — e a nota SEM
-- item nenhum simplesmente não aparece aqui, por ser um `join` interno. Isso é
-- coberto por teste: a soma tem que bater com a soma das notas elegíveis.
peso as (

    select
        i.id_nota,
        sum(i.valor_total_item) as total_itens,
        count(*)                as qtd_itens
    from itens i
    group by 1

),

venda as (

    select
        i.id_item,
        n.id                    as id_nota,
        n.chave_acesso,
        n.numero                as numero_nota,
        n.data_emissao,
        n.id_cliente,
        n.id_vendedor,
        n.vendedor,

        i.id_produto,
        i.codigo_produto,
        i.descricao_produto,
        i.cfop,

        -- mercado: exportação entra como venda (decisão D2), mas marcada, para poder
        -- ser separada por quem quiser
        case when i.cfop::text like '7%' then 'externo' else 'interno' end as mercado,

        i.quantidade,
        i.valor_unitario,
        i.valor_total_item,

        -- ---- o rateio ----
        case
            when p.total_itens > 0
                then n.valor_nota * (i.valor_total_item / p.total_itens)
            else n.valor_nota / nullif(p.qtd_itens, 0)   -- itens todos zerados: partes iguais
        end as valor_nota_rateado,

        case
            when p.total_itens > 0
                then n.valor_frete * (i.valor_total_item / p.total_itens)
            else n.valor_frete / nullif(p.qtd_itens, 0)
        end as valor_frete_rateado,

        case
            when p.total_itens > 0
                then n.valor_desconto * (i.valor_total_item / p.total_itens)
            else n.valor_desconto / nullif(p.qtd_itens, 0)
        end as valor_desconto_rateado,

        case
            when p.total_itens > 0
                then n.valor_icms * (i.valor_total_item / p.total_itens)
            else n.valor_icms / nullif(p.qtd_itens, 0)
        end as valor_icms_rateado,

        n.valor_nota    as valor_nota_cheio,   -- ⚠️ NÃO SOMAR: é da nota, não do item
        n.observacoes

    from itens i
    join notas n on n.id = i.id_nota
    join peso  p on p.id_nota = i.id_nota

    where
        -- 1. CFOP de venda (5102/6102/5108/6108 internos, 7102 exportação)
        i.cfop::text in ('5102', '6102', '5108', '6108', '7102')

        -- 2. nota autorizada e impressa
        and n.situacao = 'emitida danfe'

        -- 3. sem marcador que exclua
        and n.id not in (select id_nota from notas_excluidas)

)

select * from venda
