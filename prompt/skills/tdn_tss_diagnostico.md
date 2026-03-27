---
name: tdn_tss_diagnostico
description: Diagnostico de problemas comuns do TSS (TOTVS Service SOA) — NFe, CTe, certificados, configuracao
intents: [error_analysis, knowledge_search, procedure_lookup]
keywords: [tss, nfe, cte, mdfe, nfse, certificado, ssl, sped, documento fiscal, rejeicao, autorizacao, contingencia, inutilizacao, sefaz, webservice, xml, assinatura, tssmonitor, job, spedprocserver, tssfiscal]
priority: 75
max_tokens: 1000
specialist: "diagnostico"
---

## TSS — Diagnostico de Problemas Comuns

Fonte: Central de Atendimento TOTVS (77 artigos compilados)

### Problemas de Assinatura e Certificado
- **"NFe ainda nao foi assinada"**: Reiniciar servico TSS. Se persistir, atualizar RPO do TSS
- **Certificado expirado**: Verificar validade com `certmgr` ou `openssl x509 -enddate`
- **Erro SSL/TLS**: Configurar [SSLConfigure] no appserver.ini do TSS. TLS1=1, SSL2=0, SSL3=0
- **AUTDSTMAIL in AppMap**: Funcao nao encontrada no RPO — atualizar RPO do TSS

### Problemas de Configuracao
- **TSS nao inicia**: Verificar porta em uso, licenca, DBAccess acessivel
- **SPEDPROCSERVER**: Job principal do TSS. Se nao roda, verificar [OnStart] Jobs=SPEDPROCSERVER
- **Timeout SEFAZ**: Aumentar timeout em MV_TSSWSDT (default 120s)
- **Contingencia**: Ativar via MV_CONTING=1 e MV_TSSCSRT (tipo: SCAN, DPEC, SVC-AN, SVC-RS)

### Parametros MV_ do TSS (SX6)
| Parametro | Descricao | Valor Padrao |
|-----------|-----------|--------------|
| MV_TSSURL | URL do TSS | http://servidor:porta/ws |
| MV_TSSDIR | Diretorio de schemas XML | /tss/schemas/ |
| MV_TSSWSDT | Timeout WebService (seg) | 120 |
| MV_CONTING | Contingencia ativa | 0 |
| MV_TSSCSRT | Tipo contingencia | (vazio) |
| MV_SPEDURL | URL SPED | (varia por estado) |
| MV_ESTNEG | Estorno negativo | S/N |
| MV_DTEFIS | Data fiscal | (data) |

### Tabelas do TSS
| Tabela | Descricao |
|--------|-----------|
| SPED010 | Cabecalho documentos fiscais |
| SPED020 | Eventos (cancelamento, carta correcao) |
| SPED030 | Inutilizacao |
| CTO010 | CTe (Conhecimento Transporte) |
| MDF010 | MDFe (Manifesto Destino) |

### Fluxo de Diagnostico TSS
1. Verificar se servico TSS esta rodando (process list ou TSSMonitor)
2. Verificar logs do AppServer TSS (console.log)
3. Verificar conectividade com SEFAZ (curl para URL do WS)
4. Verificar certificado (validade, cadeia completa, formato PFX/PEM)
5. Verificar parametros MV_ na SX6 do ambiente Protheus
6. Verificar se RPO do TSS esta atualizado (versao compativel com Protheus)
