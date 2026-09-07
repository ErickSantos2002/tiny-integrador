# datacore-analytics

Camada analítica sobre os dados de vendas de um ERP (Tiny), construída com **dbt** em cima
de **PostgreSQL 17**.

O ponto de partida não é um projeto vazio: já existe um banco em produção que recebe, duas
vezes por dia, uma carga incremental do ERP. O que **não** existe é uma camada analítica —
a regra de negócio está espalhada dentro de queries de dashboard e de endpoints de uma API.
Este repositório é a correção disso.

---

## O problema, em uma frase

> A definição de "venda" está escrita em três lugares diferentes, nenhum deles é o banco,
> e os três discordam entre si.

Exemplos medidos antes de escrever qualquer linha de modelo:

| Achado | Impacto |
|---|---|
| Filtro de notas canceladas comparando texto com `IN` **case-sensitive** | 13 notas canceladas contadas como faturamento — cerca de 1% do total |
| CFOP filtrado por substring em campo de texto livre, existindo campo estruturado | 12 notas de exportação (CFOP 7102) somem do relatório, sem erro |
| `cpf_cnpj` gravado com e sem pontuação | ~20 clientes duplicados: o mesmo CNPJ vira dois clientes |

Nenhum desses erros gera mensagem de erro. É exatamente por isso que eles duram anos.

---

## O que está aqui e o que não está

Este repositório é **público**, porque o código pertence à empresa e ela precisa poder
continuar rodando sem depender de ninguém em particular. Isso impõe uma regra:

> **O repositório carrega a régua, não o resultado.**

Proporção pode — *"74,1% do faturamento não tem vendedor atribuído"* explica a decisão sem
expor o tamanho da operação. Valor absoluto em real, não. A regra é verificada por
`scripts/verificar_sem_valores.sh`, para não depender de alguém lembrar dela a cada commit.

Por isso os relatórios de medição (perfilagem da base, régua antes/depois, baseline de
qualidade, glossário de negócio, matriz de barramento, star schema comentado e o roadmap)
**não estão aqui** — eles são feitos de números. Vivem num repositório interno, na própria
VPS da empresa, dentro do ambiente onde os números já moram de qualquer forma.

Nada do que falta é preciso para **rodar**: os comentários de cada modelo carregam a
decisão e o porquê. O que falta é o aprofundamento.

---

## Arquitetura

```
  ERP (Tiny)  ──extratores Python──►  bronze        silver            gold
              notas 04h/15h UTC       schema `tiny` schema `silver`   schema `gold`
              contas 10h · estoque 16h                                + `snapshots`
                                      cópia crua    limpo,            star schema
                                      da origem     conformado,       pronto pra
                                                    regra única       consumo
                                          │
                                          └── `operacao.execucoes_job`
                                              (quando cada carga rodou e quanto trouxe)
```

- **bronze** (`tiny`) — cópia fiel da origem. Quem escreve são os **extratores Python** do
  `tiny-integrador`, que substituíram os quatro fluxos do n8n em 2026-09-04.
- **silver** — onde o dado bruto vira dado confiável: tipos corretos, texto normalizado,
  clientes deduplicados, curadoria humana versionada e **a definição única de "venda"**.
- **gold** — star schema: 2 fatos, 6 dimensões, e o monitor de volume das cargas.
- **snapshots** — SCD Tipo 2 de cliente e produto. ⚠️ Só captura quando `dbt snapshot` roda.
- **`operacao`** — não é camada de dado, é de observabilidade: é ela que responde "a carga
  rodou?" e sustenta tanto o `freshness` quanto o monitor de volume.

### O que existe hoje (2026-09-06)

| | |
|---|---|
| Modelos | **19** (13 silver, 6 gold) |
| Testes | **160**, com severidade escolhida caso a caso ([política](docs/06-politica-de-severidade.md)) |
| Seeds | 5, incluindo 739 decisões humanas versionadas |
| `dbt build` | **194 nós — PASS=192, WARN=2, ERROR=0** |
| Faturamento pela régua única | **4.330 notas** (o valor fica no repositório interno de medições) |

---

## Regras do projeto

