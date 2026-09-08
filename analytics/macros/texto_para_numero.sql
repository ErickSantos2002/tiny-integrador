{% macro texto_para_numero(coluna) %}
{#-
  Converte valor guardado como TEXTO em `numeric`, aceitando as DUAS convencoes que
  convivem na mesma base: "1234.50" (ponto decimal) e "3.880,00" (ponto de milhar com
  virgula decimal).

  ## Por que existe

  `tiny.servicos` guarda todo valor como `text`, e a mistura e POR COLUNA, nao por periodo.
  Medido em 2026-09-08 nas 5.227 linhas:

      valor_dos_servicos    ......      0 com virgula
      valor_do_iss          ...... 4.385 com virgula
      valor_total_recebido  ...... 3.123 com virgula
      valor_das_deducoes    ...... 2.857 com virgula

  O comentario da `stg_servicos` dizia "nenhuma virgula, 100% conversivel", medido em
  2026-09-06 — mas a medicao olhou so a coluna do servico, a unica que de fato nao tem. As
  outras tres sempre tiveram, e ninguem percebeu porque a silver e VIEW: o cast nunca chega
  a rodar ate alguem materializar. Quebrou no primeiro `fato_servicos`.

  ## A regra, que nao e obvia

  ⚠️ **So quando ha virgula os pontos sao separador de milhar.** Sem virgula, o ponto E o
  separador decimal — trocar isso faria "1234.50" virar 123450, cem vezes maior, sem erro
  nenhum. Sao 18 linhas com as duas coisas juntas ("3.880,00"), onde um replace ingenuo de
  virgula por ponto produziria "3.880.00", que nem numero e.

  Vazio e nulo viram 0: em valor de nota fiscal, ausencia e zero, e deixar NULL faria
  qualquer soma com ele devolver NULL.
-#}
    case
        when nullif(btrim({{ coluna }}::text), '') is null
            then 0
        when btrim({{ coluna }}::text) like '%,%'
            then replace(replace(btrim({{ coluna }}::text), '.', ''), ',', '.')::numeric
        else
            btrim({{ coluna }}::text)::numeric
    end
{% endmacro %}
