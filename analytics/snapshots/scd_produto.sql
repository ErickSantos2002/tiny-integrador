{#
  Histórico de mudanças do produto — SCD Tipo 2 (item 5.4).

  Mesma urgência do snapshot de cliente: produto que muda de nome ou sai de linha reescreve
  o passado se a dimensão sobrescrever.

  **Estratégia `check`** pelo mesmo motivo: `tiny.estoque` tem `data_criacao`, mas não tem
  data de ATUALIZAÇÃO — e criação não detecta mudança, só nascimento.

  **O que é monitorado:**
    - `nome`, `codigo_produto`, `unidade` — como o produto é reconhecido e agrupado;
    - `situacao` (A/I) — sair de linha é a mudança de estado mais consequente aqui;
    - `preco`, `preco_custo` — preço de tabela historizado é o que permite perguntar
      "por quanto isso era vendido em 2024", que hoje ninguém consegue responder.

  ⚠️ **`saldo` ficou DE FORA, e isso é deliberado.** Saldo muda todo dia: incluí-lo criaria
  uma versão nova por dia por produto e transformaria a dimensão num fato disfarçado —
  295 produtos × 365 dias de lixo por ano. Saldo é medida, não atributo; quando alguém
  precisar de série de estoque, o lugar é um fato de posição, não este snapshot.
#}

{% snapshot scd_produto %}

{{
    config(
        unique_key='id_produto',
        strategy='check',
        check_cols=['nome', 'codigo_produto', 'unidade', 'situacao', 'preco', 'preco_custo'],
        invalidate_hard_deletes=True
    )
}}

select
    id_produto,
    sk_produto,
    nome,
    codigo_produto,
    unidade,
    situacao,
    preco,
    preco_custo,
    procedencia

from {{ ref('dim_produto') }}

{% endsnapshot %}
