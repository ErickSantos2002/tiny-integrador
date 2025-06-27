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
