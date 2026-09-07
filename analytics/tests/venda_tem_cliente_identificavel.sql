{#
  Regra de negócio (6.1): venda deveria ter cliente identificável.

  Medido em 2026-09-06: **5 itens** caem no cliente sem documento — é o cadastro do ERP que
  não tem CPF/CNPJ nenhum (1 cliente), não um defeito do modelo. Por isso `warn` e não
  `error`: a origem é que está incompleta, e travar a silver não conserta cadastro no Tiny.

  O valor de deixar isto medido: se amanhã forem 500 em vez de 5, alguma coisa mudou na
  ingestão — e sem o teste isso só apareceria quando um relatório por cliente não fechasse.
#}

{{ config(severity = 'warn') }}

select
    f.sk_venda_item,
    f.id_nota,
    f.valor_nota_rateado,
    d.chave_cliente

from {{ ref('fato_vendas') }} f
join {{ ref('dim_cliente') }} d on d.sk_cliente = f.sk_cliente
where d.documento is null
