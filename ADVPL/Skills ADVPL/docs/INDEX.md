# INDEX – Acervo ADVPL / Protheus

> Mapa de tópicos → arquivo + seção. Use este índice para navegar diretamente ao conteúdo relevante sem precisar ler os arquivos completos.

**Arquivos disponíveis:** advpl-fundamentos | advpl-avancado | advpl-mvc | advpl-web | advpl-webservices | matxfis | tlpp | pontos-de-entrada | dicionario-sx | mvc-customizacao-avancada | **queries-sql**

---

## Como usar este índice

1. Identifique o tópico que precisa
2. Abra o arquivo indicado
3. Use a âncora para ir diretamente à seção

---

## Linguagem ADVPL – Fundamentos

**Arquivo:** [advpl-fundamentos.md](advpl-fundamentos.md)

| Tópico | Seção |
|--------|-------|
| Estrutura de um programa ADVPL | `#3-estrutura-de-um-programa-advpl` |
| Tipos de dados (Caracter, Numérico, Data, Lógico, Array) | `#41-tipo-de-dados` |
| Declaração de variáveis (Local, Static, Private, Public) | `#48-declaração-de-variáveis` |
| Escopo de variáveis | `#5-escopo-de-variáveis` |
| Operadores (matemáticos, lógicos, relacionais, string) | `#6-operadores-da-linguagem-advpl` |
| Macro substituição `&` | `#7-operação-de-macro-substituição` |
| Funções de manipulação de variáveis | `#8-funções-de-manipulação-de-variáveis` |
| Conversões entre tipos | `#9-conversões-entre-tipos-de-variáveis` |
| Estruturas de repetição (FOR/NEXT, WHILE/ENDDO) | `#11-estruturas-de-repetição` |
| Estruturas de decisão (IF/ELSE, DO CASE) | `#12-estruturas-de-decisão` |
| Arrays e funções de array | `#13-arrays-e-blocos-de-código` |
| Blocos de código | `#14-blocos-de-código` |
| Funções: tipos e escopos | `#151-tipos-e-escopos-de-funções` |
| Passagem de parâmetros por valor e referência | `#16-passagem-de-parâmetros-entre-funções` |
| Diretivas de compilação (#INCLUDE, #DEFINE, #IFDEF) | `#18-diretivas-de-compilação` |
| Acesso e manipulação de banco de dados (DbSeek, DbSkip, RecLock) | `#231-acesso-e-manipulação-de-bases-de-dados-em-advpl` |
| Funções de acesso a dados | `#232-funções-de-acesso-e-manipulação-de-dados` |
| Controle de numeração sequencial | `#25-controle-de-numeração-sequencial` |
| Semáforos | `#26-semáforos` |
| Customização de campos – Dicionário de Dados (SX3) | `#271-customização-de-campos--dicionário-de-dados` |
| Pictures de formação | `#272-pictures-de-formação-disponíveis` |
| Gatilhos (SX7) | `#273-customização-de-gatilhos--configurador` |
| Parâmetros MV_ (SX6) | `#274-customização-de-parâmetros--configurador` |
| Pontos de Entrada | `#28-pontos-de-entrada--conceitos-premissas-e-regras` |
| Interfaces visuais básicas (DEFINE DIALOG, DEFINE BUTTON) | `#291-sintaxe-e-componentes-das-interfaces-visuais` |
| MBrowse() | `#293-mbrowse` |
| AxFunctions() | `#294-axfunctions` |
| Boas práticas de programação | `#301-boas-práticas-de-programação` |

---

## Programação Avançada – Modelos e Relatórios

**Arquivo:** [advpl-avancado.md](advpl-avancado.md)

| Tópico | Seção |
|--------|-------|
| Modelo1() / AxCadastro() — cadastro simples | `#21-modelo1-ou-axcadastro` |
| MBrowse() avançado (AxFunctions, FilBrowse, PesqBrw, BrwLegenda) | `#22-mbrowse` |
| MarkBrowse() — seleção múltipla | `#23-markbrowse` |
| Enchoice — formulário simples | `#24-enchoice` |
| EnchoiceBar — barra de botões | `#25-enchoicebar` |
| Modelo2() — cabeçalho + itens | `#26-modelo2` |
| Modelo3() — cabeçalho + múltiplas grids | `#27-modelo3` |
| Transações: BeginTransaction / RollbackTransaction | `#3-transações` |
| BeginTran (nível mais baixo) | `#32-begintran` |
| Relatórios com TReport | `#41-treport` |
| Funções para desenvolvimento de relatórios | `#42-funções-utilizadas-para-desenvolvimento-de-relatórios` |
| AjustaSX1() | `#43-ajustasx1` |
| Queries no Protheus (Embedded SQL, TCQuery) | `#5-utilizando-queries-no-protheus` |
| Embedded SQL | `#51-embedded-sql` |
| Manipulação de arquivos texto (1ª família) | `#62-1ª-família-de-funções-de-gravação-e-leitura-de-arquivos-texto` |
| Manipulação de arquivos texto (2ª família) | `#63-2ª-família-de-funções-de-gravação-e-leitura-de-arquivos-texto` |
| Multi-lines: MsNewGetDados() | `#711-msnewgetdados` |
| TCBrowse | `#72-tcbrowse` |
| FWTemporaryTable | `#8-fwtemporarytable` |
| Arquitetura MVC (visão geral) | `#9-arquitetura-mvc` |
| FWMBrowse — browse padrão MVC | `#101-aplicações-com-browses-fwmbrowse` |
| Construção completa de aplicação MVC | `#11-construção-de-aplicação-advpl-utilizando-mvc` |
| Objetos de interface (ListBox, ScrollBox, réguas) | `#15-objetos-de-interface` |
| Componentes visuais ADVPL (botões, menus, etc.) | `#16-componentes-da-interface-visual-do-advpl` |
| Boas práticas ADVPL II | `#apêndices--boas-práticas-de-programação` |

---

## MVC – Arquitetura Completa

**Arquivo:** [advpl-mvc.md](advpl-mvc.md)

| Tópico | Seção |
|--------|-------|
| Introdução à arquitetura MVC | `#11-introdução` |
| Funções principais: ModelDef, ViewDef, MenuDef | `#21-principais-funções-da-aplicação-em-advpl-utilizando-o-mvc` |
| ModelDef — definição do modelo de dados | `#22-o-que-é-a-função-modeldef` |
| ViewDef — definição da interface | `#23-o-que-é-a-função-viewdef` |
| MenuDef — definição do menu | `#24-o-que-é-a-função-menudef` |
| FWMBrowse — construção básica | `#32-construção-básica-de-um-browse` |
| FWMBrowse — exemplo completo | `#33-exemplo-completo-de-browse` |
| Construção do MenuDef | `#41-criando-o-menudef` |
| Construção do ModelDef | `#42-construção-da-função-modeldef` |
| Exemplo completo ModelDef | `#43-exemplo-completo-da-modeldef` |
| ViewDef: CreateHorizontalBox / CreateVerticalBox | `#51-exibição-dos-dados-na-interface-createhorizontalbox--createverticalbox` |
| SetOwnerView — relacionando componente | `#52-relacionando-o-componente-da-interface-setownerview` |
| Removendo campos da tela | `#53-removendo-campos-da-tela` |
| Exemplo completo ViewDef | `#55-exemplo-completo-da-viewdef` |
| FWLoadModel — reusar modelo existente | `#6-carregar-o-modelo-de-dados-de-uma-aplicação-já-existente-fwloadmodel` |
| FWLoadView — reusar interface existente | `#7-carregar-a-interface-de-uma-aplicação-já-existente-fwloadview` |
| Desenhador MVC | `#8-instalação-do-desenhador-mvc` |
| Mensagens na interface | `#91-mensagens-exibidas-na-interface` |
| SetViewAction — ação de interface | `#92-ação-de-interface-setviewaction` |
| SetFieldAction — ação por campo | `#93-ação-de-interface-do-campo-setfieldaction` |
| GetOperation — obter operação atual | `#94-obtenção-da-operação-que-está-sendo-realizada-getoperation` |
| GetModel — obter componente do modelo | `#95-obtenção-de-componente-do-modelo-de-dados-getmodel` |
| GetValue / SetValue — ler/gravar valores | `#96-obtenção-e-atribuição-de-valores-ao-modelo-de-dados` |
| FormGrid: SetRelation, AddLine, DeleteLine | `#10-manipulação-da-componente-formgrid` |
| AddIncrementField — campo auto-incremento | `#102-campo-incremental-addincrementfield` |
| CreateFolder — abas/pastas | `#109-criação-de-pastas-createfolder` |
| AddCalc — campos calculados/totais | `#1010-criação-de-campos-de-total-ou-contadores-addcalc` |
| Validações no MVC | `#1012-validações` |
| Eventos View (SetCloseOnOk, SetAfterOkButton) | `#11-eventos-view` |

---

## Desenvolvimento Web

**Arquivo:** [advpl-web.md](advpl-web.md)

| Tópico | Seção |
|--------|-------|
| Introdução ao ADVPL ASP | `#2-introdução-ao-advpl-asp` |
| Configurando servidor HTTP/Protheus | `#4-configurando-servidor-de-web-protheus` |
| Módulos Web | `#5-módulos-web` |
| Arquivos .APH — estrutura básica | `#6-características-do-advpl-asp---arquivos-aph` |
| Método GET | `#71-método-get` |
| Método POST | `#72-método-post` |
| HTTPSESSION — sessões | `#73-método-httpsession` |
| COOKIE | `#74-método-cookie` |
| HTTPHEADIN — headers HTTP | `#75-método-httpheadin` |
| Criação do Portal | `#8-criação-do-portal` |
| Multi-empresa / multi-filial na Web | `#81-processamento-para-várias-empresasfiliais` |
| Gravação de dados via Web | `#82-processo-de-gravação-de-dados-via-páginas-da-web` |
| Página Modelo 2 / Modelo 3 | `#9-página-modelo-2--modelo-3` |
| Relatórios na Web | `#10-desenvolvimento-e-impressão-de-relatório-na-web` |
| Upload / Download | `#11-upload--download` |
| Referência de funções ApWebEx | `#referência-de-funções-apwebex` |
| Pontos de entrada APWEBEX | `#pontos-de-entrada-apwebex` |

---

## WebServices (SOAP)

**Arquivo:** [advpl-webservices.md](advpl-webservices.md)

| Tópico | Seção |
|--------|-------|
| Introdução: WebService, WSDL, XML, SOAP, UDDI | `#2-introdução-aos-webservices` |
| Configurando o servidor de WebServices | `#4-configurando-o-servidor-de-webservices` |
| WSINDEX — índice de serviços | `#7-wsindex--índice-de-serviços` |
| Codificando um serviço (WsMethod, WsService, WsStruct, WsData) | `#8-codificando-o-serviço` |
| Testando o serviço | `#9-testando-o-serviço` |
| Consumindo um serviço externo | `#10-consumo-de-serviços` |
| TWsdlManager — consumo dinâmico | `#11-twsdlmanager` |
| WebService de gravação — exemplo completo | `#12-criando-um-webservice-de-gravação` |
| Definição de estruturas (WsStruct) | `#121-definição-de-estrutura` |
| Códigos de erro WSCERR000–WSCERR073 | `#códigos-de-erro` |
| Regras de nomenclatura | `#regras-de-nomenclatura` |

---

## Motor de Impostos MATXFIS

**Arquivo:** [matxfis.md](matxfis.md)

| Função | Descrição resumida | Seção |
|--------|--------------------|-------|
| `MaFisFound()` | Verifica se NF/item existe nos arrays internos | `#21-mafisfound` |
| `MaFisSave()` | Salva estado atual em área temporária | `#22-mafissave` |
| `MaFisRestore()` | Restaura estado salvo por MaFisSave | `#23-mafisrestore` |
| `MaFisClear()` | Limpa itens, zera totalizadores (mantém cabeçalho) | `#24-mafisclear` |
| `MaFisEnd()` | Finaliza e limpa TODOS os arrays internos | `#25-mafisend` |
| `MaFisNFCab()` | Retorna array com todos os impostos calculados | `#26-mafisfcab` |
| `MaFisIni()` | Inicia MATXFIS, forma o aNFCab | `#27-mafisini` |
| `MaFisIniLoad()` | Acrescenta novo item no aNFItem (mais rápido) | `#28-mafisiniload` |
| `MaFisAdd()` | Acrescenta item e dispara cálculo completo | `#29-mafisadd` |
| `MaFisLoad()` | Carrega valor em referência fiscal (sem calcular) | `#210-mafisload` |
| `MaFisEndLoad()` | Finaliza carga do item, atualiza totalizadores | `#211-mafisendload` |
| `MaFisRet()` | Retorna valor calculado de uma referência fiscal | `#212-mafisret` |
| `MaFisSXRef()` | Mapeia campos de uma tabela para referências fiscais | `#213-mafissxref` |
| `MaFisRelImp()` | Como MaFisSXRef mas para múltiplos aliases | `#214-mafisrelimp` |
| `MaFisRef()` | Integra MATXFIS com X3_VALID (uso em dicionário) | `#215-mafisref` |
| `MaFisAlt()` | Altera referência fiscal e dispara recálculo | `#216-mafisalt` |
| `MaFisDel()` | Sincroniza deleção entre aCols e aNFItem | `#217-mafisdel` |
| `MaColsToFis()` | Carrega aCols completo no aNFItem | `#218-macolstofis` |
| `MaFisToCols()` | Atualiza aCols com valores calculados do aNFItem | `#219-mafistocols` |
| `MaFisRecal()` | Executa pilha de cálculo de impostos (uso interno) | `#220-mafisrecal` |
| `MaFisWrite()` | Grava referências fiscais nas tabelas (SF1/SD1, etc.) | `#221-mafiswrite` |
| `MaFisAtuSF3()` | Grava/exclui SF3, SFT e CD2 (Livro Fiscal + SPED) | `#222-mafisatusf3` |
| `MaFisIniNF()` | Carrega NF gravada (SF1/SF2) na MATXFIS | `#223-mafisininf` |
| `MaFisBrwLivro()` | Cria browse do Livro Fiscal na dialog | `#224-mafisbrwlivro` |
| `MaFisRodape()` | Cria browse de impostos calculados na dialog | `#225-mafisrodape` |

---

## Mapa de Tópicos por Necessidade

### "Preciso criar um cadastro simples"
→ [advpl-avancado.md — Modelo1/AxCadastro](advpl-avancado.md#21-modelo1-ou-axcadastro)

### "Preciso criar um cadastro com itens (cabeçalho + grid)"
→ [advpl-avancado.md — Modelo2](advpl-avancado.md#26-modelo2) ou [MVC completo](advpl-mvc.md#11-construção-de-aplicação-advpl-utilizando-mvc)

### "Preciso criar um relatório"
→ [advpl-avancado.md — TReport](advpl-avancado.md#41-treport)

### "Preciso fazer uma query SQL"
→ [advpl-avancado.md — Embedded SQL](advpl-avancado.md#51-embedded-sql)

### "Preciso criar um WebService (servidor)"
→ [advpl-webservices.md — Codificando o Serviço](advpl-webservices.md#8-codificando-o-serviço)

### "Preciso consumir um WebService externo"
→ [advpl-webservices.md — TWsdlManager](advpl-webservices.md#11-twsdlmanager)

### "Preciso criar uma página web"
→ [advpl-web.md — Criação do Portal](advpl-web.md#8-criação-do-portal)

### "Preciso calcular impostos em uma NF"
→ [matxfis.md — MaFisIni + fluxo completo](matxfis.md#27-mafisini)

### "Não sei qual escopo de variável usar"
→ [advpl-fundamentos.md — Escopo de Variáveis](advpl-fundamentos.md#5-escopo-de-variáveis)

### "Preciso adicionar uma grid/tabela nova em tela MVC padrão via PE"
→ [mvc-customizacao-avancada.md — Template Completo](mvc-customizacao-avancada.md#10-template-completo--adicionar-grid-em-tela-mvc-padrão)

### "Preciso criar gatilhos em cascata entre grids MVC"
→ [mvc-customizacao-avancada.md — Gatilhos em Cascata](mvc-customizacao-avancada.md#5-gatilhos-em-cascata-no-mvc)

### "Preciso usar MATXFIS dentro do MVC"
→ [mvc-customizacao-avancada.md — MATXFIS dentro do MVC](mvc-customizacao-avancada.md#53-gatilho-com-matxfis-dentro-do-mvc)

### "Preciso bloquear edição de grid por status do registro"
→ [mvc-customizacao-avancada.md — Controle por Status](mvc-customizacao-avancada.md#7-controle-de-comportamento-por-status)

### "Preciso fazer query SQL / Embedded SQL / TcGenQry"
→ [queries-sql.md — Guia Completo](queries-sql.md#1-visao-geral----sql-no-protheus)

### "Qual forma de query usar? BeginSQL, TcGenQry ou FWExecStatement?"
→ [queries-sql.md — Comparativo](queries-sql.md#54-quando-preferir-sobre-tcgenqry)

### "Preciso fazer INSERT/UPDATE/DELETE direto no banco"
→ [queries-sql.md — TCSqlExec](queries-sql.md#4-tcsqlexec----execucao-sem-retorno)

### "Como prevenir SQL Injection no Protheus"
→ [queries-sql.md — Montagem Segura](queries-sql.md#8-montagem-segura-de-queries)

### "Query está lenta, como otimizar"
→ [queries-sql.md — Performance](queries-sql.md#9-performance-e-boas-praticas)

### "Preciso entender o dicionário SX / criar campo / gatilho / parâmetro"
→ [dicionario-sx.md — Visão Geral](dicionario-sx.md#1-visão-geral-do-dicionário-de-dados)

### "Preciso criar um gatilho SX7"
→ [dicionario-sx.md — SX7 Gatilhos](dicionario-sx.md#7-sx7--gatilhos-de-campos)

### "Preciso criar/usar parâmetro MV_"
→ [dicionario-sx.md — SX6](dicionario-sx.md#6-sx6--parâmetros-mv_)

### "Preciso criar consulta F3 (SXB)"
→ [dicionario-sx.md — SXB](dicionario-sx.md#10-sxb--consultas-padrão-f3)

### "Preciso usar MsExecAuto"
→ [dicionario-sx.md — MsExecAuto](dicionario-sx.md#143-execauto-e-msexecauto)

### "Preciso criar um ponto de entrada"
→ [pontos-de-entrada.md — Guia Completo de PEs](pontos-de-entrada.md#1-conceito-e-propósito) *(guia dedicado — clássico e MVC)*
→ [advpl-fundamentos.md — Pontos de Entrada (visão geral)](advpl-fundamentos.md#28-pontos-de-entrada--conceitos-premissas-e-regras)

### "Quero usar TLPP / código moderno"
→ [tlpp.md — O que é TLPP](tlpp.md#1-o-que-é-tlpp)

### "Quero criar uma API REST no Protheus"
→ [tlpp.md — REST com TLPP](tlpp.md#8-rest-com-tlpp)

### "Quero usar classes, herança, interfaces em ADVPL moderno"
→ [tlpp.md — Orientação a Objetos](tlpp.md#4-orientação-a-objetos)

### "Quero tratar exceções com try/catch"
→ [tlpp.md — Tratamento de Exceções](tlpp.md#5-tratamento-de-exceções)

### "Preciso escrever testes unitários"
→ [tlpp.md — PROBAT](tlpp.md#11-probat--testes-unitários)

### "Diferença entre ADVPL e TLPP"
→ [tlpp.md — Comparativo Geral](tlpp.md#12-tlpp-vs-advpl--comparativo-geral)

### "Preciso customizar rotina MVC via PE"
→ [pontos-de-entrada.md — PEs MVC](pontos-de-entrada.md#3-pontos-de-entrada-mvc)

### "Quero ver exemplos de MT101OK, MA100OK, M460VISS"
→ [pontos-de-entrada.md — Exemplos reais](pontos-de-entrada.md#27-exemplos-reais-de-pes-clássicos)

---

## Pontos de Entrada – ADVPL e MVC

**Arquivo:** [pontos-de-entrada.md](pontos-de-entrada.md)

| Tópico | Seção |
|--------|-------|
| Conceito e propósito dos PEs | `#1-conceito-e-propósito` |
| ExecBlock e ExistBlock — sintaxe e uso | `#21-como-funcionam--execblock-e-existblock` |
| Estrutura básica de um PE | `#22-estrutura-básica-de-um-ponto-de-entrada` |
| PARAMIXB — recebendo parâmetros | `#23-parâmetros--paramixb` |
| Retorno dos PEs (.T./.F./NIL/Array) | `#24-retorno-dos-pontos-de-entrada` |
| Regras e premissas — o que pode e não pode | `#25-regras-e-premissas` |
| Como descobrir PEs de uma rotina | `#26-como-descobrir-quais-pes-existem-em-uma-rotina` |
| MT101OK / MT101INC / MT101ALT / MT101DEL | `#27-exemplos-reais-de-pes-clássicos` |
| MA100OK / MA100DSP (Compras) | `#27-exemplos-reais-de-pes-clássicos` |
| M460VISS / M460FIM (Faturamento) | `#27-exemplos-reais-de-pes-clássicos` |
| TReport — pontos de entrada em relatórios | `#28-pontos-de-entrada-em-relatórios-treport` |
| X3_VALID — validação de campo | `#29-pontos-de-entrada-em-validações-de-campo-x3_valid` |
| PEs MVC — diferenças do modelo clássico | `#31-diferenças-em-relação-ao-modelo-clássico` |
| Arquitetura MVC — ModelDef, ViewDef, MenuDef | `#32-estrutura-da-arquitetura-mvc` |
| PARAMIXB no MVC | `#33-paramixb-no-contexto-mvc` |
| Tabela completa de hooks MVC | `#34-tabela-completa-de-ids-de-hooks-mvc` |
| MODELPOS, FORMCOMMITTTS, MODELCOMMITTTS... | `#35-detalhamento-dos-hooks-mais-importantes` |
| Exemplos completos de PEs MVC | `#36-exemplos-completos-de-pes-mvc` |
| ValidFields / ValidLines no MVC | `#37-funções-de-validação-no-mvc--modeldef-e-viewdef` |
| Boas práticas (PE vs gatilho vs X3_VALID) | `#41-quando-usar-pe-vs-gatilho-vs-validação-de-campo` |
| GetArea / RestArea — preservar ambiente | `#42-preservar-o-ambiente--getarea-e-restarea` |
| Performance e retorno correto | `#43-performance` |
| Referência de PEs por módulo | `#5-referência-de-pes-por-módulo` |

---

## Dicionário de Dados – Estrutura SX

**Arquivo:** [dicionario-sx.md](dicionario-sx.md)

| Tópico | Seção |
|--------|-------|
| Visão geral do dicionário — o que é, por que existe | `#1-visão-geral-do-dicionário-de-dados` |
| Mapa completo da família SX | `#mapa-completo-da-família-sx` |
| SX1 — Perguntas de relatórios/processos, Pergunte(), AjustaSX1() | `#2-sx1--perguntas-do-usuário` |
| SX2 — Mapeamento de arquivos/tabelas | `#3-sx2--mapeamento-de-arquivos` |
| SX3 — Campos: estrutura, apresentação, comportamento | `#4-sx3--campos-das-tabelas` |
| SX3 — X3_VALID: validação de campo | `#44-x3_valid--validação-de-campo` |
| SX3 — X3_WHEN: habilitação condicional | `#45-x3_when--habilitação-condicional` |
| SX3 — X3_TRIGGER: disparar gatilhos | `#46-x3_trigger--gatilhos` |
| SX3 — X3_F3: consultas de pesquisa | `#47-consultas-f3-via-x3_f3` |
| SX5 — Tabelas genéricas de domínio | `#5-sx5--tabelas-genéricas` |
| SX6 — Parâmetros MV_, GetMV(), SuperGetMV() | `#6-sx6--parâmetros-mv_` |
| SX7 — Gatilhos: tipos, campos, fluxo, exemplos | `#7-sx7--gatilhos-de-campos` |
| SX7 — Encadeamento de gatilhos | `#74-encadeamento-de-gatilhos` |
| SX8 — Reserva transacional de numeração | `#8-sx8--reserva-de-numeração` |
| SX9 — Relacionamentos entre entidades (uso no MVC) | `#9-sx9--relacionamentos-entre-entidades` |
| SXB — Consultas F3: tipos de registro, criar personalizada | `#10-sxb--consultas-padrão-f3` |
| SXE/SXF — Controle de numeração sequencial | `#11-sxe-e-sxf--controle-de-numeração-sequencial` |
| SIX — Índices dos arquivos | `#12-six--índices-dos-arquivos` |
| SXA — Pastas e agrupamentos de campos | `#13-sxa--pastas-e-agrupamentos-de-campos` |
| Posicione() — posicionamento em tabela | `#142-posicione` |
| MsExecAuto() — execução automática de rotinas | `#143-execauto-e-msexecauto` |
| FieldPos(), FieldGet(), FieldPut() | `#145-fieldpos-fieldget-fieldput` |
| Funções de SX5, SX6, SX7, SX8 | `#146-funções-de-sx5` |
| Campos virtuais vs reais | `#151-campos-reais-vs-virtuais` |
| Contexto compartilhado vs exclusivo (X3_CONTEXT) | `#152-contexto-compartilhado-vs-exclusivo` |
| Convenções de nomenclatura (faixas ZZ/ZA) | `#153-convenções-de-nomenclatura` |

---

## TLPP – Linguagem Moderna

**Arquivo:** [tlpp.md](tlpp.md)

| Tópico | Seção |
|--------|-------|
| O que é TLPP, histórico, motivações | `#1-o-que-é-tlpp` |
| TLPP vs ADVPL — tabela comparativa | `#12-tlpp-vs-advpl--comparativo-geral` |
| Extensões de arquivo (.tlpp, .th) | `#13-extensões-de-arquivo` |
| tlppCore e tlpp.rpo | `#14-tlppcore-e-tlpprpo` |
| Tipagem de variáveis (as Character, as Numeric...) | `#21-tipagem-de-variáveis` |
| Nomes longos (255 chars) | `#22-nomes-longos` |
| Parâmetros nomeados | `#23-parâmetros-nomeados` |
| Includes TLPP | `#24-includes-tlpp` |
| Namespaces — declaração e uso | `#3-namespaces` |
| Orientação a Objetos — visão geral | `#4-orientação-a-objetos` |
| Modificadores de acesso (public/private/protected/static/final/abstract) | `#43-modificadores-de-acesso` |
| Construtores | `#44-construtores` |
| Herança simples | `#45-herança-simples` |
| Interfaces | `#46-interfaces` |
| Membros estáticos | `#48-métodos-e-propriedades-estáticos` |
| Try/Catch/Finally | `#51-estrutura-trycatchfinally` |
| Throw — lançamento de exceções | `#52-throw--lançamento-explícito` |
| Anotações (@Annotation) | `#6-anotações-annotation` |
| JSON nativo — literal e JsonObject | `#7-json-nativo` |
| REST: configuração do appserver.ini | `#82-configuração-do-appserverini` |
| REST: annotations (@Get, @Post, @Put, @Delete) | `#84-annotations-rest` |
| REST: objeto oRest e seus métodos | `#85-objeto-orest--métodos-disponíveis` |
| REST: exemplos completos de endpoints | `#86-exemplos-completos-de-endpoints` |
| REST: FWRest — consumindo APIs externas | `#89-fwrest--consumindo-apis-externas` |
| Interoperabilidade TLPP ↔ ADVPL | `#9-interoperabilidade-com-advpl` |
| DynCall — importação de DLL | `#10-dyncall--importação-de-dll` |
| PROBAT — testes unitários | `#11-probat--testes-unitários` |
| TDS VSCode — instalação e atalhos | `#12-tds--totvs-developer-studio-for-vscode` |
| Migração ADVPL → TLPP | `#13-migração-advpl-para-tlpp` |
| Boas práticas TLPP | `#14-boas-práticas` |
| Exemplos completos (classe bancária, CRUD REST) | `#15-exemplos-completos` |
