{#
  Dimensão de tempo — GERADA, não extraída (item 5.1).

  Gerada porque uma dimensão de tempo tirada dos fatos só tem os dias em que houve
  movimento: o mês sem venda simplesmente não existe, e a série temporal mente por omissão
  ("caiu para zero" vira "sumiu do gráfico"). Aqui todo dia existe, tenha acontecido algo
  ou não.

  **Cobertura: 2015 a 2030.** 2015 porque é onde a empresa começa — a primeira NF-e é de
  2015-01-08 e a primeira NFS-e de 2015-01-05, e as contas a receber recuperadas no item
  0.15 chegam até lá. 2030 dá folga para vencimento futuro (há contas com vencimento em
  2027) sem inchar a tabela: são ~5.800 linhas.

  ## Feriado é calculado, não listado

  Três feriados brasileiros são móveis e todos penduram na Páscoa: **Carnaval (−47 dias),
  Sexta-feira Santa (−2) e Corpus Christi (+60)**. A alternativa — uma lista de datas
  mantida à mão — envelhece em silêncio: no ano em que alguém esquecer de acrescentar, o
  Carnaval vira dia útil e todo cálculo de prazo erra sem acusar nada.

  Por isso a Páscoa sai do algoritmo gregoriano anônimo (Meeus/Jones/Butcher), aritmética
  inteira pura, válido para qualquer ano. Conferido contra datas conhecidas no teste
  `pascoa_bate_com_datas_conhecidas`.

  ⚠️ **Consciência Negra (20/11) só entra a partir de 2024**, quando virou feriado
  NACIONAL (Lei 14.759/2023). Antes disso era feriado em parte dos municípios, e tratar
  como nacional em 2015–2023 seria inventar dia não útil no passado.

  ## Feriado × ponto facultativo — a distinção que muda o número

  Pesquisado em 2026-09-06, e derrubou duas suposições minhas: **Carnaval e Corpus Christi
  NÃO são feriado** — nem nacional, nem municipal no Recife. São **ponto facultativo**, e
  a diferença é jurídica e prática: no facultativo o serviço público para, mas a empresa
  privada decide, e não há obrigação legal de liberar. Chamar de feriado tiraria da conta
  dias em que a H&S pode estar operando.

  Por isso são duas colunas, e quem consome escolhe:
    - `dia_util`               → não é fim de semana nem FERIADO (a definição legal);
    - `dia_util_operacional`   → também desconta o ponto facultativo (o que de fato
                                 acontece em Recife no Carnaval).

  **Feriados municipais do Recife**, Lei Municipal nº 9.777, de 16/06/1967 (art. 1º):
  **Sexta-feira Santa · 24/06 São João · 16/07 Nossa Senhora do Carmo (padroeira) ·
  08/12 Nossa Senhora da Conceição.** São feriados de verdade, não facultativos — e num
  negócio sediado em Recife isso muda prazo de entrega e contagem de atraso.

  ⚠️ Não modelado de propósito: a **quarta-feira de cinzas** é meio expediente (até 14h),
  e "meio dia útil" não cabe numa flag booleana. E em Pernambuco o ponto facultativo de
  Corpus Christi **costuma ser transferido para 23/06**, véspera de São João — mas isso é
  decreto estadual publicado ano a ano, não regra estável: modelar seria fingir previsão.
#}

{{ config(materialized = 'table') }}

with dias as (

    select generate_series(
        date '2015-01-01',
        date '2030-12-31',
        interval '1 day'
    )::date as data

),

anos as (

    select distinct extract(year from data)::int as ano from dias

),

-- ------------------------------------------------------------------ Páscoa
-- Algoritmo gregoriano anônimo, passo a passo. Cada CTE é uma linha do algoritmo, para
-- que dê para conferir contra a referência sem decifrar uma expressão gigante.
p1 as (

    select
        ano,
        ano % 19            as a,
        ano / 100           as b,
        ano % 100           as c
    from anos

),

p2 as (

    select
        ano, a, b, c,
        b / 4               as d,
        b % 4               as e,
        (b + 8) / 25        as f
    from p1

),

p3 as (

    select
        ano, a, b, c, d, e, f,
        (b - f + 1) / 3     as g,
        c / 4               as i,
        c % 4               as k
    from p2

),

p4 as (

    select
        ano, a, c, d, e, g, i, k,
        (19 * a + b - d - g + 15) % 30      as h
    from p3

),

p5 as (

    select
        ano, a, h,
        (32 + 2 * e + 2 * i - h - k) % 7    as l
    from p4

),

p6 as (

    select
        ano, h, l,
        (a + 11 * h + 22 * l) / 451         as m
    from p5

),

pascoa as (

    select
        ano,
        make_date(
            ano,
            (h + l - 7 * m + 114) / 31,
            ((h + l - 7 * m + 114) % 31) + 1
        ) as domingo_de_pascoa
    from p6

),

feriados_moveis as (

    select
        ano,
        domingo_de_pascoa,
        domingo_de_pascoa - 47  as carnaval,          -- terça de carnaval
        domingo_de_pascoa -  2  as sexta_santa,
        domingo_de_pascoa + 60  as corpus_christi
    from pascoa

),

base as (

    select
        d.data,
        extract(year    from d.data)::int    as ano,
        extract(month   from d.data)::int    as mes,
        extract(day     from d.data)::int    as dia,
        extract(quarter from d.data)::int    as trimestre,
        -- ISO: 1 = segunda … 7 = domingo. Explícito porque `dow` do Postgres começa no
        -- domingo com 0, e confundir os dois inverte "fim de semana".
        extract(isodow  from d.data)::int    as dia_da_semana,
        -- colunas de `f` listadas uma a uma: `f.*` traria o `ano` dele junto com o meu,
        -- e o Postgres para com "column reference ano is ambiguous"
        f.domingo_de_pascoa,
        f.carnaval,
        f.sexta_santa,
        f.corpus_christi
    from dias d
    join feriados_moveis f on f.ano = extract(year from d.data)::int

),

classificado as (

    select
        data,
        ano,
        mes,
        dia,
        trimestre,
        dia_da_semana,

        to_char(data, 'YYYY-MM')                     as ano_mes,

        -- Nome em português por CASE, não por `to_char(..., 'TMDay')`: o `TM` usa o
        -- `lc_time` do SERVIDOR, que aqui é en_US e devolvia "Thursday". Depender de
        -- locale de servidor para rotular gráfico é frágil — muda com a máquina, não
        -- com o código, e ninguém liga o defeito à causa.
        case extract(isodow from data)::int
            when 1 then 'segunda-feira' when 2 then 'terca-feira'
            when 3 then 'quarta-feira'  when 4 then 'quinta-feira'
            when 5 then 'sexta-feira'   when 6 then 'sabado'
            when 7 then 'domingo'
        end                                          as nome_dia_semana,
        case extract(month from data)::int
            when 1 then 'janeiro'   when 2  then 'fevereiro' when 3  then 'marco'
            when 4 then 'abril'     when 5  then 'maio'      when 6  then 'junho'
            when 7 then 'julho'     when 8  then 'agosto'    when 9  then 'setembro'
            when 10 then 'outubro'  when 11 then 'novembro'  when 12 then 'dezembro'
        end                                          as nome_mes,

        dia_da_semana >= 6                           as fim_de_semana,

        case
            -- nacionais fixos
            when (mes, dia) = (1, 1)    then 'confraternizacao universal'
            when (mes, dia) = (4, 21)   then 'tiradentes'
            when (mes, dia) = (5, 1)    then 'dia do trabalho'
            when (mes, dia) = (9, 7)    then 'independencia'
            when (mes, dia) = (10, 12)  then 'nossa senhora aparecida'
            when (mes, dia) = (11, 2)   then 'finados'
            when (mes, dia) = (11, 15)  then 'proclamacao da republica'
            when (mes, dia) = (12, 25)  then 'natal'
            -- nacional só a partir de 2024 (Lei 14.759/2023) — ver cabeçalho
            when (mes, dia) = (11, 20) and ano >= 2024 then 'consciencia negra'
            -- estadual de Pernambuco
            when (mes, dia) = (3, 6)    then 'revolucao pernambucana (PE)'
            -- municipais do Recife, Lei 9.777/1967 art. 1º
            when (mes, dia) = (6, 24)   then 'sao joao (Recife)'
            when (mes, dia) = (7, 16)   then 'nossa senhora do carmo, padroeira (Recife)'
            when (mes, dia) = (12, 8)   then 'nossa senhora da conceicao (Recife)'
            -- móvel, e também municipal pela mesma lei
            when data = sexta_santa     then 'sexta-feira santa'
        end                                          as feriado,

        -- NÃO são feriado: ninguém é obrigado a liberar. Ver o cabeçalho.
        case
            when data = carnaval        then 'carnaval (terca)'
            when data = carnaval - 1    then 'carnaval (segunda)'
            when data = corpus_christi  then 'corpus christi'
        end                                          as ponto_facultativo,

        domingo_de_pascoa

    from base

)

select
    data,
    ano,
    mes,
    dia,
    trimestre,
    ano_mes,
    dia_da_semana,
    btrim(nome_dia_semana)          as nome_dia_semana,
    btrim(nome_mes)                 as nome_mes,
    fim_de_semana,
    feriado is not null             as e_feriado,
    feriado,
    ponto_facultativo is not null   as e_ponto_facultativo,
    ponto_facultativo,

    -- a definição LEGAL de dia útil
    not fim_de_semana
        and feriado is null         as dia_util,
    -- o que de fato acontece em Recife: no Carnaval a cidade para, mesmo sem ser feriado
    not fim_de_semana
        and feriado is null
        and ponto_facultativo is null as dia_util_operacional,

    domingo_de_pascoa

from classificado
