# Pontos de Entrada Protheus — Referencia Completa

> Fonte: Base padrao TOTVS (extraiRPO)
> Total: 457 pontos de entrada

---

## SIGAATF

### AF012ROT
- **Rotina:** ATFA012
- **Onde chamado:** MenuDef da rotina ATFA012
- **Objetivo:** Inclusao de opcao ao menu de Ativo Fixo
- **TDN:** https://accounts.google.com/ServiceLogin?hl=pt-BR&passive=true&continue=https://www.google.com/search%3Fq%3DTOTVS%2520Protheus%2520ponto%2520de%2520entrada%2520AF012ROT%2520site:tdn.totvs.com%2520OR%2520site:centraldeatendimento.totvs.com%26sei%3DQ-O-aefUJLus5OUPuLGSgQ0&ec=futura_srp_og_si_72236_p

## SIGACOM

### MT094CPC
- **Rotina:** MATA094
- **Onde chamado:** Campos do PC na liberação do Doc. Entrada
- **Objetivo:** Exibe informações de outros campos do pedido de compra no momento da liberação do documento
- **Params saida:** Caracter (campos)
- **TDN:** https://tdn.totvs.com/pages/releaseview.action?pageId=286224513

### MT094END
- **Rotina:** MATA094
- **Onde chamado:** Ao finalizar a inclusão ou alteração de um Pedido de Compra, imediatamente após a gravação dos dados no banco.
- **Objetivo:** Permite executar customizações ou rotinas adicionais ao final do processo de inclusão/alteração de um Pedido de Compra.
- **Params entrada:** Nenhum parâmetro de entrada é passado explicitamente para o ponto de entrada.
- **Params saida:** Não há parâmetros de saída; utiliza variáveis globais e contexto do ambiente.
- **TDN:** https://tdn.totvs.com/display/public/PROT/TUMXYE_DT_PONTO_ENTRADA_MT094END

### MT094LEG
- **Rotina:** MATA094
- **Onde chamado:** Durante a geração do relatório de listagem de pedidos de compra, antes da impressão de cada linha do relatório.
- **Objetivo:** Permite customizar ou alterar os dados que serão impressos em cada linha do relatório de listagem de pedidos de compra.
- **Params entrada:** aLinha (Array com os dados da linha que será impressa no relatório)
- **Params saida:** aLinha (Array podendo ser alterado para modificar os dados impressos)
- **TDN:** https://tdn.totvs.com/pages/releaseview.action?pageId=286512466

### MT094LOK
- **Rotina:** MATA094
- **Onde chamado:** Após a leitura do registro de um item do pedido de compra, durante a rotina de manutenção de pedidos de compra.
- **Objetivo:** Permite customizar ou validar informações logo após a leitura de cada item do pedido de compra, possibilitando a inclusão de regras específicas ou tratamentos adicionais.
- **Params entrada:** aParam (Array com informações do item do pedido de compra lido)
- **Params saida:** Pode alterar o conteúdo de aParam para refletir customizações ou validações realizadas.
- **TDN:** https://tdn.totvs.com/pages/releaseview.action?pageId=248580670

### MTA094RO
- **Rotina:** MATA094
- **Onde chamado:** Liberacao Docs - Outras Acoes
- **Objetivo:** Opcoes no Outras Acoes

### MT097LVI
- **Rotina:** MATA097
- **Onde chamado:** Comportamento Visto/Livre na Liberação de Docs
- **Objetivo:** Altera Comportamento de Exibição VISTO/LIVRE na Liberação de Documentos
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360000169747

### LOCFDTR
- **Rotina:** MATA101N
- **Onde chamado:** Filtro no MATA101N
- **Objetivo:** Ponto de entrada para habilitar filtro no MATA101N
- **Params saida:** Caracter (filtro)
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360000169747

### A103BLOQ
- **Rotina:** MATA103
- **Onde chamado:** Durante a validação de bloqueio de documentos de entrada na rotina de documento de entrada
- **Objetivo:** Permite customizar a validação de bloqueio de documentos de entrada, possibilitando implementar regras específicas para determinar se um documento deve ser bloqueado ou liberado
- **Params entrada:** PARAMIXB: Array — É passado como parâmetro um array com uma dimensão
PARAMIXB[1]: .T. = Indica que houve bloqueio por tolerância de recebimento.
PARAMIXB[1]: .F. = Indica que não houve nenhum bloqueio por tolerância de recebimento.
- **Params saida:** Lógico — .T. = bloquear o documento de entrada por Tolerância de Recebimento, sem precisar vincular o Pedido de Compra
- **TDN:** https://tdn.totvs.com/pages/releaseview.action?pageId=272704614

### GRPAPEC
- **Rotina:** MATA103
- **Onde chamado:** Grupo de aprovação para entidades contábeis
- **Objetivo:** Manipulação do grupo de aprovação para entidades contábeis
- **Params saida:** Caracter
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360000169747

### M103BROW
- **Rotina:** MATA103
- **Onde chamado:** Browse do Documento de Entrada
- **Objetivo:** Exibição e controle dos dados do Browse do Doc. de Entrada
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/x/ttpc

### M103CODR
- **Rotina:** MATA103
- **Onde chamado:** Código de retenção de imposto no Doc. Entrada
- **Objetivo:** Validação de código de retenção de imposto
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360000169747

### M103COR
- **Rotina:** MATA103
- **Onde chamado:** Cores no Browse do Doc. de Entrada
- **Objetivo:** Adiciona novas regras de cores para apresentação de status na Mbrowse
- **Params saida:** Array de cores
- **TDN:** https://tdn.totvs.com/display/public/PROT/MT103COR

### M103FILB
- **Rotina:** MATA103
- **Onde chamado:** Filtro no Browse do Doc. de Entrada
- **Objetivo:** Filtra registros da Mbrowse do Doc. de Entrada
- **Params saida:** Caracter (filtro)
- **TDN:** https://tdn.totvs.com/display/public/PROT/M103FILB

### M103GERT
- **Rotina:** MATA103
- **Onde chamado:** Lançamento futuro ou título no Doc. Entrada
- **Objetivo:** Ponto para definir se irá gerar lançamento futuro ou título
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360000169747

### MA103ATF
- **Rotina:** MATA103
- **Onde chamado:** aCols/aItens para integração com Ativo Fixo
- **Objetivo:** Manipulação do aCols e aItens enviados para Integração com Ativo Fixo
- **Params saida:** Array
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360000169747

### MA103OPC
- **Rotina:** MATA103
- **Onde chamado:** Menu do Documento de Entrada
- **Objetivo:** Adição de itens no menu da MATA103
- **Params saida:** Array de menu
- **TDN:** https://tdn.totvs.com/pages/releaseview.action?pageId=6085341

### MT103APC
- **Rotina:** MATA103
- **Onde chamado:** Importação de PC no Doc. de Entrada
- **Objetivo:** Validações da importação do Pedido de Compras
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=692931252

### MT103APV
- **Rotina:** MATA103
- **Onde chamado:** Grupo de Aprovação do Doc. de Entrada
- **Objetivo:** Ponto de entrada para alterar o Grupo de Aprovação
- **Params saida:** Caracter
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=305038698

### MT103BPC
- **Rotina:** MATA103
- **Onde chamado:** Importação de PC por item
- **Objetivo:** Validações da importação do Pedido de Compras por item
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/x/y9xc

### MT103BXCR
- **Rotina:** MATA103
- **Onde chamado:** Compensação automática na devolução
- **Objetivo:** Define se haverá compensação automática ou não na devolução de vendas
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=583763834

### MT103CLAS
- **Rotina:** MATA103
- **Onde chamado:** Informações do item NF-e a classificar
- **Objetivo:** Ponto que permite manipular informações do item e das duplicatas da NF-e a classificar
- **Params saida:** Array
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360000169747

### MT103CPC
- **Rotina:** MATA103
- **Onde chamado:** aCols com PCs selecionados
- **Objetivo:** PE para não carregar o aCols com os pedidos de compra selecionados
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360000169747

### MT103DCF
- **Rotina:** MATA103
- **Onde chamado:** Aba DANFE no Doc. de Entrada
- **Objetivo:** Habilita botão Mais Inf. e acrescenta campos na aba DANFE
- **TDN:** https://tdn.totvs.com/x/uM2iJg

### MT103DEV
- **Rotina:** MATA103
- **Onde chamado:** Filtro para NFs de Saída na devolução
- **Objetivo:** Alterar filtro para Notas Fiscais de saída na devolução
- **Params saida:** Caracter (filtro)
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360000169747

### MT103DRF
- **Rotina:** MATA103
- **Onde chamado:** Validação de código do fornecedor no Doc. Entrada
- **Objetivo:** Ponto utilizado na validação do código do fornecedor
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/x/uM2iJg

### MT103END
- **Rotina:** MATA103
- **Onde chamado:** Criação de lotes na Produção
- **Objetivo:** Validação de linhas inseridas na tela Criação de lotes na Produção
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360000169747

### MT103FIN
- **Rotina:** MATA103
- **Onde chamado:** Folder financeiro do Doc. de Entrada
- **Objetivo:** Última validação do folder financeiro na nota de Entrada
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/x/J9tc

### MT103MNT
- **Rotina:** MATA103
- **Onde chamado:** aCols de múltiplas naturezas
- **Objetivo:** Carrega aCols de múltiplas naturezas no Doc. de Entrada
- **Params saida:** Array aCols
- **TDN:** https://tdn.totvs.com/x/-9tc

### MT103MSG
- **Rotina:** MATA103
- **Onde chamado:** Mensagem de salvar informações
- **Objetivo:** Inibe a mensagem "Deseja salvar as informações inseridas até o momento?"
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/releaseview.action?pageId=270903927

### MT103NFE
- **Rotina:** MATA103
- **Onde chamado:** Rotina da NF-e no Doc. de Entrada
- **Objetivo:** Chamada de qualquer rotina da NF-e no Doc. de Entrada
- **TDN:** https://tdn.totvs.com/x/J9tc

### MT103QPC
- **Rotina:** MATA103
- **Onde chamado:** Query ao selecionar PC no Doc. de Entrada
- **Objetivo:** Manipular query ao selecionar Pedido de Compras
- **Params entrada:** Caracter (query original)
- **Params saida:** Caracter (query alterada)
- **TDN:** https://tdn.totvs.com/x/ctxc

### MT103TXPC
- **Rotina:** MATA103
- **Onde chamado:** Moeda e taxa ao importar PC
- **Objetivo:** Alteração de moeda/taxa e check box conforme Pedido de Compras
- **TDN:** https://tdn.totvs.com/x/kolmBg

### MT103VPC
- **Rotina:** MATA103
- **Onde chamado:** Filtro na importação do PC
- **Objetivo:** Executa filtro na importação do pedido de compras
- **Params saida:** Caracter (filtro)
- **TDN:** https://tdn.totvs.com/x/N9tc

### MTA103OK
- **Rotina:** MATA103
- **Onde chamado:** TudoOk do Doc. de Entrada
- **Objetivo:** Altera o resultado da validação padrão para inclusão e alteração
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/x/buRc

### MTIPCBUT
- **Rotina:** MATA103
- **Onde chamado:** Toolbar de importação de PCs
- **Objetivo:** Adicionar botões do usuário na toolbar de importação de Pedidos
- **Params saida:** Array de botões
- **TDN:** https://tdn.totvs.com/x/1Ntc

### ITMT110
- **Rotina:** MATA110
- **Onde chamado:** Campos customizados na SC1
- **Objetivo:** Ponto para incluir campos customizados na SC1
- **Params saida:** Array de campos
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360000169747

### M110EXIT
- **Rotina:** MATA110
- **Onde chamado:** Após a exclusão da solicitação de compras
- **Objetivo:** Permite executar rotinas específicas após a exclusão de uma solicitação de compras, como limpeza de dados relacionados, integração com sistemas externos ou validações adicionais
- **Params entrada:** PARAMIXB[1]: Validação do Usuario para a inclusão, alteração ou exclusão
- **Params saida:** lRet: logico — lRet = .F. impede a saida da dialog
lRet = .T. valida a saida da Dialog
- **TDN:** https://tdn.totvs.com/pages/releaseview.action?pageId=6085310

### M110STTS
- **Rotina:** MATA110
- **Onde chamado:** Após a gravação da solicitação de compras, permitindo alterar o status dos itens
- **Objetivo:** Permite customizar o status dos itens da solicitação de compras após a gravação, possibilitando definir status específicos conforme regras de negócio da empresa
- **Params entrada:** PARAMIXB[1]: Caractere — Numero da Solicitação
PARAMIXB[3]: Lógico — Se a Solicitação de Compra é originada de uma cópia (tipo: LÓGICO)
PARAMIXB[4]: Lógico — Elemento não usado
- **Params saida:** Verificar na documentação TDN - conteúdo da página não foi fornecido
- **TDN:** https://tdn.totvs.com/pages/releaseview.action?pageId=6085312

### MT110ROT
- **Rotina:** MATA110
- **Onde chamado:** Opções no menu da Solicitação de Compras
- **Objetivo:** Adiciona mais opções no menu da SC
- **Params saida:** Array de menu
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360028916371

### M116ACOL
- **Rotina:** MATA116
- **Onde chamado:** Conhecimento de Frete
- **Objetivo:** Manipulacao no Conhecimento de Frete

### A103VSG1
- **Rotina:** MATA120
- **Onde chamado:** Durante a validação dos dados do cabeçalho do Pedido de Compras, antes da gravação do pedido.
- **Objetivo:** Permite customizar e validar informações do cabeçalho do Pedido de Compras antes de sua gravação.
- **Params entrada:** Nenhum parâmetro de entrada formal; utiliza variáveis públicas do ambiente, como MV_PAR01, MV_PAR02, etc., e campos do cabeçalho do pedido (SC1).
- **Params saida:** Retorno lógico (.T. ou .F.) indicando se a validação foi bem-sucedida (.T.) ou não (.F.).
- **TDN:** https://tdn.totvs.com/pages/releaseview.action?pageId=6085262

### AVALCOPC
- **Rotina:** MATA120
- **Onde chamado:** Manipulação do Pedido de Compras
- **Objetivo:** Manipula o Pedido de Compras
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360000169747

### ITMT120
- **Rotina:** MATA120
- **Onde chamado:** Campos customizados na SC7
- **Objetivo:** Ponto que permite adicionar campos customizados na SC7 via Integração
- **Params saida:** Array de campos
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360000169747

