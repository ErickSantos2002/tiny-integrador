{#
  Clientes, tipados e com o documento normalizado (item 4.3).

  Só limpeza — nenhuma decisão de identidade aqui. Quem vence quando o mesmo documento
  aparece duas vezes é assunto do 4.4, e é decisão de negócio, não de SQL.

  Por que o `documento` é a peça central: `servicos` e `contas_*` NÃO têm `id_cliente`,
  guardam só o CPF/CNPJ em texto com máscara inconsistente. O documento em dígitos é a
  única chave que atravessa os três processos — sem ele, 90% dos tomadores de NFS-e não
  encontram seu cliente e as ilhas do item 4.8 continuam ilhas.

  Medido em 2026-09-06 sobre as 2.083 linhas da bronze:
    - 2.062 documentos distintos, **20 documentos aparecem duas vezes** (40 linhas);
    - 1 cliente sem documento nenhum;
    - 0 documentos com tamanho estranho — todos têm 11 (69) ou 14 (2.013) dígitos.
      A máscara suja é só pontuação, não há lixo de digitação. Por isso a limpeza
      resolve o formato inteiro e sobra apenas o problema de identidade.

  🔒 A tabela carrega PII (documento, nome, e-mail, telefone). Regra 6 do roadmap: não
  sai do servidor. A `dim_cliente` da Fase 5 é que isola isso com acesso restrito (5.2).
#}

with bronze as (

    select * from {{ source('tiny', 'clientes') }}

),

limpo as (

    select
        id,

        -- a chave de negócio (Fase 1.5)
        {{ so_digitos('cpf_cnpj') }}                     as documento,
        cpf_cnpj                                         as documento_original,

        -- Derivado do TAMANHO, não do campo `tipo_pessoa` da origem: o tamanho é um
        -- fato do documento, enquanto `tipo_pessoa` é digitado e pode divergir. Manter
        -- os dois lado a lado deixa a divergência medível em vez de invisível.
        case length({{ so_digitos('cpf_cnpj') }})
            when 11 then 'cpf'
            when 14 then 'cnpj'
            else null
        end                                              as tipo_documento,
        tipo_pessoa                                      as tipo_pessoa_origem,

        {{ normalizar_texto('nome') }}                   as nome,
        nome                                             as nome_original,

        {{ normalizar_texto('cidade') }}                 as cidade,
        upper(nullif(btrim(uf), ''))                     as uf,
        {{ normalizar_texto('bairro') }}                 as bairro,
        {{ normalizar_texto('endereco') }}               as endereco,
        numero                                           as endereco_numero,
        {{ normalizar_texto('complemento') }}            as complemento,
        {{ so_digitos('cep') }}                          as cep,

        {{ so_digitos('fone') }}                         as telefone,
        lower(nullif(btrim(email), ''))                  as email,
        nullif(btrim(ie), '')                            as inscricao_estadual

    from bronze

)

select * from limpo
