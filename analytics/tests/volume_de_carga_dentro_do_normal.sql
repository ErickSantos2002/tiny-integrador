{#
  Avisa quando alguma carga trouxe volume fora do normal (item 6.4).

  `severity: warn` de propósito: volume fora do normal **pode** ser defeito e pode ser a
  vida real (feriado, cliente grande, backfill). Quem decide é gente olhando — travar a
  build por causa de um dia atípico ensinaria a equipe a ignorar build vermelha, que é
  exatamente o que a política de severidade (6.2) existe para evitar.

  ⚠️ Enquanto o histórico for curto, este teste passa por omissão: o monitor devolve
  `sem base de comparacao` e não há o que julgar. Isso é honesto, não é falha — mas
  significa que **este alarme ainda não protege nada**, e só passa a proteger conforme as
  execuções se acumulam.
#}

{{ config(severity = 'warn') }}

select
    job,
    inicio,
    volume,
    volume_mediano,
    execucoes_comparaveis,
    veredito

from {{ ref('monitor_volume_carga') }}
where veredito not in ('ok', 'sem base de comparacao')
