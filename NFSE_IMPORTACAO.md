# Importação Automática de NFSe

## Endpoint criado

**POST** `/notas_servico/importar`

Este endpoint busca NFSe na Prefeitura do Recife e salva automaticamente no banco de dados.

## Parâmetros (Query String)

- `data_inicial` (opcional): Data inicial da busca (formato: YYYY-MM-DD)
- `data_final` (opcional): Data final da busca (formato: YYYY-MM-DD)

**Padrão**: Se não informar datas, busca de ontem até hoje.

## Exemplos de Uso

### 1. Buscar NFSe de ontem até hoje (padrão)
```
POST http://seu-servidor/notas_servico/importar
```

### 2. Buscar NFSe de um período específico
```
POST http://seu-servidor/notas_servico/importar?data_inicial=2025-11-20&data_final=2025-11-27
```

### 3. Buscar NFSe de um dia específico
```
POST http://seu-servidor/notas_servico/importar?data_inicial=2025-11-26&data_final=2025-11-26
```

## Resposta de Sucesso

```json
{
  "success": true,
  "message": "Importação concluída com sucesso",
  "periodo": {
    "data_inicial": "2025-11-26",
    "data_final": "2025-11-27"
  },
  "total_encontradas": 2,
  "total_importadas": 2,
  "total_atualizadas": 0,
  "erros": null
}
```

## Resposta quando não há notas

```json
{
  "success": true,
  "message": "Nenhuma NFSe encontrada no período",
  "periodo": {
    "data_inicial": "2025-11-26",
    "data_final": "2025-11-27"
  },
  "total_encontradas": 0,
  "total_importadas": 0,
  "total_atualizadas": 0
}
```

## Resposta de Erro

```json
{
  "success": false,
  "erro": "Descrição do erro",
  "message": "Erro ao importar NFSe"
}
```

---

## Configuração no N8N

### Workflow Diário de Importação

1. **Schedule Trigger** (Cron)
   - Configure para rodar todo dia às 8h da manhã, por exemplo
   - Cron: `0 8 * * *`

2. **HTTP Request Node**
   - **Method**: POST
   - **URL**: `http://seu-servidor/notas_servico/importar`
   - **Authentication**: Nenhuma (ou configure se tiver)
   - **Query Parameters**: (deixe vazio para buscar ontem e hoje)

3. **IF Node** (opcional)
   - Verifica se `success` é `true`
   - Se sim, prossegue para próximo passo
   - Se não, envia alerta de erro

4. **Slack/Email/Webhook Node** (opcional)
   - Envia notificação com resultado:
     - Total de notas importadas
     - Total de notas atualizadas
     - Erros (se houver)

### Exemplo de Workflow N8N (JSON)

```json
{
  "nodes": [
    {
      "name": "Schedule Trigger",
      "type": "n8n-nodes-base.scheduleTrigger",
      "position": [250, 300],
      "parameters": {
        "rule": {
          "interval": [
            {
              "field": "cronExpression",
              "expression": "0 8 * * *"
            }
          ]
        }
      }
    },
    {
      "name": "Importar NFSe",
      "type": "n8n-nodes-base.httpRequest",
      "position": [450, 300],
      "parameters": {
        "method": "POST",
        "url": "http://seu-servidor/notas_servico/importar"
      }
    },
    {
      "name": "Verificar Sucesso",
      "type": "n8n-nodes-base.if",
      "position": [650, 300],
      "parameters": {
        "conditions": {
          "boolean": [
            {
              "value1": "={{$json[\"success\"]}}",
              "value2": true
            }
          ]
        }
      }
    },
    {
      "name": "Notificar Sucesso",
      "type": "n8n-nodes-base.slack",
      "position": [850, 250],
      "parameters": {
        "message": "=✅ NFSe importadas com sucesso!\n\n📊 Total encontradas: {{$json[\"total_encontradas\"]}}\n➕ Importadas: {{$json[\"total_importadas\"]}}\n🔄 Atualizadas: {{$json[\"total_atualizadas\"]}}"
      }
    },
    {
      "name": "Notificar Erro",
      "type": "n8n-nodes-base.slack",
      "position": [850, 350],
      "parameters": {
        "message": "=❌ Erro ao importar NFSe!\n\n{{$json[\"erro\"]}}"
      }
    }
  ],
  "connections": {
    "Schedule Trigger": {
      "main": [[{"node": "Importar NFSe", "type": "main", "index": 0}]]
    },
    "Importar NFSe": {
      "main": [[{"node": "Verificar Sucesso", "type": "main", "index": 0}]]
    },
    "Verificar Sucesso": {
      "main": [
        [{"node": "Notificar Sucesso", "type": "main", "index": 0}],
        [{"node": "Notificar Erro", "type": "main", "index": 0}]
      ]
    }
  }
}
```

---

## Configurações Necessárias

As configurações de certificado e credenciais estão no arquivo `.env`:

```env
# Banco de dados
DATABASE_URL=postgresql://user:password@localhost/database

# NFSe Recife
NFSE_CERT_PATH=C:/NFSe/cert.crt
NFSE_KEY_PATH=C:/NFSe/key.key
NFSE_CNPJ=08857492000148
NFSE_INSCRICAO_MUNICIPAL=3694208
```

**IMPORTANTE**: Os arquivos de certificado (`cert.crt` e `key.key`) devem estar no caminho especificado e acessíveis pela aplicação.

---

## Como Testar

### 1. Via cURL

```bash
curl -X POST "http://localhost:8000/notas_servico/importar"
```

### 2. Via Python

```python
import requests

response = requests.post("http://localhost:8000/notas_servico/importar")
print(response.json())
```

### 3. Via Postman/Insomnia

- **Method**: POST
- **URL**: `http://localhost:8000/notas_servico/importar`
- **Headers**: Nenhum necessário
- Clique em Send

---

## Funcionamento Interno

1. **Consulta na Prefeitura**: O endpoint usa o serviço `NFSeRecifeService` que faz requisição SOAP para o Web Service da Prefeitura do Recife
2. **Parse do XML**: Converte a resposta XML em objetos Python
3. **Verificação de Duplicatas**: Verifica se a NFSe já existe no banco (por número)
4. **Inserção/Atualização**:
   - Se não existe: cria novo registro
   - Se existe: atualiza os dados
5. **Commit**: Salva todas as alterações no banco de dados
6. **Resposta**: Retorna JSON com estatísticas da importação

---

## Logs

Os logs aparecem no console da aplicação FastAPI:

```
Consultando NFSe de 2025-11-26 até 2025-11-27...
INFO:     127.0.0.1:54321 - "POST /notas_servico/importar HTTP/1.1" 200 OK
```

Em caso de erro:
```
ERRO NA IMPORTAÇÃO:
Traceback (most recent call last):
  ...
```

---

## Troubleshooting

### Erro: "Certificate verify failed"
- Verifique se os arquivos de certificado estão corretos e no caminho especificado

### Erro: "Connection timeout"
- Verifique a conexão com a internet
- Verifique se o Web Service da Prefeitura está no ar

### Erro: "Database error"
- Verifique se o banco de dados está acessível
- Verifique se a tabela `tiny.servicos` existe

### NFSe não aparecem no banco
- Verifique se há NFSe no período consultado
- Verifique os logs da aplicação
- Teste manualmente com o script `teste_nfse_simples.py`