| # | Regra | Por quê |
|---|---|---|
| 1 | O schema `tiny` é **intocável** | É a bronze. Desde 2026-09-04 quem escreve nela são os extratores Python, não mais o n8n — a regra não mudou, trocou de dono. |
| 2 | Nada roda como superusuário | Existe uma role `dbt` sem permissão de escrita na bronze. |
| 3 | Todo SQL vive no Git | Se está só no dashboard, não existe. |
| 4 | Nada vai pra `prod` sem passar por `dev` | Dois targets no dbt. |
| 5 | O que existe hoje continua funcionando | Migração gradual, sem big bang. |
| 6 | PII não sai do servidor | O banco tem CPF, nome e email de pessoas físicas. |

A regra 2 não é disciplina: a role `dbt` foi testada e **não consegue** executar
`INSERT`, `UPDATE`, `DELETE`, `DROP`, `CREATE`, `ALTER` nem `TRUNCATE` no schema `tiny`.

---

## Stack

- **PostgreSQL 17.9** — origem e destino (bronze, silver, gold e snapshots no mesmo banco)
- **dbt-core 1.12** com `dbt-postgres` — transformação, testes, documentação e linhagem
- **Git** — versionamento de toda a regra de negócio
- **Extratores Python** (`tiny-integrador`), em timers systemd na VPS — substituíram o n8n
- Orquestração (Fase 8, pendente): hoje cada peça roda em timer próprio, e **o `dbt` ainda
  não está agendado** — inclusive os snapshots, que só guardam história quando rodam

---

## Como rodar

```bash
python -m venv .venv && source .venv/bin/activate   # bash/zsh
pip install dbt-postgres

dbt debug          # confere a conexão
dbt run            # constrói silver e gold
dbt test           # roda os testes de dados
dbt docs generate && dbt docs serve   # catálogo e linhagem
```

A conexão fica em `~/.dbt/profiles.yml`, **fora deste repositório**. A senha vem de variável
de ambiente — nunca de um arquivo versionado.

---

## Estado

👉 **Retomando o trabalho? Comece por [`ONDE-PARAMOS.md`](ONDE-PARAMOS.md)** — o que foi
feito por último, o que espera decisão e como conferir que nada quebrou.


O roteiro completo está em [`ROADMAP.md`](ROADMAP.md), dividido em 11 fases — cada item
marcado com o que foi medido, e **com as vezes em que o próprio roadmap estava errado**.

| Fase | Estado |
|---|---|
| 0 — Fundação e rede de segurança | ✅ menos o 0.9 (risco de segurança, decisão pendente) |
| 1 — Descoberta | ✅ |
| 2 — Definir o negócio | ✅ |
| 3 — Bronze declarada | ✅ |
| 4 — Silver | ✅ (4.1 parcial por decisão) |
| 5 — Gold: star schema | ✅ (falta `fato_servicos`, que o desenho prevê e nenhum item pede) |
| 6 — Qualidade e observabilidade | ✅ menos o 6.5 (depende do frontend do DataCoreHS) |
| 7 — Documentação | em andamento |
| 8 a 11 | pendentes |

**Documentos que valem a leitura antes do código:**

- [`docs/02-glossario.md`](docs/02-glossario.md) — as decisões de negócio, datadas. É o que
  responde "por que o faturamento é esse número".
- [`docs/06-qualidade-depois.md`](docs/06-qualidade-depois.md) — o antes e depois medido,
  **incluindo o que piorou**.
- [`docs/06-politica-de-severidade.md`](docs/06-politica-de-severidade.md) — por que nem
  todo teste é `error`.
- [`docs/02-star-schema.md`](docs/02-star-schema.md) — o desenho e as cinco divergências
  entre ele e a obra.

⚠️ **Limites conhecidos**, para não descobrir depois:
- o `dbt` não está agendado (Fase 8) — inclusive os snapshots;
- o monitor de volume ainda não tem histórico para julgar;
- 20 clientes duplicados, 318 itens sem código e 79% das notas sem vendedor seguem
  esperando conserto **na origem**, onde este projeto não alcança;
- o Postgres **não tem backup configurado** no EasyPanel.
