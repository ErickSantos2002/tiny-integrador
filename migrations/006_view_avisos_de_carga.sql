-- 006 — `operacao.avisos_cargas`: o que está errado com a ingestão, pronto para exibir.
--
-- POR QUÊ
-- A migration 005 registrou o FATO (cada execução). Isto aqui é o JULGAMENTO: quais
-- desses fatos merecem virar aviso na tela. São coisas diferentes de propósito — o fato
-- é imutável e serve de histórico; a regra do que é "problema" muda com o tempo, e
-- muda num lugar só.
--
-- A regra mora no banco, e não no frontend, para que só exista UMA definição de "a carga
-- está com problema". Se cada tela reimplementasse o critério, elas discordariam entre si
-- na primeira mudança de horário de timer — e foi exatamente assim que a régua de
-- faturamento acabou espalhada por vários lugares.
--
-- OS TRÊS ESTADOS, que não são a mesma coisa
--   falha       o job rodou e terminou mal — pede investigação
--   inacabada   começou e nunca fechou a linha: foi morto (deploy durante a carga manda
--               SIGKILL) ou a VPS caiu. Não é falha; costuma bastar rodar de novo
--   atrasada    o timer não disparou, ou disparou e o processo nem chegou a registrar.
--               É a falha mais perigosa das três, porque é 100% silenciosa: sem esta
--               regra, uma carga que simplesmente PARA nunca vira aviso nenhum
--
-- A folga de atraso é generosa (15h/30h contra timers de 12h/24h) porque aviso que pisca
-- por meia hora de atraso vira ruído, e alarme ruidoso é alarme desligado.
--
-- REVERSÃO
--   DROP VIEW operacao.avisos_cargas;

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
        WHEN u.resultado IS NULL AND now() - u.inicio > interval '3 hours'
                                                             THEN 'inacabada'
        WHEN now() - u.inicio > (e.horas_ate_atraso * interval '1 hour')
                                                             THEN 'atrasada'
        ELSE 'ok'
    END AS estado,
    CASE
        WHEN u.job IS NULL THEN
            'A carga de ' || e.rotulo || ' nunca registrou execução.'
        WHEN u.resultado = 'falha' THEN
            'A carga de ' || e.rotulo || ' falhou com ' || u.erros || ' erro(s).'
        WHEN u.resultado IS NULL AND now() - u.inicio > interval '3 hours' THEN
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
    'por job SEMPRE (inclusive job que nunca rodou — o LEFT JOIN é de propósito: carga que '
    'sumiu tem de aparecer, e ela não tem linha em execucoes_job para ser encontrada). '
    'Filtre por estado <> ''ok'' para mostrar só o que está errado.';

GRANT SELECT ON operacao.avisos_cargas TO dbt;

COMMIT;
