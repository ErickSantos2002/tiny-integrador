-- 003 — Marca a conta que sumiu do Tiny, em vez de deixá-la "em aberto" para sempre.
--
-- POR QUÊ
-- Confirmado com o financeiro em 2026-09-05: quando uma conta **atrasa**, eles excluem
-- a conta em aberto no Tiny e emitem uma nova, com id novo. A antiga desaparece da
-- origem, mas continua aqui como `situacao = 'aberto'` — inflando o passivo com
-- compromisso que já foi substituído.
--
-- O tamanho do engano, medido em 2026-09-05:
--   contas_pagar    237 em aberto (R$ 1.019.016,68) → só 11 (R$ 56.945,11) existem no Tiny
--   contas_receber  608 em aberto (R$ 2.226.367,87) → 567 (R$ 2.052.887,07) existem
-- As 226 + 41 restantes a API responde com codigo_erro 32, "Conta não localizada".
--
-- Não é passivo único, é fluxo contínuo: entre 04/09 e 05/09 surgiram 3 órfãs novas.
-- Por isso quem marca é o job, a cada passagem, e não um UPDATE de mão.
--
-- POR QUE MARCAR E NÃO APAGAR
-- A linha é a prova de que aquele atraso aconteceu — matéria-prima para medir
-- inadimplência na gold. `DELETE` destrói isso e não tem volta; a coluna tem. E a
-- bronze registra o que a origem disse, inclusive que a conta deixou de existir:
-- filtrar é trabalho da silver (Regra 1 do roadmap segue de pé).
--
-- REVERSÃO
--   ALTER TABLE tiny.contas_pagar   DROP COLUMN excluida_na_origem_em;
--   ALTER TABLE tiny.contas_receber DROP COLUMN excluida_na_origem_em;

BEGIN;

ALTER TABLE tiny.contas_pagar
    ADD COLUMN IF NOT EXISTS excluida_na_origem_em TIMESTAMP NULL;
ALTER TABLE tiny.contas_receber
    ADD COLUMN IF NOT EXISTS excluida_na_origem_em TIMESTAMP NULL;

COMMENT ON COLUMN tiny.contas_pagar.excluida_na_origem_em IS
    'Quando o Tiny passou a responder "não localizada" (codigo_erro 32) para esta conta. '
    'NULL = existe na origem. Preenchido = foi excluída lá, quase sempre por atraso: o '
    'financeiro exclui a conta vencida e reemite com id novo. Não somar em "em aberto".';
COMMENT ON COLUMN tiny.contas_receber.excluida_na_origem_em IS
    'Quando o Tiny passou a responder "não localizada" (codigo_erro 32) para esta conta. '
    'NULL = existe na origem. Preenchido = foi excluída lá, quase sempre por atraso: o '
    'financeiro exclui a conta vencida e reemite com id novo. Não somar em "em aberto".';

-- O job pergunta "o que ainda preciso reconferir?" a cada passagem: as em aberto que
-- ainda existem na origem. Sem índice isso é varredura na tabela inteira todo dia.
CREATE INDEX IF NOT EXISTS contas_pagar_reconferir_idx
    ON tiny.contas_pagar (situacao) WHERE excluida_na_origem_em IS NULL;
CREATE INDEX IF NOT EXISTS contas_receber_reconferir_idx
    ON tiny.contas_receber (situacao) WHERE excluida_na_origem_em IS NULL;

COMMIT;
