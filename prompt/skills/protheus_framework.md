---
name: protheus_framework
description: Framework Protheus - MVC, FW classes, funcoes de dicionario, MsExecAuto, REST TLPP, ABM, BIRT, SmartLink
intents: [framework_info, mvc_info, function_info, rest_info, abm_info, birt_info]
keywords: [MVC, FWFormView, FWBrowse, FWFormStruct, MsExecAuto, execauto, rotina automatica, REST, TLPP, annotation, GetMV, TamSX3, GetSx3Cache, dicionario, funcao, framework, model, view, ABM, BIRT, SmartLink, FWRestModel, FWAdapterBaseV2, Embedded SQL, MenuDef, FWMVCMenu]
priority: 80
max_tokens: 800
specialist: "knowledge"
---

## FRAMEWORK PROTHEUS

> Base: 5.226 itens indexados da TDN (Framework Microsiga Protheus)
> Fonte: https://tdn.totvs.com/display/framework

### MVC (Model-View-Controller)

#### Conceito
Separa logica de negocio (Model) da interface (View). Permite teste e manutencao isolados.

#### Classes Principais

| Classe | Tipo | Uso |
|--------|------|-----|
| FWFormModel | Model | Logica de negocio, validacoes, persistencia |
| MPFormModel | Model | Extensao com Help, variaveis de memoria, campos SX3 |
| FWFormView | View | Construcao de interface (formularios, grids) |
| FWFormStruct | Struct | Cria estrutura a partir do metadado SX3 |
| FWFormModelStruct | Struct | Estrutura especifica para Model |
| FWFormViewStruct | Struct | Estrutura especifica para View |
| FwBrowse | Browse | Grid de consulta/listagem |
| FWExecView | Exec | Execucao de View externa |
| FWViewExec | Exec | Execucao de View alternativa |

#### Funcoes Auxiliares MVC

| Funcao | Uso |
|--------|-----|
| FWFormStruct(nTipo, cAlias) | Cria estrutura: 1=Model, 2=View |
| FWLoadBrw("PROGRAMA") | Carrega browse na funcao principal |
| FWMVCMenu() | Menu padrao (Visualizar, Incluir, Alterar, Excluir, Imprimir, Copiar) |
| FWRestModel | Publica MVC via REST automaticamente |

#### Estrutura Padrao MVC
```
// Funcao principal
User Function XPTO()
  Local oBrowse := FwLoadBrw("XPTO")
  oBrowse:Activate()
Return

// Model
Static Function ModelDef()
  Local oStruct := FWFormStruct(1, "SA1")
  Local oModel := MPFormModel():New("XPTOMD")
  oModel:AddFields("MASTER", /*owner*/, oStruct)
  oModel:SetPrimaryKey({"A1_FILIAL","A1_COD","A1_LOJA"})
Return oModel

// View
Static Function ViewDef()
  Local oStruct := FWFormStruct(2, "SA1")
  Local oView := FWFormView():New()
  oView:SetModel(FWLoadModel("XPTO"))
  oView:AddField("VIEW_SA1", oStruct, "MASTER")
Return oView

// Menu
Static Function MenuDef()
Return FWMVCMenu("XPTO")
```

### MsExecAuto (Rotinas Automaticas)

#### Sintaxe
```
MSExecAuto({|x,y| ROTINA(x,y)}, aArray, nOpc)
// nOpc: 3=Inclusao, 4=Alteracao, 5=Exclusao
```

#### Variaveis de Controle
```
Private lMsHelpAuto := .T.      // Nao exibe helps
Private lAutoErrNoFile := .T.   // Nao grava log em arquivo
Private lMsErroAuto := .F.      // Flag de erro (.T. = erro ocorreu)
```

#### Rotinas Principais

