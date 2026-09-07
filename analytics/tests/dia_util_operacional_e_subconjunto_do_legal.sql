{#
  Invariante: todo dia útil OPERACIONAL também é dia útil LEGAL.

  O operacional desconta ponto facultativo além do feriado, então ele só pode ser mais
  restrito, nunca mais largo. Se um dia aparecer como operacional sem ser legal, alguém
  inverteu a lógica das duas colunas — e o erro passaria despercebido porque os dois
  números continuam parecendo plausíveis (248 e 245 não gritam nada).
#}

{{ config(severity = 'error') }}

select data, dia_util, dia_util_operacional
from {{ ref('dim_tempo') }}
where dia_util_operacional and not dia_util