### MT120LOK
- **Rotina:** MATA120
- **Onde chamado:** Durante a validação de linha do pedido de compras, antes de posicionar na próxima linha
- **Objetivo:** Permite validações customizadas na linha do pedido de compras durante a digitação/alteração, podendo bloquear a confirmação da linha
- **Params entrada:** Verificar na documentacao TDN
- **Params saida:** Logical — .T. permite confirmar a linha, .F. bloqueia a confirmação da linha

### MT120RCC
- **Rotina:** MATA120
- **Onde chamado:** aCols do rateio no PC
- **Objetivo:** Ponto que permite manipular o aCols do Rateio no PC
- **Params saida:** Array aCols
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360000169747

### A120F4CP
- **Rotina:** MATA120/MATA121/MATA122
- **Onde chamado:** Substituição de Função de Carga no PC
- **Objetivo:** Substituição de Função de Carga no Pedido de Compras
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360006480572

### MT120ABU
- **Rotina:** MATA120/MATA121/MATA122
- **Onde chamado:** Exclusão/alteração de botões no PC
- **Objetivo:** Exclusão e/ou alteração de botões dentro da rotina Pedido de Compra
- **Params saida:** Array de botões
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360006480572

### MT120C1C
- **Rotina:** MATA120/MATA121/MATA122
- **Onde chamado:** Títulos das colunas do PC
- **Objetivo:** Acrescenta os títulos das colunas acrescidas ao PC
- **Params saida:** Array de títulos
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360006480572

### MT120C1D
- **Rotina:** MATA120/MATA121/MATA122
- **Onde chamado:** Elementos no array dos dados do PC
- **Objetivo:** Acrescenta elementos no array dos dados do PC
- **Params saida:** Array
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360006480572

### MT120COR
- **Rotina:** MATA120/MATA121/MATA122
- **Onde chamado:** Cores do status do PC
- **Objetivo:** Manipula regras de cores de status na mBrowse do PC
- **Params saida:** Array de cores
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360006480572

### MT120F
- **Rotina:** MATA120/MATA121/MATA122
- **Onde chamado:** Dados do PC na tabela SC7
- **Objetivo:** Manipula os dados no pedido de Compras na tabela SC7
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360006480572

### MT120FIL
- **Rotina:** MATA120/MATA121/MATA122
- **Onde chamado:** Filtro do PC
- **Objetivo:** Filtrar Pedido de compras e Autorização de entrega no browse
- **Params saida:** Caracter (filtro)
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360006480572

### MT120FIX
- **Rotina:** MATA120/MATA121/MATA122
- **Onde chamado:** Ordem dos campos aFixe no PC
- **Objetivo:** Manipula a ordem dos campos do aFixe no Pedido de Compras
- **Params saida:** Array de campos
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360006480572

### MT120QRY
- **Rotina:** MATA120/MATA121/MATA122
- **Onde chamado:** Filtra pedidos por quantidade
- **Objetivo:** Filtra pedidos de quantidade para exibição
- **Params saida:** Caracter (query)
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360006480572

### MT120SCR
- **Rotina:** MATA120/MATA121/MATA122
- **Onde chamado:** Objeto Dialog do PC
- **Objetivo:** Disponibiliza como parâmetro o Objeto da dialog oDlg para manipulação
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360006480572

### MT120USR
- **Rotina:** MATA120/MATA121/MATA122
- **Onde chamado:** Restrição de PC sem SC
- **Objetivo:** Restringe a entrada de pedidos de compras sem solicitação de compra amarrada
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360006480572

### MT120VIT
- **Rotina:** MATA120/MATA121/MATA122
- **Onde chamado:** Array na seleção de compras
- **Objetivo:** Manipula o Array na rotina Seleção de Compras
- **Params saida:** Array
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360006480572

### AVALCOT
- **Rotina:** MATA130
- **Onde chamado:** Manipulação da SC7 na cotação
- **Objetivo:** Manipula Pedido de Compras da tabela SC7 na cotação
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360000169747

### MT131C8
- **Rotina:** MATA131
- **Onde chamado:** Campos SC8 no grid de fornecedores
- **Objetivo:** Exibe informações de outros campos da SC8 no grid de fornecedores da cotação
- **Params saida:** Array de campos
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360000169747

### MT131VAL
- **Rotina:** MATA131
- **Onde chamado:** Validação da cotação
- **Objetivo:** Verificar se a cotação pode ser gerada
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360000169747

### MT161CPO
- **Rotina:** MATA161
- **Onde chamado:** Campos customizados na cotação MATA161
- **Objetivo:** Ponto de entrada para incluir campos customizados no MATA161
- **Params saida:** Array de campos
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360000169747

### MT161LEG
- **Rotina:** MATA161
- **Onde chamado:** Nova legenda na cotação MATA161
- **Objetivo:** Ponto para inclusão da condição de nova legenda na cotação
- **Params entrada:** ParamIXB[1]=Array de legendas
- **Params saida:** Array de legendas
- **TDN:** https://tdn.totvs.com/pages/releaseview.action?pageId=266982442

### MT161OK
- **Rotina:** MATA161
- **Onde chamado:** TudoOk da análise de cotação
- **Objetivo:** Ponto utilizado para validar as propostas dos fornecedores
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360000169747

### MT161PRO
- **Rotina:** MATA161
- **Onde chamado:** Análise de cotação - botão analisar
- **Objetivo:** Executado no momento do clique no botão de análise de cotação
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360000169747

### MT170FIM
- **Rotina:** MATA170
- **Onde chamado:** Geração da Solicitação de Compras
- **Objetivo:** Manipula os dados ao gerar a solicitação de compras
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360000169747

### MT170QRY
- **Rotina:** MATA170
- **Onde chamado:** Solic. Ponto de Pedido
- **Objetivo:** Query na geracao de SCs

### MT170SC1
- **Rotina:** MATA170
- **Onde chamado:** Pós-gravação da SC1 na Solicitação de Compras
- **Objetivo:** Executado após a gravação da SC1
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360000169747

### A179ARMZ
- **Rotina:** MATA179
- **Onde chamado:** Filtro de armazéns na reposição
- **Objetivo:** Manipulação dos filtros de armazéns na reposição
- **Params saida:** Array de armazéns
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360000169747

### MT179CONS
- **Rotina:** MATA179
- **Onde chamado:** Consumo médio na reposição
- **Objetivo:** Recalcula previsão de consumo para o produto na filial a abastecer
- **Params saida:** Numérico
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360000169747

### MT179SAB
- **Rotina:** MATA179
- **Onde chamado:** Saldo da filial abastecida
- **Objetivo:** Ponto para tratar saldo da filial abastecida
- **Params saida:** Numérico
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360000169747

## SIGACTB

### CT010TOK
- **Rotina:** CTBA010
- **Onde chamado:** Calendario Contabil
- **Objetivo:** Validacao no Calendario Contabil

### CTA030TOK
- **Rotina:** CTBA030
- **Onde chamado:** Centro de Custo - Confirmar
- **Objetivo:** Validacao ao Confirmar Centro de Custo

### CTB102ESTL
- **Rotina:** CTBA102
- **Onde chamado:** Lancamentos Automaticos
- **Objetivo:** Validacao de lancamentos automaticos

### CT105CTK
- **Rotina:** CTBA105
- **Onde chamado:** Lancamento Contabil - tabela CTK
- **Objetivo:** Tratamento na tabela CTK

### CT105POS
- **Rotina:** CTBA105
- **Onde chamado:** Lancamento Contabil
- **Objetivo:** Valida Lancamento Contabil
- **TDN:** https://accounts.google.com/ServiceLogin?hl=pt-BR&passive=true&continue=https://www.google.com/search%3Fq%3DTOTVS%2520Protheus%2520ponto%2520de%2520entrada%2520CT105POS%2520site:tdn.totvs.com%2520OR%2520site:centraldeatendimento.totvs.com%26sei%3DjOO-adyLPPDP1sQP5saFmQg&ec=futura_srp_og_si_72236_p

### CTB500USU
- **Rotina:** CTBA500
- **Onde chamado:** Contabilizacao TXT
- **Objetivo:** Validacao na Contabilizacao TXT

## SIGAEST

### A010TOK
- **Rotina:** MATA010
- **Onde chamado:** TudoOk do Cadastro de Produtos
- **Objetivo:** Validação para inclusão ou alteração do Produto
- **Params saida:** Lógico (.T./.F.)
- **TDN:** http://tdn-homolog.totvs.com/display/public/PROT/Pontos+de+Entrada+-+Estoque+e+Custos+-+P12

### MA035ALT
- **Rotina:** MATA035
- **Onde chamado:** Após confirmação de alteração
- **Objetivo:** Permite efetuar tratamentos após confirmação da alteração
- **TDN:** http://tdn-homolog.totvs.com/display/public/PROT/Pontos+de+Entrada+-+Estoque+e+Custos+-+P12

### MTARETDC
- **Rotina:** MATA103
- **Onde chamado:** Casas decimais no Custo de Entrada
- **Objetivo:** Informa quantas casas decimais serão utilizadas no cálculo do Custo de Entrada
- **Params saida:** Numérico
- **TDN:** http://tdn-homolog.totvs.com/display/public/PROT/Pontos+de+Entrada+-+Estoque+e+Custos+-+P12

### MTA242C
- **Rotina:** MATA242
- **Onde chamado:** Produtos na desmontagem
- **Objetivo:** Preenche o array aCols com os produtos da desmontagem ou valida o código do produto
- **Params saida:** Array aCols
- **TDN:** http://tdn-homolog.totvs.com/display/public/PROT/Pontos+de+Entrada+-+Estoque+e+Custos+-+P12

### MTA242E
- **Rotina:** MATA242
- **Onde chamado:** Pós-gravação de itens estornados na desmontagem
- **Objetivo:** Executa ajustes após a gravação de cada item estornado pela rotina de desmontagem
- **TDN:** http://tdn-homolog.totvs.com/display/public/PROT/Pontos+de+Entrada+-+Estoque+e+Custos+-+P12

### MTA242Q
- **Rotina:** MATA242
- **Onde chamado:** Quantidades na desmontagem
- **Objetivo:** Preenche o array aCols com quantidades de produtos da desmontagem ou valida a quantidade
- **Params saida:** Array aCols
- **TDN:** http://tdn-homolog.totvs.com/display/public/PROT/Pontos+de+Entrada+-+Estoque+e+Custos+-+P12

### A260GRV
- **Rotina:** MATA260
- **Onde chamado:** Gravação de movimento no Estoque
- **Objetivo:** Valida movimento e atualiza valor das variáveis
- **TDN:** http://tdn-homolog.totvs.com/display/public/PROT/Pontos+de+Entrada+-+Estoque+e+Custos+-+P12

### MTVIEWFIL
- **Rotina:** MATA260
- **Onde chamado:** Filtro na consulta de saldos
- **Objetivo:** Filtra a consulta de saldos em estoque
- **Params saida:** Caracter (filtro)
- **TDN:** http://tdn-homolog.totvs.com/display/public/PROT/Pontos+de+Entrada+-+Estoque+e+Custos+-+P12

### MVIEWSALDO
- **Rotina:** MATA260
- **Onde chamado:** Valores de saldos na consulta
- **Objetivo:** Manipula valores de saldos apresentados na consulta de estoque
- **Params saida:** Array de saldos
- **TDN:** http://tdn-homolog.totvs.com/display/public/PROT/Pontos+de+Entrada+-+Estoque+e+Custos+-+P12

### A290PEES
- **Rotina:** MATA290
- **Onde chamado:** Estoque de segurança
- **Objetivo:** Permite manipular o valor do estoque de segurança
- **Params saida:** Numérico
- **TDN:** http://tdn-homolog.totvs.com/display/public/PROT/Pontos+de+Entrada+-+Estoque+e+Custos+-+P12

### CALCLELM
- **Rotina:** MATA290
- **Onde chamado:** Cálculo de necessidades compras/produção
- **Objetivo:** Calcula necessidades de compras/produção
- **TDN:** http://tdn-homolog.totvs.com/display/public/PROT/Pontos+de+Entrada+-+Estoque+e+Custos+-+P12

### MT290SD3
- **Rotina:** MATA290
- **Onde chamado:** Movimentos Internos SD3 no recálculo
- **Objetivo:** Valida os Movimentos Internos SD3 que farão parte do recálculo do consumo médio do mês
- **Params saida:** Lógico (.T./.F.)
- **TDN:** http://tdn-homolog.totvs.com/display/public/PROT/Pontos+de+Entrada+-+Estoque+e+Custos+-+P12

### MTA290FIL
- **Rotina:** MATA290
- **Onde chamado:** Filtro antes do cálculo - Lote Econômico
- **Objetivo:** Insere condição de filtro antes do cálculo do Lote Econômico
- **Params saida:** Caracter (filtro)
- **TDN:** http://tdn-homolog.totvs.com/display/public/PROT/Pontos+de+Entrada+-+Estoque+e+Custos+-+P12

### M310CABEC
- **Rotina:** MATA310
- **Onde chamado:** Transf. Filiais - cabecalho
- **Objetivo:** Tratamento no cabecalho

### M310ITENS
- **Rotina:** MATA310
- **Onde chamado:** Transf. Filiais - itens
- **Objetivo:** Tratamento nos itens

### A330CDEV
- **Rotina:** MATA330
- **Onde chamado:** Contabilização de devolução de compras
- **Objetivo:** Contabilização dos movimentos de devolução de compras
- **TDN:** http://tdn-homolog.totvs.com/display/public/PROT/Pontos+de+Entrada+-+Estoque+e+Custos+-+P12

### ATUSBF
- **Rotina:** MATA330
- **Onde chamado:** Atualiza saldos por endereço
- **Objetivo:** Atualiza saldos por endereço no estoque
- **TDN:** http://tdn-homolog.totvs.com/display/public/PROT/Pontos+de+Entrada+-+Estoque+e+Custos+-+P12

### AVALBLOQ
- **Rotina:** MATA330
- **Onde chamado:** Validação de armazéns bloqueados
- **Objetivo:** Manipula validação de armazéns
- **Params saida:** Lógico (.T./.F.)
- **TDN:** http://tdn-homolog.totvs.com/display/public/PROT/Pontos+de+Entrada+-+Estoque+e+Custos+-+P12

### MTSLDSER
- **Rotina:** MATA330
- **Onde chamado:** Subtração de reservas no saldo disponível
- **Objetivo:** Indica subtração do acumulado de reservas (B2_RESERVA) no cálculo de saldo disponível
- **Params saida:** Lógico (.T./.F.)
- **TDN:** http://tdn-homolog.totvs.com/display/public/PROT/Pontos+de+Entrada+-+Estoque+e+Custos+-+P12

