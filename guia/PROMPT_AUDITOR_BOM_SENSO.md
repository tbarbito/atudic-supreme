# Prompt de Implementacao — Auditor INI: Bom Senso por Papel

> Aplicar no AtuDIC no arquivo `app/services/ini_auditor.py`
> Commits de referencia no AtuDIC: d51e719..e4e4dd1 (5 commits)
> Data: 2026-03-22

---

## Contexto

O Auditor de INI Protheus precisa de **bom senso** na auditoria. O cenario real: o arquivo enviado **ja funcionava em producao** — o objetivo e identificar riscos, nao reescrever o arquivo. As mudancas abaixo implementam filtro por papel, regras condicionais e LLM com formato de resumo executivo.

---

## 1. Filtro de Regras por Papel (`_ROLE_RELEVANT_SECTIONS`)

Substituir o dicionario `_ROLE_RELEVANT_SECTIONS` existente pelo novo, que define **quais secoes do INI sao relevantes para cada papel**. Regras de secoes fora da lista sao descartadas ANTES da comparacao.

### Principio
- **Brokers** (http/soap/rest): apenas `[General]` — sao balanceadores simples, NAO possuem DBAccess, Environment, Drivers, TCP, Broker, SSLConfigure, LicenseClient, WebApp, HTTP, OnStart
- **Slaves**: Environment, DBAccess, Drivers, TCP, WebApp, LicenseClient, SSL. NAO possuem Broker, HTTPREST (exceto slave_rest)
- **Job server**: Environment, DBAccess, OnStart. NAO atende WebApp/HTTP
- **REST server**: + HTTPJOB, HTTPREST, HTTPURI
- **Standalone/TSS**: sem filtro (todas as regras)
- **DBAccess master/slave**: apenas General, Service e secoes de banco

### Codigo

```python
_ROLE_RELEVANT_SECTIONS = {
    "broker_http": {"general"},
    "broker_soap": {"general"},
    "broker_rest": {"general"},
    "slave": {
        "general", "drivers", "tcp", "webapp", "dbaccess", "environment",
        "licenseclient", "service", "sslconfigure", "webagent",
    },
    "slave_ws": {
        "general", "drivers", "tcp", "webapp", "http", "dbaccess", "environment",
        "licenseclient", "service", "sslconfigure", "onstart",
    },
    "slave_rest": {
        "general", "drivers", "tcp", "webapp", "http", "dbaccess", "environment",
        "licenseclient", "service", "sslconfigure", "onstart",
        "httpjob", "httpv11", "httprest", "httpuri",
    },
    "job_server": {
        "general", "drivers", "tcp", "dbaccess", "environment",
        "licenseclient", "service", "onstart",
    },
    "rest_server": {
        "general", "drivers", "tcp", "http", "dbaccess", "environment",
        "service", "sslconfigure", "onstart",
        "httpjob", "httpv11", "httprest", "httpuri",
    },
    "standalone": None,
    "standalone_multi_env": None,
    "tss": None,
    "dbaccess_master": {"general", "service", "oracle", "mssql", "postgresql"},
    "dbaccess_slave": {"general", "service", "oracle", "mssql", "postgresql"},
    "dbaccess_standalone": None,
}
```

---

## 2. Chaves Irrelevantes para Brokers (`_BROKER_IRRELEVANT_KEYS`)

Adicionar set de chaves de `[General]` que NAO fazem sentido para brokers. Brokers so fazem roteamento — as unicas chaves relevantes sao de LOG.

