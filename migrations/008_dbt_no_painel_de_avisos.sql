-- 008: a reconstrucao da camada analitica (dbt) entra no painel de avisos
--
-- POR QUE: o timer `datacore-dbt.timer` roda todo dia as 05:00 UTC e, ate agora, falhava
-- CALADO — ninguem ficava sabendo. O aviso ja existe para as tres cargas do Tiny; o dbt
-- passa a usar o mesmo caminho em vez de inventar canal novo, entao a falha aparece no
-- mesmo lugar que as outras, e o frontend que consumir /operacao/avisos mostra as quatro
-- de graca.
--
-- QUEM ESCREVE O REGISTRO: o proprio dbt, pelo hook `on-run-end` do dbt_project.yml.
-- Por isso a role `dbt` precisa de escrita — nesta tabela e em nenhuma outra.

GRANT INSERT, UPDATE ON operacao.execucoes_job TO dbt;
GRANT USAGE, SELECT ON SEQUENCE operacao.execucoes_job_id_seq TO dbt;

-- A view ganha uma quarta linha em `esperado`. Tolerancia de 26 horas: o job e diario,
-- entao 24h mais duas de folga — atraso de fila nao vira alarme falso, e um dia inteiro
-- sem rodar vira.
--
-- O rotulo entra nas frases como "A carga de dados analiticos ...", que e a forma que a
-- view ja monta para as outras tres. Nao e carga no sentido estrito (o dbt transforma, nao
-- carrega), mas quem le o aviso entende o que quebrou, e inventar uma segunda forma de
-- frase so para este job deixaria o painel inconsistente.
CREATE OR REPLACE VIEW operacao.avisos_cargas AS
 WITH esperado(job, rotulo, horas_ate_atraso) AS (
         VALUES ('extrair_notas'::text,'notas fiscais'::text,15), ('extrair_contas'::text,'contas'::text,30), ('extrair_estoque'::text,'estoque'::text,30), ('dbt_build'::text,'dados analíticos'::text,26)
        ), ultima AS (
         SELECT DISTINCT ON (execucoes_job.job) execucoes_job.job,
            execucoes_job.id,
            execucoes_job.inicio,
            execucoes_job.fim,
            execucoes_job.resultado,
            execucoes_job.erros,
            execucoes_job.contagens
           FROM operacao.execucoes_job
          ORDER BY execucoes_job.job, execucoes_job.inicio DESC
        )
 SELECT e.job,
    e.rotulo,
    u.id AS execucao_id,
    u.inicio,
    u.fim,
    u.resultado,
    u.erros,
    u.contagens,
    round(EXTRACT(epoch FROM now() - u.inicio) / 3600.0, 1) AS horas_desde_inicio,
        CASE
            WHEN u.job IS NULL THEN 'sem_registro'::text
            WHEN u.resultado = 'falha'::text THEN 'falha'::text
            WHEN u.resultado IS NULL AND (now() - u.inicio) <= '03:00:00'::interval THEN 'rodando'::text
            WHEN u.resultado IS NULL THEN 'inacabada'::text
            WHEN (now() - u.inicio) > (e.horas_ate_atraso::double precision * '01:00:00'::interval) THEN 'atrasada'::text
            ELSE 'ok'::text
        END AS estado,
        CASE
            WHEN u.job IS NULL THEN ('A carga de '::text || e.rotulo) || ' nunca registrou execução.'::text
            WHEN u.resultado = 'falha'::text THEN ((('A carga de '::text || e.rotulo) || ' falhou com '::text) || u.erros) || ' erro(s).'::text
            WHEN u.resultado IS NULL AND (now() - u.inicio) <= '03:00:00'::interval THEN ('A carga de '::text || e.rotulo) || ' está rodando agora.'::text
            WHEN u.resultado IS NULL THEN (('A carga de '::text || e.rotulo) || ' começou e não terminou — provavelmente foi '::text) || 'interrompida. Rodar de novo costuma resolver.'::text
            WHEN (now() - u.inicio) > (e.horas_ate_atraso::double precision * '01:00:00'::interval) THEN ((('A carga de '::text || e.rotulo) || ' não roda há '::text) || round(EXTRACT(epoch FROM now() - u.inicio) / 3600.0)) || ' horas.'::text
            ELSE ('A carga de '::text || e.rotulo) || ' rodou normalmente.'::text
        END AS mensagem
   FROM esperado e
     LEFT JOIN ultima u ON u.job = e.job;
