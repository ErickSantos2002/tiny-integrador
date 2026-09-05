-- 005 — Registro de execuções das cargas.
--
-- POR QUÊ
-- Desde 2026-09-05 os jobs terminam com código de saída honesto (antes o de contas
-- falhava todo dia por um motivo conhecido e mascarava falha nova). Só que **ninguém lê**
-- esse código: ele morre no journal da VPS. Um alarme que toca numa sala vazia não é
-- alarme.
--
-- O aviso precisa chegar na máquina do Erick, e ela não pode perguntar à VPS por SSH: a
-- chave tem passphrase e o JARVIS dispara 3 minutos depois do login, quando o ssh-agent
-- normalmente ainda está vazio. Falharia em silêncio — o pior defeito possível num alarme.
--
-- Então o estado vem para o banco, que o desktop já lê sem senha interativa (`.pgpass`).
-- O `situacao` do JARVIS faz um SELECT e avisa. Nada de canal novo: o JARVIS já existe
-- para isso, e notificação de mão única (mako) já foi testada e recusada.
--
-- E fica um segundo uso, que sozinho já pagaria a tabela: **histórico de carga**. Quando
-- rodou, quanto trouxe, quanto demorou. É a matéria-prima do "monitor de volume" (item
-- 6.4 do ROADMAP) — "hoje chegaram 3 notas em vez de 300" é uma falha que código de saída
-- nenhum detecta, porque o job termina feliz.
--
-- POR QUE UM SCHEMA NOVO E NÃO `tiny`
-- Isto é metadado de operação, não dado de negócio. Em `tiny` poluiria o `sources.yml` da
-- Fase 3 e confundiria a bronze com o registro de quem a preenche. A Regra 1 do ROADMAP
-- continua valendo: `tiny` tem um dono só.
--
-- REVERSÃO
--   DROP SCHEMA operacao CASCADE;

BEGIN;

CREATE SCHEMA IF NOT EXISTS operacao;

CREATE TABLE IF NOT EXISTS operacao.execucoes_job (
    id          BIGSERIAL PRIMARY KEY,
    job         TEXT        NOT NULL,
    inicio      TIMESTAMPTZ NOT NULL DEFAULT now(),
    fim         TIMESTAMPTZ,
    resultado   TEXT,
    erros       INTEGER     NOT NULL DEFAULT 0,
    contagens   JSONB       NOT NULL DEFAULT '{}'::jsonb,
    detalhe     TEXT,
    argumentos  TEXT
);

-- TIMESTAMPTZ e não TIMESTAMP: a VPS roda em UTC e a máquina do Erick em UTC-3. Este é
-- justamente o dado que vai ser lido de fora, então o fuso precisa viajar junto — as
-- tabelas de negócio guardam data do documento, o que é outro problema.

COMMENT ON TABLE operacao.execucoes_job IS
    'Uma linha por execução de carga. Lida pelo JARVIS na máquina do Erick para avisar '
    'quando a ingestão falha, e base do monitor de volume (item 6.4 do ROADMAP).';
COMMENT ON COLUMN operacao.execucoes_job.resultado IS
    'sucesso | falha. NULL significa que o job NÃO chegou ao fim — foi morto (deploy '
    'durante a carga manda SIGKILL) ou a VPS caiu. É diferente de falha, e a diferença '
    'importa: falha pede investigação, morte pede só rodar de novo.';
COMMENT ON COLUMN operacao.execucoes_job.contagens IS
    'O resumo que o job imprime, como objeto: {"criada": 41, "inalterada": 553, ...}.';

CREATE INDEX IF NOT EXISTS execucoes_job_recentes_idx
    ON operacao.execucoes_job (job, inicio DESC);

-- O JARVIS lê como `dbt` (só leitura), nunca como `administrador`: Regra 2 do ROADMAP.
GRANT USAGE ON SCHEMA operacao TO dbt;
GRANT SELECT ON ALL TABLES IN SCHEMA operacao TO dbt;
ALTER DEFAULT PRIVILEGES IN SCHEMA operacao GRANT SELECT ON TABLES TO dbt;

COMMIT;
