{#
  Normalização de texto digitado por gente.

  Existe porque a bronze é cheia de campo livre — marcador, natureza de operação,
  histórico de conta — e o mesmo conceito aparece como "NF cancelada", "nf cancelada"
  e "NF CANCELADA ". Comparar sem normalizar já custou caro: em 2026-08-13 duas cópias
  da régua de faturamento divergiram exatamente por isso (uma normalizava o caixa, a
  outra não) e o relatório de 2025 saiu inflado.

  O que faz, nesta ordem:
    1. apaga os invisíveis de largura zero (soft hyphen, zero-width, BOM)
    2. troca os espaços que não são o espaço comum (NBSP, tab, ideográfico) por espaço
    3. minúsculas
    4. remove acento (`unaccent` não está instalado no servidor — `translate` resolve
       sem exigir extensão, e a lista cobre o que aparece em português)
    5. colapsa espaço repetido e quebra de linha em um espaço só
    6. tira espaço das pontas

  Os passos 1 e 2 entraram em 2026-09-06, ao deduplicar cliente (4.4). Dois cadastros do
  mesmo CNPJ pareciam empresas diferentes porque um deles tinha **NBSP no lugar do espaço
  e soft hyphen no lugar do hífen** — invisíveis na tela, e o texto normalizado continuava
  diferente. Medido na bronze inteira naquele dia: 3 linhas de `clientes.nome` afetadas
  (uma com NBSP+soft hyphen, duas com TAB) e **zero** em `marcadores.descricao` e
  `natureza_operacao`, então o faturamento nunca esteve em risco por isso — conferido
  rodando a silver antes e depois: mesmas 4.330 notas, mesmo faturamento.

  Os zero-width (8203, 8204, 8205, 65279) e os espaços tipográficos (8239, 12288) não
  apareceram na medição: entram porque são exatamente a mesma classe de defeito e custam
  um caractere na lista. Melhor do que descobrir um a um, cada vez com um cliente órfão.
#}

{% macro normalizar_texto(coluna) %}
    nullif(
        btrim(
            regexp_replace(
                translate(
                    lower(
                        translate(
                            -- espaços que não são o espaço comum viram espaço:
                            -- NBSP, tab, narrow NBSP, ideográfico
                            translate(
                                -- invisíveis de largura zero somem (destino vazio):
                                -- soft hyphen, ZWSP, ZWNJ, ZWJ, BOM
                                -- `::text` porque coluna que "parece texto" às vezes não é:
                                -- `servicos.status_da_nota_fiscal` é numeric, e sem o cast
                                -- a macro estoura com "function translate(numeric...) does
                                -- not exist" só na hora de rodar.
                                {{ coluna }}::text,
                                chr(173) || chr(8203) || chr(8204) || chr(8205) || chr(65279),
                                ''
                            ),
                            chr(160) || chr(9) || chr(8239) || chr(12288),
                            '    '
                        )
                    ),
                    'áàâãäéèêëíìîïóòôõöúùûüçñ',
                    'aaaaaeeeeiiiiooooouuuucn'
                ),
                '\s+', ' ', 'g'
            )
        ),
        ''
    )
{% endmacro %}


{#
  Só os dígitos de um CPF/CNPJ.

  É a CHAVE DE NEGÓCIO do cliente (Fase 1.5) e a única que atravessa os três processos:
  `servicos` e `contas_*` não têm `id_cliente`, guardam o documento em texto com máscara
  inconsistente. Sem isso, 90% dos tomadores de NFS-e não encontram seu cliente.
#}

{% macro so_digitos(coluna) %}
    nullif(regexp_replace(coalesce({{ coluna }}, ''), '[^0-9]', '', 'g'), '')
{% endmacro %}
