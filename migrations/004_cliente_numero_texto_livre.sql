-- 004 — `cliente_numero` deixa de ser varchar(10).
--
-- POR QUÊ
-- O campo se chama "número" e parece caber em 10 caracteres, mas na origem é TEXTO LIVRE:
-- o Tiny aceita o que o usuário digitar. Em 2026-09-04 uma conta a receber de R$ 23.520
-- (ITUIUTABA BIOENERGIA, id 616934028) foi rejeitada inteira com StringDataRightTruncation
-- porque o número do endereço vinha como "NAO INFORMADO" — 13 caracteres.
--
-- O `caber_no_schema` daquele dia impediu a perda do registro, mas corta o valor: aquela
-- conta está no banco com "NAO INFORM". É remendo, não conserto — o lugar certo de
-- resolver é a largura da coluna, e é isto aqui.
--
-- 60 e não 10: cabe qualquer variação de "número não informado" que a origem invente, sem
-- fingir que um campo de texto livre tem tamanho previsível. Fica alinhado com os vizinhos
-- (`cliente_endereco` e `cliente_complemento` são varchar(150)).
--
-- Conferido antes de aplicar: das 14 linhas com exatamente 10 caracteres, 13 são o literal
-- "SEM NUMERO", que tem 10 de verdade e não foi cortado. Só uma foi mutilada.
-- Ampliar a coluna não muda dado nenhum; quem restaura o valor é a passagem seguinte do
-- extrator, que reconfere a conta (está `aberto`) e vê a diferença.
--
-- ALTER de varchar(10) para varchar(60) não reescreve a tabela no PostgreSQL (só amplia o
-- limite no catálogo), então não trava as contas em produção.
--
-- REVERSÃO (só possível enquanto nenhum valor passar de 10 caracteres)
--   ALTER TABLE tiny.contas_pagar   ALTER COLUMN cliente_numero TYPE VARCHAR(10);
--   ALTER TABLE tiny.contas_receber ALTER COLUMN cliente_numero TYPE VARCHAR(10);

BEGIN;

ALTER TABLE tiny.contas_pagar   ALTER COLUMN cliente_numero TYPE VARCHAR(60);
ALTER TABLE tiny.contas_receber ALTER COLUMN cliente_numero TYPE VARCHAR(60);

COMMENT ON COLUMN tiny.contas_pagar.cliente_numero IS
    'Número do endereço do cliente. TEXTO LIVRE na origem: aceita "SEM NUMERO", '
    '"NAO INFORMADO" e o que o usuário digitar. Não tratar como numérico.';
COMMENT ON COLUMN tiny.contas_receber.cliente_numero IS
    'Número do endereço do cliente. TEXTO LIVRE na origem: aceita "SEM NUMERO", '
    '"NAO INFORMADO" e o que o usuário digitar. Não tratar como numérico.';

COMMIT;