```python
_BROKER_IRRELEVANT_KEYS = {
    "maxstringsize", "servermemorylimit", "servermemoryinfo",
    "maxbucketcommittime", "inactivetimeout", "canacceptmonitor",
    "canacceptdebugger", "canacceptfsremote", "buildkillusers",
    "canacceptlb", "heaplimit", "logtimestamp",
    "showfulllog", "showipclient", "showipclients",
    "servertype", "app_environment", "installpath",
    "maxquerysize", "checkspecialkey", "canrunjobs",
    "echoconsolelog", "debugthreadusedmemory", "enablediagnosticsfile",
    "enablememinfocsv", "monitorconnections",
    "minidumpmode", "file_max", "canacceptrpc",
    "changeencodingbehavior", "logmessages",
    "sslredirect", "ipc_activetimeout", "workthreadqtdmin",
    "latencylog", "latencylogfile", "latencylogmaxsize", "latencypinginterval",
    "floatingpointprecise", "newerclientconnection",
    "writeconsolelog", "inicustomization", "kv_engine",
    "loghttpfuncs", "ctreemode", "usegdb", "useprocdump",
    "wsdlstreamtype", "gt_reinsertall", "gt_reinsertall_time",
    "errormaxsize", "powerschemeshowupgradesuggestion",
    "powerschemetimeinterval", "sqlite_collateritrim",
    "sqlite_rebuildtables", "sqlite_trailspace",
    "socketdefaultipv6", "socketsdefaultipv6",
}
```

---

## 3. Aplicar Filtros em `compare_against_best_practices()`

No inicio da funcao, apos carregar as `practices`, adicionar:

```python
is_broker = ini_role in ("broker_http", "broker_soap", "broker_rest")
relevant_sections = _ROLE_RELEVANT_SECTIONS.get(ini_role)
if relevant_sections is not None:
    practices = [
        bp for bp in practices
        if bp["section"].lower() in relevant_sections
    ]
if is_broker:
    practices = [
        bp for bp in practices
        if bp["key_name"].lower() not in _BROKER_IRRELEVANT_KEYS
    ]
```

---

## 4. Regras Condicionais (nao universalmente obrigatorias)

### 4.1 DBAccess: remover MaxStringSize
MaxStringSize NAO se aplica ao DBAccess — e configuracao do AppServer.
Substituir a regra por comentario:
```python
# MaxStringSize NAO se aplica ao DBAccess — e configuracao do AppServer
```

### 4.2 DBAccess: drivers sao condicionais
MSSQL, Oracle, PostgreSQL Server/Database: mudar de `req=True, sev="critical"` para `req=False, sev="warning"`.
O arquivo pode usar qualquer driver — so avaliar se a secao existir:
```python
r("MSSQL", "Server", vtype="client_config", sev="warning", ini_type="dbaccess", ...)
r("MSSQL", "Database", vtype="client_config", sev="warning", ini_type="dbaccess", ...)
r("Oracle", "Server", vtype="client_config", sev="warning", ini_type="dbaccess", ...)
r("Oracle", "Database", vtype="client_config", sev="warning", ini_type="dbaccess", ...)
r("PostgreSQL", "Server", vtype="client_config", sev="warning", ini_type="dbaccess", ...)
r("PostgreSQL", "Database", vtype="client_config", sev="warning", ini_type="dbaccess", ...)
```

### 4.3 AppServer: [Broker] e opcional
Broker Enable/Port/Type/Servers: mudar de `req=True, sev="critical"` para `req=False, sev="warning"`.
Broker.Port: mudar vtype para `client_config`:
```python
r("Broker", "Enable", val="1", vtype="boolean", sev="warning", ...)
r("Broker", "Port", vtype="client_config", sev="warning", ...)
r("Broker", "Type", vtype="enum", ..., sev="warning", ...)
r("Broker", "Servers", sev="warning", ...)
```

### 4.4 TSS: certificados SSL sao condicionais
SSLConfigure CertificateClient/KeyClient: mudar de `req=True` para `req=False` e vtype `client_config`:
```python
r("SSLConfigure", "CertificateClient", ini_type="tss", vtype="client_config", sev="critical", ...)
r("SSLConfigure", "KeyClient", ini_type="tss", vtype="client_config", sev="critical", ...)
```