| Rotina | Modulo | Tabelas | Descricao |
|--------|--------|---------|-----------|
| MATA010 | SIGAEST | SB1 | Cadastro de Produtos |
| MATA020 | SIGAEST | SA2 | Cadastro de Fornecedores |
| MATA030 | SIGAFAT | SA1 | Cadastro de Clientes |
| MATA103 | SIGACOM | SF1+SD1 | Documento de Entrada (NF) |
| MATA110 | SIGACOM | SC1 | Solicitacao de Compra |
| MATA120 | SIGACOM | SC7 | Pedido de Compra |
| MATA140 | SIGAEST | SD3 | Movimentacoes Internas |
| MATA200 | SIGAPCP | SC2 | Ordem de Producao |
| MATA230 | SIGAPCP | SD3 | Apontamento de Producao |
| MATA270 | SIGAEST | SB7 | Inventario |
| MATA410 | SIGAFAT | SC5+SC6 | Pedido de Venda |
| MATA461 | SIGAFAT | SF2+SD2 | Documento de Saida (NF) |
| MATA650 | SIGAPCP | SC2 | OP via ExecAuto |
| FINA050 | SIGAFIN | SE1 | Contas a Receber |
| FINA040 | SIGAFIN | SE2 | Contas a Pagar |

### Funcoes de Dicionario

#### SX3 (Campos)
| Funcao | Parametros | Retorno |
|--------|-----------|---------|
| GetSx3Cache(cCampo, cColuna) | Campo, coluna SX3 | Valor da coluna |
| TamSX3(cCampo) | Nome do campo | Array {tamanho, decimal, tipo} |
| X3Titulo() | (posicionado) | Titulo do campo no idioma |
| X3Descric() | (posicionado) | Descricao do campo |
| X3Picture(cCampo) | Nome do campo | Mascara de exibicao |
| X3Obrigat(cCampo) | Nome do campo | .T. se obrigatorio |
| X3CBox() | (posicionado) | Combo box options |
| X3Uso(cUsado, nModulo) | Flag uso, modulo | .T. se campo usado |
| PesqPict(cAlias, cCampo) | Alias, campo | Mascara |

#### SX6 (Parametros)
| Funcao | Parametros | Retorno |
|--------|-----------|---------|
| GetMV(cParam, lConsulta, xDefault) | Nome param, consulta, default | Conteudo do parametro |
| X6Conteud() | (posicionado) | Conteudo |
| X6Descric() | (posicionado) | Descricao |

#### SX7 (Gatilhos)
| Funcao | Parametros | Retorno |
|--------|-----------|---------|
| ExistTrigger(cCampo) | Nome do campo | .T. se existe gatilho |
| RunTrigger(nTipo, nLin, cMacro, oObj, cField) | Tipo, linha, macro, obj, campo | Executa o gatilho |

#### SXE/SX8 (Numeracao)
| Funcao | Parametros | Retorno |
|--------|-----------|---------|
| GetSXENum(cAlias, cCampo, cAliasSXE, nOrdem) | Alias, campo, alias SXE, ordem | Proximo numero |
| GetSX8Num(cAlias, cCampo) | Alias, campo | Numero reservado |
| ConfirmSX8(lVerifica) | Flag verificacao | Confirma numeracao |
| RollBackSx8() | — | Desfaz numeracao |

#### SX1 (Perguntas)
| Funcao | Parametros | Retorno |
|--------|-----------|---------|
| X1Def01() a X1Def05() | (posicionado) | Definicoes de combo (1a a 5a) |

#### SX2 (Tabelas)
| Funcao | Parametros | Retorno |
|--------|-----------|---------|
| X2Nome() | (posicionado) | Descricao da tabela |

#### SX5 (Tabelas Genericas)
| Funcao | Parametros | Retorno |
|--------|-----------|---------|
| X5Descri(cAlias) | Alias da tabela | Descricao no idioma |

#### SXB (Consulta Padrao)
| Funcao | Parametros | Retorno |
|--------|-----------|---------|
| Conpad1(...) | Multiplos | Exibe tela de consulta F3 |

### REST no Protheus