### A335CUSTO
- **Rotina:** MATA335
- **Onde chamado:** Ajuste do Custo de Reposição
- **Objetivo:** Ajuste do Custo de Reposição
- **Params saida:** Numérico
- **TDN:** http://tdn-homolog.totvs.com/display/public/PROT/Pontos+de+Entrada+-+Estoque+e+Custos+-+P12

### MT340ACOK
- **Rotina:** MATA340
- **Onde chamado:** Acerto de saldo no inventário
- **Objetivo:** Executar uma rotina quando não houver acerto de saldo para os produtos inventariados
- **TDN:** http://tdn-homolog.totvs.com/display/public/PROT/Pontos+de+Entrada+-+Estoque+e+Custos+-+P12

### A390ZERO
- **Rotina:** MATA390
- **Onde chamado:** Manutenção de lotes
- **Objetivo:** Manutenção de lotes no estoque
- **Params saida:** Lógico (.T./.F.)
- **TDN:** http://tdn-homolog.totvs.com/display/public/PROT/Pontos+de+Entrada+-+Estoque+e+Custos+-+P12

### MT390DTV
- **Rotina:** MATA390
- **Onde chamado:** Manutencao de Lotes
- **Objetivo:** Validacoes na data de validade

### A460AMZP
- **Rotina:** MATA460
- **Onde chamado:** Armazéns para seção Em Processo
- **Objetivo:** Define um ou mais armazéns para seção Em Processo
- **Params saida:** Array de armazéns
- **TDN:** http://tdn-homolog.totvs.com/display/public/PROT/Pontos+de+Entrada+-+Estoque+e+Custos+-+P12

### A460RLOC
- **Rotina:** MATA460
- **Onde chamado:** Intervalos de filtro de armazéns
- **Objetivo:** Adiciona intervalos de filtro de armazéns
- **Params saida:** Array de intervalos
- **TDN:** http://tdn-homolog.totvs.com/display/public/PROT/Pontos+de+Entrada+-+Estoque+e+Custos+-+P12

### MT550EAI
- **Rotina:** MATA550
- **Onde chamado:** Integração Grade de Produtos
- **Objetivo:** Permite editar JSON da integração de mensagem única do Cadastro de Grade de Produtos
- **Params saida:** Caracter (JSON)
- **TDN:** http://tdn-homolog.totvs.com/display/public/PROT/Pontos+de+Entrada+-+Estoque+e+Custos+-+P12

### MT550PG
- **Rotina:** MATA550
- **Onde chamado:** Novos produtos gravados na SB1
- **Objetivo:** Códigos dos novos produtos gravados na tabela SB1 para customizações do usuário
- **Params saida:** Array de códigos
- **TDN:** http://tdn-homolog.totvs.com/display/public/PROT/Pontos+de+Entrada+-+Estoque+e+Custos+-+P12

## SIGAFAT

### CRM980MDef
- **Rotina:** CRMA980
- **Onde chamado:** Cadastro de Clientes MVC
- **Objetivo:** PE padrao MVC do Cadastro de Clientes

### FAT050BUT
- **Rotina:** FATA050
- **Onde chamado:** Toolbar de Metas de Venda
- **Objetivo:** Inclui opções do usuário na EnchoiceBar de Metas de Venda
- **Params saida:** Array de botões
- **TDN:** https://tdn.totvs.com/x/QYRn

### FT050MNU
- **Rotina:** FATA050
- **Onde chamado:** Browse de Metas de Venda
- **Objetivo:** Antecede abertura do Browse de Metas de Venda
- **TDN:** https://tdn.totvs.com/x/RIRn

### FT050TOK
- **Rotina:** FATA050
- **Onde chamado:** Validação de Metas de Venda
- **Objetivo:** Validação do usuário na inclusão/alteração de metas
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/x/FoZn

### FT080MRN
- **Rotina:** FATA080
- **Onde chamado:** Botões em Regras de Desconto
- **Objetivo:** Adicionar novos botões à EnchoiceBar da rotina Regras de Desconto
- **Params saida:** Array de botões
- **TDN:** https://tdn.totvs.com/display/public/PROT/Pontos+de+Entrada+-+Faturamento+-+Protheus+12

### FT080RDES
- **Rotina:** FATA080
- **Onde chamado:** Substituição da rotina de regra de desconto
- **Objetivo:** Substituição da rotina de regra de desconto padrão
- **TDN:** https://tdn.totvs.com/display/public/PROT/Pontos+de+Entrada+-+Faturamento+-+Protheus+12

### FT300ABR
- **Rotina:** FATA300
- **Onde chamado:** Abertura de Proposta Comercial
- **Objetivo:** Permite ou não o prosseguimento da inclusão/alteração/exclusão/visualização
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/display/public/PROT/Pontos+de+Entrada+-+Faturamento+-+Protheus+12

### FT300CHP
- **Rotina:** FATA300
- **Onde chamado:** Fechamento de Proposta Comercial
- **Objetivo:** Ponto de Entrada para o Fechamento de Proposta Comercial
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/display/public/PROT/Pontos+de+Entrada+-+Faturamento+-+Protheus+12

### FT340BUT
- **Rotina:** FATA340
- **Onde chamado:** Botões do Banco de Conhecimento
- **Objetivo:** Criação de opções do usuário na tela de Banco de Conhecimento
- **Params saida:** Array de botões
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784104

### FT340CHG
- **Rotina:** FATA340
- **Onde chamado:** Nome do arquivo no Banco de Conhecimento
- **Objetivo:** Alteração de nome do arquivo no banco de conhecimento
- **Params saida:** Caracter
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784480

### FT340TAM
- **Rotina:** FATA340
- **Onde chamado:** Tamanho do arquivo do Banco de Conhecimento
- **Objetivo:** Controlar o Tamanho do Arquivo do Banco de Conhecimento
- **Params saida:** Numérico
- **TDN:** https://tdn.totvs.com/display/PROT/PE+FT340TAM

### MAAVCRFIN
- **Rotina:** FATXFUN
- **Onde chamado:** Query de avaliação de crédito financeiro
- **Objetivo:** Permite alterar a query padrão de avaliação de crédito financeiro do cliente
- **Params entrada:** Caracter (query original)
- **Params saida:** Caracter (query alterada)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=309397444

### MAAVCRPR
- **Rotina:** FATXFUN
- **Onde chamado:** Avaliação de crédito do cliente
- **Objetivo:** Após avaliação padrão do crédito do cliente
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/display/PROT/MAAVCRPR

### MAAVSC5
- **Rotina:** FATXFUN
- **Onde chamado:** Avaliação eventos cabeçalho do PV
- **Objetivo:** Pós-execução da rotina de avaliação dos eventos do cabeçalho do PV
- **TDN:** https://tdn.totvs.com/display/PROT/MAAVSC5

### DT_PE_MT030INT
- **Rotina:** MATA030
- **Onde chamado:** Cadastro de Clientes via integração
- **Objetivo:** Permite a alteração do cadastro de cliente para registros gerados via integração
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/7408549780631

### M030Alt
- **Rotina:** MATA030
- **Onde chamado:** Cadastro Clientes - alteracao
- **Objetivo:** Alteracao do cadastro de clientes

### M030DEL
- **Rotina:** MATA030
- **Onde chamado:** Cadastro Clientes - exclusao
- **Objetivo:** Exclusao do cadastro de clientes

### M030PALT
- **Rotina:** MATA030
- **Onde chamado:** Cadastro Clientes - pos-alteracao
- **Objetivo:** Validacao apos alteracao

### MT125TEL
- **Rotina:** MATA125
- **Onde chamado:** Contrato de Parceria
- **Objetivo:** Antes da montagem das pastas

### MT360GRV
- **Rotina:** MATA360
- **Onde chamado:** Condicao de Pagamento
- **Objetivo:** Apos atualizacao de tabelas

### A410BLCO
- **Rotina:** MATA410
- **Onde chamado:** aCols itens bonificados PV
- **Objetivo:** Alteração da linha do aCols dos itens bonificados no PV
- **Params saida:** Array aCols
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784029

### A410BONU
- **Rotina:** MATA410
- **Onde chamado:** Cálculo de bônus no PV
- **Objetivo:** Cálculo de bônus no Pedido de Vendas
- **Params saida:** Numérico
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784030

### A410BPRC
- **Rotina:** MATA410
- **Onde chamado:** Acesso à planilha de formação de preços do PV
- **Objetivo:** Acesso à planilha de formação de preços no PV
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784031

### A410BPRO
- **Rotina:** MATA410
- **Onde chamado:** Inibição do botão Estrutura de Produtos no PV
- **Objetivo:** Inibição do botão Estrutura de Produtos no PV
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784032

### A410CONS
- **Rotina:** MATA410
- **Onde chamado:** Botões na EnchoiceBar do PV
- **Objetivo:** Inclusão de botões na EnchoiceBar do Pedido de Vendas
- **Params saida:** Array de botões
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784033

### A410EXC
- **Rotina:** MATA410
- **Onde chamado:** Exclusão do Pedido de Vendas
- **Objetivo:** Executado na exclusão do Pedido de Vendas
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784034

### A410GRDW
- **Rotina:** MATA410
- **Onde chamado:** Itens de grade no PV
- **Objetivo:** Manipula a interface de grade de produtos no PV
- **Params saida:** Array de itens
- **TDN:** https://tdn.totvs.com/display/PROT/A410GRDW

### A410GVLD
- **Rotina:** MATA410
- **Onde chamado:** Validação de grade de produtos no PV
- **Objetivo:** Validação da grade de produtos no PV
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784036

### A410PLAN
- **Rotina:** MATA410
- **Onde chamado:** Planilha financeira no PV
- **Objetivo:** Acesso à Planilha Financeira no PV
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/display/PROT/A410PLAN

### A410PVCL
- **Rotina:** MATA410
- **Onde chamado:** Alteração do Vendedor no PV
- **Objetivo:** Alteração do Vendedor no Pedido de Venda
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784546

### A410TAB
- **Rotina:** MATA410
- **Onde chamado:** Tabela de preços no PV
- **Objetivo:** Tabela de preços no Pedido de Vendas
- **Params saida:** Caracter
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784037

### A410VTIP
- **Rotina:** MATA410
- **Onde chamado:** Validação condição pgto tipo 9 no PV
- **Objetivo:** Validação em PV - Condição de Pagamento Tipo 9
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784540

### GEMXGRCVND
- **Rotina:** MATA410
- **Onde chamado:** Condição de pagamento no PV
- **Objetivo:** Manutenção na condição de pagamento no pedido de venda
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784609

### GMMA410BUT
- **Rotina:** MATA410
- **Onde chamado:** Botões na Enchoice do PV
- **Objetivo:** Adição de botões na Enchoice do PV
- **Params saida:** Array de botões
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784493

### M410ABN
- **Rotina:** MATA410
- **Onde chamado:** Cancelamento de PV
- **Objetivo:** Cancelamento de pedido de venda
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/display/PROT/M410ABN

### M410ACDL
- **Rotina:** MATA410
- **Onde chamado:** Valida itens liberados no PV
- **Objetivo:** Validar itens liberados no PV
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/display/PROT/M410ACDL

### M410AGRV
- **Rotina:** MATA410
- **Onde chamado:** Gravação das alterações do PV
- **Objetivo:** Gravação das alterações no Pedido de Vendas
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784142

### M410ALDT
- **Rotina:** MATA410
- **Onde chamado:** Altera DATABASE no PV
- **Objetivo:** Altera a DATABASE no Pedido de Vendas
- **TDN:** https://tdn.totvs.com/display/PROT/M410ALDT

### M410ALOK
- **Rotina:** MATA410
- **Onde chamado:** Alteração de PV
- **Objetivo:** Executado na alteração do pedido de venda
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784143

### M410CODBAR
- **Rotina:** MATA410
- **Onde chamado:** Código de barras no PV
- **Objetivo:** Uso de rotina específica de código de barras no PV
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784144

### M410EBAR
- **Rotina:** MATA410
- **Onde chamado:** Colunas do PV para código de barras
- **Objetivo:** Preenchimento das Colunas do PV para código de barras
- **Params saida:** Array de colunas
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=58720659

### M410FLDR
- **Rotina:** MATA410
- **Onde chamado:** Folder Rentabilidade no PV
- **Objetivo:** Botão para inibir a apresentação do folder Rentabilidade
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6077187

### M410FSQL
- **Rotina:** MATA410
- **Onde chamado:** Filtro de PVs
- **Objetivo:** Filtro de pedidos de venda no browse
- **Params saida:** Caracter (filtro)
- **TDN:** https://tdn.totvs.com/display/PROT/M410FSQL

### M410GET
- **Rotina:** MATA410
- **Onde chamado:** Montagem de tela do PV
- **Objetivo:** Montagem de tela do Pedido de Vendas
- **TDN:** https://tdn.totvs.com/display/PROT/M410GET

### M410ICM
- **Rotina:** MATA410
- **Onde chamado:** ICMS no PV
- **Objetivo:** Retorno do valor de ICMS no PV
- **Params saida:** Numérico
- **TDN:** https://tdn.totvs.com/display/PROT/M410ICM

### M410INIC
- **Rotina:** MATA410
- **Onde chamado:** Validação de usuário no PV
- **Objetivo:** Validação de usuário na inicialização do PV
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784147

### M410IPI
- **Rotina:** MATA410
- **Onde chamado:** IPI no PV
- **Objetivo:** Retorno do valor de IPI no PV
- **Params saida:** Numérico
- **TDN:** https://tdn.totvs.com/display/PROT/M410IPI

### M410LIOK
- **Rotina:** MATA410
- **Onde chamado:** Validação de linha de PV
- **Objetivo:** Validação de linha no pedido de venda
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784149

### M410PCDV
- **Rotina:** MATA410
- **Onde chamado:** Pedido de Venda - grid
- **Objetivo:** Preenchimento do grid do PV

### M410PLNF
- **Rotina:** MATA410
- **Onde chamado:** Pós-cálculo de impostos da planilha financeira do PV
- **Objetivo:** Pós-cálculo dos impostos da planilha financeira
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6787794

### M410PVNF
- **Rotina:** MATA410
- **Onde chamado:** Geração de NFs a partir de PV
- **Objetivo:** Geração de notas fiscais a partir do PV
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784152

### M410REC
- **Rotina:** MATA410
- **Onde chamado:** Reprocessamento do Fluxo de Caixa no PV
- **Objetivo:** Reprocessamento do Fluxo de Caixa a partir do PV
- **TDN:** https://tdn.totvs.com/display/PROT/M410REC

