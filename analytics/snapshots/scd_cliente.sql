{#
  Histórico de mudanças do cliente — SCD Tipo 2 (item 5.4).

  ⚠️ **Este é o item que não dá para adiar.** Histórico não se recupera depois: se um
  cliente muda de cidade em 2027 e a dimensão sobrescreve, TODA a venda de 2024 passa a
  parecer que aconteceu na cidade nova. O snapshot precisa começar a rodar ANTES da
  primeira mudança — e cada dia sem ele é um dia de história perdida em silêncio.

  **Estratégia `check`, não `timestamp`**, e não é preferência: `tiny.clientes` NÃO TEM
  coluna de data nenhuma (nem criação, nem atualização — medido no item 4.4). Sem coluna
  para comparar, o jeito de detectar mudança é olhar o conteúdo das colunas que importam.

  **O que é monitorado, e por quê cada uma:**
    - `nome`      — razão social muda, e a nota antiga foi emitida para o nome antigo;
    - `cidade`/`uf` — é o que faz "faturamento por região" mentir se for sobrescrito;
    - `procedencia` — muda quando um cliente que só existia em NFS-e/contas passa a ser
      cadastrado no ERP. É uma mudança de estado real, não ruído.

  **O que ficou de fora de propósito:** `documento` e `tipo_documento` são a IDENTIDADE —
  se mudassem, seria outro cliente, não uma versão nova dele. E `id_no_erp` /
  `qtd_cadastros_erp` são detalhe de origem, não atributo de análise: mudam quando alguém
  mexe no cadastro sem que nada de negócio tenha mudado, e gerariam versão nova à toa.
#}

{% snapshot scd_cliente %}

{{
    config(
        unique_key='chave_cliente',
        strategy='check',
        check_cols=['nome', 'cidade', 'uf', 'procedencia'],
        invalidate_hard_deletes=True
    )
}}

select
    chave_cliente,
    sk_cliente,
    documento,
    tipo_documento,
    nome,
    cidade,
    uf,
    procedencia,
    existe_no_erp,
    existe_em_nfse,
    existe_em_contas

from {{ ref('dim_cliente') }}

{% endsnapshot %}
