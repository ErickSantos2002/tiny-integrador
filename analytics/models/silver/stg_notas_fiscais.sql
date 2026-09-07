{#
  Notas fiscais, tipadas e com os campos livres normalizados (itens 4.1 e 4.2).

  Nenhuma regra de negócio aqui — só limpeza. Quem decide o que é venda é `vendas.sql`.
  Separar as duas coisas é o que permite reusar esta base para locação, calibração e
  demonstração sem copiar tratamento.
#}

with bronze as (

    select * from {{ source('tiny', 'notas_fiscais') }}

),

{#
  Curadoria humana em CSV versionado (item 4.9). `notas_fiscais.tipo` NÃO vem da origem:
  são 516 notas classificadas à mão pela tela (`PATCH /{id}/tipo`) — 435 Inbound, 79
  ReCompra, 2 Outbound. Enquanto isso morava só na bronze, uma recarga apagava o
  trabalho; o extrator protege o campo (`CAMPOS_DE_CURADORIA_LOCAL`), mas proteção em
  código não sobrevive a um TRUNCATE, e não deixa ver quem mudou o quê.

  A seed VENCE, e a bronze fica de reserva: assim a classificação sobrevive à recarga, e
  a curadoria nova feita na tela continua valendo até alguém exportar. O teste
  `curadoria_de_tipo_fora_da_seed` é que avisa quando essa exportação está atrasada —
  sem ele, a divergência seria silenciosa.
#}
tipo_curado as (

    select id, tipo from {{ ref('notas_tipo_curado') }}

),

limpo as (

    select
        bronze.id,
        chave_acesso,
        numero,
        serie,

        data_emissao,
        data_saida,

        -- ⚠️ `situacao` é o CÓDIGO numérico (7, 3, 8…); o texto está em
        -- `descricao_situacao`. Filtrar a coluna errada devolve zero linhas sem erro
        -- nenhum — armadilha que já custou uma investigação em 2026-09-05. Os dois
        -- ficam com nome explícito para que ninguém mais confunda.
        situacao                                        as situacao_codigo,
        {{ normalizar_texto('descricao_situacao') }}     as situacao,
        descricao_situacao                               as situacao_original,

        {{ normalizar_texto('natureza_operacao') }}      as natureza_operacao,
        {{ normalizar_texto('nome_vendedor') }}          as vendedor,
        id_vendedor,
        id_cliente,

        -- valores: a bronze já traz numeric, aqui só o coalesce que evita NULL
        -- contaminando soma (0 é o neutro correto para dinheiro ausente)
        coalesce(valor_nota, 0)                          as valor_nota,
        coalesce(valor_produtos, 0)                      as valor_produtos,
        coalesce(valor_frete, 0)                         as valor_frete,
        coalesce(valor_desconto, 0)                      as valor_desconto,
        coalesce(valor_icms, 0)                          as valor_icms,
        coalesce(valor_servicos, 0)                      as valor_servicos,

        -- campo livre, e o mais completo da tabela: guarda número de série,
        -- chave da nota de remessa, prazo de teste. Ver docs/02-star-schema.md
        observacoes,

        -- seed primeiro, bronze de reserva — ver o bloco de curadoria acima
        coalesce(tipo_curado.tipo, bronze.tipo)          as tipo,
        finalidade

    from bronze
    left join tipo_curado on tipo_curado.id = bronze.id

)

select * from limpo
