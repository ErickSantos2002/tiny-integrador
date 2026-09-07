{#
  A Páscoa calculada tem que bater com as datas reais, ano a ano.

  O algoritmo gregoriano anônimo é aritmética inteira e não tem como "quase funcionar":
  ou acerta, ou erra por dias inteiros. Como Carnaval, Sexta-feira Santa e Corpus Christi
  penduram nele, um erro aqui move TRÊS feriados por ano e corrompe todo cálculo de prazo
  e de dia útil — em silêncio, porque a data errada continua sendo uma data válida.

  As 13 datas abaixo são de calendário, verificáveis fora daqui. Cobrem 2015 (onde a
  empresa começa) até 2027 (onde há conta com vencimento).

  `severity: error`: se isto falhar, a dimensão inteira está mentindo.
#}

{{ config(severity = 'error') }}

with conhecidas (ano, pascoa_real) as (

    values
        (2015, date '2015-04-05'),
        (2016, date '2016-03-27'),
        (2017, date '2017-04-16'),
        (2018, date '2018-04-01'),
        (2019, date '2019-04-21'),
        (2020, date '2020-04-12'),
        (2021, date '2021-04-04'),
        (2022, date '2022-04-17'),
        (2023, date '2023-04-09'),
        (2024, date '2024-03-31'),
        (2025, date '2025-04-20'),
        (2026, date '2026-04-05'),
        (2027, date '2027-03-28')

),

calculada as (

    select distinct ano, domingo_de_pascoa
    from {{ ref('dim_tempo') }}

)

select
    c.ano,
    c.pascoa_real,
    k.domingo_de_pascoa as pascoa_calculada

from conhecidas c
join calculada k on k.ano = c.ano
where k.domingo_de_pascoa <> c.pascoa_real
