---
name: tdn_appserver_config
description: Referencia de configuracao do AppServer/DBAccess Protheus — secoes e chaves do appserver.ini
intents: [ini_audit, knowledge_search, error_analysis, procedure_lookup]
keywords: [appserver, dbaccess, ini, configuracao, config, secao, chave, porta, port, driver, database, threads, connections, maxstringsize, topconnect, license, smartclient, http, rest, ssl, certificado, log, environment, rpodb]
priority: 75
max_tokens: 1200
specialist: "settings"
---

## Configuracao AppServer Protheus — Secoes Principais

Fonte: TDN TOTVS (tdn.totvs.com/display/tec/Application+Server)

### [DBAccess] — Conexao com banco de dados
| Chave | Descricao | Exemplo |
|-------|-----------|---------|
| Server | IP/hostname do DBAccess | 192.168.1.10 |
| Port | Porta do DBAccess | 7890 |
| Database | Nome do banco | protheus |
| Alias | Alias da conexao | protheus_hml |
| Driver | Driver do banco (mssql, oracle, postgres) | mssql |
| MemoMega | Habilita MEMO em campos grandes | 1 |

### [Drivers] — Protocolos de conexao
| Chave | Descricao | Exemplo |
|-------|-----------|---------|
| Active | Protocolo ativo | TCP |
| MultiProtocolPort | Porta unificada | 1 |
| MultiProtocolPortSecure | Porta SSL | 0 |

### [TCP] — Configuracao TCP
| Chave | Descricao | Exemplo |
|-------|-----------|---------|
| Type | Tipo de conexao | TCPIP |
| Port | Porta do AppServer | 1234 |

### [<Environment>] — Ambiente Protheus (ex: [environment])
| Chave | Descricao | Exemplo |
|-------|-----------|---------|
| SourcePath | Caminho do RPO | /totvs/protheus/apo |
| RootPath | Caminho raiz | /totvs/protheus |
| StartPath | Caminho de inicializacao | /system/ |
| RpoDb | Banco para RPO (Top, ctree) | Top |
| RpoLanguage | Idioma (portuguese, english, spanish) | portuguese |
| RpoVersion | Versao do RPO | 120 |
| localfiles | Formato arquivos locais (ctree, ads) | ctree |
| localdbextension | Extensao dos arquivos locais | .dtc |
| PictFormat | Formato de data (DEFAULT, US) | DEFAULT |
| DateFormat | Formato de data | dd/mm/yyyy |
| MaxStringSize | Tamanho maximo de string | 10 |

### [General] — Configuracoes gerais
| Chave | Descricao | Exemplo |
|-------|-----------|---------|
| ConsoleLog | Habilita log no console | 1 |
| ConsoleLogFile | Arquivo de log | console.log |
| MaxLocks | Maximo de locks simultaneos | 500000 |
| InstallPath | Caminho de instalacao | /totvs/protheus |

### [HTTP] — Servidor HTTP/REST embutido
| Chave | Descricao | Exemplo |
|-------|-----------|---------|
| Enable | Habilita HTTP | 1 |
| Port | Porta HTTP | 8080 |
| Path | Caminho web | /web/ |
| Instances | Instancias HTTP | 1,5 |
| TimeOut | Timeout em segundos | 120 |

### [HTTPREST] — REST API do Protheus
| Chave | Descricao | Exemplo |
|-------|-----------|---------|
| URL | URL base da REST API | /rest |
| PrepareIn | Environment para REST | environment |
| Instances | Working threads (min,max) | 1,10 |
| CORSEnable | Habilita CORS | 1 |
| AllowOrigin | Origens permitidas | * |

### [SSLConfigure] — SSL/TLS
| Chave | Descricao | Exemplo |
|-------|-----------|---------|
| CertificateServer | Caminho do certificado | /certs/server.pem |
| KeyServer | Caminho da chave privada | /certs/server.key |
| PassPhrase | Senha do certificado | (vazio ou senha) |
| SSL2 | Habilita SSLv2 (desabilitar!) | 0 |
| SSL3 | Habilita SSLv3 (desabilitar!) | 0 |
| TLS1 | Habilita TLSv1 | 1 |

### [License] — Licenciamento
| Chave | Descricao | Exemplo |
|-------|-----------|---------|
| Server | IP do License Server | 192.168.1.5 |
| Port | Porta do License Server | 5555 |

### Diagnostico comum de erros INI
- **Porta em uso**: Verificar se outra instancia ja usa a porta (netstat -tlnp)
- **RPO nao encontrado**: Checar SourcePath + RpoVersion + existencia do arquivo .rpo
- **DBAccess timeout**: Checar Server/Port, firewall, servico DBAccess rodando
- **MaxStringSize**: Se < 10, campos MEMO podem truncar (recomendado: 10)
- **REST nao responde**: Checar [HTTPREST] Enable=1, PrepareIn correto, Instances > 0
