-- 002 — A identidade da NFS-e passa a ser a CHAVE DE ACESSO, não o número.
--
-- POR QUÊ
-- A constraint `servicos_numero_nf_unique` assume que o número da NFS-e é único.
-- Essa premissa deixou de valer em 18/06/2026, quando a emissão migrou para o
-- Emissor Nacional e a numeração REINICIOU: a série do Recife estava em 5.723 e a
-- nacional recomeçou em 725. Com a constraint no lugar, a nota nova nº 749 não pode
-- coexistir com a nota de 2019 de mesmo número — e foi por isso que a importação
-- passou a sobrescrever notas antigas em vez de inserir (~280 notas de 2018-2021
-- perdidas antes da correção do endpoint).
--
-- Sem esta migration, o endpoint corrigido também não funciona: ao tentar INSERIR
-- a nota nova, o banco rejeita por violação de unicidade e a nota não é importada.
--
-- O QUE MUDA
-- 1) Remove a unicidade do número, cuja premissa é falsa.
-- 2) Cria unicidade sobre a chave de acesso (50 dígitos), que é única por documento
--    fiscal. É um índice PARCIAL de propósito: as 4.858 linhas históricas não têm
--    chave de acesso de verdade (guardam o código curto da prefeitura, ou o literal
--    'ADN - ' deixado por uma carga antiga) e não podem entrar numa constraint de
--    unicidade. O índice cobre exatamente o que precisa ser protegido: o que a
--    importação de hoje grava.
--
-- Verificado em 2026-08-23 sobre os dados reais: 329 linhas com chave de acesso,
-- 329 chaves distintas — o índice é criado sem violação.
--
-- REVERSÃO
--   DROP INDEX tiny.servicos_chave_acesso_unique;
--   ALTER TABLE tiny.servicos ADD CONSTRAINT servicos_numero_nf_unique
--       UNIQUE ("nº_da_nota_fiscal_eletrônica");
--   -- (a reversão só é possível enquanto não houver dois números iguais na tabela)

BEGIN;

ALTER TABLE tiny.servicos
    DROP CONSTRAINT IF EXISTS servicos_numero_nf_unique;

CREATE UNIQUE INDEX IF NOT EXISTS servicos_chave_acesso_unique
    ON tiny.servicos ("código_de_verificação_nf")
    WHERE "código_de_verificação_nf" ~ '^[0-9]{50}$';

COMMENT ON INDEX tiny.servicos_chave_acesso_unique IS
    'Identidade da NFS-e no padrão nacional. Parcial porque as notas históricas '
    'não têm chave de acesso. O número da nota NÃO é único: a numeração reiniciou '
    'em 18/06/2026 com a migração para o Emissor Nacional.';

COMMIT;
