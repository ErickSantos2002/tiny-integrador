# Fase 6.2 — Política de severidade

Escrito em **2026-09-06**, com 160 testes no projeto.

**O problema que esta política evita** é conhecido e já aconteceu aqui: o job de contas
falhava **todo dia** por um motivo conhecido, e uma falha nova ficava indistinguível do
barulho (item 0.11). Alarme que grita sempre é alarme desligado — e desligado por quem
tinha razão em desligar.

Por isso a regra não é "quanto mais `error`, mais seguro". É o contrário.

---

## As três categorias, e o critério para escolher

### 🔴 `error` — o número está errado ou vai ficar
Trava a build. Reservado para o que **corrompe o dado ou o esconde**:

| Teste | O que pega |
|---|---|
| `fato_vendas_reconcilia_com_a_silver` | linha perdida ou multiplicada num join do star schema |
| `fato_contas_reconcilia_com_a_silver` | o mesmo, no fato de contas |
| `rateio_reconcilia_com_a_nota` | rateio que não fecha com a nota (tolerância R$ 0,01) |
| `achatamento_nao_multiplicou_nota` | as 43 notas multi-marcador duplicando o faturamento |
| `regra_valores_nao_sao_negativos` | dinheiro negativo em fato |
| `regra_datas_nao_sao_futuras` | emissão/liquidação no futuro (erro de digitação de ano) |
| `nota_fora_da_quarentena_esta_completa` | nota quebrada **nova** (as conhecidas estão na 6.3) |
| `pascoa_bate_com_datas_conhecidas` | Páscoa errada move três feriados por ano |
| `dia_util_operacional_e_subconjunto_do_legal` | as duas flags de dia útil invertidas |
| `unique` / `not_null` de chave, `relationships` fato→dimensão | integridade do modelo |

**O traço comum:** todos falham com número plausível na tela. Nenhum deles grita sozinho —
é por isso que precisam travar.

### 🟡 `warn` — a origem está incompleta, e o modelo não conserta origem
Aparece no relatório, não trava:

| Teste | Por que não é `error` |
|---|---|
| `marcador_com_grafia_nova` | grafia nova é evento esperado; exige decisão humana, não correção de código |
| `marcador_ambiguo_apos_o_padrao` | ambiguidade é do negócio, e a decisão do dono foi deixar contando |
| `curadoria_de_tipo_fora_da_seed` | alguém curou na tela e não exportou — lembrete, não defeito |
| `curadoria_de_nfse_cancelada_fora_da_seed` | idem |
| `cliente_com_nome_divergente_nao_revisado` | par novo precisa de olho humano antes de fundir |
| `documento_de_cliente_tem_tamanho_valido` | documento torto se conserta no Tiny, não aqui |
| `venda_tem_cliente_identificavel` | 5 itens; o cadastro é que não tem documento |
| `source_not_null_tiny_itens_nota_cfop` | 2 itens sem CFOP na origem |

**O traço comum:** travar a silver não conserta nenhum deles. O conserto é humano e mora
em outro sistema.

### 🔵 Quarentena — problema conhecido, medido e separado
Não é teste: é **modelo** (`quarentena_notas`, item 6.3). A linha sai do caminho da análise
mas continua existindo, com motivo escrito.

Serve para o caso em que `warn` viraria permanente. As 22 notas vazias eram exatamente
isso — um aviso de 22 linhas que ninguém leria depois da segunda semana. Hoje estão
registradas, e o que vigia é um `error` sobre o que **sobra**.

**A diferença que essa distinção compra:** "temos 22 notas quebradas há meses" é dívida
conhecida; "apareceu uma nota quebrada hoje" é incidente. Sem quarentena, as duas coisas
produzem exatamente o mesmo aviso.

---

## Como o build ficou

| Momento | Avisos |
|---|---|
| manhã de 2026-09-06 | 5 |
| depois da quarentena (6.3) | **1** |

O que restou é um `warn` real: 2 itens sem CFOP na origem.

⚠️ **Regra de manutenção:** todo `warn` precisa de **destino escrito** — o item do roadmap
que vai zerá-lo, ou a decisão de que ele é permanente. `warn` sem destino é ruído com
autorização, e volta a ser desligado.

---

## Quando promover um `warn` a `error`

Aconteceu hoje e serve de exemplo: os `relationships` das ilhas (`servicos` e
`contas_receber` → cliente) nasceram `warn` acusando 240 e 260 linhas. Não eram defeito
daquelas tabelas — era a `dim_cliente` que ainda não existia. Quando a 5.2 ficou pronta, o
teste passou a apontar para a dimensão conforme e **virou `error`**, porque a partir dali
linha sem cliente É defeito.

**O critério:** um `warn` vira `error` quando a causa dele deixa de existir. Enquanto a
causa é estrutural e conhecida, `error` só ensina a equipe a ignorar a build vermelha.