---

## 5. LLM: Resumo Executivo (nao analise detalhada)

### 5.1 Premissas no prompt do LLM

Substituir as instrucoes de resposta por:

```
## Premissas OBRIGATORIAS (respeite SEMPRE):
- O arquivo enviado JA FUNCIONAVA em producao — o objetivo e identificar riscos, nao reescrever
- NUNCA critique valores de: portas, paths, servidores, nomes de banco, environments, aliases,
  ThreadMin/Max/Inc, Instances, metricas de performance, nomes de servico, LicenseServer/Port.
  Estes sao ESCOLHA DO CLIENTE conforme infraestrutura
- Secoes de drivers de banco (MSSQL, Oracle, PostgreSQL) so avalia SE EXISTIREM no arquivo.
  Se usa Oracle, NAO critique ausencia de MSSQL ou PostgreSQL
- Secoes como [Broker], [WebAgent], [HTTPREST], [FTP] sao OPCIONAIS —
  so avalie se existirem no arquivo
- Chaves opcionais ausentes NAO sao erro — no maximo uma dica sutil
- MaxStringSize NAO se aplica a DBAccess
- Chaves como ConsoleMaxSize, InactiveTimeout, ServerMemoryLimit com valores diferentes
  do padrao NAO sao erro — o cliente ajustou conforme ambiente

## Formato da resposta — RESUMO EXECUTIVO:
1. Primeira linha: papel do servidor (ex: 'DBAccess Slave conectado ao Master')
2. Estado geral: 1-2 frases sobre a saude do arquivo
3. Pontos de atencao (se houver): lista curta APENAS dos itens que realmente impactam.
   Maximo 3-5 itens, formato bullet point
4. Dicas de melhoria (opcional): 1-3 sugestoes rapidas
5. NAO faca analise detalhada item por item — isso ja e mostrado nos findings
6. NAO sugira adicionar secoes/chaves que nao fazem sentido para o papel
7. Responda em portugues brasileiro, formato markdown, maximo ~200 palavras
```

### 5.2 Filtrar apenas critical/warning para o LLM

No `generate_llm_insights()`, filtrar problemas antes de enviar ao LLM:

```python
impactful = [p for p in problems if p["severity"] in ("critical", "warning")]
impactful_commented = [cf for cf in (commented_findings or []) if cf["severity"] in ("critical", "warning")]
if not impactful and not impactful_commented:
    return {"summary": "Nenhum problema critico ou de alerta encontrado.", ...}
```

---

## 6. Resultado Esperado por Papel

| Papel | Regras avaliadas | Antes (falsos positivos) |
|-------|-----------------|--------------------------|
| broker_http/soap/rest | 5 (so log) | 47 ausentes |
| slave | 95 | OK |
| slave_ws | 105 | OK |
| slave_rest | 105 | OK |
| job_server | 69 (sem WebApp/HTTP) | OK |
| rest_server | 95 | OK |
| standalone | 158 (sem filtro) | OK |
| tss | 66 (regras TSS) | OK |
| dbaccess_master/slave | ~48 (sem MaxStringSize) | MaxStringSize + 6 drivers falsos |

---

## 7. Validacao

Testar com os 11 INIs reais:
```
AppServer_TSS.ini          -> tss
AppServer_ws05.ini         -> slave_ws
AppServer_webagent_broker  -> broker_http
AppServer_slv01.ini        -> slave
appserver_sust.ini         -> standalone_multi_env
AppServer_job01.ini        -> job_server
AppServer_ws_rest02.ini    -> slave_rest
appserver_broker_soap.ini  -> broker_soap
appserver_broker_rest.ini  -> broker_rest
dbaccess_slave.ini         -> dbaccess_slave
dbaccess_broker.ini        -> dbaccess_master
```

Cada um deve ter score coerente com seu papel, sem falsos positivos de secoes/chaves irrelevantes.
