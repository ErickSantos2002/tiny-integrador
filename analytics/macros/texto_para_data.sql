{% macro texto_para_data(coluna) %}
{#-
  Converte data guardada como TEXTO em `date`, aceitando as duas convencoes que convivem na
  mesma coluna: "17/01/2024" (brasileira) e "2024-01-17" (ISO).

  ## Por que NAO da para usar `::date` direto

  ⚠️ Este e o defeito mais perigoso que este projeto encontrou, porque ele **acerta o
  suficiente para nao levantar erro**. O banco esta com `datestyle = ISO, MDY` — mes
  primeiro. Entao:

      "17/01/2024"::date  ->  ERRO (nao existe mes 17)
      "05/01/2024"::date  ->  1 de MAIO, silenciosamente. Era 5 de janeiro.

  Medido em 2026-09-08 em `tiny.servicos.data_de_competência`, 5.227 linhas:
  2.856 no formato brasileiro e 2.370 em ISO. Das brasileiras, **1.346 tem dia <= 12** —
  essas trocariam dia por mes sem reclamar. As outras 1.510 estouram, e foi so por isso que
  o problema apareceu: o `fato_servicos` bateu numa das que estouram. Se todas as datas
  fossem de dia 1 a 12, o modelo teria sido construido com um terco das competencias
  jogadas para o mes errado e ninguem veria.

  ## A regra

  O formato e decidido pelo PADRAO do texto, nunca pelo `datestyle` do servidor — que e
  configuracao de ambiente e pode mudar sem ninguem avisar. `to_date` com mascara explicita
  nao depende dele.

  Texto que nao casa com nenhum dos dois formatos vira NULL, e nao um erro: data
  desconhecida e um fato sobre o dado, e derrubar a construcao inteira por causa dela
  esconderia as outras 5.226 linhas boas. Quem precisa que nao seja nula poe um `not_null`.
-#}
    case
        when nullif(btrim({{ coluna }}::text), '') is null
            then null
        when btrim({{ coluna }}::text) ~ '^\d{2}/\d{2}/\d{4}'
            then to_date(substring(btrim({{ coluna }}::text) from 1 for 10), 'DD/MM/YYYY')
        when btrim({{ coluna }}::text) ~ '^\d{4}-\d{2}-\d{2}'
            then to_date(substring(btrim({{ coluna }}::text) from 1 for 10), 'YYYY-MM-DD')
        else null
    end
{% endmacro %}
