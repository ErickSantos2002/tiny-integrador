{#
  Quarentena de notas (item 6.3).

  **Quarentena não é lixeira.** A linha rejeitada continua existindo, com o motivo escrito
  do lado — o que permite revisar, medir o tamanho do problema e provar depois que ele
  diminuiu. Apagar seria mais fácil e destruiria a única evidência de que havia algo errado.

  ## O caso que motivou o item: as 22 notas vazias

  Medido em 2026-09-06, e as três pistas eram a mesma: as **22 notas sem `data_emissao`**
  (achado da Fase 1), as 22 sem `situacao_codigo` e as 22 **sem nenhum item** são
  exatamente o mesmo conjunto. Além disso: **valor zero, sem chave de acesso, e nenhuma
  delas entra em `vendas`**.

  Nota sem data, sem situação, sem item, sem chave e sem valor **não é uma nota** — é
  registro criado e nunca preenchido. Não afeta faturamento em nada; o dano é outro, e é
  real: elas somem de qualquer agregação por período **sem erro nenhum**, e quem contar
  notas encontra 8.198 onde existem 8.176 de verdade.

  ## Por que ficam na silver em vez de serem filtradas

  Se `stg_notas_fiscais` as excluísse, a contagem passaria a bater com a realidade e
  ninguém mais saberia que elas existem — inclusive quem for consertar o cadastro no Tiny.
  Aqui elas são separadas e nomeadas; os testes de qualidade passam a IGNORAR o que está
  em quarentena, então o aviso deixa de piscar sem que o problema tenha sido varrido.

  ⚠️ **Rotina de revisão:** este modelo é para ser olhado quando `qtd` mudar. Aumentou =
  a origem está criando lixo novo; diminuiu = alguém limpou. Hoje são 22, todas do mesmo
  motivo.
#}

with notas as (

    select * from {{ ref('stg_notas_fiscais') }}

),

com_item as (

    select distinct id_nota from {{ ref('stg_itens_nota') }}

),

avaliado as (

    select
        n.id                                    as id_nota,
        n.numero                                as numero_nota,
        n.chave_acesso,
        n.data_emissao,
        n.valor_nota,

        -- Cada motivo é uma condição isolada de propósito: uma nota pode entrar por mais de
        -- um, e saber POR QUAIS é o que diz se são o mesmo problema ou problemas diferentes.
        n.data_emissao is null                  as sem_data_emissao,
        n.situacao_codigo is null               as sem_situacao,
        i.id_nota is null                       as sem_item,
        n.chave_acesso is null                  as sem_chave_acesso,
        coalesce(n.valor_nota, 0) = 0           as valor_zero

    from notas n
    left join com_item i on i.id_nota = n.id

)

select
    id_nota,
    numero_nota,
    chave_acesso,
    data_emissao,
    valor_nota,

    sem_data_emissao,
    sem_situacao,
    sem_item,
    sem_chave_acesso,
    valor_zero,

    -- rótulo único para quem for revisar não ter que ler cinco booleanos
    case
        when sem_data_emissao and sem_situacao and sem_item and valor_zero
            then 'registro vazio: criado e nunca preenchido'
        when sem_item
            then 'nota sem item'
        when sem_data_emissao
            then 'nota sem data de emissao'
        else 'outro'
    end                                         as motivo

from avaliado
where sem_data_emissao
   or sem_situacao
   or sem_item
