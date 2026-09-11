# Fase 7.4 — Runbook: o que fazer quando quebrar às 3 da manhã

Escrito em **2026-09-06**. Todo cenário aqui **já aconteceu** — nenhum é hipótese.

> **Regra zero:** antes de consertar, **meça**. Metade dos incidentes deste projeto foram
> diagnosticados errado na primeira leitura (o mirror do pacman, o `created_at`, o cadastro
> com mojibake). Uma consulta de 30 segundos evita uma hora de conserto na coisa errada.

---

## Onde olhar primeiro

| Pergunta | Onde responde |
|---|---|
| A carga rodou? | `select * from operacao.avisos_cargas;` |
| Rodou e trouxe pouco? | `select * from gold.monitor_volume_carga order by inicio desc;` |
| O dado está velho? | `dbt source freshness` |
| O número está errado? | `dbt test` — a reconciliação é `error` |
| O que a carga fez, linha a linha? | `journalctl -u tiny-extrator@extrair_notas.service -o short-iso` |

---

## 1. A carga não rodou

**Sintoma:** `avisos_cargas` diz *atrasada*, ou o `freshness` dá `ERROR STALE`.

⚠️ **"Atrasada" é o caso mais perigoso dos três** (falha, inacabada, atrasada) porque é o
único **100% silencioso**: nada falhou, simplesmente não aconteceu.

```bash
ssh datacore
systemctl list-timers 'tiny-extrator*'          # o timer está ativo?
systemctl status tiny-extrator-notas.timer
journalctl -u tiny-extrator@extrair_notas.service -n 50 --no-pager
```

**Conserto:** `systemctl start tiny-extrator@extrair_notas.service` — os extratores são
idempotentes e commitam por registro, então rodar de novo é seguro.

⚠️ **Se o timer estiver `inactive`, procure quem desligou antes de religar.** Em 2026-09-05
o timer de notas foi pausado **de propósito** para não colidir com um backfill de 7h, com
religamento agendado. Religar no meio de um backfill estoura o limite de 20 chamadas/min
da API do Tiny.

---

## 2. A carga rodou, mas trouxe quase nada

**Sintoma:** `monitor_volume_carga` com `volume MUITO abaixo do normal`. O job terminou em
**sucesso** — nenhum alarme tradicional dispara.

1. Confirme que não é sazonal: sábado trazer 1 nota é normal (o monitor já compara pelo dia
   da semana, mas confira o `veredito` e o `execucoes_comparaveis`).
2. Veja o log da execução: a API do Tiny devolve **erro com HTTP 200**
   (`retorno.status = "Erro"`), então falha de origem aparece como carga vazia, não como
   exceção.
3. Rode de novo. Se repetir, é a origem.

⚠️ Se o veredito for `sem base de comparacao`, **o monitor não está dizendo que está tudo
bem** — está dizendo que não tem histórico para julgar.

---

## 3. `dbt build` falhou

**Primeiro: leia a severidade.** `WARN` **não** quebrou nada — ver
[política de severidade](06-politica-de-severidade.md). Só `ERROR` exige ação.

| Teste que falhou | O que significa |
|---|---|
| `*_reconcilia_com_a_silver` | 🔴 **Pare tudo.** O fato não bate com a silver: alguma linha se perdeu ou se multiplicou num join. O faturamento está errado agora. |
| `achatamento_nao_multiplicou_nota` | 🔴 Alguém trocou a agregação de marcadores por join — 43 notas duplicaram. |
| `rateio_reconcilia_com_a_nota` | 🔴 O rateio não fecha com a nota. |
| `nota_fora_da_quarentena_esta_completa` | 🟠 Apareceu nota quebrada **nova** (as conhecidas estão na quarentena). |
| `pascoa_bate_com_datas_conhecidas` | 🟠 Cálculo de feriado errado — move três feriados por ano. |
| `relationships_*` | 🟠 Fato apontando para dimensão que não tem a chave. |

---

## 4. "A view sumiu" depois de rodar um modelo isolado

**Sintoma:** `relation "silver.notas" does not exist` logo depois de um
`dbt build --select <um modelo>`.

**Causa:** o dbt-postgres recria view com `DROP ... CASCADE`. Reconstruir um staging
isoladamente **derruba as views que dependem dele**, e elas não voltam sozinhas.

**Conserto:** `dbt build` completo. Aconteceu em 2026-09-06 ao rebuildar
`stg_notas_fiscais` sozinho.

**Como evitar:** use `--select modelo+` (com o `+`) para levar os dependentes junto.

---

## 5. O deploy matou um job no meio

**Sintoma:** carga registrada como **inacabada**; container morreu com SIGKILL (137).

**Causa:** publicar no EasyPanel derruba o container, e `docker exec` morre junto.

**Conserto:** rodar o job de novo — os extratores são idempotentes, dedup por id, zero
duplicata. Sem dano.

**Como evitar:** conferir se há carga rodando **antes** de publicar:
```bash
ssh datacore 'C=$(docker ps --format "{{.Names}}" | grep -m1 "^erick_datacore-api"); docker exec "$C" ps -eo args | grep app.jobs'
```

---

## 6. O dbt não conecta

```
FATAL: password authentication failed for user "dbt"
```

Quase sempre é a variável de ambiente, não a senha.

```bash
cd ~/Projetos/datacore-analytics
source ./env.sh          # ⚠️ com ./ — sem a barra, o bash procura no PATH e falha calado
echo ${#DBT_PG_PASSWORD}  # tem que ser 32
```

