---
name: protheus_tlpp
description: TLPP (TL++) - linguagem moderna do Protheus com classes, tipagem, REST nativo, annotations, regex, JSON, PROBAT
intents: [tlpp_info, tlpp_syntax, tlpp_rest, tlpp_classes, tlpp_regex, tlpp_json]
keywords: [TLPP, TL++, namespace, classe, tipagem, annotation, reflection, REST, PROBAT, regex, JSON, tJWE, tMetrics, tPBKDF2, tSFTPClient, tUnicode, KV Redis, DynCall, nomes longos, try catch, i18n]
priority: 80
max_tokens: 800
specialist: "knowledge"
---

## TLPP (TL++) — LINGUAGEM MODERNA PROTHEUS

> Base: 448 itens indexados da TDN
> Fonte: tdn_scraper/tdn_tlpp_v2.json

### Visao Geral

TLPP e a evolucao do AdvPL com recursos modernos de linguagem. Compila no mesmo RPO e convive com codigo AdvPL existente.

### Recursos de Linguagem (132 itens)

| Recurso | Descricao |
| ------- | --------- |
| Nomes longos | Identificadores maiores que 10 caracteres |
| Namespace | Organizacao hierarquica de codigo |
| Classes | Heranca, polimorfismo, encapsulamento (11 sub-itens) |
| Tipagem | Tipagem forte opcional, verificacao em compilacao (25 sub-itens) |
| Try...Catch | Tratamento de excecoes estruturado |
| Parametros Nomeados | Chamada de funcao com nome dos parametros |
| JSON | Manipulacao nativa de JSON (2 sub-itens) |
| Reflection e Annotation | Metaprogramacao, decorators para REST e outros (52 sub-itens) |
| TGetData e TGetMethods | Introspeccao de objetos |
| DynCall | Chamada dinamica de funcoes (uso interno, 30 sub-itens) |

### TlppCore — Ferramentas e Modulos (261 itens)

| Modulo | Itens | Descricao |
| ------ | ----- | --------- |
| GUI | 6 | Interface grafica TLPP |
| PROBAT | 80 | Framework de testes automatizados (unitarios, integracao) |
| RegEx | 36 | Expressoes regulares nativas |
| REST | 84 | Framework REST nativo com annotations (@Get, @Post, @Put, @Delete) |
| KV Redis | 23 | Cache key-value com Redis integrado |
| i18n | 8 | Internacionalizacao e traducao |
| DBMonitor Web | 14 | Monitor de banco de dados via interface web |
| tlpp-tools | — | Ferramentas auxiliares de desenvolvimento |

### Funcoes Uteis (9 itens)

| Funcao | Descricao |
| ------ | --------- |
| GetPatchFile | Obtem arquivo de patch |
| GetShortCutKey | Obtem tecla de atalho |
| SRCheckSourceSignature | Verifica assinatura de fonte |
| SRGetRpoStatus | Status do RPO |
| SRGetSignSourceCount | Contagem de fontes assinados |
| SRGetSourceCount | Contagem total de fontes no RPO |
| SRGetSourceStatus | Status de um fonte especifico |
| SRGetWhereIam | Identifica localizacao no RPO |
| tlpp.toStr | Conversao generica para string |

### Classes Uteis (27 itens)

| Classe | Itens | Descricao |
| ------ | ----- | --------- |
| tJWE | — | JSON Web Encryption (criptografia de tokens) |
| tMetrics | — | Coleta de metricas de performance |
| tPBKDF2 | — | Derivacao de chaves criptograficas |
| tSFTPClient | 20 | Cliente SFTP completo (upload, download, listagem) |
| tUnicode | 2 | Manipulacao de strings Unicode |

### Sintaxe Basica TLPP vs AdvPL

```
// AdvPL tradicional
User Function Teste()
  Local cVar := "hello"
Return cVar

// TLPP com tipagem
Namespace myapp.utils

@Annotation()
User Function Teste() As Character
  Local cVar As Character := "hello"
Return cVar
```

### REST TLPP com Annotations

```
#Include "tlpp-core.th"
#Include "tlpp-rest.th"

Namespace myapp.api

@Get("/api/v1/items")
User Function ListItems() As Logical
  Local oJson As Json
  oJson := JsonObject():New()
  oJson["items"] := {}
  oRest:setResponse(oJson:toJson())
Return .T.

@Post("/api/v1/items")
User Function CreateItem() As Logical
  Local cBody As Character := oRest:getBodyRequest()
  // processar...
  oRest:setStatusCode(201)
Return .T.
```

### PROBAT — Testes Automatizados

Framework de testes integrado ao TLPP:
- Testes unitarios e de integracao
- Assertions (AssertTrue, AssertFalse, AssertEquals, AssertNotEquals)
- Setup/Teardown por teste e por suite
- Execucao via AppServer ou linha de comando
- Relatorios de cobertura

### Notas de Release Rastreadas

Versoes documentadas: 01.04.02, 01.04.05, 01.04.06, 01.04.07, 01.04.10, 01.05.04

### Avisos Importantes

- `StaticCall` foi inibida em TLPP — usar alternativas recomendadas pela TOTVS
