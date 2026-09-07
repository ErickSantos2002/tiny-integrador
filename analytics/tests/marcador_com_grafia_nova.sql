{#
  FALHA quando aparece um marcador com grafia que ninguém revisou ainda.

  Este é o teste que o glossário chama de inegociável, e a razão está no histórico:
  o problema dos marcadores durou anos porque **grafia nova não gerava erro, gerava
  silêncio**. A nota simplesmente entrava como venda, sem nada acontecer.

  A classificação por radical cobre a maioria das frases novas sozinha — mas só a
  maioria. Quando alguém digita `n° da nf intilizada.` (inutilizada com erro de
  digitação) ou inventa um sinônimo, o radical não pega e o `else` manda para `neutro`,
  que é justamente o balde do "conta como venda". O erro se disfarça de normalidade.

  Por isso a defesa não é o radical: é este teste. `seeds/marcadores_revisados.csv`
  é o registro do que já passou por olho humano. Grafia fora dele é assunto pendente,
  não silêncio.

  **Severidade `warn`, de propósito.** Um marcador novo é evento rotineiro do negócio —
  gente escreve o que precisa. Derrubar o pipeline por isso faria alguém desligar o
  teste na terceira vez, e aí a proteção morre de vez. `warn` aparece no log, entra no
  relatório e não impede a carga de rodar.

  Como resolver quando aparecer:
    1. olhar a grafia nova que o teste listou;
    2. decidir se ela exclui do faturamento;
    3. se o radical já acertou, é só acrescentar a linha em `marcadores_revisados.csv`;
       se errou, acrescentar TAMBÉM em `marcadores_excecoes.csv`, que vence o radical.
#}

{{ config(severity = 'warn') }}

select
    m.descricao,
    m.conceito                as classificado_pelo_radical,
    m.exclui_do_faturamento,
    count(*)                  as ocorrencias,
    count(distinct m.id_nota) as notas

from {{ ref('stg_marcadores') }} m
left join {{ ref('marcadores_revisados') }} r
       on r.descricao = m.descricao

where r.descricao is null

group by 1, 2, 3
order by 5 desc
