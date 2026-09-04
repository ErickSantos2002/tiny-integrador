# 📦 Tiny Integrador – API REST com FastAPI + PostgreSQL

Este projeto é uma API REST desenvolvida com **FastAPI**, conectada a um banco **PostgreSQL**, que integra os dados do sistema **Tiny ERP** para exposição em dashboards, sistemas internos ou aplicações web.

---

## 🚀 Objetivo

Automatizar a extração, transformação e disponibilização de dados do Tiny ERP (como notas fiscais, clientes e itens de venda) em uma **API robusta, segura e escalável**, rodando 24/7 em uma VPS com suporte ao consumo por aplicações como Power BI, dashboards web e sites.

---

## 🛠 Tecnologias Utilizadas

- **Python 3.11+**
- **FastAPI**
- **SQLAlchemy**
- **PostgreSQL**
- **Uvicorn + Gunicorn**
- **Docker (opcional)**
- **Easypanel** (para deploy e gerenciamento da VPS)

---

## 📂 Estrutura do Projeto

```
tiny-integrador/
├── app/
│   ├── api/endpoints/         # Endpoints da API REST
│   ├── core/                  # Configurações e segurança
│   ├── models/                # Modelos SQLAlchemy (tabelas do banco)
│   ├── schemas/               # Schemas Pydantic (validação e respostas)
│   └── main.py                # Ponto de entrada da aplicação
├── .env                       # Variáveis de ambiente
├── requirements.txt           # Dependências do projeto
├── Dockerfile                 # (Opcional) Containerização com Docker
└── README.md
```

---

## 🔗 Endpoints disponíveis

- `/notas` → Listagem de notas fiscais
- `/clientes` → Dados dos clientes
- `/itens_nota` → Itens associados às notas fiscais
- `/formas_envio` → Formas de envio utilizadas
- `/enderecos_entrega` → Endereços associados às notas
- `/marcadores` → Tags/categorias vinculadas

Todos os endpoints são **GET** por padrão e podem ser expandidos com filtros e autenticação por token.

---

## 🧪 Como rodar localmente

### 1. Clone o repositório
```bash
git clone https://github.com/seu-usuario/tiny-integrador.git
cd tiny-integrador
```

### 2. Instale as dependências
```bash
pip install -r requirements.txt
```

### 3. Configure o `.env`
Crie um arquivo `.env` com:

```env
DATABASE_URL=postgresql://usuario:senha@localhost:5432/tiny
```

### 4. Rode a API em modo desenvolvimento
```bash
uvicorn app.main:app --reload
```

---

## 🐳 Deploy com Docker (opcional)

Você pode utilizar o `Dockerfile` para rodar a aplicação em ambiente isolado:

```bash
docker build -t tiny-api .
docker run -d -p 8000:8000 tiny-api
```

---

## 🔒 Segurança e Produção

- Em produção, utilize **Gunicorn com UvicornWorker**
- Configure HTTPS na VPS via Easypanel
- Planeje o uso de **JWT** ou API Key com header seguro
- Acesso ao banco com usuário limitado e protegido por firewall

---

## 📊 Futuro

- [ ] Implementar autenticação com token seguro
- [ ] Adicionar filtros e paginação nos endpoints
- [ ] Criar documentação automática com Swagger (`/docs`)
- [ ] Conectar ao dashboard em Power BI ou app web
- [ ] Criar endpoints adicionais para relatórios e métricas

---

## 🧑‍💻 Autor

**[Seu Nome ou Empresa]**  
Desenvolvido para integração com Tiny ERP e exposição de dados em tempo real.

---

---

## 🔄 Extratores do Tiny (substituem o n8n)

Carga da bronze (`schema tiny`) direto da API do Tiny, substituindo os **quatro** fluxos
do n8n. Cada um é um comando, e cada um roda sozinho:

| fluxo do n8n | comando | rodava |
|---|---|---|
| `[DATACORE] Puxar_Notas` | `python -m app.jobs.extrair_notas` | 4h e 15h |
| `[DATACORE] Puxar_Contas_Pagar` | `python -m app.jobs.extrair_contas --tipo pagar` | 10h |
| `[DATACORE] Puxar_Contas_Receber` | `python -m app.jobs.extrair_contas --tipo receber` | 12h |
| `[DATACORE] Atualizar estoque` | `python -m app.jobs.extrair_estoque` | 16h |

Todos aceitam `--dry-run` (mostra o que faria, não escreve) e `--limite N` (para testar).
Precisam de `TINY_TOKEN` e `DATABASE_URL` no ambiente.

### Notas fiscais

```bash
python -m app.jobs.extrair_notas --dias 14 --dry-run   # mostra o que faria, não escreve
python -m app.jobs.extrair_notas --dias 14             # a carga de rotina
python -m app.jobs.extrair_notas --desde 2018-01-01    # backfill histórico
python -m app.jobs.extrair_notas --id 617079728        # uma nota específica
```

Precisa de `TINY_TOKEN` e `DATABASE_URL` no ambiente.

### Por que substituir o n8n

Dois defeitos medidos em 2026-09-01, que juntos inflaram o faturamento em **R$ 226.685**
(11 notas canceladas/recusadas contando como venda):

| defeito no n8n | causa | como fica aqui |
|---|---|---|
| marcador chegava com descrição em branco | lia `marcadores.marcador.descricao` do **XML**, onde 2+ marcadores viram lista | origem é **JSON**, onde `marcadores` é sempre lista (`tiny_api`) |
| marcador posto depois da carga nunca entrava | o ramo de update só rodava se um dos 31 campos da nota mudasse, e marcador não é um deles | os filhos da nota são conferidos em **toda** passagem, independente da nota ter mudado |

### Decisões que valem saber