### M410REMB
- **Rotina:** MATA410
- **Onde chamado:** Dados de remessa para beneficiamento no PV
- **Objetivo:** Manipular dados de remessa para beneficiamento no PV
- **TDN:** https://tdn.totvs.com/display/PROT/M410REMB

### M410SOLI
- **Rotina:** MATA410
- **Onde chamado:** ICMS Solidário no PV
- **Objetivo:** Retorno do valor de ICMS Solidário no PV
- **Params saida:** Numérico
- **TDN:** https://tdn.totvs.com/display/PROT/M410SOLI

### M410STTS
- **Rotina:** MATA410
- **Onde chamado:** Alterações gerais no PV
- **Objetivo:** Alterações diversas no Pedido de Venda
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784155

### M410TIP9
- **Rotina:** MATA410
- **Onde chamado:** Substituição de validação tipo 9 no PV
- **Objetivo:** Substituição de validação de função condição pgto tipo 9
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784156

### M410VIS
- **Rotina:** MATA410
- **Onde chamado:** Antes de visualização do PV
- **Objetivo:** Antes de visualização de pedido de venda
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784157

### M410VRES
- **Rotina:** MATA410
- **Onde chamado:** Confirmação de eliminação de resíduos no PV
- **Objetivo:** Confirmação de eliminação de resíduos no PV
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784158

### M410lDel
- **Rotina:** MATA410
- **Onde chamado:** Exclusão de itens na alteração do PV
- **Objetivo:** Validar a exclusão de itens na alteração do PV
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784565

### MA410BOM
- **Rotina:** MATA410
- **Onde chamado:** Estrutura de produtos no PV
- **Objetivo:** Inclusão de produtos na estrutura do pedido de venda
- **Params saida:** Array de produtos
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784266

### MA410COR
- **Rotina:** MATA410
- **Onde chamado:** Cores do status do PV
- **Objetivo:** Alterar cores do cadastro do status do pedido no browse
- **Params saida:** Array de cores
- **TDN:** https://tdn.totvs.com/display/PROT/MA410COR

### MA410LEG
- **Rotina:** MATA410
- **Onde chamado:** Textos da legenda do status do PV
- **Objetivo:** Alterar textos da legenda de status do pedido
- **Params saida:** Array de textos
- **TDN:** https://tdn.totvs.com/display/PROT/MA410LEG

### MA410MNU
- **Rotina:** MATA410
- **Onde chamado:** Menu do PV
- **Objetivo:** Customização do menu no browse do PV
- **Params saida:** Array de menu
- **TDN:** https://tdn.totvs.com/display/PROT/MA410MNU

### MA410PR
- **Rotina:** MATA410
- **Onde chamado:** Validação de linha com opcionais no PV
- **Objetivo:** Validação de linha que contenha opcionais no PV
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=63276419

### MA410RPV
- **Rotina:** MATA410
- **Onde chamado:** Valores e exibição no PV
- **Objetivo:** Alterar valores ou inibir demonstrações de valores no PV
- **Params saida:** Array de valores
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784271

### MA410VLD
- **Rotina:** MATA410
- **Onde chamado:** Não confirmação de inclusão/alteração do PV
- **Objetivo:** Tratamento de não confirmação de inclusão ou alteração do PV
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784272

### MRatLOk
- **Rotina:** MATA410
- **Onde chamado:** Rateio no PV
- **Objetivo:** Rateio no Pedido de Vendas
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/display/PROT/MRatLOk

### MT410ACE
- **Rotina:** MATA410
- **Onde chamado:** Verificar acessos dos usuários no PV
- **Objetivo:** Verificar acessos dos usuários no PV
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784346

### MT410ALT
- **Rotina:** MATA410
- **Onde chamado:** Alteração no PV
- **Objetivo:** Ponto de entrada de alteração no PV
- **TDN:** https://tdn.totvs.com/display/PROT/MT410ALT

### MT410BRW
- **Rotina:** MATA410
- **Onde chamado:** Browse do PV
- **Objetivo:** Ponto de entrada no browse do PV
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/display/PROT/MT410BRW

### MT410CPY
- **Rotina:** MATA410
- **Onde chamado:** aCols e variáveis da Enchoice do PV
- **Objetivo:** Alteração do aCols e de variáveis da Enchoice no PV
- **Params saida:** Array aCols
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784349

### MT410INC
- **Rotina:** MATA410
- **Onde chamado:** Inclusão do PV
- **Objetivo:** Ponto de entrada na inclusão do PV
- **TDN:** https://tdn.totvs.com/display/PROT/MT410INC

### MT410PC
- **Rotina:** MATA410
- **Onde chamado:** Condição pgto tipo 9 no PV
- **Objetivo:** Validar Condição de Pagamento Tipo 9 no PV
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784351

### MT410ROD
- **Rotina:** MATA410
- **Onde chamado:** Rodapé do PV
- **Objetivo:** Alterar valores informados no rodapé do PV
- **Params saida:** Array de valores
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784352

### MT410TOK
- **Rotina:** MATA410
- **Onde chamado:** Confirmação da operação no PV
- **Objetivo:** Validar confirmação da operação no PV
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784353

### MT410TRV
- **Rotina:** MATA410
- **Onde chamado:** Lock SA1/SA2/SB2 no PV
- **Objetivo:** Otimização do lock de registros para as tabelas SA1/SA2/SB2
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=187531533

### MTA410
- **Rotina:** MATA410
- **Onde chamado:** Validação de toda a tela do PV
- **Objetivo:** Validação de toda a tela no Pedido de Venda
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784388

### MTA410BR
- **Rotina:** MATA410
- **Onde chamado:** Código de barras para SB1 no PV
- **Objetivo:** Transformar código de barras em código do SB1 no PV
- **Params saida:** Caracter
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784389

### MTA410V
- **Rotina:** MATA410
- **Onde chamado:** Visualização do PV
- **Objetivo:** Ponto de entrada executado na visualização do PV
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784393

### PVORDGRL
- **Rotina:** MATA410
- **Onde chamado:** Preenchimento de linha de grade no PV
- **Objetivo:** Substituir preenchimento de linha de grade no PV
- **TDN:** https://tdn.totvs.com/display/PROT/PVORDGRL

### MT411EAI
- **Rotina:** MATA411
- **Onde chamado:** Arrays do PV EDI antes da gravação
- **Objetivo:** Edição dos Arrays de cabeçalho e itens antes da gravação na Integração EDI
- **Params entrada:** Array (aHeader/aItens)
- **Params saida:** Array alterado
- **TDN:** https://tdn.totvs.com/display/public/PROT/Pontos+de+Entrada+-+Faturamento+-+Protheus+12

### A415LIOK
- **Rotina:** MATA415
- **Onde chamado:** TudoOk do orçamento de venda
- **Objetivo:** Validação do processo de orçamento de venda
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784038

### A415PLAN
- **Rotina:** MATA415
- **Onde chamado:** Planilha financeira em orçamento
- **Objetivo:** Planilha Financeira na rotina de Orçamentos
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=90277467

### A415TBPR
- **Rotina:** MATA415
- **Onde chamado:** Tabela de preços em orçamento
- **Objetivo:** Tabela de preços da proposta comercial
- **Params saida:** Caracter
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784573

### M415CANC
- **Rotina:** MATA415
- **Onde chamado:** Cancelamento de orçamento
- **Objetivo:** Validação de cancelamento do orçamento
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784159

### M415COPIA
- **Rotina:** MATA415
- **Onde chamado:** Cópia de orçamento
- **Objetivo:** Cópia de orçamento de venda
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784160

### M415FSQL
- **Rotina:** MATA415
- **Onde chamado:** Filtro de orçamentos
- **Objetivo:** Filtro de orçamentos no browse
- **Params saida:** Caracter (filtro)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=143655488

### M415GRV
- **Rotina:** MATA415
- **Onde chamado:** Gravação de orçamento
- **Objetivo:** Gravação do orçamento de venda
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784161

### M415ICM
- **Rotina:** MATA415
- **Onde chamado:** ICMS na planilha financeira do orçamento
- **Objetivo:** Altera os Valores do ICMS referentes à Planilha Financeira do orçamento
- **Params saida:** Numérico
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=185729394

### M415NCPO
- **Rotina:** MATA415
- **Onde chamado:** Inibição de campos do orçamento
- **Objetivo:** Inibição dos campos do orçamento de venda
- **Params saida:** Array de campos
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=102924503

### M415SOLI
- **Rotina:** MATA415
- **Onde chamado:** ICMS Solidário no orçamento
- **Objetivo:** Retorna o valor do ICMS Solidário no orçamento
- **Params saida:** Numérico
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784578

### M415TIP9
- **Rotina:** MATA415
- **Onde chamado:** Substituição validação tipo 9 no orçamento
- **Objetivo:** Substituição de validação de função condição pgto tipo 9 no orçamento
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784162

### MA415BUT
- **Rotina:** MATA415
- **Onde chamado:** Botões no orçamento
- **Objetivo:** Adicionar botões na atualização de orçamentos de venda
- **Params saida:** Array de botões
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784273

### MA415COR
- **Rotina:** MATA415
- **Onde chamado:** Cores do status do orçamento
- **Objetivo:** Alterar cores do Browse do cadastro de status do orçamento
- **Params saida:** Array de cores
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784274

### MA415END
- **Rotina:** MATA415
- **Onde chamado:** Endereço no orçamento
- **Objetivo:** Ponto de entrada de endereço no orçamento
- **TDN:** https://tdn.totvs.com/display/PROT/MA415END

### MA415LEG
- **Rotina:** MATA415
- **Onde chamado:** Legendas do status do orçamento
- **Objetivo:** Alterar textos da legenda de status do orçamento
- **Params saida:** Array de textos
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784276

### MA415MNU
- **Rotina:** MATA415
- **Onde chamado:** Menu do orçamento
- **Objetivo:** Customização do menu no browse do orçamento
- **Params saida:** Array de menu
- **TDN:** https://tdn.totvs.com/display/PROT/MA415MNU

### MA415OPOR
- **Rotina:** MATA415
- **Onde chamado:** Orçamento x Oportunidade de Venda
- **Objetivo:** Manipula as informações do orçamento a partir da alteração da oportunidade de Venda
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=51249271

### MA415RVP
- **Rotina:** MATA415
- **Onde chamado:** Valores no orçamento
- **Objetivo:** Alterar valores ou inibir demonstração de valores no orçamento
- **Params saida:** Array de valores
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784278

### MT415AUT
- **Rotina:** MATA415
- **Onde chamado:** Autorizar baixa do orçamento
- **Objetivo:** Autorizar baixa do orçamento de venda
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784354

### MT415BRW
- **Rotina:** MATA415
- **Onde chamado:** Filtro do browse do orçamento
- **Objetivo:** Filtrar registros exibidos no browser do orçamento
- **Params saida:** Caracter (filtro)
- **TDN:** https://tdn.totvs.com/display/PROT/MT415BRW

### MT415CPY
- **Rotina:** MATA415
- **Onde chamado:** Campos adicionais ao cabeçalho do orçamento
- **Objetivo:** Acrescentar campos ao cabeçalho do orçamento
- **Params saida:** Array de campos
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784356

### MT415EFT
- **Rotina:** MATA415
- **Onde chamado:** Efetivação do orçamento
- **Objetivo:** Validar efetivação do orçamento
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784357

### A440BUT
- **Rotina:** MATA440
- **Onde chamado:** Botões na Liberação de PVs
- **Objetivo:** Criação de botões na rotina de Liberação de Pedidos de Venda
- **Params saida:** Array de botões
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784040

### A440F4AE
- **Rotina:** MATA440
- **Onde chamado:** Comunicação com autorizações na liberação de PV
- **Objetivo:** Comunicação com autorizações na liberação de PV
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784041

### A440STK
- **Rotina:** MATA440
- **Onde chamado:** Saldo na liberação de PV
- **Objetivo:** Criação de rotina de saldo na liberação de PV
- **Params saida:** Numérico
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784042

### M440ACOL
- **Rotina:** MATA440
- **Onde chamado:** aCols da liberação de PV
- **Objetivo:** Alteração do aCols na liberação de PV
- **Params saida:** Array aCols
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784508

### M440FIL
- **Rotina:** MATA440
- **Onde chamado:** Filtro browse da liberação de PV
- **Objetivo:** Filtro no Browse da liberação de pedidos de venda
- **Params saida:** Caracter (filtro)
- **TDN:** https://tdn.totvs.com/display/PROT/M440FIL

### M440SC9I
- **Rotina:** MATA440
- **Onde chamado:** Gravação de campos na liberação de PV
- **Objetivo:** Gravação de campos na liberação de PV
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784165

### M440STTS
- **Rotina:** MATA440
- **Onde chamado:** Liberação de PV
- **Objetivo:** Liberação de pedido de venda
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784166

### MA440COR
- **Rotina:** MATA440
- **Onde chamado:** Alteração de regras na liberação de PV
- **Objetivo:** Alteração de regras na liberação de PV
- **Params saida:** Array de regras
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784501

### MA440GRLT
- **Rotina:** MATA440
- **Onde chamado:** Verificação de estoque e lote/localização
- **Objetivo:** Checar estoque e otimizar lote/localização na liberação
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784285

### MA440MNU
- **Rotina:** MATA440
- **Onde chamado:** Menu de liberação de PV
- **Objetivo:** Menu de Liberação de pedido de venda
- **Params saida:** Array de menu
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784287

### MA440SC6
- **Rotina:** MATA440
- **Onde chamado:** Validação de registro SC6 na liberação
- **Objetivo:** Validação de registro SC6 na liberação de PV
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784504

### MT440AT
- **Rotina:** MATA440
- **Onde chamado:** Impedir liberação de PV
- **Objetivo:** Impedir liberação do pedido de venda
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784362

### MT440FIL
- **Rotina:** MATA440
- **Onde chamado:** Filtrar registros do C6 na liberação
- **Objetivo:** Filtrar registros do C6 na liberação de PV
- **Params saida:** Caracter (filtro)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784363

### MT440LIB
- **Rotina:** MATA440
- **Onde chamado:** Redefinir quantidade a liberar no PV
- **Objetivo:** Redefinir quantidade a ser liberada no PV
- **Params saida:** Numérico
- **TDN:** https://tdn.totvs.com/display/PROT/MT440LIB

### MT440VLD
- **Rotina:** MATA440
- **Onde chamado:** Inibir liberação automática de PV
- **Objetivo:** Inibir liberação automática de pedido de venda
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784366

