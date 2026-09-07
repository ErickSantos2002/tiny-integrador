{#
    Onde cada model vai parar.

    O comportamento padrao do dbt e grudar o schema custom no schema do target
    (silver viraria "dbt_dev_erick_silver" em dev E em prod). Isso quebra prod.

    Aqui:
      target prod  ->  silver / gold / snapshots        (os schemas de verdade)
      target dev   ->  dbt_dev_erick_silver / _gold ... (isolado, nunca colide)

    Consequencia pratica: rodar `dbt run` sem pensar NAO tem como sujar producao.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}

    {%- set default_schema = target.schema -%}

    {%- if custom_schema_name is none -%}
        {{ default_schema }}

    {%- elif target.name == 'prod' -%}
        {{ custom_schema_name | trim }}

    {%- else -%}
        {{ default_schema }}_{{ custom_schema_name | trim }}

    {%- endif -%}

{%- endmacro %}
