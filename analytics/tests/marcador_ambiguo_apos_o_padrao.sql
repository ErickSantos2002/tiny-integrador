{#
  AVISA quando um marcador ambíguo aparece numa nota emitida DEPOIS que o padrão passou
  a existir.

  Contexto (2026-09-05). Existem marcadores que sugerem que a venda não valeu, mas não
  provam: `cancelamento solicitado` (solicitado não é efetivado), reemissão, duplicidade,
  estorno. Nas notas antigas eles ficaram sem veredito — **decisão do dono: deixar
  contando**, porque o financeiro de hoje não consegue confirmar o que não foi ele que fez.

  Só que essa é uma decisão sobre o PASSADO, e transformá-la em regra eterna seria o tipo
  de erro que não dá sinal: uma nota de 2027 com `cancelamento solicitado` seguiria contando
  para sempre, mesmo tendo sido escrita sob um padrão em que o autor sabia como cancelar
  direito.

  Medido — quando o padrão (`NF cancelada` / `NF recusada`) começou a ser usado:

      até 2023    0 usos do padrão, 24 grafias livres
      2024        4 usos do padrão, 25 grafias livres
      2025       27 usos do padrão, 21 grafias livres   ← vira maioria
      2026       13 usos do padrão,  4 grafias livres

  Por isso o corte é **2025-01-01**. Depois dele, quem quisesse cancelar tinha como
  escrever `NF cancelada`. Um marcador ambíguo aí é anomalia: ou a venda foi mesmo anulada
  e ninguém usou o padrão, ou o marcador significa outra coisa. Nos dois casos, alguém
  precisa olhar — e é isso que este teste faz. Ele NÃO exclui a nota; só recusa o silêncio.

  `warn` de propósito: é pedido de conferência, não defeito de código.
#}

{{ config(severity = 'warn') }}

select
    n.numero        as nota,
    n.data_emissao,
    n.valor_nota,
    m.descricao_original as marcador,
    'marcador ambíguo em nota posterior ao padrão de 2025 — conferir se deveria ter saído'
        as o_que_fazer

from {{ ref('stg_marcadores') }} m
join {{ ref('stg_notas_fiscais') }} n on n.id = m.id_nota

where m.conceito = 'ambiguo'
  and n.data_emissao >= date '2025-01-01'

order by n.valor_nota desc