### MTA440AC
- **Rotina:** MATA440
- **Onde chamado:** Campos na liberação de PV
- **Objetivo:** Inclusão de campos na liberação do pedido de venda
- **Params saida:** Array de campos
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784397

### MTA440C5
- **Rotina:** MATA440
- **Onde chamado:** Campos a alterar na liberação de PV
- **Objetivo:** Informar campos a ser alterados na liberação de PV
- **Params saida:** Array de campos
- **TDN:** https://tdn.totvs.com/display/PROT/MTA440C5

### MTA440C9
- **Rotina:** MATA440
- **Onde chamado:** Liberação no SC9
- **Objetivo:** Liberação de pedido de venda no SC9
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784399

### MTA440L
- **Rotina:** MATA440
- **Onde chamado:** Quantidade a abater no saldo do produto
- **Objetivo:** Quantidade a abater do saldo do produto na liberação
- **Params saida:** Numérico
- **TDN:** https://tdn.totvs.com/display/PROT/MTA440L

### Ma440VLD
- **Rotina:** MATA440
- **Onde chamado:** Validação na liberação de PV
- **Objetivo:** Validação na liberação do pedido de vendas
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784532

### A455SLT1
- **Rotina:** MATA455
- **Onde chamado:** Montagem de lotes 1
- **Objetivo:** Montagem de lotes na liberação de estoque
- **Params saida:** Array de lotes
- **TDN:** https://tdn.totvs.com/display/PROT/A455SLT1

### A455SLT2
- **Rotina:** MATA455
- **Onde chamado:** Montagem de lotes 2
- **Objetivo:** Montagem de lotes (segunda chamada) na liberação de estoque
- **Params saida:** Array de lotes
- **TDN:** https://tdn.totvs.com/display/PROT/A455SLT2

### A455VENC
- **Rotina:** MATA455
- **Onde chamado:** Apresentação da tela de lotes
- **Objetivo:** Manipulação da apresentação da tela de lotes na liberação de estoque
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784610

### MTA455E
- **Rotina:** MATA455
- **Onde chamado:** Validação liberação automática de estoque
- **Objetivo:** Validação da liberação automática de bloqueio de estoque
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784549

### MTA455I
- **Rotina:** MATA455
- **Onde chamado:** Liberação de estoque
- **Objetivo:** Liberação de estoque no PV
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784408

### MTA455ML
- **Rotina:** MATA455
- **Onde chamado:** Total da quantidade selecionada
- **Objetivo:** Retorna total da quantidade selecionada na liberação de estoque
- **Params saida:** Numérico
- **TDN:** https://tdn.totvs.com/display/PROT/MTA455ML

### MTA455NL
- **Rotina:** MATA455
- **Onde chamado:** Atualização de arquivos na liberação de estoque
- **Objetivo:** Atualização de arquivos na liberação de estoque
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784410

### MTA455P
- **Rotina:** MATA455
- **Onde chamado:** Valida liberação de estoque
- **Objetivo:** Valida liberação de estoque no PV
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784411

### MTA455SLD
- **Rotina:** MATA455
- **Onde chamado:** Array aSaldos com lotes/endereçamentos
- **Objetivo:** Manipular Array aSaldos com lotes/endereçamentos
- **Params saida:** Array de saldos
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784412

### MTA455VL
- **Rotina:** MATA455
- **Onde chamado:** Validação de seleção de Lotes/Endereçamento
- **Objetivo:** Valida a seleção de Lotes/Endereçamento na liberação
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784562

### MTA456I
- **Rotina:** MATA456
- **Onde chamado:** Liberação de crédito/estoque
- **Objetivo:** Controle da liberação de crédito/estoque no PV
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784413

### MTA456L
- **Rotina:** MATA456
- **Onde chamado:** Liberação de pedidos na MATA456
- **Objetivo:** Liberação de pedidos na MATA456
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784414

### MTA456MNU
- **Rotina:** MATA456
- **Onde chamado:** Habilitar/desabilitar NBrowse na MATA456
- **Objetivo:** Habilitar ou desabilitar NBrowse na MATA456
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/display/PROT/MTA456MNU

### MTA456P
- **Rotina:** MATA456
- **Onde chamado:** Processo de liberação de crédito/estoque
- **Objetivo:** Liberação de crédito/estoque - Processo
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784416

### MTA456R
- **Rotina:** MATA456
- **Onde chamado:** Rejeição na liberação de crédito/estoque
- **Objetivo:** Liberação de crédito/estoque - Rejeição
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784417

### F440COM
- **Rotina:** MATA460
- **Onde chamado:** Comissão em adiantamento no Doc. Saída
- **Objetivo:** Cálculo da comissão para títulos de adiantamento no Doc. Saída
- **Params saida:** Numérico
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/7224837938327

### CHGX5FIL
- **Rotina:** MATA460/MATA461
- **Onde chamado:** Tabela 01 exclusiva em SX5 compartilhado
- **Objetivo:** Utiliza tabela 01 exclusiva em um SX5 compartilhado no Doc. de Saída
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/7224837938327

### F040FRT
- **Rotina:** MATA460/MATA461
- **Onde chamado:** Cálculo de impostos Doc. de Saída
- **Objetivo:** Manipulação de filiais no cálculo de impostos no Doc. de Saída
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/7224837938327

### FATTRAVSA1
- **Rotina:** MATA460/MATA461
- **Onde chamado:** Lock SA1 no Doc. Saída
- **Objetivo:** Trava/Destrava os registros da tabela SA1 no processamento do Doc. Saída
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/7224837938327

### M460FIL
- **Rotina:** MATA460A
- **Onde chamado:** Doc Saida - MarkBrowse
- **Objetivo:** Filtro na selecao do Doc Saida

### A490ATU
- **Rotina:** MATA490
- **Onde chamado:** Gravação de comissões
- **Objetivo:** Gravação de informações nas comissões
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784048

### A490TDOK
- **Rotina:** MATA490
- **Onde chamado:** TudoOk das comissões
- **Objetivo:** Validação da interface das comissões
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784049

### MA490ALT
- **Rotina:** MATA490
- **Onde chamado:** Após alteração de Comissões
- **Objetivo:** Execução após a alteração de Comissões de Venda
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=58098202

### MA490CDEL
- **Rotina:** MATA490
- **Onde chamado:** Exclusão de comissões
- **Objetivo:** Valida exclusão de comissões de venda
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784503

### MT490BUT
- **Rotina:** MATA490
- **Onde chamado:** Botões de comissões
- **Objetivo:** Adicionar botões na EnchoiceBar das comissões
- **Params saida:** Array de botões
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6784383

### MS520VLD
- **Rotina:** MATA521
- **Onde chamado:** Exclusao Doc Saida
- **Objetivo:** Validacao na exclusao da nota

### OM010COR
- **Rotina:** OMSA010
- **Onde chamado:** Cores do Browse de Tabelas de Preço
- **Objetivo:** Alterar as cores do Browse do cadastro de Tabela de Preços
- **Params saida:** Array de cores
- **TDN:** https://tdn.totvs.com/x/hwESCw

### OM010DA1
- **Rotina:** OMSA010
- **Onde chamado:** Gravação de Itens DA1
- **Objetivo:** Grava Itens da Tabela de Preços na DA1
- **TDN:** https://tdn.totvs.com/x/CNBvJ

### OM010MEM
- **Rotina:** OMSA010
- **Onde chamado:** Comentários na Tabela de Preços
- **Objetivo:** Adiciona Comentários na Tabela de Preços
- **Params saida:** Caracter
- **TDN:** https://tdn.totvs.com/x/9RahJQ

### OM010MNU
- **Rotina:** OMSA010
- **Onde chamado:** Tabelas de Preco - menu
- **Objetivo:** Opcoes no menu

### OM010QRY
- **Rotina:** OMSA010
- **Onde chamado:** Tabelas de Preco - consulta
- **Objetivo:** Campos na consulta

### OM010TOK
- **Rotina:** OMSA010
- **Onde chamado:** Tabelas de Preco - validacao
- **Objetivo:** Validacao das Tabelas de Preco

### OS010BTN
- **Rotina:** OMSA010
- **Onde chamado:** Botões na Tabela de Preços
- **Objetivo:** Adiciona Botões na toolbar da Tabela de Preços
- **Params saida:** Array de botões
- **TDN:** https://tdn.totvs.com/x/tlWhJQ

### OS010END
- **Rotina:** OMSA010
- **Onde chamado:** Inclusão/Alteração de Tabela de Preço
- **Objetivo:** Inclui ou Altera dados da Tabela de Preço
- **TDN:** https://tdn.totvs.com/x/plOhJQ

### OS010EXT
- **Rotina:** OMSA010
- **Onde chamado:** Exclusão de Tabela de Preço
- **Objetivo:** Controle de Exclusão da Tabela de Preço
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/x/-1KhJQ

### OS010GRV
- **Rotina:** OMSA010
- **Onde chamado:** Gravação da Tabela de Preço
- **Objetivo:** Controle da Gravação da Tabela de Preço
- **TDN:** https://tdn.totvs.com/x/HlKhJQ

### OS010MAN
- **Rotina:** OMSA010
- **Onde chamado:** Cabeçalho da Tabela de Preço
- **Objetivo:** Manipula cabeçalho da Tabela de Preço
- **Params saida:** Array de dados
- **TDN:** https://tdn.totvs.com/x/HFGhJQ

### OS010MNP
- **Rotina:** OMSA010
- **Onde chamado:** Atualização de Produto em Tabela de Preços
- **Objetivo:** Controle da Atualização do Produto na Tabela de Preços
- **TDN:** https://tdn.totvs.com/x/wFChJQ

## SIGAFIN

### F040ALTR
- **Rotina:** FINA040
- **Onde chamado:** Contas a Receber
- **Objetivo:** Validacao de alteracao no CR

### F040BLQ
- **Rotina:** FINA040
- **Onde chamado:** Bloqueio de rotinas CR
- **Objetivo:** Bloqueio de rotinas no Contas a Receber
- **Params saida:** Lógico (.T./.F.)
- **TDN:** http://tdn.totvs.com/display/public/mp/F040BLQ

### F040DTMV
- **Rotina:** FINA040
- **Onde chamado:** Data de inclusão de título CR
- **Objetivo:** Validação da data de inclusão do título a receber
- **Params saida:** Lógico (.T./.F.)
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6071441

### F040FILB
- **Rotina:** FINA040
- **Onde chamado:** Browse Contas a Receber
- **Objetivo:** Inclusão de filtro no browse de CR
- **Params saida:** Caracter (filtro)
- **TDN:** https://tdn.totvs.com/display/PROT/TVR071_DT_Criacao_do_PE_F040FILB_Ctas_Receber

### FA040INC
- **Rotina:** FINA040
- **Onde chamado:** TudoOk inclusão CR
- **Objetivo:** Validação na inclusão do Contas a Receber
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=780767310

### FINALEG
- **Rotina:** FINA040/FINA050/FINA740/FINA750
- **Onde chamado:** Legendas das rotinas financeiras
- **Objetivo:** Manipula legendas de diversas rotinas do financeiro
- **Params saida:** Array de legendas
- **TDN:** https://tdn.totvs.com/display/PROT/FINALEG

### F050ACOL
- **Rotina:** FINA050
- **Onde chamado:** aCols de rateios CP
- **Objetivo:** Inicializa aCols na opção de rateios de Contas a Pagar
- **Params saida:** Array aCols
- **TDN:** https://tdn.totvs.com/display/PROT/F050ACOL

### F050ADPC
- **Rotina:** FINA050
- **Onde chamado:** Adiantamento de PC em CP
- **Objetivo:** Valida inclusão de título de adiantamento quando incluído do pedido de compras
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/display/PROT/F050ADPC

### F050BROW
- **Rotina:** FINA050
- **Onde chamado:** Browse CP
- **Objetivo:** Pré-valida dados no browse de CP
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/display/PROT/F050BROW

### F050CALIR
- **Rotina:** FINA050
- **Onde chamado:** Acumula IR em CP
- **Objetivo:** Acumula cálculo de IR
- **Params saida:** Numérico
- **TDN:** https://tdn.totvs.com/display/PROT/F050CALIR

### F050CHEQ
- **Rotina:** FINA050
- **Onde chamado:** Verificação de cheque PA
- **Objetivo:** Permite ao usuário verificar o cheque de PA
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/display/PROT/F050CHEQ

### F050FILB
- **Rotina:** FINA050
- **Onde chamado:** Filtro browse CP
- **Objetivo:** Permite inserir filtro direto no browse da rotina de CP
- **Params saida:** Caracter (filtro)
- **TDN:** https://tdn.totvs.com/display/PROT/TVJQD8_DT_Inclusao_do_ponto_de_entada_F050FILB

### F050HST
- **Rotina:** FINA050
- **Onde chamado:** Histórico contabilização exclusão rateada CP
- **Objetivo:** Histórico de contabilização em exclusão rateada de CP
- **Params saida:** Caracter
- **TDN:** https://tdn.totvs.com/display/PROT/F050HST

### F050NPROV
- **Rotina:** FINA050
- **Onde chamado:** Substituição de títulos provisórios CP
- **Objetivo:** Executado na rotina de substituição de títulos provisórios
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/display/PROT/F050NPROV

### F050ORI
- **Rotina:** FINA050
- **Onde chamado:** Origem na exclusão com rateio CP
- **Objetivo:** Manipula origem na exclusão de CP com rateio na emissão
- **Params saida:** Caracter
- **TDN:** https://tdn.totvs.com/display/PROT/F050ORI

### F050ROT
- **Rotina:** FINA050
- **Onde chamado:** Menu FINA050
- **Objetivo:** Inclui itens de menu na FINA050
- **Params saida:** Array de menu
- **TDN:** https://tdn.totvs.com/display/PROT/F050ROT

### F50TFINS
- **Rotina:** FINA050
- **Onde chamado:** Inclusão títulos com cálculo INSS
- **Objetivo:** Inclusão de títulos no Financeiro com configurações para cálculo de INSS
- **TDN:** https://tdn.totvs.com/display/PROT/F50TFINS

### FA050FOR
- **Rotina:** FINA050
- **Onde chamado:** Total de notas por fornecedor
- **Objetivo:** Verifica total de notas do fornecedor pela raiz do CNPJ que vencem no mesmo mês
- **Params saida:** Numérico
- **TDN:** https://tdn.totvs.com/display/PROT/FA050FOR