#### Duas abordagens

| Tipo | Linguagem | Classe/Recurso | Uso |
|------|-----------|----------------|-----|
| REST ADVPL | AdvPL | WSRESTFul classes | APIs legadas, compatibilidade |
| REST TLPP | TL++ | Annotations (@Get, @Post...) | APIs modernas, melhor performance |

#### REST TLPP (Annotations)
```
#Include "Protheus.Ch"
#Include "tlpp-core.th"
#Include "tlpp-rest.th"

@Get(endpoint="/api/v1/clientes", description="Lista clientes")
User Function GetClientes()
  Local oRest := oRest  // Objeto REST injetado
  Local cJson := '{"status":"ok"}'
  oRest:setResponse(cJson)
Return .T.

@Post(endpoint="/api/v1/clientes", description="Cria cliente")
User Function PostCliente()
  Local cBody := oRest:getBodyRequest()
  // processar...
  oRest:setResponse('{"created":true}')
  oRest:setStatusCode(201)
Return .T.
```

#### Configuracao REST (appserver.ini)
```ini
[HTTPJOB]
MAIN=HTTP_START
ENVIRONMENT=AMBIENTE

[HTTP]
ENABLE=1
PORT=8080

[HTTPV11]
ENABLE=1
SOCKETS=HTTPREST

[HTTPREST]
PORT=8181
URIS=HTTPURI

[HTTPURI]
URL=/rest
INSTANCES=3,10
```

#### FWRestModel
Publica MVC existente via REST sem criar classe REST:
```
PUBLISH USER MODEL REST NAME XPTO
```

### Componentes Framework (Indice TDN - 5.226 itens)

#### Artigos e Recursos (80 itens)
| Componente | Descricao |
|------------|-----------|
| ABM (Audit Business Monitor) | Monitoramento de regras de negocio (linguagem, parser, configuracao, objetos ABMAIL/ABMRST/ABMWS) |
| BIRT | Relatorios: instalacao Web Viewer, rptdesign, Data Source, Data Set (SQL/ADVPL), Report |
| Embedded SQL | Queries SQL embutidas em codigo AdvPL |
| Central de Ajuda | Help contextual no Protheus (fonte customizada, habilitacao) |
| Gráficos e Visões do Browse | Widgets graficos com visoes no FwBrowse |
| Consulta Generica Relacional | Exportacao XML, impressao, MPView |
| Troca de Temas | Modo escuro, tokens de cores, classe ProtheusTheme |
| Bloqueio Troca Quente | Regra de RPOs distintos no mesmo ambiente |

#### Framework Microsiga Protheus (principais categorias)
| Area | Conteudo |
|------|----------|
| MVC | FWFormModel, FWFormView, FWFormStruct, MPFormModel, ModelDef, ViewDef, MenuDef |
| Browse | FwBrowse, FwLoadBrw, FWMVCMenu, visoes, graficos |
| REST | WSRESTFul (ADVPL), Annotations TLPP (@Get/@Post), FWRestModel, FWAdapterBaseV2 |
| MsExecAuto | 15+ rotinas automaticas (MATA010-MATA650, FINA040/050) |
| Dicionario | GetSx3Cache, TamSX3, GetMV, SXE/SX8 numeracao, SX7 gatilhos |
| SmartLink | Integracao com Carol/Antecipa, metricas, Wizard TechFin |
| DBAccess | Atualizacao, TopConnect, conexao Oracle/SQL Server |
| Menu | SIGACFG, reimportacao, menu funcional, MenuDef |
| Traducao | Arquivos .CH, flavour, i18n |
| Impressao | Consulta generica, BIRT, Web Viewer |

#### Release Notes (2.604 itens)
Areas com release notes rastreados: Lib-Core, SmartLink (versoes 1.6.x a 2.4.x+)

#### Base de Conhecimento (2.536 itens)
Artigos de troubleshooting, configuracoes avancadas e integracao.
