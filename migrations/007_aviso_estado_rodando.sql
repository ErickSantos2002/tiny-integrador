-- 007 — Carga em andamento ganha estado próprio: `rodando`.
--
-- POR QUÊ
-- Defeito visto na primeira execução real (2026-09-05, minutos depois de aplicar a 006):
-- enquanto o job de contas rodava, a view dizia **"A carga de contas rodou normalmente"**.
-- Era literalmente falso — ela não tinha rodado, estava rodando. A linha existe desde o
-- primeiro instante, com `resultado` nulo, e a regra só transformava nulo em `inacabada`
-- depois de 3 horas; antes disso caía no ELSE, que é o ramo do "está tudo bem".
--
-- O erro de desenho foi usar o ELSE como se fosse "ok". ELSE é "nenhum dos casos acima",
-- que não é a mesma coisa — e a diferença aparece justamente no estado que ninguém pensa
-- em modelar, o transitório.
--
-- Importa mais do que parece cosmético: uma carga de 8 horas (o backfill) passaria a tarde
-- inteira anunciando que terminou bem. Quem olhasse a tela no meio confiaria num "ok" que
-- ainda não foi decidido.
--
-- REVERSÃO: reaplicar a migration 006.

BEGIN;

CREATE OR REPLACE VIEW operacao.avisos_cargas AS
WITH esperado(job, rotulo, horas_ate_atraso) AS (
    VALUES ('extrair_notas',   'notas fiscais', 15),   -- roda 04:00 e 15:00 UTC
           ('extrair_contas',  'contas',        30),   -- roda 10:00 UTC
           ('extrair_estoque', 'estoque',       30)    -- roda 16:00 UTC
),
ultima AS (
    SELECT DISTINCT ON (job) job, id, inicio, fim, resultado, erros, contagens
    FROM operacao.execucoes_job
    ORDER BY job, inicio DESC
)
SELECT
    e.job,
    e.rotulo,
    u.id                                   AS execucao_id,
    u.inicio,
    u.fim,
    u.resultado,
    u.erros,
    u.contagens,
    ROUND(EXTRACT(EPOCH FROM (now() - u.inicio)) / 3600.0, 1) AS horas_desde_inicio,
    CASE
        WHEN u.job IS NULL                                   THEN 'sem_registro'
        WHEN u.resultado = 'falha'                           THEN 'falha'
        -- ainda não decidiu: nem sucesso, nem falha. Só vira `inacabada` depois de 3h,
        -- quando já não dá para acreditar que ainda esteja viva.
        WHEN u.resultado IS NULL AND now() - u.inicio <= interval '3 hours'
                                                             THEN 'rodando'
        WHEN u.resultado IS NULL                             THEN 'inacabada'
        WHEN now() - u.inicio > (e.horas_ate_atraso * interval '1 hour')
                                                             THEN 'atrasada'
        ELSE 'ok'
    END AS estado,
    CASE
        WHEN u.job IS NULL THEN
            'A carga de ' || e.rotulo || ' nunca registrou execução.'
        WHEN u.resultado = 'falha' THEN
            'A carga de ' || e.rotulo || ' falhou com ' || u.erros || ' erro(s).'
        WHEN u.resultado IS NULL AND now() - u.inicio <= interval '3 hours' THEN
            'A carga de ' || e.rotulo || ' está rodando agora.'
        WHEN u.resultado IS NULL THEN
            'A carga de ' || e.rotulo || ' começou e não terminou — provavelmente foi '
            || 'interrompida. Rodar de novo costuma resolver.'
        WHEN now() - u.inicio > (e.horas_ate_atraso * interval '1 hour') THEN
            'A carga de ' || e.rotulo || ' não roda há '
            || ROUND(EXTRACT(EPOCH FROM (now() - u.inicio)) / 3600.0) || ' horas.'
        ELSE
            'A carga de ' || e.rotulo || ' rodou normalmente.'
    END AS mensagem
FROM esperado e
LEFT JOIN ultima u ON u.job = e.job;

COMMENT ON VIEW operacao.avisos_cargas IS
    'Estado atual de cada carga da ingestão, com a mensagem pronta para exibir. Uma linha '
    'por job SEMPRE (inclusive job que nunca rodou — o LEFT JOIN é de propósito). Estados: '
    'ok · rodando · falha · inacabada · atrasada · sem_registro. Filtre por estado NOT IN '
    '(''ok'', ''rodando'') para mostrar só o que exige atenção.';

GRANT SELECT ON operacao.avisos_cargas TO dbt;

COMMIT;
