{#
  Cliente único por documento — o item 4.4, a regra de sobrevivência.

  **A identidade é o DOCUMENTO, não a linha de cadastro.** Decidido por Erick em
  2026-09-06, com os números na mesa:

    - 20 documentos aparecem em dois cadastros (40 linhas de 2.083);
    - em **18 dos 20**, os dois lados têm o MESMO número de campos preenchidos — ou seja,
      "vence o mais completo" não decidiria quase nada (11,7 contra 11,6 de média);
    - em **19 dos 20**, os DOIS lados têm nota emitida. Não é caso de descartar o cadastro
      vazio: é fusão de verdade, e 34 notas ficariam órfãs se a regra fosse escolher uma
      linha e ignorar a outra.

  Por isso o registro canônico é **construído, não escolhido**: cada atributo pega o valor
  mais recente que não esteja vazio. Nada se perde — o telefone que só o cadastro antigo
  tinha continua no resultado, junto do e-mail que só o novo tinha.

  ⚠️ **"Mais recente" aqui é o maior `id`**, e isso é uma aproximação consciente:
  `tiny.clientes` NÃO tem coluna de data (nem `created_at`, nem `updated_at`). O id do Tiny
  é sequencial, então id maior = cadastrado depois. Se um dia a origem ganhar data de
  cadastro, é ela que deve mandar aqui.

  `ids_originais` existe para o remapeamento: as notas apontam para ids diferentes do mesmo
  cliente, e é por esse array que o join se resolve sem perder as 34 notas.

  ## Proveniência (item 4.5) — preparando a entrada do CRM

  `dim_cliente` (5.2) vai ser a UNIÃO de três fontes: este cadastro do ERP, os tomadores de
  NFS-e e os sacados das contas. Medido em 2026-09-06: **119 tomadores e 143 sacados não
  estão aqui** — quem só comprou serviço, ou quem comprou antes de 2018. Ou seja, a dimensão
  não pode ser uma cópia desta tabela, e a união só é possível se cada linha souber DE ONDE
  veio e QUAL era seu id lá.

  Por isso `sistema_origem` + `id_no_erp` já nascem aqui, com uma fonte só. Parece redundante
  hoje e deixa de ser no dia em que o GrowthHS (CRM) entrar: `chave_cliente` continua sendo o
  documento, e o mesmo cliente vindo de dois sistemas casa sozinho.

  ⚠️ **A chave de quem não tem documento carrega o sistema**, e isso não é preciosismo:
  `sem-documento:tiny_erp:124` × `sem-documento:crm:124`. Sem o sistema no meio, o cliente
  124 do CRM se fundiria com o 124 do Tiny — dois clientes diferentes viram um, em silêncio.
#}

with base as (

    select * from {{ ref('stg_clientes') }}

),

revisao as (

    -- Exceções decididas caso a caso, versionadas em CSV — mesmo desenho do de-para de
    -- marcadores (4.2b). Hoje tem uma linha só, e ela é necessária: o cadastro 2016 tem o
    -- nome corrompido por encoding e é justamente o id MAIOR, então a regra automática
    -- escolheria o nome ilegível.
    select id, decisao from {{ ref('clientes_revisados') }}

),

marcado as (

    select
        b.*,
        coalesce(r.decisao, '') = 'ignorar_nome'            as nome_reprovado,

        -- O cliente sem documento (1 hoje) não pode sumir na agregação nem se juntar aos
        -- outros sem documento: ganha chave própria, e ela carrega o sistema de origem
        -- para não colidir com o id de outro sistema (item 4.5).
        coalesce(
            b.documento,
            'sem-documento:' || '{{ var("sistema_origem_erp", "tiny_erp") }}' || ':' || b.id::text
        )                                                    as chave_cliente

    from base b
    left join revisao r on r.id = b.id

),

canonico as (

    select
        chave_cliente,

        max(id)                     as id_canonico,
        array_agg(id order by id)   as ids_originais,
        count(*)                    as qtd_cadastros,

        -- Proveniência (4.5): de onde veio e qual era o id lá. Hoje há uma fonte só; a
        -- coluna existe para que a união da 5.2 não exija reescrever este modelo.
        '{{ var("sistema_origem_erp", "tiny_erp") }}'   as sistema_origem,
        max(id)                                          as id_no_erp,

        max(documento)              as documento,
        max(tipo_documento)         as tipo_documento,

        -- O nome respeita a seed de revisão; o coalesce é a rede para o caso de TODOS os
        -- nomes de um documento estarem reprovados — melhor um nome ruim que nenhum.
        coalesce(
            (array_agg(nome order by id desc) filter (where nome is not null and not nome_reprovado))[1],
            (array_agg(nome order by id desc) filter (where nome is not null))[1]
        )                                                                                as nome,
        coalesce(
            (array_agg(nome_original order by id desc) filter (where nome_original is not null and not nome_reprovado))[1],
            (array_agg(nome_original order by id desc) filter (where nome_original is not null))[1]
        )                                                                                as nome_original,

        -- Daqui para baixo, sempre a mesma regra: o mais recente que não está vazio.
        (array_agg(tipo_pessoa_origem  order by id desc) filter (where tipo_pessoa_origem  is not null))[1] as tipo_pessoa_origem,
        (array_agg(cidade              order by id desc) filter (where cidade              is not null))[1] as cidade,
        (array_agg(uf                  order by id desc) filter (where uf                  is not null))[1] as uf,
        (array_agg(bairro              order by id desc) filter (where bairro              is not null))[1] as bairro,
        (array_agg(endereco            order by id desc) filter (where endereco            is not null))[1] as endereco,
        (array_agg(endereco_numero     order by id desc) filter (where endereco_numero     is not null))[1] as endereco_numero,
        (array_agg(complemento         order by id desc) filter (where complemento         is not null))[1] as complemento,
        (array_agg(cep                 order by id desc) filter (where cep                 is not null))[1] as cep,
        (array_agg(telefone            order by id desc) filter (where telefone            is not null))[1] as telefone,
        (array_agg(email               order by id desc) filter (where email               is not null))[1] as email,
        (array_agg(inscricao_estadual  order by id desc) filter (where inscricao_estadual  is not null))[1] as inscricao_estadual

    from marcado
    group by chave_cliente

)

select * from canonico