### FA050INC
- **Rotina:** FINA050
- **Onde chamado:** TudoOk inclusão CP
- **Objetivo:** Validação da TudoOk na inclusão do Contas a Pagar
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/display/PROT/FA050INC

### FA050RTF
- **Rotina:** FINA050
- **Onde chamado:** Filiais para retenção PCC
- **Objetivo:** Avalia filiais da empresa para verificação de valores NF com vencimento no período de retenção PCC
- **Params saida:** Array de filiais
- **TDN:** https://tdn.totvs.com/display/PROT/FA050RTF

### FA050UPD
- **Rotina:** FINA050
- **Onde chamado:** Pré-validação CRUD CP
- **Objetivo:** Pré-validação da inclusão/alteração/exclusão de CP
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/display/PROT/FA050UPD

### FIN050IR
- **Rotina:** FINA050
- **Onde chamado:** Query de IR em CP
- **Objetivo:** Incremento de Query no Cálculo de IR
- **Params entrada:** Caracter (query adicional)
- **Params saida:** Caracter
- **TDN:** https://tdn.totvs.com/display/PROT/FIN050IR

### FINCDRET
- **Rotina:** FINA050
- **Onde chamado:** Códigos de retenção únicos
- **Objetivo:** Retorna os códigos de retenção que devem ser tratados como código único de retenção
- **Params saida:** Array de códigos
- **TDN:** https://tdn.totvs.com/display/PROT/FINCDRET

### F060ACT
- **Rotina:** FINA060
- **Onde chamado:** Gravação de transferência
- **Objetivo:** Grava dados da transferência financeira
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6070904

### F060ASIT
- **Rotina:** FINA060
- **Onde chamado:** Trava de título em borderô
- **Objetivo:** Invalida a trava de título em borderô
- **Params saida:** Lógico (.T./.F.)
- **TDN:** http://tdn.totvs.com/pages/viewpage.action?pageId=90276678

### F060CHAV
- **Rotina:** FINA060
- **Onde chamado:** Chave de ordenação do borderô
- **Objetivo:** Altera chave de ordenação dos títulos no borderô
- **Params saida:** Caracter
- **TDN:** http://tdn.totvs.com/pages/viewpage.action?pageId=6071548

### F060DGV
- **Rotina:** FINA060
- **Onde chamado:** Transferência descontada para carteira
- **Objetivo:** Manipulação de valores de transferência descontada para a carteira
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=829308092

### F060HIST
- **Rotina:** FINA060
- **Onde chamado:** Histórico da transferência
- **Objetivo:** Manipulação da variável cHistorico na transferência
- **Params saida:** Caracter
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6070910

### F060ABT
- **Rotina:** FINA060/FINA061
- **Onde chamado:** Abatimentos em borderô
- **Objetivo:** Considera os abatimentos no processo de borderô/transferência
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=804035973

### F060BOR
- **Rotina:** FINA060/FINA061
- **Onde chamado:** Numeração do borderô
- **Objetivo:** Recuperação do número do borderô
- **Params saida:** Caracter (número)
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6070905

### F060BROW
- **Rotina:** FINA060/FINA061
- **Onde chamado:** Browse de Transferência/Borderô
- **Objetivo:** Revalidação de dados antes da exibição no browse
- **Params saida:** Lógico (.T./.F.)
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6070906

### F060COL
- **Rotina:** FINA060/FINA061
- **Onde chamado:** Colunas do browse de borderô
- **Objetivo:** Alteração da ordem das colunas do browse do borderô
- **Params saida:** Array de colunas
- **TDN:** http://tdn.totvs.com/display/public/mp/F060COL

### F060CORES
- **Rotina:** FINA060/FINA061
- **Onde chamado:** Cores de legendas do borderô
- **Objetivo:** Alteração de cores das Legendas na FINA060/FINA061
- **Params saida:** Array de cores
- **TDN:** http://tdn.totvs.com/display/PROT/DT_F060CORES

### F060CPBOR
- **Rotina:** FINA060/FINA061
- **Onde chamado:** Seleção de campos para borderô
- **Objetivo:** Seleciona os campos na seleção dos títulos para gerar o borderô
- **Params saida:** Array de campos
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6070907

### F060DPM
- **Rotina:** FINA060/FINA061
- **Onde chamado:** Marcação de títulos no borderô
- **Objetivo:** Marcação de títulos para inclusão no borderô
- **Params saida:** Lógico (.T./.F.)
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6070909

### F060EXIT
- **Rotina:** FINA060/FINA061
- **Onde chamado:** Exibição do número do borderô
- **Objetivo:** Mostra número de Borderô após geração
- **TDN:** http://tdn.totvs.com/pages/viewpage.action?pageId=59900691

### F060LEGEN
- **Rotina:** FINA060/FINA061
- **Onde chamado:** Legenda personalizada
- **Objetivo:** Permite criar a própria legenda na rotina de Transferências
- **Params saida:** Array de legendas
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6071637

### F060MARK
- **Rotina:** FINA060/FINA061
- **Onde chamado:** Acesso multiusuário ao borderô
- **Objetivo:** Permissão a mais de um usuário à rotina de borderô
- **Params saida:** Lógico (.T./.F.)
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6070911

### F060NDES
- **Rotina:** FINA060/FINA061
- **Onde chamado:** Campos de natureza no borderô
- **Objetivo:** Validação de campos de natureza no borderô
- **Params saida:** Lógico (.T./.F.)
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6071449

### F060OK
- **Rotina:** FINA060/FINA061
- **Onde chamado:** Confirmação da transferência/borderô
- **Objetivo:** Gravação dos dados na confirmação da transferência/borderô
- **Params saida:** Lógico (.T./.F.)
- **TDN:** http://tdn.totvs.com/display/PROT/F060OK

### F060POR2
- **Rotina:** FINA060/FINA061
- **Onde chamado:** Validação de Portador
- **Objetivo:** Validação do Portador no borderô
- **Params saida:** Lógico (.T./.F.)
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6071653

### F060PROC
- **Rotina:** FINA060/FINA061
- **Onde chamado:** Pós-confirmação de seleção para remessa
- **Objetivo:** Disponibilização de informações após a confirmação da seleção de títulos para a remessa
- **TDN:** http://tdn.totvs.com/pages/viewpage.action?pageId=201729988

### F060QRCP
- **Rotina:** FINA060/FINA061
- **Onde chamado:** Query do borderô
- **Objetivo:** Manipula Query do borderô
- **Params entrada:** Caracter (query original)
- **Params saida:** Caracter (query alterada)
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6071544

### F060SEA2
- **Rotina:** FINA060/FINA061
- **Onde chamado:** Informações adicionais SEA
- **Objetivo:** Alteração das informações adicionais na tabela SEA
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6071651

### F060TRB
- **Rotina:** FINA060/FINA061
- **Onde chamado:** Novos campos no borderô
- **Objetivo:** Inclui novos campos no borderô
- **Params saida:** Array de campos
- **TDN:** http://tdn.totvs.com/display/public/mp/F060Trb

### F060VLOK
- **Rotina:** FINA060/FINA061
- **Onde chamado:** Validação de parâmetros do borderô
- **Objetivo:** Validação de informações na tela de parâmetros do borderô após clicar em OK
- **Params saida:** Lógico (.T./.F.)
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6071468

### F060VLTOT
- **Rotina:** FINA060/FINA061
- **Onde chamado:** Valor limite do borderô
- **Objetivo:** Permite alterar o valor limite para seleção de títulos do borderô
- **Params saida:** Numérico
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=791847963

### F060SITUAC
- **Rotina:** FINA061
- **Onde chamado:** Novas situações de cobrança
- **Objetivo:** Incluir novas situações de cobranças na geração de borderôs
- **Params saida:** Array de situações
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6071493

### F070ACRE
- **Rotina:** FINA070
- **Onde chamado:** Antes da confirmação da Baixa CR
- **Objetivo:** Execução antes da confirmação da Baixa a Receber
- **Params saida:** Lógico (.T./.F.)
- **TDN:** http://tdn.totvs.com/pages/viewpage.action?pageId=110432873

### F070AltV
- **Rotina:** FINA070
- **Onde chamado:** Data da baixa CR
- **Objetivo:** Validação da data da baixa a receber
- **Params saida:** Lógico (.T./.F.)
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6070913

### F070BAUT
- **Rotina:** FINA070
- **Onde chamado:** ExecAuto baixa CR
- **Objetivo:** Valida ExecAuto de baixa a receber
- **Params saida:** Lógico (.T./.F.)
- **TDN:** http://tdn.totvs.com/display/public/mp/F070BAUT

### F070BROW
- **Rotina:** FINA070
- **Onde chamado:** Browse de baixa CR
- **Objetivo:** Pré-validação de dados na baixa de títulos a receber
- **Params saida:** Lógico (.T./.F.)
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6070914

### F070BXPC
- **Rotina:** FINA070
- **Onde chamado:** Exibição automática tela de baixas CR
- **Objetivo:** Exibição automática da tela de baixas a receber
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=1028930737

### F070BtOK
- **Rotina:** FINA070
- **Onde chamado:** Confirmação da baixa CR
- **Objetivo:** Confirmação da baixa a receber
- **Params saida:** Lógico (.T./.F.)
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6070915

### F070BxLt
- **Rotina:** FINA070
- **Onde chamado:** Validação de baixa CR
- **Objetivo:** Validação de baixa a receber
- **Params saida:** Lógico (.T./.F.)
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6071684

### F070CANCEL
- **Rotina:** FINA070
- **Onde chamado:** Cancelamento de baixas CR
- **Objetivo:** Manipula as variáveis no Cancelamento de Baixas a Receber
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=1022364179

### F070CCAN
- **Rotina:** FINA070
- **Onde chamado:** Validação do cancelamento de baixa CR
- **Objetivo:** Validações adicionais no cancelamento de Baixas a Receber ao Cancelar
- **Params saida:** Lógico (.T./.F.)
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6071588

### F070CHDV
- **Rotina:** FINA070
- **Onde chamado:** Campo de cancelamento por devolução de cheque
- **Objetivo:** Campo cancelamento por devolução de cheque irá aparecer selecionado ou não
- **Params saida:** Lógico (.T./.F.)
- **TDN:** http://tdn.totvs.com/display/public/mp/F070CHDV

### F070CLOK
- **Rotina:** FINA070
- **Onde chamado:** Validação de linhas de grade CR
- **Objetivo:** Validação de linhas de grade na baixa a receber
- **Params saida:** Lógico (.T./.F.)
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6070916

### F070CMC7
- **Rotina:** FINA070
- **Onde chamado:** Dados do cheque na baixa CR
- **Objetivo:** Validações ou alterações das informações dos dados do cheque
- **TDN:** http://tdn.totvs.com/display/PROT/DT_F070CMC7_Impressora_de_Cheque

### F070CTB
- **Rotina:** FINA070
- **Onde chamado:** Somatório de valores na baixa CR
- **Objetivo:** Somas de valores desejados com valor do Título na baixa a receber
- **Params saida:** Numérico
- **TDN:** http://tdn.totvs.com/pages/viewpage.action?pageId=113804788

### F070DCDESC
- **Rotina:** FINA070
- **Onde chamado:** Desconto no cancelamento de baixa CR
- **Objetivo:** Alteração de valor de desconto no cancelamento da baixa a receber
- **Params saida:** Numérico
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6071563

### F070DCHQ
- **Rotina:** FINA070
- **Onde chamado:** Dados adicionais do cheque
- **Objetivo:** Altera ou insere dados adicionais na inclusão do cheque
- **TDN:** http://tdn.totvs.com/display/PROT/F070DCHQ

### F070DCNB
- **Rotina:** FINA070
- **Onde chamado:** Campos juros/multa/desconto na baixa
- **Objetivo:** Desabilita campos juros/multa/desconto e outros na baixa a receber
- **Params saida:** Lógico (.T./.F.)
- **TDN:** http://tdn.totvs.com/display/public/mp/F070DCNB

### F070DESC
- **Rotina:** FINA070
- **Onde chamado:** Validação de desconto na baixa CR
- **Objetivo:** Validação de desconto informado na baixa a receber
- **Params saida:** Lógico (.T./.F.)
- **TDN:** http://tdn.totvs.com/pages/viewpage.action?pageId=6071704

### F070DSC
- **Rotina:** FINA070
- **Onde chamado:** Digitação de desconto na baixa CR
- **Objetivo:** Permite a digitação de valor de desconto na tela de baixa
- **Params saida:** Numérico
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6070920

### F070DtRe
- **Rotina:** FINA070
- **Onde chamado:** Data de recebimento na baixa CR
- **Objetivo:** Permite a digitação do campo Data Recebimento
- **Params saida:** Data
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6071326

### F070HisCan
- **Rotina:** FINA070
- **Onde chamado:** Histórico de cancelamento de baixa CR
- **Objetivo:** Alteração do Cancelamento de Baixa a Receber
- **Params saida:** Caracter
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6071607

### F070IMP2
- **Rotina:** FINA070
- **Onde chamado:** Recálculo de impostos na baixa
- **Objetivo:** Permite recalcular os impostos de retenção no momento da baixa do título
- **TDN:** https://tdn.totvs.com/display/PROT/PE+F070IMP2+-+Recalculo+de+impostos

### F070JRS
- **Rotina:** FINA070
- **Onde chamado:** Digitação de juros na baixa CR
- **Objetivo:** Digitação de valor de juros na baixa a receber
- **Params saida:** Numérico
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6070922

### F070JRVlr
- **Rotina:** FINA070
- **Onde chamado:** Alteração de valor de juros
- **Objetivo:** Alteração do valor de Juros na Baixa a Receber
- **Params saida:** Numérico
- **TDN:** http://tdn.totvs.com/pages/viewpage.action?pageId=6071608

### F070KCO
- **Rotina:** FINA070
- **Onde chamado:** Validação do código de banco
- **Objetivo:** Valida código do banco na baixa a receber
- **Params saida:** Lógico (.T./.F.)
- **TDN:** http://tdn.totvs.com/pages/viewpage.action?pageId=39125013

### F070MNAT
- **Rotina:** FINA070
- **Onde chamado:** Rateio entre múltiplas naturezas
- **Objetivo:** Rateio de título baixado entre múltiplas naturezas
- **Params saida:** Array de naturezas
- **TDN:** http://tdn.totvs.com/pages/viewpage.action?pageId=111182103

### F070MUL
- **Rotina:** FINA070
- **Onde chamado:** Digitação de multa na baixa CR
- **Objetivo:** Digitação do valor de multa na baixa de CR
- **Params saida:** Numérico
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6070923