- **Janela de 14 dias**, igual à do n8n: nota muda depois de emitida (cancelamento,
  marcador, situação), então a carga precisa reolhar o passado recente.
- **Idempotente.** Rodar duas vezes seguidas não altera nada na segunda.
- **Curadoria local é intocável.** `CAMPOS_DE_CURADORIA_LOCAL` (hoje `tipo`) nunca é
  sobrescrito — mesma proteção que já existe para `cancelada` na NFS-e.
- **Comparação tolerante, gravação limpa.** O n8n gravava `''` em vez de `NULL` e deixava
  espaço no fim do texto. Isso não conta como alteração (senão a primeira carga
  reescreveria as 8 mil notas e esconderia as mudanças de verdade), mas o que for gravado
  daqui em diante vai normalizado. Padronizar o que já está lá é trabalho da silver.
- **Cliente existente não é atualizado**, como sempre foi. Deduplicação e regra de
  sobrevivência são trabalho da silver, não da bronze.
- **Uma transação por nota.** Falha numa nota não derruba o lote nem deixa nota pela metade.

### Contas a pagar e a receber

```bash
python -m app.jobs.extrair_contas --dry-run          # as duas
python -m app.jobs.extrair_contas --tipo pagar
python -m app.jobs.extrair_contas --desde 2018-01-01 # backfill
```

O n8n pesquisava a partir de uma **data escrita à mão dentro do nó** (30/06/2026 nas
contas a pagar, 14/03/2026 nas a receber). Isso envelhece sozinho: conta emitida antes
daquele dia nunca mais era reconferida, então conta antiga que fosse paga continuava
`aberto` no banco para sempre. Em 2026-09-03 o banco dizia **226 contas a pagar em
aberto, R$ 962.071,57** — a mais antiga de 2021 — contra **3** de verdade no Tiny.

Trocar a data fixa por uma janela móvel não resolveria: a conta muda de situação muito
depois de emitida. Por isso a carga tem duas partes:

1. **janela por emissão** (padrão 14 dias) — traz conta nova;
2. **reconferência de tudo que está em aberto**, de qualquer data — é o que percebe
   pagamento. Desligável com `--sem-reconferir`, mas aí a carga volta a ser cega a isso.

### Estoque

```bash
python -m app.jobs.extrair_estoque --dry-run
python -m app.jobs.extrair_estoque --sem-saldo   # só o cadastro, sem 1 chamada por produto
```

O fluxo do n8n tinha **três blocos copiados**, um para a página 1, outro para a 2 e outro
para a 3 — paginação escrita à mão. Hoje a origem tem exatamente 3 páginas de produto: a
quarta não seria lida, e sem erro nenhum para avisar. Pior, **só o bloco da página 1
inseria produto novo** — as outras duas só atualizavam saldo, então produto das páginas 2
e 3 que ainda não estivesse no banco nunca entrava (270 no banco contra 300 na origem).

Aqui a paginação segue o `numero_paginas` que a própria API devolve, e todo produto novo
entra, de qualquer página.

### Uma armadilha da api2 que vale saber

A API **não tem uma resposta vazia só**. Às vezes devolve `status_processamento = 2`
(nenhum registro), às vezes devolve **erro** com código 20 e a mensagem "A consulta não
retornou registros". Os dois querem dizer a mesma coisa. Tratar o segundo como falha faz
a carga abortar sempre que um filtro vier vazio — foi o que aconteceu no primeiro
dry-run, procurando contas com situação "parcial" num dia em que não existia nenhuma.

### Testes

```bash
docker run -d --rm --name extrator-teste -e POSTGRES_PASSWORD=teste \
    -e POSTGRES_DB=testdb -p 55433:5432 postgres:17
python testar_extrator_notas.py
python testar_extrator_contas_estoque.py
docker rm -f extrator-teste
```

Nunca aponte para produção: os scripts fazem `DROP SCHEMA tiny CASCADE`. Cobrem os bugs
do n8n um a um, idempotência, curadoria preservada e dry-run — e foram **verificados por
mutação**: reintroduzir cada bug faz o teste correspondente falhar.

### Agendamento (o que substitui os gatilhos do n8n)

Os quatro fluxos do n8n tinham horário próprio. Aqui isso vira três timers do systemd na
VPS, em `deploy/`:

| timer | horário (UTC) | substitui |
|---|---|---|
| `tiny-extrator-notas` | 04:00 e 15:00 | `Puxar_Notas` |
| `tiny-extrator-contas` | 10:00 | `Puxar_Contas_Pagar` + `Puxar_Contas_Receber` |
| `tiny-extrator-estoque` | 16:00 | `Atualizar estoque` |

```bash
cp deploy/rodar-job.sh /opt/datacore-jobs/
cp deploy/systemd/* /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now tiny-extrator-notas.timer tiny-extrator-contas.timer tiny-extrator-estoque.timer
journalctl -u 'tiny-extrator@*' -f     # acompanhar
```

O `rodar-job.sh` acha o container **pelo prefixo do nome**, não pelo nome inteiro: o
EasyPanel troca o sufixo (`erick_datacore-api.1.<hash>`) a cada publicação, então nome
fixo quebraria no primeiro deploy.

### Ritmo das chamadas

A API informa o teto do plano no cabeçalho `x-limit-api` — **20 por minuto** no plano da
empresa. O cliente lê esse cabeçalho e ajusta o intervalo sozinho, usando 85% do teto.
Andar no limite cravado (3s = 20/min exatos) é o que fez a primeira carga levar
`API Bloqueada`: a conta é por janela de minuto, e qualquer atraso de rede empurra duas
chamadas para o mesmo minuto. Ao ser bloqueado, o cliente espera 1, 2 e 4 minutos antes
de desistir, em vez de insistir de imediato.
