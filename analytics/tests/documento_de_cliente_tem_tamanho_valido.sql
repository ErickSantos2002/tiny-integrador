{#
  O documento do cliente, depois de limpo, ou é CPF (11) ou é CNPJ (14).

  Medido em 2026-09-06: hoje isso vale para todas as 2.082 linhas com documento — a
  sujeira da origem é só máscara (ponto, barra, traço), que `so_digitos` resolve. O teste
  existe para o dia em que deixar de valer: documento truncado ou com dígito a mais entra
  em silêncio, casa com ninguém, e o cliente simplesmente some das análises que cruzam
  NFS-e e contas pelo documento (item 4.8) — sem erro nenhum aparecer.

  `severity: warn` de propósito: documento torto na origem não pode derrubar a build da
  silver inteira, mas tem que aparecer no relatório. Quem conserta é o cadastro no Tiny.
#}

{{ config(severity = 'warn') }}

select
    id,
    length(documento) as digitos

from {{ ref('stg_clientes') }}

where documento is not null
  and length(documento) not in (11, 14)