### F070OWN
- **Rotina:** FINA070
- **Onde chamado:** Filtro da baixa CR
- **Objetivo:** Montagem do filtro da baixa a receber
- **Params saida:** Caracter (expressão)
- **TDN:** http://tdn.totvs.com/display/public/mp/F070OWN

### F070TPBA
- **Rotina:** FINA070
- **Onde chamado:** Campo Mov. Bancário
- **Objetivo:** Validação do Campo Mov. Bancário (ED_MOVBCO) na baixa
- **Params saida:** Lógico (.T./.F.)
- **TDN:** http://tdn.totvs.com/display/PROT/F070TPBA

### F070TREA
- **Rotina:** FINA070
- **Onde chamado:** Tag de processo mensagem única
- **Objetivo:** Envio de valor personalizado na tag de processo da mensagem única UpdateContractParcel
- **Params saida:** Caracter
- **TDN:** http://tdn.totvs.com/pages/viewpage.action?pageId=381046561

### F070TXPER
- **Rotina:** FINA070
- **Onde chamado:** Taxa de permanência
- **Objetivo:** Altera ou valida taxa de permanência na baixa
- **Params saida:** Numérico
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6071603

### F070VDATA
- **Rotina:** FINA070
- **Onde chamado:** Validação geral de dados da baixa CR
- **Objetivo:** Validar os dados da baixa dos campos: Taxa contratada/Desconto/Multa/Juros
- **Params saida:** Lógico (.T./.F.)
- **TDN:** http://tdn.totvs.com/display/public/mp/F070VDATA

### F70GRSE1
- **Rotina:** FINA070
- **Onde chamado:** Pós-baixa CR completa
- **Objetivo:** Operações após todo o processo de baixa (gravar dados adicionais/eventos)
- **Params entrada:** ParamIXB[1]=Caracter (código ocorrência CNAB)
- **TDN:** https://tdn.totvs.com/display/public/PROT/Pontos+de+Entrada+-+Financeiro+-+P12

### F080BENEF
- **Rotina:** FINA080
- **Onde chamado:** Campo Beneficiário na baixa CP
- **Objetivo:** Manipular o campo Beneficiário na baixa de CP
- **Params saida:** Caracter
- **TDN:** http://tdn.totvs.com/display/PROT/TUPQD3_DT_PE_F080BENEF

### F080BROW
- **Rotina:** FINA080
- **Onde chamado:** Browse de Baixa CP
- **Objetivo:** Pré-avaliação de dados no browse de baixa de CP
- **Params saida:** Lógico (.T./.F.)
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6070927

### F080BXLOTE
- **Rotina:** FINA080
- **Onde chamado:** Lote da baixa CP
- **Objetivo:** Manipular a variável cLoteFin na baixa por lote de CP
- **Params saida:** Caracter
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6071475

### F080BXLT
- **Rotina:** FINA080
- **Onde chamado:** Baixa por lote CP
- **Objetivo:** Controle de baixa por lote de CP
- **Params saida:** Lógico (.T./.F.)
- **TDN:** http://tdn.totvs.com/display/public/mp/F080BXLT

### F080BXVEND
- **Rotina:** FINA080
- **Onde chamado:** Variáveis na baixa CP
- **Objetivo:** Manipula variáveis no processo de baixa de CP
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6071466

### F080BXVL
- **Rotina:** FINA080
- **Onde chamado:** Auto-validação na baixa CP
- **Objetivo:** Mecanismos de Auto-Validação na baixa de CP
- **Params saida:** Lógico (.T./.F.)
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6071364

### FA080DT
- **Rotina:** FINA080
- **Onde chamado:** Data da baixa CP
- **Objetivo:** Validação da data da baixa no contas a pagar
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/display/public/mp/FA080DT

### FA080POS
- **Rotina:** FINA080
- **Onde chamado:** Pós-baixa CP
- **Objetivo:** Altera variáveis de memória após baixa de CP
- **TDN:** https://tdn.totvs.com/display/PROT/FA080POS

### FA080VEST
- **Rotina:** FINA080
- **Onde chamado:** Validação de estorno CP
- **Objetivo:** Validação de estorno na FINA080
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=273977943

### FIN080PCC
- **Rotina:** FINA080
- **Onde chamado:** Query de PCC na baixa CP
- **Objetivo:** Incremento de query no cálculo de PCC
- **Params entrada:** Caracter (query adicional)
- **Params saida:** Caracter
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=63277108

### A085ABRW
- **Rotina:** FINA085A
- **Onde chamado:** Browse de Ordens de Pagamento
- **Objetivo:** Filtro do browse de Ordens de Pagamento
- **Params saida:** Caracter (filtro)
- **TDN:** https://tdn.totvs.com/pages/releaseview.action?pageId=126190759

### A085AFIM
- **Rotina:** FINA085A
- **Onde chamado:** Gravação de Ordem de Pagamento
- **Objetivo:** Gravação de dados adicionais após gravar OP
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=45220094

### A085AFM2
- **Rotina:** FINA085A
- **Onde chamado:** Visualização de Ordem de Pagamento
- **Objetivo:** Visualiza registros da Ordem de Pagamento
- **TDN:** https://tdn.totvs.com/pages/releaseview.action?pageId=6071596

### A085AFOP
- **Rotina:** FINA085A
- **Onde chamado:** Gravação de cada OP individualmente
- **Objetivo:** Gravação de dados adicionais após a gravação de cada OP
- **TDN:** https://tdn.totvs.com/pages/releaseview.action?pageId=185749610

### A085ALNA
- **Rotina:** FINA085A
- **Onde chamado:** Campo Natureza em OP
- **Objetivo:** Inibe o campo natureza na FINA085A
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/releaseview.action?pageId=135495972

### A085BTN
- **Rotina:** FINA085A
- **Onde chamado:** Toolbar de Ordens de Pagamento
- **Objetivo:** Adição de botões na visualização de OPs
- **Params saida:** Array de botões
- **TDN:** https://tdn.totvs.com/pages/releaseview.action?pageId=6071359

### A087NATVAZ
- **Rotina:** FINA087A
- **Onde chamado:** Geração de recibos sem Natureza
- **Objetivo:** Permite a geração de recibos sem código da Natureza
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/releaseview.action?pageId=54427859

### A087TIPTI
- **Rotina:** FINA087A
- **Onde chamado:** Tipos de títulos em recibos
- **Objetivo:** Alteração dos tipos de títulos
- **Params saida:** Array de tipos
- **TDN:** https://tdn.totvs.com/pages/releaseview.action?pageId=42042575

### A087TUDOK
- **Rotina:** FINA087A
- **Onde chamado:** TudoOk painel de recebimentos diversos
- **Objetivo:** Valida o painel dos recebimentos diversos
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/releaseview.action?pageId=165282518

### A089CAMP
- **Rotina:** FINA089
- **Onde chamado:** Liquidação de cheques
- **Objetivo:** Gravação de informações adicionais na liquidação de cheques
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=47907767

### A089CONDS
- **Rotina:** FINA089
- **Onde chamado:** Filtro de liquidação de cheques
- **Objetivo:** Expressões adicionais de filtro na rotina de liquidação de cheques
- **Params saida:** Caracter (expressão filtro)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=47907941

### 200GEMBX
- **Rotina:** FINA200
- **Onde chamado:** Baixa bancária CNAB
- **Objetivo:** Tratar valores dos títulos na baixa bancária CNAB
- **Params saida:** Array de valores
- **TDN:** http://tdn.totvs.com/display/public/mp/200GEMBX

### F060SEA
- **Rotina:** FINA200/FINA060
- **Onde chamado:** Dados do borderô na tabela SEA
- **Objetivo:** Gravação de dados do borderô (SEA) na transferência
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=465391018

### F240FIL
- **Rotina:** FINA240
- **Onde chamado:** Bordero de Pagamentos
- **Objetivo:** Filtro apos tela de dados do bordero

### F240MARK
- **Rotina:** FINA240
- **Onde chamado:** Bordero - MarkBrowse
- **Objetivo:** Alteracao de campos no MarkBrowse

### F241MARK
- **Rotina:** FINA241
- **Onde chamado:** Bordero - MarkBrowse
- **Objetivo:** Customizacao de posicoes e labels

### F260BUT
- **Rotina:** FINA260
- **Onde chamado:** Conciliacao DDA
- **Objetivo:** Inclusao de botoes no menu

### F290BAIXA
- **Rotina:** FINA290
- **Onde chamado:** Histórico de contabilização de fatura
- **Objetivo:** Adiciona informações no histórico de contabilização via STRLCTPAD
- **Params saida:** Caracter
- **TDN:** https://tdn.totvs.com/display/PROT/F290BAIXA

### F290BFIL
- **Rotina:** FINA290
- **Onde chamado:** Filtro de Faturas a Pagar
- **Objetivo:** Adiciona filtros na tela de Faturas a Pagar
- **Params saida:** Caracter (filtro)
- **TDN:** https://tdn.totvs.com/display/PROT/F290BFIL

### F290CHK
- **Rotina:** FINA290
- **Onde chamado:** Filtro de seleção de títulos para fatura
- **Objetivo:** Substitui filtro padrão para seleção de títulos
- **Params saida:** Caracter (filtro)
- **TDN:** https://tdn.totvs.com/display/PROT/F290CHK

### F290FIL
- **Rotina:** FINA290
- **Onde chamado:** Filtro de Faturas a Pagar adicional
- **Objetivo:** Adiciona filtros na rotina de Faturas a Pagar FINA290
- **Params saida:** Caracter (filtro)
- **TDN:** https://tdn.totvs.com/display/PROT/F290FIL

### FA420NAR
- **Rotina:** FINA420
- **Onde chamado:** Arquivo de Pagamentos
- **Objetivo:** Alterar nome do arquivo de saida

### F450BROW
- **Rotina:** FINA450
- **Onde chamado:** Browse de compensação entre carteiras
- **Objetivo:** Manipula campos e define quais compõem o browser na compensação entre carteiras
- **Params saida:** Array de campos
- **TDN:** https://tdn.totvs.com/pages/releaseview.action?pageId=528453462

### F450CAES
- **Rotina:** FINA450
- **Onde chamado:** Cancelamento/Estorno de compensação
- **Objetivo:** Valida ou executa procedimento após confirmação de Cancelamento/Estorno
- **TDN:** https://tdn.totvs.com/display/public/mp/F450CAES

### F450Conf
- **Rotina:** FINA450
- **Onde chamado:** Marcação de título para compensação
- **Objetivo:** Valida a marcação do título para compensação
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6071061

### F450FIL
- **Rotina:** FINA450
- **Onde chamado:** Filtro IndRegua em compensação
- **Objetivo:** Customização do filtro da IndRegua em ambientes TopConnect
- **Params saida:** Caracter (filtro)
- **TDN:** https://tdn.totvs.com/display/public/PROT/FIN0106_CPAG_FINA450_PONTOS+DE+ENTRADA

### F450GRAVA
- **Rotina:** FINA450
- **Onde chamado:** Dados temporários TRB na compensação
- **Objetivo:** Manipula dados temporários da tabela TRB na compensação
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=653141268

### F450ORDEM
- **Rotina:** FINA450
- **Onde chamado:** Ordenação de títulos na compensação
- **Objetivo:** Permite a alteração da ordem dos títulos apresentados para seleção
- **Params saida:** Caracter (chave de ordem)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6071392

### F450OWN1
- **Rotina:** FINA450
- **Onde chamado:** Filtro da tabela SE2 na compensação
- **Objetivo:** Monta a expressão de filtro adicional para SE2
- **Params saida:** Caracter (expressão)
- **TDN:** https://tdn.totvs.com/display/PROT/F450OWN1

### F450SE1C
- **Rotina:** FINA450
- **Onde chamado:** Dados complementares na compensação SE1
- **Objetivo:** Grava dados complementares na SE1
- **TDN:** https://tdn.totvs.com/display/public/mp/F450SE1C

### F450SE2C
- **Rotina:** FINA450
- **Onde chamado:** Dados complementares na compensação SE2
- **Objetivo:** Grava dados complementares na SE2
- **TDN:** https://tdn.totvs.com/display/public/mp/F450SE2C

### F450SE5
- **Rotina:** FINA450
- **Onde chamado:** Pós-compensação de todos os títulos
- **Objetivo:** Executado após a compensação de todos os títulos selecionados
- **TDN:** https://tdn.totvs.com/pages/releaseview.action?pageId=6071066

### F450ValCon
- **Rotina:** FINA450
- **Onde chamado:** Validação pós-seleção de títulos
- **Objetivo:** Validação após a seleção de títulos na compensação
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/releaseview.action?pageId=6071685

### F450valid
- **Rotina:** FINA450
- **Onde chamado:** Validação na tela de compensação
- **Objetivo:** Validação de informações da tela de compensação entre carteiras
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=6071689

### FA450BU
- **Rotina:** FINA450
- **Onde chamado:** Botão em compensação entre carteiras
- **Objetivo:** Criação de botão personalizado na FINA450
- **Params saida:** Array de botões
- **TDN:** https://tdn.totvs.com/pages/releaseview.action?pageId=6071571

### FA450BUT
- **Rotina:** FINA450
- **Onde chamado:** Barra de ferramentas FINA450
- **Objetivo:** Inclusão de opções na barra de ferramentas da FINA450
- **Params saida:** Array de opções
- **TDN:** https://tdn.totvs.com/pages/releaseview.action?pageId=6071229

### FILEMOT
- **Rotina:** FINA450
- **Onde chamado:** Arquivo de motivos de baixa CR
- **Objetivo:** PE utilizado para leitura do arquivo de texto de motivos de baixa de CR
- **Params saida:** Caracter
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360050384814

### A460COL
- **Rotina:** FINA460
- **Onde chamado:** Getdados de liquidação CR
- **Objetivo:** Acrescenta colunas na getdados da liquidação
- **Params saida:** Array de colunas
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6070842

### A460PARC
- **Rotina:** FINA460
- **Onde chamado:** Liquidação a receber - leitora CMC7
- **Objetivo:** Tratamento de leitora CMC7 na liquidação
- **TDN:** https://tdn.totvs.com/display/public/PROT/A460PARC

### F460BROW
- **Rotina:** FINA460
- **Onde chamado:** Browse de Liquidação a Receber
- **Objetivo:** Pré-validação de dados no browse de liquidação a receber
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360018386511

### F070TRAVA
- **Rotina:** FINA460/FINA070
- **Onde chamado:** Lock SA1 na liquidação CR
- **Objetivo:** Trava ou destrava registros da tabela SA1 na liquidação a receber
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360018386511

