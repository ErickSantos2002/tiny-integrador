-- Adiciona coluna 'cancelada' na tabela servicos
-- Execute este script no seu banco de dados PostgreSQL

ALTER TABLE tiny.servicos
ADD COLUMN IF NOT EXISTS cancelada BOOLEAN DEFAULT FALSE;

-- Atualiza notas existentes para não canceladas por padrão
UPDATE tiny.servicos
SET cancelada = FALSE
WHERE cancelada IS NULL;

-- Comentário da coluna
COMMENT ON COLUMN tiny.servicos.cancelada IS 'Indica se a nota fiscal foi cancelada';