⚠️ **`~/.dbt/profiles.yml` é compartilhado entre TODOS os projetos dbt da máquina.** Em
2026-08-24 o profile `datacore` foi apagado quando outro projeto sobrescreveu o arquivo.
**Nunca sobrescrever — sempre acrescentar.** Há backups em `profiles.yml.bak-*`.

---

## 7. Preciso rodar um backfill

**Nunca em foreground pelo SSH** — a conexão cai e leva o job junto.

```bash
ssh datacore
systemd-run --unit=backfill-<nome> --description="..." \
  /opt/datacore-jobs/rodar-job.sh extrair_contas --tipo receber \
  --desde 2015-01-01 --ate 2017-12-31 --sem-reconferir
```

Acompanhar: `journalctl -u backfill-<nome>.service -f`

⚠️ **Cheque a janela dos timers antes** (UTC): notas 04:00 e 15:00 · contas 10:00 ·
estoque 16:00. Duas cargas juntas estouram o limite de 20 chamadas/min da API.
(A importação de NFS-e, 04:30, não entra nessa conta: ela fala com o ADN nacional, não
com o Tiny.)

⚠️ **`--limite 0` NÃO limita** — `if args.limite:` trata zero como ausente, e o job
processa tudo. Para testar, use `--limite 1`.

⚠️ **Dry-run é registrado em `operacao.execucoes_job`** como se fosse carga. Em 2026-09-06,
11 das 20 execuções eram dry-run de investigação. O monitor de volume filtra, mas o
histórico fica sujo.

---

## 8. Preciso escrever no banco de produção

1. **Backup primeiro**, sempre: `pg_dump -t <schema>.<tabela> ... -f backups/<tabela>-<data>.sql`
2. **Liste os triggers antes de escrever:**
   ```sql
   select c.relname, t.tgname from pg_trigger t join pg_class c on c.oid=t.tgrelid
   where c.relnamespace='tiny'::regnamespace and not t.tgisinternal;
   ```
   Em 2026-09-06 um UPDATE de conserto disparou `trg_contas_receber_updated_at` e marcou
   7.442 linhas como "atualizadas agora" — falso. Só `contas_receber` tem trigger;
   `contas_pagar` não.
3. Se precisar desligar o trigger, faça **dentro da transação**: o rollback religa sozinho.
4. Rode em `BEGIN` … `COMMIT` com contagem **antes e depois** no mesmo script.

⚠️ `backups/` está no `.gitignore`: aqueles dumps têm nome, CPF/CNPJ, endereço e telefone
de ~9 mil clientes. **Nunca commitar.**

---

## 9. Números que devem bater (se não baterem, algo quebrou)

| O quê | Valor em 2026-09-06 |
|---|---|
| Faturamento (`silver.vendas` = `gold.fato_vendas`) | 4.330 notas · 5.089 itens · valor conferido contra o repositório interno de medições |
| Clientes na dimensão | 2.215 (2.063 do ERP + 151 só das ilhas + 1 "não informado") |
| Produtos | 295 (280 cadastrados + 15 órfãos) |
| Contas a receber | 9.634, desde 2015 |
| Notas em quarentena | 22 |
| `dbt build` | 194 nós — PASS=192, WARN=2, ERROR=0 |

**Se o faturamento mudou e ninguém mexeu na régua, o problema é técnico, não de negócio.**

---

## 10. Fiz o deploy e o número na tela não mudou

**Não é bug. O deploy do `datacore-dbt` sobe o código; ele não executa nada.**

A última linha do `Dockerfile` é `CMD ["sleep", "infinity"]`, e isso é decisão, não
descuido: o EasyPanel **reinicia todo container que morre**. Se o `CMD` fosse `dbt build`,
o container terminaria em trinta segundos, o EasyPanel o reviveria, e o resultado seria um
`dbt build` em laço infinito contra o banco de produção.

Quem dispara o trabalho é o timer, de fora, com `docker exec` — mesmo padrão dos quatro
extratores. Ou seja:

| Serviço | O deploy já é o efeito? |
|---|---|
| `datacore-api`, `DataCoreHS` | **Sim** — servem requisição, sobem já valendo |
| `datacore-dbt` | **Não** — o código novo fica dormindo até o próximo build |

**Como confirmar em que pé está**, sem adivinhar pelo número:

```bash
# a imagem é nova? (compare com a hora do seu deploy)
ssh datacore 'docker inspect --format "{{.Created}}" \
  $(docker ps --format "{{.Names}}" | grep -m1 dbt)'

# o código novo está DENTRO dela? (troque pelo arquivo que você acabou de subir)
ssh datacore 'docker exec $(docker ps --format "{{.Names}}" | grep -m1 dbt) \
  ls seeds/'

# quando o build roda de novo?
ssh datacore 'systemctl list-timers datacore-dbt.timer --no-pager'
```

Imagem nova + código dentro + build ainda não rodado = **está tudo certo, só falta a hora**.

**Para antecipar** (é o mesmo comando do timer, sem esperar as 05:00 UTC):

```bash
ssh datacore '/opt/datacore-jobs/rodar-dbt.sh'
```

⚠️ Antecipar faz os **snapshots SCD2** tirarem a foto agora em vez de às 05:00. É correto e
é o comportamento desejado — só não é reversível, então é escolha e não automatismo.

---
