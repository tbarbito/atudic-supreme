# Documentação da API do AtuDIC

Bem-vindo à documentação oficial da API Externa do AtuDIC. Estas rotas permitem integrar aplicações externas (como sistemas de CI/CD, webhooks customizados ou ferramentas de CLI próprias) diretamente ao AtuDIC de maneira segura.

---

## 🔐 Autenticação

Para se autenticar em qualquer endpoint desta API, você precisará de uma **API Key** gerada através da aba de **Configurações > Integrações API** da interface web.

Há duas formas de enviar o token de autenticação:

1.  **Cabeçalho `x-api-key`:**
    ```bash
    curl -H "x-api-key: at_XXXXXXXXX" http://seu-servidor:5000/api/v1/...
    ```

2.  **Cabeçalho genérico `Authorization` (Bearer):**
    ```bash
    curl -H "Authorization: Bearer at_XXXXXXXXX" http://seu-servidor:5000/api/v1/...
    ```

> [!CAUTION]
> Ao revogar uma chave pela UI, o acesso aos serviços que a estavam utilizando será interrompido imediatamente com o status **401 Unauthorized**. Guarde as chaves com muito cuidado.

---

## 🚀 Endpoints de Pipeline

Inicie execuções (runs) de Pipelines cadastrados remotamente.

### 1. Iniciar Pipeline
Dispara a execução de um Pipeline existente em background. O Pipeline passará a exibir seus logs na UI instantaneamente.

**Requisição:**
`POST /api/v1/pipelines/{pipeline_id}/trigger`

**Exemplo:**
```bash
curl -X POST http://localhost:5000/api/v1/pipelines/4/trigger \
     -H "x-api-key: at_SuaChaveSecreta"
```

**Resposta de Sucesso (202 Accepted):**
```json
{
  "success": true,
  "message": "Pipeline Aplicativo Principal iniciado com sucesso via API.",
  "pipeline_id": 4
}
```

### 2. Checar Status da Pipeline
Verifica se determinado Pipeline está finalizado, rodando ou disponível. Este endpoint também retorna informações sobre a última execução iniciada.

**Requisição:**
`GET /api/v1/pipelines/{pipeline_id}/status`

**Exemplo:**
```bash
curl -X GET http://localhost:5000/api/v1/pipelines/4/status \
     -H "x-api-key: at_SuaChaveSecreta"
```

**Resposta de Sucesso (200 OK):**
```json
{
  "pipeline_id": 4,
  "name": "Aplicativo Principal",
  "pipeline_status": "ready",
  "last_run_details": {
    "id": 16,
    "status": "success",
    "started_at": "Mon, 01 Jan 2024 16:03:00 GMT",
    "finished_at": "Mon, 01 Jan 2024 16:05:22 GMT"
  }
}
```

---

## ⚙️ Endpoints de Ações de Serviço (Service Actions)

Permite controlar remotamente, por script, o estado dos serviços que compõem sua aplicação ou servidor infra (Start, Stop, Restart).

### 1. Iniciar Service Action
Aciona uma Ação de Serviço, executando comandos via SSH no respectivo servidor para controlar serviços (ex: AppServer, PostgreSQL, Nginx). Os fluxos de encerramento forçado e gerenciadores de log também são engatilhados.

**Requisição:**
`POST /api/v1/services/actions/{action_id}/trigger`

**Exemplo:**
```bash
curl -X POST http://localhost:5000/api/v1/services/actions/14/trigger \
     -H "x-api-key: at_SuaChaveSecreta"
```

**Resposta de Sucesso (202 Accepted):**
```json
{
  "success": true,
  "message": "Service Action 'Restart Cluster Backend' iniciada via API.",
  "action_id": 14
}
```

---

## 🔔 Integração de Notificações

Por padrão, quando uma execução via API é acionada:
- A engine tenta encontrar destinações ativas de SMTP/E-mail configuradas dentro das propriedades da Pipeline.
- A engine aciona os Webhooks de WhatsApp associados, seguindo a parametrização do Payload e dos Headers cadastrados (ex: Evolution API ou Z-API).
- Os administradores podem observar o autor destas ações de API pelos IDs de Logs Internos, que virão carimbados como `Autor: API Key (Seu Nome da Chave)`.
