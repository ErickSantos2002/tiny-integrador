{#-
  Nota listada em `notas_fora_do_faturamento` NAO pode aparecer em `vendas`.

  Parece obvio — o modelo acabou de filtrar por essa lista. Mas o teste existe pelo caso
  em que alguem mexe no `where` de `vendas.sql` e derruba a condicao 4 sem perceber: a
  seed continua no repositorio, com o motivo escrito e a decisao datada, dando a impressao
  de que a curadoria esta valendo, enquanto o faturamento voltou a contar demonstracao
  como venda. Um numero que volta sozinho e pior que um que nunca esteve certo.

  Severidade `error` de proposito: e curadoria humana, decidida caso a caso. Se parou de
  valer, o build tem que parar tambem.
-#}

select
    v.id_nota,
    c.motivo,
    c.decidido_em

from {{ ref('vendas') }} v
join {{ ref('notas_fora_do_faturamento') }} c
  on c.id_nota = v.id_nota

group by 1, 2, 3
