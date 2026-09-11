-- 009: a importação das NFS-e entra no painel de avisos
--
-- POR QUE: até 2026-09-11 a importação das notas de serviço não tinha agendamento — só o
-- endpoint `POST /notas_servico/importar`, que ninguém chamava. Medido no dia: 31 notas de
-- 04/09 a 10/09 fora do banco, sem aviso nenhum. Agora roda pelo `tiny-extrator-nfse.timer`
-- (04:30 UTC) e registra em `operacao.execucoes_job` como `importar_nfse`; esta view passa a
-- esperar por ela, então o dia em que ela parar vira `atrasada` em vez de silêncio.
--
-- Tolerância de 26 horas: o job é diário, como o dbt — 24h mais duas de folga.
--
-- Nenhum GRANT: o job roda dentro do container da API, com a mesma conexão dos extratores.
--
-- REVERSÃO: reaplicar a 008 (a view volta a ter quatro linhas).
CREATE OR REPLACE VIEW operacao.avisos_cargas AS
 WITH esperado(job, rotulo, horas_ate_atraso) AS (
         VALUES ('extrair_notas'::text,'notas fiscais'::text,15), ('extrair_contas'::text,'contas'::text,30), ('extrair_estoque'::text,'estoque'::text,30), ('dbt_build'::text,'dados analíticos'::text,26), ('importar_nfse'::text,'notas de serviço'::text,26)
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