### A565COL
- **Rotina:** FINA565
- **Onde chamado:** Baixa CNAB a pagar
- **Objetivo:** Alteração do posicionamento antes do incremento ao array Aaltera
- **Params saida:** Array
- **TDN:** https://tdn.totvs.com/display/PROT/TUHG27_DT_correcao_ponto_de_entrada_A565COL

### A565TXL
- **Rotina:** FINA565
- **Onde chamado:** Liquidação com moeda estrangeira
- **Objetivo:** Informa a taxa contratada de moeda estrangeira para os títulos gerados
- **Params saida:** Numérico (taxa)
- **TDN:** https://tdn.totvs.com/pages/releaseview.action?pageId=607878335

### FA740BRW
- **Rotina:** FINA740
- **Onde chamado:** Funcoes CR - mBrowse
- **Objetivo:** Itens no menu do CR

### FA750BRW
- **Rotina:** FINA750
- **Onde chamado:** Funcoes CP - mBrowse
- **Objetivo:** Itens no menu do CP

### A850PAOK
- **Rotina:** FINA850
- **Onde chamado:** Pagamento antecipado - OP modelo II
- **Objetivo:** Validação do pagamento antecipado na ordem de pagamento modelo II
- **Params saida:** Lógico (.T./.F.)
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=184779783

### F010CQFT
- **Rotina:** FINC010
- **Onde chamado:** Query de faturamento na posição do cliente
- **Objetivo:** Alteração da query de consulta do faturamento
- **Params entrada:** Caracter (query original)
- **Params saida:** Caracter (query alterada)
- **TDN:** https://tdn.totvs.com/display/PROT/F010CQFT

### F010CQPE
- **Rotina:** FINC010
- **Onde chamado:** Query de pedidos na posição do cliente
- **Objetivo:** Permite a alteração da Query na consulta de Pedidos
- **Params entrada:** Caracter (query original)
- **Params saida:** Caracter (query alterada)
- **TDN:** https://tdn.totvs.com/display/PROT/F010CQPE

### F010CQTA
- **Rotina:** FINC010
- **Onde chamado:** Query de títulos em aberto
- **Objetivo:** Alteração da query de títulos em aberto na posição do cliente
- **Params entrada:** Caracter (query original)
- **Params saida:** Caracter (query alterada)
- **TDN:** https://tdn.totvs.com/display/PROT/F010CQTA

### F010CQTR
- **Rotina:** FINC010
- **Onde chamado:** Query de títulos recebidos
- **Objetivo:** Alteração da query de títulos recebidos na posição do cliente
- **Params entrada:** Caracter (query original)
- **Params saida:** Caracter (query alterada)
- **TDN:** https://tdn.totvs.com/display/PROT/F010CQTR

### F010ORD1
- **Rotina:** FINC010
- **Onde chamado:** Ordenação de registros na posição do cliente
- **Objetivo:** Muda a ordenação dos registros que são apresentados na consulta
- **Params saida:** Caracter (chave de ordem)
- **TDN:** http://tdn.totvs.com/pages/viewpage.action?pageId=113805450

### FC0103FAT
- **Rotina:** FINC010
- **Onde chamado:** Colunas adicionais na consulta posição cliente
- **Objetivo:** Inclusão de colunas adicionais na aba Faturamento da consulta posição
- **Params saida:** Array de colunas
- **TDN:** https://tdn.totvs.com/display/PROT/FC0103FAT

### FC010BOL
- **Rotina:** FINC010
- **Onde chamado:** Personaliza tela de títulos em aberto/recebidos
- **Objetivo:** Personaliza a tela de Títulos em Aberto e/ou Títulos Recebidos
- **TDN:** https://tdn.totvs.com/display/PROT/FC010BOL

### FC010BTN
- **Rotina:** FINC010
- **Onde chamado:** Posicao do Cliente
- **Objetivo:** Botoes customizados na consulta

### FC010CON
- **Rotina:** FINC010
- **Onde chamado:** Consulta específica na posição do cliente
- **Objetivo:** Efetua consulta específica via opção Cons.Especif
- **TDN:** https://tdn.totvs.com/display/PROT/FC010CON

### FC010FIL
- **Rotina:** FINC010
- **Onde chamado:** Filtro inicial na consulta posição de clientes
- **Objetivo:** Implementa filtro inicial na consulta de posição de clientes
- **Params saida:** Caracter (filtro)
- **TDN:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/9189321033879

### FC010HEAD
- **Rotina:** FINC010
- **Onde chamado:** Posicao do Cliente - Abrir Titulo
- **Objetivo:** Colunas apos Abrir Titulo

### FC010LIST
- **Rotina:** FINC010
- **Onde chamado:** Linhas na listbox da consulta posição
- **Objetivo:** Inclui novas linhas na listbox da consulta posição de clientes
- **Params saida:** Array de linhas
- **TDN:** https://tdn.totvs.com/display/PROT/FC010LIST

### FC010PEDI
- **Rotina:** FINC010
- **Onde chamado:** Coluna de pedidos na posição do cliente
- **Objetivo:** Inclui nova coluna após clicar no botão Pedido
- **Params saida:** Array de colunas
- **TDN:** https://tdn.totvs.com/display/PROT/FC010PEDI

### FC010bxHe
- **Rotina:** FINC010
- **Onde chamado:** Posicao do Cliente - titulos
- **Objetivo:** Alterar query de titulos recebidos

### F040GRCOM
- **Rotina:** FINXBX
- **Onde chamado:** Gravação de baixa CR
- **Objetivo:** Gravação de dados complementares na baixa a receber
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6071626

### F070DISS
- **Rotina:** FINXBX
- **Onde chamado:** Função fa070Grv
- **Objetivo:** Chamado na função fa070Grv após a baixa
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6070919

### F070GERAB
- **Rotina:** FINXBX
- **Onde chamado:** Baixa com abatimento
- **Objetivo:** Baixa de título com abatimento
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6071682

### F070GRVHIS
- **Rotina:** FINXBX
- **Onde chamado:** Histórico complementar na baixa IR
- **Objetivo:** Permite a gravação de histórico complementar na operação de baixa de IR
- **Params saida:** Caracter
- **TDN:** https://tdn.totvs.com/display/PROT/MSERV-8607+DT+ponto+de+entrada+F070GRVHIS

### F070HIST
- **Rotina:** FINXBX
- **Onde chamado:** Histórico no título RA
- **Objetivo:** Tratamento do Histórico no título de RA
- **Params saida:** Caracter
- **TDN:** http://tdn.totvs.com/pages/viewpage.action?pageId=28574988

### F070MV1
- **Rotina:** FINXBX
- **Onde chamado:** Contabilização de baixa CR com Acréscimo/Decréscimo
- **Objetivo:** Alteração da contabilização de Baixa a Receber com Acréscimo/Decréscimo
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6071609

### ATUDPPAG
- **Rotina:** FINXFIN
- **Onde chamado:** Atualização SE2
- **Objetivo:** Atualização no SE2 após baixa
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6784051

### F040ADLE
- **Rotina:** FINXFIN
- **Onde chamado:** Legendas do FINA040
- **Objetivo:** Adicionar legenda em FINA040
- **Params saida:** Array de legendas
- **TDN:** https://tdn.totvs.com/x/Zz4bIg

### F040BUT
- **Rotina:** FINXFIN
- **Onde chamado:** Toolbar Contas a Receber
- **Objetivo:** Adição de botões na toolbar de CR
- **Params saida:** Array de botões
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6070863

### F040COF
- **Rotina:** FINXFIN
- **Onde chamado:** Geração de título COFINS
- **Objetivo:** Geração de título de COFINS a partir de CR
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6784056

### F040CSL
- **Rotina:** FINXFIN
- **Onde chamado:** Geração de título CSLL
- **Objetivo:** Geração de título de CSLL a partir de CR
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6784057

### F040GER
- **Rotina:** FINXFIN
- **Onde chamado:** Gravação de CR
- **Objetivo:** Gravação dos dados complementares no CR
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6071349

### F040IMA
- **Rotina:** FINXFIN
- **Onde chamado:** Imposto IMA em CR
- **Objetivo:** Complementar a gravação do titulo do imposto IMA gerado no contas a receber
- **TDN:** http://tdn.totvs.com/pages/viewpage.action?pageId=433253251

### F040INS
- **Rotina:** FINXFIN
- **Onde chamado:** Geração de título INSS
- **Objetivo:** Geração de título de INSS a partir de CR
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6070868

### F040IRF
- **Rotina:** FINXFIN
- **Onde chamado:** Geração de título IRRF
- **Objetivo:** Geração de título de IRRF a partir de CR
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6070869

### F040ISS
- **Rotina:** FINXFIN
- **Onde chamado:** Geração de título ISS
- **Objetivo:** Gravação de título de ISS a partir de CR
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6070870

### F040MISS
- **Rotina:** FINXFIN
- **Onde chamado:** Valor mínimo de retenção ISS em CR
- **Objetivo:** Alteração de valor mínimo de retenção ISS
- **Params saida:** Numérico
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6070871

### F040PIS
- **Rotina:** FINXFIN
- **Onde chamado:** Geração de título PIS
- **Objetivo:** Geração de título de PIS a partir de CR
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6784060

### F040TRVSA1
- **Rotina:** FINXFIN
- **Onde chamado:** Lock SA1 em CR
- **Objetivo:** Trava/Destrava os registros da tabela SA1 em operações de CR
- **Params saida:** Lógico (.T./.F.)
- **TDN:** http://tdn.totvs.com/pages/viewpage.action?pageId=185737827

### F040URET
- **Rotina:** FINXFIN
- **Onde chamado:** Nova legenda em CR
- **Objetivo:** Inclui condição para nova legenda no CR
- **Params saida:** Array de legendas
- **TDN:** https://tdn.totvs.com/x/zDobIg

### F050GER
- **Rotina:** FINXFIN
- **Onde chamado:** Gravação de CP
- **Objetivo:** Gravação para dados complementares idênticos no CP
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6071348

### F050ISS
- **Rotina:** FINXFIN
- **Onde chamado:** Natureza ISS em CP
- **Objetivo:** Natureza de ISS no Contas a Pagar
- **Params saida:** Caracter
- **TDN:** http://tdn.totvs.com/display/public/mp/F050ISS

### F050PISS
- **Rotina:** FINXFIN
- **Onde chamado:** Alíquota ISS diferente em CP
- **Objetivo:** Alíquota de ISS diferente no Contas a Pagar
- **Params saida:** Numérico
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6070896

### F050SES
- **Rotina:** FINXFIN
- **Onde chamado:** Títulos após gravação SEST
- **Objetivo:** Alteração de títulos após gravação do SEST
- **TDN:** https://tdn.totvs.com/display/PROT/DT_F050SES_Alteracao_titulos_apos_gravacao_sest

### F070DES
- **Rotina:** FINXFIN
- **Onde chamado:** Cálculo de desconto na baixa CR
- **Objetivo:** Cálculo do valor de desconto na baixa a receber
- **Params saida:** Numérico
- **TDN:** http://tdn.totvs.com/pages/releaseview.action?pageId=6070918

### SPDF6002
- **Rotina:** FINXSPD
- **Onde chamado:** Bloco F600 do SPED PIS/COFINS
- **Objetivo:** Seleciona quais os tipos de indicadores de retenção não devem ser gerados no bloco F600
- **Params saida:** Array de tipos
- **TDN:** https://tdn.totvs.com/pages/viewpage.action?pageId=1021204615

## SIGAFIS

### MT089CD
- **Rotina:** MATA089
- **Onde chamado:** TES Inteligente
- **Objetivo:** Campos na TES Inteligente

## SIGAGCT

### CN100SIT
- **Rotina:** CNTA100
- **Onde chamado:** Apos mudanca de situacao do contrato
- **Objetivo:** Tratamento customizado nas situacoes do contrato
- **TDN:** https://accounts.google.com/ServiceLogin?hl=pt-BR&passive=true&continue=https://www.google.com/search%3Fq%3DTOTVS%2520Protheus%2520ponto%2520de%2520entrada%2520CN100SIT%2520site:tdn.totvs.com%2520OR%2520site:centraldeatendimento.totvs.com%26sei%3DTuO-aYGhLNXj1AH8hprQAQ&ec=futura_srp_og_si_72236_p

### CN120CMP
- **Rotina:** CNTA120
- **Onde chamado:** Consulta da Medicao
- **Objetivo:** Adicao de campos customizados no grid da Medicao

### CN120ESY
- **Rotina:** CNTA120
- **Onde chamado:** Consulta da Medicao
- **Objetivo:** Inclusao de campos na query da Medicao

### CN121PED
- **Rotina:** CNTA121
- **Onde chamado:** Geracao do pedido na Medicao
- **Objetivo:** Tratamento antes da geracao do pedido na Medicao

### CNT121BT
- **Rotina:** CNTA121
- **Onde chamado:** Menu principal da Medicao
- **Objetivo:** Adicionar botoes no menu da Medicao

### CN300PCMT
- **Rotina:** CNTA300
- **Onde chamado:** Manutencao de Contratos MVC
- **Objetivo:** PE adicional na rotina de Contratos

## SIGAOMS

### OM040BRW
- **Rotina:** OMSA040
- **Onde chamado:** Cad. Motoristas - browse
- **Objetivo:** Botoes no browse

### OM040TOK
- **Rotina:** OMSA040
- **Onde chamado:** Cad. Motoristas - validacao
- **Objetivo:** Validacao no cadastro

### OS040GRV
- **Rotina:** OMSA040
- **Onde chamado:** Cad. Motoristas - gravacao
- **Objetivo:** Gravacao do registro

### OM200BRW
- **Rotina:** OMSA200
- **Onde chamado:** Montagem Carga - browse
- **Objetivo:** Filtro no browse

### OM200FIM
- **Rotina:** OMSA200
- **Onde chamado:** Montagem Carga - fim
- **Objetivo:** Final do carregamento

### OM200OK
- **Rotina:** OMSA200
- **Onde chamado:** Montagem Carga - confirmacao
- **Objetivo:** Confirmacao da operacao

### OM200QRY
- **Rotina:** OMSA200
- **Onde chamado:** Montagem Carga - filtro
- **Objetivo:** Filtro dos pedidos

### OM200US
- **Rotina:** OMSA200
- **Onde chamado:** Montagem Carga - menu
- **Objetivo:** Botoes no menu

### OM460MNU
- **Rotina:** OMSA460B
- **Onde chamado:** Fat. por Carga
- **Objetivo:** Menu do Doc Saida por Carga
