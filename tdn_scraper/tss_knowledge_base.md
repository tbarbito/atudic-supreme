# Base de Conhecimento TSS — TOTVS Service SOA

> Fonte: Central de Atendimento TOTVS
> Coletado em: 2026-03-22 01:22:00
> Total de artigos: 77

---

## Indice por Categoria

- **Configuracao e Parametros** (44 artigos)
- **Instalacao, Migracao e Atualizacao** (2 artigos)
- **Erros Comuns e Rejeicoes** (5 artigos)
- **Seguranca, SSL e Certificados** (4 artigos)
- **Banco de Dados e Tabelas TSS** (9 artigos)
- **Monitoramento e Logs** (2 artigos)
- **Documentos Fiscais (NFe, CTe, MDFe, NFSe)** (8 artigos)
- **Jobs e Processos** (1 artigos)
- **Outros** (2 artigos)


## Configuracao e Parametros

### Cross Segmentos - Backoffice Protheus - TSS - 003 NFe ainda não foi assinada - aguarde a assinatura

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/4407917322263-Cross-Segmentos-Backoffice-Protheus-TSS-003-NFe-ainda-n%C3%A3o-foi-assinada-aguarde-a-assinatura

Dúvida
Como corrigir a mensagem NFe ainda não foi assinada - aguarde a assinatura ?

Ambiente
Cross Segmento - TOTVS Backoffice (Linha Protheus) - TOTVS Documentos Eletrônicos - Todas as versões.

Solução


1- Reinicie o serviço do TSS;

2- Se mesmo após reiniciar o serviço o erro continuar, verifique se o TSS está com as atualizações do link : MP - TSS - Atualização do Repositório (RPO) do TSS

---

### Cross Segmentos - Backoffice Protheus - TSS - AUTDSTMAIL in AppMap

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/4409202028823-Cross-Segmentos-Backoffice-Protheus-TSS-AUTDSTMAIL-in-AppMap

Dúvida
Como corrigir AUTDSTMAIL in AppMap ?

Ambiente
Cross Segmento - TOTVS Backoffice (Linha Protheus) - TOTVS Documentos Eletrônicos - Todas as versões.

Solução
Realizar as atualizações abaixo:

 

1 - Aplique as atualizações abaixo no PROTHEUS:
Protheus: 12.1.2310

Protheus: 12.1.2410

Rdmake

2- Refaça as configurações do envio de email:
Cross Segmentos - Backoffice Protheus - Doc. Eletrônicos - Como enviar DANFE e XML por e-mail via TSS

---

### Cross Segmentos - Backoffice Protheus - TSS - Classificação dos serviços do tss offline

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360062042954-Cross-Segmentos-Backoffice-Protheus-TSS-Classifica%C3%A7%C3%A3o-dos-servi%C3%A7os-do-tss-offline

Dúvida

Quais são as classificações do serviço do tss off-line.


Ambiente
TSS25 e TSS27

Solução

1- Possibilita a Emissão de documentos Em modalidade OFFLINE em caso de perda de comunicação com TSS.

2- Deve ser instalado no mesmo equipamento ou rede de instalação do ERP.

3- Permite contingência OFFLINE apenas para os modelos de Documentos que possuam a modalidade OFFLINE.

4- Possui banco de dados embarcado no appserver.

5- As requisições OFFLINE são registradas na tabela DLL0001.

6- Possui JOB Sincronização das requisições com TSS ON-LINE.

7- É composto pela mesma estrutura do TSS padrão.

8- A conexão é limitada entre ERP e TSS ON-LINE(TSS padrão).

---

### Cross Segmentos - Backoffice Protheus - TSS - Como configurar e utilizar tabela SPED059 (Rotina Portal do cliente)

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/22847223925399-Cross-Segmentos-Backoffice-Protheus-TSS-Como-configurar-e-utilizar-tabela-SPED059-Rotina-Portal-do-cliente

Dúvida
Como configurar e utilizar tabela SPED059 (Rotina Portal do cliente)?

Ambiente
Cross Segmento - TOTVS Backoffice (Linha Protheus) - TOTVS Documentos Eletrônicos - Todas as versões.

Solução:
1. Parametrizar o Rest no INI do TSS, exemplo:

[HTTPJOB]
MAIN=HTTP_START
ENVIRONMENT=SPED

[HTTPV11]
Enable=1
Sockets=HTTPREST
TimeOut=120

 

[HTTPREST]
Port=1322
IPsBind=
URIs=HTTPURI
Security=0
;Para correto funcionamento do uso de REST com TSS o conteudo da
;chave Security nao deve ser alterado, permanecendo como 0
;Mais detalhes de uso consulte: https://tdn.totvs.com/x/gkkSCw

 

[HTTPURI]
URL=/rest
PrepareIn=
Instances=1,10
CORSEnable=0
AllowOrigin=*
EXPIRATIONTIME=120
EXPIRATIONDELTA=1

Ao subir o serviço do TSS (appserver), no console aparecerá o REST habilitado, conforme imagem abaixo:

 

Teste de conexão com o REST:

 

2. Gravação tabela SPED059:

No configurador (SIGACFG SX6) quando o valor do parâmetro MV_SPEDGRV  = 1, não gravará na tabela SPED059 (comportamento padrão);  

Quando o valor do parâmetro MV_SPEDGRV = 2,  será habilitada a gravação na tabela SPED059.

 

CRIAÇÃO DO PARÂMETRO

a) Acessar o SIGACFG (SX6)

 

b) Acessar a rotina Base de Dados \ Dicionário \ Base de Dados ou Ambiente \ Cadastros \ Parâmetros;

 

c) Selecionar Parâmetros em seguida, clicar na opção Incluir.

 

d) Informar os dados da criação do parâmetro:

 

Na aba Informações, para os campos:

Filial: pode ser específico por filial ou em branco (genérico para todas as filiais).

Nome da Var.: nome do parâmetro:  MV_SPEDGRV.

Tipo: deve ser 1-caractere.

Cont. Por: Preencher conforme orientações do tópico 02. Exemplo de Utilização.

 

e) Na aba Descrição, para os campos:

 

Descrição: Parâmetro que define como deve ser enviada nova tag

Cont. Descriç: (GRVDOCAUX) do método DISTRIBUICAODEDOCUMENTOS.

f) Clique em Salvar e o parâmetro será criado.

 

3. O parâmetro MV_FNPCTSS deve conter o endereço do servidor REST do TSS (exemplo: [seuip]:[suaporta]/[caminhorest]/) 
Observação: Caso haja necessidade criação deste parâmetro o Tipo= CARACTER 

 

4. O processo atualmente é dependente do uso do envio automático de DANFE para integração com a Rotina Portal do cliente: Distribuição de DANFE e DANFSE Protheus automática

Configuração INI Protheus, deverá incluir os seguintes JOBS: 

[DistMail]
Main=DistMail
Environment=NomeDoSeuAmbiente
[IPC_DISTMAIL]
Main=prepareIPCWAIT
Environment=NomeDoSeuAmbiente
instances=1,10,1,1
ExpirationTime=120
ExpirationDelta=1
[OnStart]
jobs=DistMail, IPC_DISTMAIL
RefreshRate=10

 

Importante:      No diretório appserver do ERP Protheus será necessário ter o arquivo Printer.exe

Na Rotina NFE SEFAZ opção Wiz. Config, será necessário na parametrização SMTP campo Envio DANFE por e-mail? Selecionar opção 2- Enviar Danfe do ERP

 

 

Após realize uma transmissão NF-e. Assim que o JOB DISTMAIL configurado no INI do ERP disparar o SMTP com Danfe e XML ao destinatário, será gravado o Registro na SPED059:

---

### Cross Segmentos - Backoffice Protheus - TSS - Como verificar o Inspetor de Objetos do TSS?

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/1500007988782-Cross-Segmentos-Backoffice-Protheus-TSS-Como-verificar-o-Inspetor-de-Objetos-do-TSS

Dúvida
Como poderá ser verificado a data dos fontes através do Inspetor de Objetos do TSS?

Ambiente
Cross Segmento - TOTVS Backoffice (Linha Protheus) - TOTVS Documentos Eletrônicos - Todas as versões.

Solução
Para verificar o Inspetor de Objetos do TSS, é recomendado a utilização do Visual Studio Code, junto com o plugin TOTVS Developer Studio: 



I. Já dentro do VSCode, deverá ser configurado o servidor referente ao ambiente do TSS:



II. Após configurado com todas as informações corretas, deverá conectar ao ambiente com as credencias (por padrão, usuário = ADMIN e senha em branco).





III. Com o ambiente conectado, clicando com o botão direito no mesmo, será apresentada a opção de 'Inspetor de Objetos':



IV. Em seguida será apresentada uma tela com a opção de pesquisa por fonte específico ou a exportação completa de todos os fontes (é necessário utilizar o * para lista todos com suas respectivas datas):

---

### Cross Segmentos - Backoffice Protheus - TSS - Configuração da fonte de dados ODBC

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/22313590251415-Cross-Segmentos-Backoffice-Protheus-TSS-Configura%C3%A7%C3%A3o-da-fonte-de-dados-ODBC

Dúvida

Como realizar a configuração da fonte de dados ODBC?

Ambiente
Cross Segmento - TOTVS Backoffice (Linha Protheus) - TOTVS Documentos Eletrônicos - Todas as versões.

Solução


Criação da FONTE DE DADOS ODBC:

Para utilizar o DBAccess em uma base SQL, é necessário configurar uma fonte de dados ODBC da seguinte maneira:

1- Acessar o Painel de controle | Ferramentas Administrativas |Fonte de Dados (ODBC).

Na pasta “Fontes de Dados do Sistema”, clicar em “Adicionar” e selecionar a FONTE DE DADOS

OBSERVAÇÃO: Caso o sistema operacional seja 64 Bits, o caminho da fonte de dados é diferente: C: |Windows |siswow64 |executar o arquivo ODBCAD32.exe.

 

 

2- Para adicionar o Driver é necessário informar os dados abaixo: *Servidor – Informar o Servidor onde está instalado o Banco de Dados SQL.

 

3- A configuração do Logon deve ser parametrizada conforme abaixo e nos campos identificação de “Logon e Senha” deve ser preenchidos com seu usuário e senha de acesso ao Banco de dados.

 

 

4- Nesta tela deve-se marcar o parâmetro “alterar o banco de dados padrão para", e selecionar uma Base de Dados válida (não é recomendada a utilização da base CORPORE, recomendamos que seja criada uma base especifica para os dados do TSS, onde o usuário utilizado no passo anterior tenha permissão total na mesma).

 

5- Nesta próxima etapa não é necessário alterar as configurações, basta finalizar e testar a conexão.

 

6 – Verifique se foi criado seu ambiente como na imagem abaixo:

---

### Cross Segmentos - Backoffice Protheus - TSS - Envio de e-mail do danfe gerado pelo erp (customização disponível via rdMake)

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360041452974-Cross-Segmentos-Backoffice-Protheus-TSS-Envio-de-e-mail-do-danfe-gerado-pelo-erp-customiza%C3%A7%C3%A3o-dispon%C3%ADvel-via-rdMake

Dúvida
Como realizar o envio de e-mail do DANFE gerado no ERP (customização disponível via RDMake).
Pré-Requisitos:
-TSS versão 3.0 ou superior, com o pacote atualizado DSERTSS1-13395;
-Protheus com o pacote atualizado DSERTSS1-13514 (inclusive o fonte DANFEII.PRW com data igual ou superior a 16/10/2019).


Ambiente
Microsiga Protheus - a partir da versão 12.1.17

Solução
1. No assistente de configuração da rotina SPEDNFE, selecione a opção 2-Enviar Danfe do ERP.


 

 

2. CONFIGURAÇÃO DO APPSERVER.INI

Inclua a seguinte chave e a ativação na inicialização do appserver.ini do ERP;
Na chave ENVIRONMENT após o = preencher com o nome do seu ambiente Protheus (Deve constar apenas um ambiente, caso insira mais de um irá apresentar erro.);
Em caso de balanceamento, não é necessário informar a configuração em todos os slaves, recomendamos informar apenas em um único appserver.ini, ou um dos slaves que será utilizado para distribuição de e-mail. 

 

[DistMail]
Main=DistMail
Environment=NomeDoSeuAmbiente

 

[IPC_DISTMAIL]
Main=prepareIPCWAIT
Environment=NomeDoSeuAmbiente
instances=1,10,1,1
ExpirationTime=120
ExpirationDelta=1

 

[OnStart]
jobs=DistMail, IPC_DISTMAIL
RefreshRate=10

 

3. É necessário que possua o arquivo printer nas pastas Smartclient e Appserver do Protheus e TSS:

 

Link de download do artefato do Windows:

Printer Windows X64

Printer Windows X32

 

Link de download do artefato do MAC:

Printer MAC

 

Link de download do artefato do Linux:

Printer Linux X64

PDF Printer X64

Printer Linux X32

PDF Printer X32

 

4. Na tabela SPED000 do TSS, veja se os parâmetros estão preenchidos conforme abaixo para a respectiva Entidade:

MV_AUTDIST = 0
MV_NFEDISD =1 

 

É possivel que a realização do envio da Danfe via ERP seja configurada também via schedule, temos o passo a passo a ser realizado no link abaixo:

https://tdn.totvs.com/pages/releaseview.action?pageId=498696242

---

### Cross Segmentos - Backoffice Protheus - TSS - NFSe - Configuração do NewNfse

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/16784834285847-Cross-Segmentos-Backoffice-Protheus-TSS-NFSe-Configura%C3%A7%C3%A3o-do-NewNfse

Dúvida
Como configurar o TSS (TOTVS Service SOA) para transmissão de NFS-e via WEB Service utilizando a New NFS-e?

Ambiente
Cross Segmento - TOTVS Backoffice (Linha Protheus) - TOTVS Documentos Eletrônicos - Todas as versões.

Solução
Configuração da New NFS-e para Transmissão de NFS-e via WebService.

Segue o passo a passo abaixo:

1. Pare o serviço do TSS:


2. Acesse a pasta de instalação do TSS, extraia o arquivo tssNewNfse.JSON e salve na pasta system do TSS: TSSNEWNFSE

 

 

3. Clique com o botão direto do mouse no arquivo e acesse as propriedades do arquivo. Desmarque a opção "somente leitura" caso esteja marcada:

 

4. Reinicie o serviço do TSS para que o arquivo tssNewNfse.json seja consumido e deletado pelo TSS da pasta system:


5. Se arquivo não for apagado da pasta system, entre na APSDU do TSS, filtre a tabela SPED000  e apague o conteúdo do parâmetro MV_VERNFSE do TSS e refaça o procedimento;

6. Após conclusão, reinicie o serviço do TSS.

 

IMPORTANTE!
Após realizar o processo de implantação da New NFS-e, será criado a Tabela TSS0013 e populado, com os municípios adequados para utilização da New NFS-e.

Após o arquivo tssNewNfse.JSON ser apagado e a tabela TSS0013 ser populada, será criado um parâmetro no ambiente do TSS, Tabela de Parâmetros(SPED000) >> Parâmetro MV_NEWNFSE. Este parâmetro define o fluxo de Transmissão, Consulta e Cancelamento da NFS-e, se será pela New NFS-e ou fluxo padrão do TSS.

O parâmetro MV_NEWNFSE é atualizado automaticamente, após a leitura do arquivo tssNewNfse.JSON e criação da tabela TSS0013 ( municípios NewNfse ).

Caso o conteúdo do parâmetro MV_NFSEMUN da entidade ( tabela SPED000 campo ID_ENT ) exista na tabela TSS0013 ( campo COD_MUN ), o parâmetro MV_NEWNFSE receberá o conteúdo "S", caso não existe receberá o conteúdo "N".


Observações finais:

Para identificar se o município está homologado no NewNFSe, veja na relação de municípios homologados, no campo 'Versão TSS Implementação' sigla NW:

 TSS0009_Relação_de_Municípios_Homologados_para_Emissão_de_NFS-e

---

### Cross Segmentos - TSS - Cliente não habilitado para operar na Totvs-Infra

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360058808373-Cross-Segmentos-TSS-Cliente-n%C3%A3o-habilitado-para-operar-na-Totvs-Infra

Dúvida

Como corrigir a mensagem  Cliente não habilitado para operar na Totvs-Infra ?

 

Ambiente
Protheus – TSS – A partir da versão 12.1.17

Solução


Este erro ocorre quando o cliente possui seu ambiente TSS alocado em cloud.

Para que o ambiente seja liberado, solicitar a sua devida liberação junto ao cloud e posteriormente executar o wizard de configuração da rotina a ser acessada (NF-e, CT-e, NFS-e, Manifesto, etc).

---

### Cross Segmentos - TSS - Comando Topmemomega para gravação dos xmls

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/1500000291782-Cross-Segmentos-TSS-Comando-Topmemomega-para-grava%C3%A7%C3%A3o-dos-xmls

Dúvida
Funcionalidade do comando TOPMEMOMEGA no TSS.

 

Ambiente
TSS 25 e TSS 27



Solução


Topmemomega: permite que as conexões SGBD (Sistema de Gerenciamento de Banco de Dados), realizadas por meio do ByYou DBAccess, utilizem o campo M (Memo) com até 1.000.000 de bytes. Este parâmetro é necessário, pois o TSS utiliza campos MEMO para gravação dos XML. Deve estar dentro da seção que tiver a configuração do TopConnect, geralmente na chave do ambiente [Environment] ou na chave do TopConnect.

Exemplo:

[Environment]

TOPMEMOMEGA=1

---

### Cross Segmentos - TSS - Comando log_period

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/1500000200082-Cross-Segmentos-TSS-Comando-log-period

Dúvida
Como utilizar o comando LOG_PERIOD



Ambiente
TSS 12.1.25 e TSS 12.1.27


Solução


LOG_PERIOD: Configura a quantidade de dias retroativos para, a partir desta data, realizar a limpeza da tabela TSS0004.

 

Exemplo:

Neste exemplo, foi definido que deve ser realizado a limpeza da tabela TSS0004, 10 dias retroativos.

[Environment]

LOG_PERIOD=10

---

### Cross Segmentos - TSS - Comando log_period_tr2

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360060498393-Cross-Segmentos-TSS-Comando-log-period-tr2

Dúvida


Funcionalidade do comando LOG_PERIOD_TR2


Ambiente
TSS12.1.25 e TSS12.1.27

Solução


LOG_PERIOD_TR2: Configura a quantidade de dias retroativos para, a partir desta data, realizar a limpeza da tabela TSSTR2.

 

Exemplo:

Neste exemplo, foi definido que deve ser realizado a limpeza da tabela TSSTR2, 10 dias retroativos.

[Environment]

LOG_PERIOD_TR2=10

---

### Cross Segmentos - TSS - Como acessar as interfaces gráficas do TSS

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360049308093-Cross-Segmentos-TSS-Como-acessar-as-interfaces-gr%C3%A1ficas-do-TSS

Dúvida
Como acessar as interfaces gráficas do TSS?

Ambiente
A partir da versão 11 do TSS.

Solução
O TSS possui aplicativos com interfaces gráficas que ajudam a monitorar e manusear informações que estão no Sistema.
Os aplicativos que o TSS possui com interface são:

•  TSSMonitor
Utilizado para monitorar os documentos eletrônicos, visualizar informações sobre as entidades cadastradas e configurações do TSS.

•  TSSInterface
Utilizado para monitorar e manipular informações do serviço do TSS, proporcionando um gerenciamento rápido, simples e fácil.

Estas ferramentas não estão disponíveis para serviços Localizados (Mercado Internacional) e para a versão offline do TSS (TSS Offline).

 

Para realizar o acesso as interfaces do TSS é necessário um usuário configurado com acesso ao Sistema.

Exemplo:
1. Execute o SmartClient do TSS acessando algum aplicativo de interface;

Exemplo da configuração do smartclient.ini do TSS:

2. No primeiro acesso faça o login com o usuário ADMIN e senha ADMIN; o aplicativo solicita que seja definida uma nova senha para o usuário ADMIN;

3. O aplicativo tem acesso ao gerenciamento de usuários que permite manipular as contas de usuários que podem acessar as interfaces gráficas;

4. Crie um usuário fornecendo o nome e clicando no ícone de Adição;

5. Desmarque a opção 'Alterar senha no próximo logon' e adicione o(s) CNPJ(s) da empresa/filial que o usuário terá acesso;

6. Clique no ícone representado pelo disquete para salvar as configurações do usuário;

7. Acesse o aplicativo com o usuário recém-criado para utilizar as funcionalidades.

---

### Cross Segmentos - TSS - Configurar o TSS para utilizar a comunicação HTTPS

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/1500002745522-Cross-Segmentos-TSS-Configurar-o-TSS-para-utilizar-a-comunica%C3%A7%C3%A3o-HTTPS

Dúvida
Como configurar o TSS para utilizar a comunicação HTTPS?


Ambiente
Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Todas as versões
Solução
Para comunicação com TSS utilizando o protocolo HTTPS, é preciso realizar algumas configurações manuais no arquivo de configuração do Application server.

 

Link para acesso as configurações e pré-requisitos e mais informações clicando aqui.

Obs: Após instalação do certificado, baixe o executável que consta na documentação referenciada no passo 2, execute o comando via prompt de comando do sistema operacional.

 Navegue pelo prompt de comando até o diretório onde foi baixado o arquivo exe.
Execute o comando totvs_certificates [-cert file] [-key file] [-passwd password]

-cert : Nome do arquivo de certificado. (padrão: totvs_certificate.crt)
-key : Nome do arquivo de chave de certificado. (padrão: totvs_certificate_key.pem)
-passwd : Palavra chave do certificado (senha)

 

Exemplo para execução do comando: totvs_certificates -cert informe o nome do arquivo.crt -key informe o nome da chave.pem -passwd 12345

 

Ao executar o comando, será apresentado as seguintes informações reportando a criação dos arquivos crt e pem no mesmo diretório onde consta o exe.

Após o processo, prossiga com as demais configurações contidas na documentação.

---

### Cross Segmentos - TSS - Configuração de proxy

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360056653873-Cross-Segmentos-TSS-Configura%C3%A7%C3%A3o-de-proxy

Dúvida

Como configurar a seção de Proxy no appserver.ini do TSS.

 


Ambiente


TSS 12


Solução

 

Se na rede local o acesso a Internet passa por um Proxy e o servidor onde está instalado o TSS - TOTVS Service SOA, será necessário inserir o Proxy no arquivo de configuração do TSS, o appserver.ini, para que o serviço do TSS também consiga estabelecer conexão com as URLs do governo.


No appserver.ini do TSS, deve ser inserida a seção abaixo:

[PROXY]
Enable=1
Server=endereco do Proxy
Port=porta do Proxy
User=dominio/usuario
Password=senha do usuario no Proxy
NoProxyFor=<DomainList>

 

NoProxyFor = Nela, deve-se informar uma lista de domínios ou IPs que não devem utilizar o proxy.

Mais detalhes da seção proxy no link:
https://tdn.totvs.com/pages/viewpage.action?pageId=6064913

---

### Cross Segmentos - TSS - Contingência automática

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360058570334-Cross-Segmentos-TSS-Conting%C3%AAncia-autom%C3%A1tica

Dúvida
Como configurar o sistema para entrada em contingência automática

Ambiente
TSS - a partir da versão 12.1.25

Solução

 

Contingência Automática TSS

Disponibilizado para transmissão da NF-e.

 

Objetivo

Emitir de forma automática a nota fiscal eletrônica em modalidade de contingência, quando não houver comunicação com a SEFAZ de origem, seja por problemas técnicos de infraestrutura local ou por motivos de manutenção da própria SEFAZ.

 

Modalidades de contingência disponíveis*:

EPEC - Disponível a partir do Release 12.1.17

SVC-AN e SVC-RS - Disponíveis a partir do Release 12.1.25

* Liberada para o uso no produto TSS, verifique a disponibilidade desta configuração no ERP utilizado.

 

Configuração

A configuração será realizada através do método CFGAUTOCONT, por filial, modelo e modalidade, ou seja, será permitido apenas a configuração de uma modalidade de contingência para a entidade selecionada.

Lembrando que:

Os Eventos deverão estar devidamente configurados;

O Proxy deverá permanecer corretamente configurado no arquivo INI;

 

Fluxo do processo:

1..O ERP envia as notas eletrônicas para o TSS.

2. O TSS valida, monta o lote e transmite para a SEFAZ de Origem.

3. O TSS não consegue postar ou não recebe o retorno.

4. Neste momento o TSS irá consultar a tabela de configuração, para verificar se a entidade está habilitada e qual a sua contingência.

5. A nota com falha de post, será rejeitada com a justificativa  “NF-e rejeitada pelo TSS devido a falha de comunicação com a Sefaz de origem. Realizar o cancelamento e a retransmissão com uma nova numeração. E com a Recomendação: "014 - NF-e não autorizada - Corrija o problema e retransmita as notas fiscais eletrônicas. 000/NF-e rejeitada pelo TSS devido a falha de comunicação com a Sefaz de origem. Realizar o Cancelamento e a Retransmissão com uma nova numeração".

 

A configuração da contingencia automática pode ser habilitada ou desabilitada no caminho abaixo: 

 

Observação

Uma vez habilitada a contingência automática não será possível a alteração manual de modalidade, sendo necessário desativar a configuração através do método CFGAUTOCONT.

 

Consulta SEFAZ

Ao utilizar os seguintes métodos MONITORSEFAZMODELO e MONITORSEFAZ,  e o retorno do status da operação for diferente de Serviço em Operação ou o tempo médio de retorno for maior que o tempo de espera configurado pelo ERP, será habilitada a entrada em contingência.

---

### Cross Segmentos - TSS - Erro no console log, por falta do arquivo Printer

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360048828614-Cross-Segmentos-TSS-Erro-no-console-log-por-falta-do-arquivo-Printer

Dúvida
Como corrigir o erro abaixo no console log do TSS?
[WARN ][SERVER] Cannot update a constant string
[WARN ][SERVER] [Thread 9568] TOTVS Printer: Printer Agent not found on Server path. Check if "d:\outsourcing\clientes\6f16fy_tss_prd\bin_tss\appserver_11301\printer.exe" file exists.
file2Printer()::CreateProcessA FAILED WITH ERROR = 0

Ambiente
A partir da versão 11.80 do Protheus e TSS11.

Solução
Este erro ocorre por falta do arquivo Printer no TSS.
Para que o envio do danfe e/ou dacte em PDF por email funcione corretamente, é necessário ter o arquivo Printer dentro dos diretórios Smartclient e Appserver do TSS.

A falta deste arquivo em um ou em ambos os diretórios, causa o erro acima citado e impede a geração e envio do PDF por email.

Para correção do erro é necessário colocar o arquivo Printer nos diretórios informados.

Dica: Caso tenha o arquivo somente em um diretório, pode copiar e colar no outro que não tem o arquivo.

Segue link do Portal do Cliente contendo o arquivo Printer:
https://suporte.totvs.com/portal/p/10098/download#all/all/all/search/printer

---

### Cross Segmentos - TSS - Habilita ou desabilita o envio de e-mail para todos os processos de um modelo especifico

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360060468333-Cross-Segmentos-TSS-Habilita-ou-desabilita-o-envio-de-e-mail-para-todos-os-processos-de-um-modelo-especifico

Dúvida
A etapa de envio de e-mail é realizada por padrão pelo sistema TSS, podendo ser desabilitada para o(s) modelo(s) desejado(s) através da TAG NOSENDMAIL presente na sessão do ambiente no arquivo appserver.ini.

Ambiente
TSS 25 e TSS 27

Solução


Os documentos que possuem essa funcionalidade são:

CT-e (57);

Exemplo:

Neste exemplo, iremos desabilitar o envio de e-mail para todos os processos do modelo CT-e (modelo 57). O arquivo de appserver.ini deverá conter:

[Environment]

NOSENDMAIL=CTE

---

### Cross Segmentos - TSS - Job tsstaskproc

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360043282893-Cross-Segmentos-TSS-Job-tsstaskproc

Dúvida
Funcionalidade do Job TSSTASKPROC


Ambiente
Apartir do TSS 12.1.17  3.0  


Solução
O job TSSTASKPROC é responsável, para processar as notas da tabela TSSTR1, esse comando deve ser informado na seção ONSTART no appserver.ini do TSS, e dessa maneira as Threads serão processadas, e  o fluxo das transmissões ocorrerá normalmente.

---

### Cross Segmentos - TSS - MENSAGENS NO CONSOLE LOG - [WARN ][SSL] Failed verification of server CA certificate [27: certificate not trusted]

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360044294153-Cross-Segmentos-TSS-MENSAGENS-NO-CONSOLE-LOG-WARN-SSL-Failed-verification-of-server-CA-certificate-27-certificate-not-trusted

Dúvida
O que representa as mensagens abaixo, no console do TSS?

INFO ][SSL] [tSSLSocketAPI][Connect] Connecting SSL.
[INFO ][SSL] [tSSLSocketClientAPI][Initialize] starting handshake ..
[INFO ][SSL] [tSSLSocketClientAPI] Using TLS/SSL protocol.
[INFO ][SSL] [tSSLSocketClientAPI][Initialize] KeyFile (D:\totvsTAF\certs\000008_key.pem)
[INFO ][SSL] Using PrivKey from WS (d:\totvstaf\certs\000008_key.pem)
[INFO ][SSL] [tSSLSocketClientAPI][Initialize] CertificateFile (D:\totvsTAF\certs\000008_all.pem)
[INFO ][SSL] Using Certificate from WS (d:\totvstaf\certs\000008_all.pem)
[INFO ][SSL] SSL CIPHERS ALL
[INFO ][SSL] [tSSLSocketClientAPI][Initialize] Bugs (1)
[INFO ][SSL] [tSSLSocketClientAPI][Initialize] SSL2 (0), SSL3 (1), TLS1.0 (1), TLS1.1 (1), TLS1.2 (1)
[INFO ][SSL] [tSSLSocketClientAPI][Initialize] State (0)
[INFO ][SSL] [tSSLSocketClientAPI][Initialize] End handshake (1)
[WARN ][SSL] Failed verification of server CA certificate [20: unable to get local issuer certificate].
[WARN ][SSL] Failed verification of server CA certificate [27: certificate not trusted].
[INFO ][SSL] [tSSLSocketAPI][Connect] Connected SSL version: TLSv1.2.


Ambiente
Protheus á partir da  versão 11.
TSS á partir da versão 11.

Solução
Estas mensagens de WARN são apenas avisos sobre a validação da cadeia certificadora de seu certificado digital.
Basicamente, a mensagem informa que a cadeia certificadora pode estar desatualizada em seu servidor ou em seu terminal.

Vale lembrar que esta mensagem não interfere no processamento do TSS, são apenas mensagens informativas.
É possível desabilitar o aparecimento destas mensagens por meio da configuração abaixo no appserver.ini do TSS:

Chave da seção [SSLConfigure]
Verbose=0 (1=habilitado, 0=desabilitado)

Esta chave faz a depuração da comunicação SSL entre o TSS e as urls externas.

---

### Cross Segmentos - TSS - Procedimento para ativar os logs de comunicação do TSS

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/1500007834222-Cross-Segmentos-TSS-Procedimento-para-ativar-os-logs-de-comunica%C3%A7%C3%A3o-do-TSS

Dúvida
Como ativar os logs de comunicação do ERP com o TSS, e do TSS com as urls externas?

Ambiente
Cross Segmento - TSS Transmissão de Documentos Eletrônicos - Todas as versões.

Solução
O TSS possui algumas configurações que podem ser realizadas para uso geral dos serviços por ele gerenciado.
A seguir, apresentamos duas destas configurações e suas respectivas seções para a configuração.

 

Onde e como configurar?

1. No arquivo de configuração appserver.ini que existe dentro do diretório \bin\appserver da instalação do TSS, habilite/crie as chaves conforme os exemplos abaixo:

SPED_SAVEWSDL: Habilita a gravação dos xmls de comunicação do TSS com os Web Services Externos. Os arquivos gerados são gravados na pasta System do TSS.
Esta chave deve ser habilitada apenas em casos que sejam realmente necessários, pois pode causar certa lentidão na comunicação.

Exemplo:
[SPED]
SPED_SAVEWSDL=1

 

XMLSAVEALL: Chave que permite a gravação de todos os xmls de comunicação entre o TSS e as aplicações dos clientes do Web services do TSS (ERP's). Os arquivos gerados são gravados na pasta WSLOGXML do TSS.
Esta chave deve ser habilitada somente para ajudar na análise de inconsistências, pois gera um grande número de arquivos xml.

Exemplo:
[JOB_WS]
XMLSAVEALL=1

 

2. Para que as chaves comecem a funcionar, após configurar e salvar o appserver.uni, é necessário reiniciar o TSS;

Dica: Antes de realizar a simulação, apague todos os arquivos *.xml das pastas WSLOGXML e SYSTEM, para que fiquem apenas os registros gerados durante a simulação;



3. Realize a simulação do incidente em questão e ao término da simulação, envie os seguintes arquivos para análise da situação:

- Os arquivos com a extensão _in e _out gerados na pasta WSLOGXML, localizada no diretório raiz do TSS;
- Os arquivos com a extensão _rcv e _snd gerados na pasta SYSTEM, também localizada no diretório de instalação do TSS.

 

4. Ao final da gravação, comente com ; (ponto e vírgula) ou desabilite (deixando com conteúdo zero) as chaves acima informadas e reinicie o TSS novamente;
-;SPED_SAVEWSDL=1 ou SPED_SAVEWSDL=0

 

Vale Lembrar: Os parâmetros para geração dos logs só devem estar ativos durante a simulação. Após a simulação, altere novamente o arquivo appserver.ini, desabilitando os parâmetros XMLSAVEALL e SPED_SAVEWSDL e reinicie o serviço do TSS, assim a aplicação não irá gerar logs desnecessários.

---

### Cross Segmentos - TSS - Reprocesso para envio de e-mail

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360057909674-Cross-Segmentos-TSS-Reprocesso-para-envio-de-e-mail

Dúvida

Como reprocessar o envio de e-mail ?

 

Ambiente
TSS - A partir da versão 12.1.25

Solução

 

TRYREPROC: Define a quantidade de tentativas de envio de e-mail que deverá ser realizada pelo TSS, caso haja alguma falha no processo de envio do e-mail na primeira tentativa.

Para habilitar, adicione o parâmetro TRYREPROC na chave IPC_SMTP no APPSERVER.INI 

Quando habilitado, caso haja alguma falha no processo de envio do e-mail, será gravado no CONSOLE.LOG qual a falha ocorrida e o número da tentativa atual.


Para não realizar o reprocesso, informe 0 (zero)

Mínimo permitido é 0

Máximo permitido é 3.

 

Exemplo:

[IPC_SMTP]
MAIN=prepareIPCWAIT
INSTANCES=1,25,1,1
ENVIRONMENT=SPED
EXPIRATIONTIME=120
EXPIRATIONDELTA=1
TRYREPROC=3

No exemplo acima, foi definido que o TSS irá realizar até 03 tentativas de envio do e-mail caso haja alguma falha durante o processo.

Caso o parâmetro não seja informado, o TSS assume o valor padrão de 3 (três) tentativas.

 

Observação
Configuração de tentativas disponível para o processo de envio de e-mail do XML (autorização ou cancelamento) e Documento Auxiliar (PDF) de NF-e, CT-e e CT-eOS.

 

Link da Issue: https://tdn.totvs.com/pages/viewpage.action?pageId=570360609

---

### Cross Segmentos - TSS - Suporte do Cloud reiniciar o serviço ou servidor

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/4403736483095--Cross-Segmentos-TSS-Suporte-do-Cloud-reiniciar-o-servi%C3%A7o-ou-servidor

Dúvida
Qual o procedimento para Reiniciar o serviço ou servidor do TSS no cloud ?

Ambiente
Cross Segmentos - TSS - a partir da versão 11

Solução

 

Os canais de atendimento no Cloud, será necessário abertura de um ticket ou entrar em contato através do Central de Atendimento por telefone. 

 


O guia de relacionamento Totvs encontra-se disponível na home do Portal do Cliente. Para realizar o download do documento, realize os passos abaixo:

Acesse o Portal do Cliente, clique aqui;
Utilize a barra de rolagem do navegador e siga até o meio da página;
Clique em Conheça o Guia de Relacionamento TOTVS;

 

Realize o dowload do arquivo ou visualize na tela do Fluig.

 

Saiba mais:

Para prosseguir a análise favor informar o CNPJ da filial que emitiu a nota e sua URL de acesso ao servidor TSS, verificar a sua URL por um dos seguintes meios:


1. Acesse a rotina SPEDNFE opção Wiz.Config, verificar a URL após o primeiro “Avançar”;

2. Acessar o módulo Configurador (SIGACFG), em seguida em Ambiente / Cadastros / Parâmetros clicar MV_SPEDURL, neste parâmetro contém o conteúdo da URL.

---

### Cross Segmentos - TSS - Tabela TSS0006

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/1500003569722-Cross-Segmentos-TSS-Tabela-TSS0006

Dúvida
Funcionalidade da tabela tss0006.

Ambiente
TSS25 e TSS27

Solução
Tem o objetivo de registrar os certificados na base de dados é garantir a configuração dos certificados em caso de perda da instalação do TSS ou replica de instalação. Por padrão a aplicação exige que os certificados estejam disponíveis no diretório de instalação.
Esse comportamento exige a configuração ou replica manual do certificado para cada instância do TSS instalada em file system distinto.

Para definir a persistência do certificado na base de dados é necessário habilitá-lo no environment do TSS. Conforme abaixo:

[SPED]

AUTOSCALING=1

---

### Cross Segmentos - TSS -Comando systimeadjust

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/1500000007722-Cross-Segmentos-TSS-Comando-systimeadjust

Dúvida
Funcionalidade do comando SYSTIMEADJUST


Ambiente
A partir da versão TSS 12.1.25



Solução
O campo TIME_NFE da tabela SPED050 por conceito sempre será alimentado com o horário do servidor TSS, independente do horário da filial responsável pela geração da nota.


Se no INI do TSS na seção ENVIRONMENT utilizada for inserido o comando por exemplo:
[SPED]
SYSTIMEADJUST=-1

O campo TIME_NFE será gravado com 1(hora) a menos em relação ao horário do servidor.

---

### Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Atualização do Appserver (binário) do TSS

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360062416694-Cross-Segmentos-TSS-Transmiss%C3%A3o-de-Documentos-Eletr%C3%B4nicos-Atualiza%C3%A7%C3%A3o-do-Appserver-bin%C3%A1rio-do-TSS

Dúvida
Como realizar a atualização do appserver (binário) do TSS?

Ambiente
Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Todas as versões

Solução
Segue abaixo um passo a passo de como deverá ser realizado a atualização do appserver do TSS, o qual vale lembrar que são reaproveitados os mesmos arquivos do Protheus, pois possuem arquiteturas similares.

1. Deverá parar o serviço do TSS;

2. É necessário baixar a última versão de appserver disponível no Portal do Cliente através dos links abaixo:


Releases 12.1.2210 e 12.1.2310
Windows - Clique aqui para download.
Linux - Clique aqui para download.

 

Release 12.1.2410
Windows - Clique aqui para download.
Linux - Clique aqui para download.

3. No diretório de instalação do TSS, realize o backup da pasta appserver.

4. Em seguida, descompacte os arquivos em que fez o download e copie todo o conteúdo na pasta appserver.

 

Obs: Após atualização do binário, é necessário que atualizem o arquivo do dbapi.dll (para Windows) ou dbapi.so (para Linux) dentro da pasta do Appserver do TSS, de acordo com a versão do DBAccess utilizada.

 

Link do gif: https://bit.ly/3CX2aI9

---

### Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Como acessar a APSDU do TSS via Smartclient Web

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/31004091954839-Cross-Segmentos-TSS-Transmiss%C3%A3o-de-Documentos-Eletr%C3%B4nicos-Como-acessar-a-APSDU-do-TSS-via-Smartclient-Web

Dúvida
Como acessar a APSDU do TSS via Smartclient Web ?


Ambiente
Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Todas as versões


Solução
Para acessar o banco de dados pelo smartclient web para extração de tabelas, acesse a APSDU.

 

1 - Acesse a pasta de instalação do TSS e acesse a pasta appserver:

Diretório: Raiz de instalação do TSS -> BIN -> APPSERVER

 

2 - Abra o arquivo appsever.ini do TSS e verifique a sessão do WebApp

 

 

OBS: Essa porta deve ser utilizada em conjunto com o endereço IP ou local do TSS

 

 

3 - Acesse usuário com "admin" e senha em "branco";

 

4 - Para acessar as tabelas do ambiente do TSS, clique em Arquivo -> Abrir:

 

5 - Seleciona o driver "TopConnect (TOPCONN)":

 

6 - Confirme os dados de conexão com o banco de dados e clique em Ok:

 

7 - Na tela a seguir, informe o nome da tabela que deseja abrir e clique em Ok:

 

8 - Faça o filtro(Ctrl+F ) necessário para localizar o documento ou a entidade em questão.
No exemplo abaixo, filtramos a SPED000 pela entidade que representa a filial, clique incluir e posteriormente em Ok:

Campos = Nome do campo que deseja realizar o filtro

Operadores = Condição para ser usado no filtro

Expressão = Conteúdo a ser filtrado

 

9 - Após filtro, copie o conteúdo filtrado para envio ao suporte em ÚTIL -> Copiar para:

 

10 - No caminho, clique nos três pontos(...) e informe o caminho onde será salvo o arquivo.

Obs: No driver sempre deixe Ctree

 

Após estes passos, localize o arquivo salvo no diretório informado e envie ao suporte para prosseguir com a analise.

---

### Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Como aplicar patch no TSS

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/24560205471383-Cross-Segmentos-TSS-Transmiss%C3%A3o-de-Documentos-Eletr%C3%B4nicos-Como-aplicar-patch-no-TSS

Dúvida
Como aplicar um patch no TSS?

Ambiente
Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Todas as versões

Pré-requisitos
- Visual Studio Code instalado;
- Extensão 'TOTVS Developer Studio for VSCode (AdvPL, TLPP e 4GL)' instalada no VSCODE;
- TSS deve estar com o serviço no ar, porém com os JOBS comentados (item 1 mais abaixo);
- Ambiente do TSS conectado e configurado dentro do VSCODE.

Solução:
1. Pare o serviço do TSS e comente a seção [ONSTART] do arquivo appserver.ini do seu TSS, colocando um ";" no início e salve as alterações, conforme imagem abaixo.


2. Verifique se os arquivos sigaadv.pss item (1) e sigapss.spf item (2) estão presentes dentro da pasta /system do seu TSS. Verifique imagem abaixo. 


3. O arquivo de patch tem a extensão .ptm e deve ser selecionado conforme a versão do seu TSS item (1). Sugerimos que seja criado uma pasta dentro da pasta raiz do seu TSS para salvar o patch que será utilizado item (2).

 

4. Instalação e configuração do Plug-in do TDS para VSCode
Para continuidade, recomendamos seguir os procedimentos dos vídeos abaixo. Caso já tenha efetuado as configurações e a conexão do seu ambiente com o appserver, avance para o passo 5.

 

5. Configure a porta TCP do seu TSS no arquivo smartclient.ini com a mesma porta informada no appserver.ini, conforme imagem abaixo:

Arquivo appserver.ini, localizado em \bin\appserver:

Arquivo smartclient.ini, localizado em \bin\appserver:

A partir desse ponto, acompanhe a ilustração abaixo para criar corretamente a conexão.

6. Abra seu VSCode e acesse a barra de ferramentas disponível na lateral esquerda na posição vertical, o atalho TOTVS AppServer Ícone do plug-in da TOTVS no VSCode, destacado no item (1) abaixo, depois clique no na opção na caixa superior de filtro, item(2).


Selecione o ambiente que criado (ou o ambiente que deseja aplicar o patch), clique com o botão direito do seu mouse em seguida clique em "Connect" item (1), conforme imagem abaixo.


Inicie o serviço do TSS. Recomendamos que seja iniciado em modo console.


Em um ambiente já conectado, clique com o botão direto e selecione a opção "Patch Apply"

As opções do ambiente já virão preenchidas automaticamente item (1).

Clique em "Escolher Arquivos" item (2), navegue até a pasta em que salvou o patch desejado e clique em "Abrir"

 

Clique em "Aplly" ou "Apply/Close"

 

Verifique o console do seu TSS, pois nele deverá indicar os arquivos que foram atualizados nessa patch.

Na Aba "Output" do seu VSCode, irá indicar se o patch foi aplicado com sucesso "Patch (xxxx) successfully applied.".

 

Caso essa aba não esteja aparecendo para você, aperte CTRL + ' (Aspa simples) no seu teclado.

 

Após realizada a aplicação do patch aplicado com sucesso, retire o comentário ";" da seção [ONSTART] no arquivo appserver.ini e reiniciar o serviço do TSS, conforme imagem.

 

Aplicação de patch finalizada e TSS pronto para uso.


Observações
Obs.: Para aplicação do pacote, sugerimos que o binário e

[... conteudo truncado, ver artigo completo ...]

---

### Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Configuração do DBACCESS para o TSS

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/23502657258647-Cross-Segmentos-TSS-Transmiss%C3%A3o-de-Documentos-Eletr%C3%B4nicos-Configura%C3%A7%C3%A3o-do-DBACCESS-para-o-TSS

Dúvida
Como realizar a instalação e configuração do DBAccess para Windows.

 

Ambiente
Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Todas as versões

 

Solução

Passo 1: Para a instalação e configuração do DBAccess é necessário efetuar a Configuração da fonte de dados ODBC:

Cross Segmentos - Backoffice Protheus - TSS - Configuração da fonte de dados ODBC

 

Passo 2: Instalação DBAccess

O DBAccess não possui executável, para sua instalação, realize as instruções a seguir:

 

Faça o dowloand do arquivo e descompacte no local de preferencia na máquina ou no servidor.

Win 64: Download Dbacess Windows

Linux: Download Dbacess Linux

 

**O DBACCESS não depende de licença para uso**

Guia de instalação do Dbaccess:

http://tdn.totvs.com.br/pages/viewpage.action?pageId=6064461

 

Caso ja possua um DBACCESS instalado para outra aplicação Totvs e vá instalar um DBACCESS exclusivo para o TSS, será necessário adicionar no dbaccess.ini do novo DBACCESS  e as linhas [GENERAL] e [SERVICE] para diferenciar a porta e o serviço do novo DBACCESS

Ex:

[General]

Port=7891 -> porta diferente da primeira instalação

[SERVICE]

NAME=DBACCESS_TSS -> nome do serviço diferente do primeiro

DISPLAYNAME=DBACCESS_TSS

 

Configuração do DBAccess:

1 - Para iniciar o aplicativo, é necessário que o serviço “TOTVSDBAccess64” esteja iniciado por serviço do Windows ou em modo console.

​Ao iniciar o aplicativo DBMonitor.exe na pasta TOTVSDBAccess64 criada, irá aparecer uma janela, como mostra a figura abaixo com as portas “Servidor: localhost” e a “Porta:7890” como default: 

 

 

2 - Após clicar em OK, o DBMonitor irá iniciar uma tela mostrando as informações de conexão com o banco de dados:

 

 

3 - Na aba Configurações, sub aba Microsoft SQL, preencha os campos nome e senha com os dados do usuário utilizado para criação da fonte de dados ODBC:

 

4 - Após salvar as configurações do usuário, acesse a aba Assistentes > Validação de conexão.

Selecione o tipo de banco de dados.

Este processo é executado para testar a comunicação entre o DBAccess e base de dados.

 

5 - Será solicitado o preenchimento do nome do ambiente a ser testado.

Preencha o nome da fonte de dados ODBC criada, clique em finalizar logo em seguida OK:

​


Para mais informações acesse:

 

Caso precise apenas validar os dados de configuração do banco de dados devem seguir apenas o Passo 1 (configuração do ODBC) e a validação de comunicação com o banco de dados no DBMonitor.

---

### Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Configuração parâmetros evento de desacordo de CTE

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/21132103099799-Cross-Segmentos-TSS-Transmiss%C3%A3o-de-Documentos-Eletr%C3%B4nicos-Configura%C3%A7%C3%A3o-par%C3%A2metros-evento-de-desacordo-de-CTE

Dúvida
 Como configurar a versão correta para o evento de desacordo de CTE?
  
Ambiente
Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Todas as versões
 
Solução
Para alterar a versão do evento de desacordo do CTE devem acessar a rotina de documentos de entrada Outras ações > Ev. Desacordo > Parâmetros:


É importante que alterem como o exemplo da imagem abaixo:
(FAVOR REFAZER ATÉ CLICAR NO BOTÃO "OK" PARA RECONFIGURAR O TSS)
Além da configuração da rotina de documento de entrada devem confirmar as configurações da versão do CTE na rotina de faturamento como abaixo:
 
Acesse a rotina de Faturamento > Atualizações > Nf-e e Nfs-e > Nf-e Sefaz.

 

Dentro da rotina Parâmetros > Nfe/CTE etc. Verifique se os parâmetros estão corretos, conforme o exemplo abaixo:

 

 

Após informar os parâmetros nas duas rotinas, confirme clicando em + Salvar como grupo administrador e clique em "OK" para confirmar.

 

Obs: Caso não esteja disponível a versão 4.00 para o CT-e, será necessário atualizar a rotina SPEDNFE aplicando o patch abaixo de acordo com sua versão do Protheus (Deve ser aplicado no RPO do Protheus):




Protheus 12.1.2310: Clique aqui para download.

Protheus 12.1.2410: Clique aqui para download.

 

Caso não tenham realizado as atualizações da versão 4.00 do CTE para o TSS é necessário que apliquem as atualizações abaixo no TSS:

MP - TSS - Atualização do Repositório (RPO) do TSS

TSS - Atualização das URLs do TSS

 

Após realizado a configuração devem fazer o envio do evento de desacordo.

---

### Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Consulta Chave CTEOS

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360015997531-Cross-Segmentos-TSS-Transmiss%C3%A3o-de-Documentos-Eletr%C3%B4nicos-Consulta-Chave-CTEOS

Dúvida
Como consultar a chave de acesso de CTEOS?



Ambiente
Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Todas as versões

Solução
A rotina de compras utiliza os parâmetros e o certificado do TSS para consultar as chaves. Para corrigir essa mensagem, é necessário verificar se o certificado da filial que está consultando o documento está válido e se os parâmetros estão configurados como indicado abaixo:

Acesse a rotina de Faturamento > Atualizações > Nf-e e Nfs-e > Nf-e Sefaz.


Dentro da rotina, redefina os parâmetros em Outras ações > Parâmetros > CTEos etc. Verifique se os parâmetros estão corretos, conforme o exemplo abaixo:

 

 

Após informar os parâmetros, confirme clicando em + Salvar como grupo administrador e clique em "OK" para confirmar.

É necessário que o RPO do TSS também esteja atualizado devido a correções realizadas recentemente:
MP - TSS - Atualização do Repositório (RPO) do TSS

 

Importante: As URL's devem estar atualizadas, conforme link abaixo:
Atualização URL

 
Feito isso, siga o procedimento para criar a espécie CTE-OS conforme link abaixo:
Como incluir Conhecimento de Transportes, modelo 67 (Espécie CT-e OS)



Para habilitar o campo de chave para espécie CTE-OS no documento de entrada:

Verifique se existe o parâmetro MV_CHVESPE em seu ambiente. Caso sim, informe a espécie CTEOS neste parâmetro. 

Caso não existir, você pode cadastrá-lo manualmente:
Parâmetro: MV_CHVESPE
Tipo: Caractere
Cont. Por: (Informar as espécies que devem possuir chave)
Descrição: Define quais Espécies de Nota Fiscal permite a geração da chave da DANFE.


Se mesmo assim não conseguir consultar a chave,  na tabela SPED000 do TSS os parâmetros devem ficar conforme abaixo:

MV_ACTEOS = 1
MV_MCTEOS  = 1
MV_VCTEOS  = 4.00

 

Obs: Caso não esteja disponível a versão 4.00 para o CT-e/CTeOS , será necessário atualizar a rotina SPEDNFE aplicando o patch abaixo de acordo com sua versão do Protheus (Deve ser aplicado no RPO do Protheus):

Protheus 12.1.2310: Clique aqui para download.

Protheus 12.1.2410: Clique aqui para download.

---

### Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Criação e atualização do parâmetro MV_RTC130

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/36864716890135-Cross-Segmentos-TSS-Transmiss%C3%A3o-de-Documentos-Eletr%C3%B4nicos-Cria%C3%A7%C3%A3o-e-atualiza%C3%A7%C3%A3o-do-par%C3%A2metro-MV-RTC130

Tempo aproximado para leitura: 00:03:00 min

Dúvida

Como efetuar a criação do parametro MV_RTC130 na tabela SPED000?

Ambiente
Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Todas as versões


Solução

O parâmetro é criado automaticamente caso esteja com o RPO do TSS atualizado

 

Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Atualização do Repositório (RPO) do TSS

 

Caso não exista o parâmetro na base de dados do TSS o mesmo será criado sem entidade vinculada, com a data de 05/01/2025 no ato da emissão de uma nota com IBS/CBS.

 

No caso da necessidade da parametrização por entidade, será necessario efetuar a criação ou alteração manualmente e inserir o ID_ENT necessario.

---

### Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Erro ao subir o serviço do TSS

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/4405004041623-Cross-Segmentos-TSS-Transmiss%C3%A3o-de-Documentos-Eletr%C3%B4nicos-Erro-ao-subir-o-servi%C3%A7o-do-TSS

Dúvida
Como verificar o erro ao subir o serviço do TSS

Ambiente
Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Todas as versões


Solução
1. Verifique na pasta do TSS \bin\appserver procure o arquivo console.log;

2. Após isso, verifique o último  erro no console.log do TSS ;

3. Realize a busca pelo erro apresentado no console.log do TSS ;

 

Saiba mais:
Caso o TSS seja no Cloud da TOTVS verificar as orientações abaixo:
Cross Segmentos - TSS - Suporte do Cloud reiniciar o serviço ou servidor

---

### Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Logo no Danfe enviado automaticamente

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360018871591-Cross-Segmentos-TSS-Transmiss%C3%A3o-de-Documentos-Eletr%C3%B4nicos-Logo-no-Danfe-enviado-automaticamente

Dúvida
Como configurar o logo no DANFE em PDF enviada pelo TSS? 

 

Ambiente
Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Todas as versões

Solução
O procedimento abaixo está disponível para configuração do LOGOTIPO no DANFE enviado automaticamente.

 

1. Para configurar  o LOGO do Danfe da empresa, basta criar um arquivo na pasta SYSTEM do TSS, com o seguinte nome:

"LGRL+CNPJ"_DANFE.BMP
Exemplo: "LGRL321999888000199_DANFE.BMP”

 

2. A dimensão recomendada para o arquivo BMP é de 90 x 90. Formato: BMP de 256 cores




Pasta SYSTEM do TSS:

 

OBS: O TSS só envia DANFE em formato retrato (DANFEII).

---

### Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Migração para 12.1.2410 - (Instalação)

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360038065954-Cross-Segmentos-TSS-Transmiss%C3%A3o-de-Documentos-Eletr%C3%B4nicos-Migra%C3%A7%C3%A3o-para-12-1-2410-Instala%C3%A7%C3%A3o

Dúvida
Como migrar o TSS para a última release (12.1.2410)? 

Ambiente
Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Todas as versões


Solução
O TSS 12.1.2410 é um produto diferente das versões anteriores e é compatível com diferentes versões de ERP, sendo necessário que seja efetuada uma nova instalação e não seja reutilizado nenhum arquivo de configuração referente as releases anteriores (pastas, appserver.ini e etc.).

Mesmo que não seja reaproveitado o arquivo appserver.ini, é possível reutilizar APENAS as portas de conexões TCP, HTTP e até mesmo a URL do serviço.

Para essa nova versão devem atualizar o DBAccess antes de migração e checar se o banco de dados utilizado no ambiente é compatível:
- Framework - Linha Protheus - Atualização do DBAccess
- Engenharia - Linha Protheus - Banco de Dados Homologados

Após a migração, é necessário que atualizem o arquivo do dbapi.dll (para Windows) ou dbapi.so (para Linux) dentro da pasta do Appserver do TSS, de acordo com a versão do DBAccess utilizada. (Giff com o processo de atualização: clique aqui.)

O banco de dados poderá ser o mesmo, pois ao subir o novo serviço o próprio sistema fica encarregado de atualizar os índices e estruturas das tabelas.

É necessário notar que a versão 12.1.2410 possui um binário e um RPO especifico para essa versão, deve-se atentar para não aplicar atualizações referente a releases diferentes. 

O uso do smartclient foi descontinuado na release 2410, desta forma no processo de funcionamento padrão do sistema não será possível utilizar o smartclient de versões anteriores. Sendo assim, o acesso deverá ser realizado via WebApp: detalhes clicando aqui.

Após a migração deverá ser instalado o webagent e atualizar o webapp.dll na pasta appserver para ter acesso as interfaces gráficas do TSS, que a partir dessa versão será via web:
- https://tdn.totvs.com/display/tec/2.+WebApp+-+WebAgent

Webapp
- https://suporte.totvs.com/portal/p/10098/download#detail/1168455 (Windows 64)
- https://suporte.totvs.com/portal/p/10098/download#detail/1168456 (Linux)

Instaladores Release 12.1.2410:
- Windows: clique aqui.
- Linux: clique aqui.


Importante

Após Instalação, será necessário aplicar as ultimas atualizações do binário e fontes (RPO) disponibilizados conforme consta na documentação abaixo:
- MP - TSS - Atualização do Appserver (binário) do TSS
- MP - TSS - Atualização do Repositório (RPO) do TSS
- TSS - Atualização dos SCHEMAS
- TSS - Atualização das URLs do TSS
- TSS Transmissão de Documentos Eletronicos - NFSe - Configuração do NEWNFSE


Processo de instalação do TSS:
- Instalação TSS on-line
- Instalação do TSS off-line


Atenção: A versão off-line do TSS deve ser utilizada apenas para os clientes que utilizam o módulo do loja para comunicação dos caixas com a retaguarda.

---

### Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Modelo do documento informado não corresponde a um Documento Eletrônico

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360019536732-Cross-Segmentos-TSS-Transmiss%C3%A3o-de-Documentos-Eletr%C3%B4nicos-Modelo-do-documento-informado-n%C3%A3o-corresponde-a-um-Documento-Eletr%C3%B4nico

Dúvida
Como corrigir a mensagem TOTVS SPED Services: 007 - Modelo do documento informado não corresponde a um Documento Eletrônico

Ambiente
Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Todas as versões

Solução
Verificar o conteúdo do parâmetro MV_ESPECIE se está correto e se o campo F3_ESPECIE da nota está igual a SPED.

Tabela SPED000 do TSS verificar o parâmetro MV_VERDPEC, deve estar com o conteúdo igual a 1.01 em todas as entidades.

Após configurações, exclua a nota, gere novamente e transmita.

---

### Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - NFSE - Logs de Comunicação

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/38125222453015-Cross-Segmentos-TSS-Transmiss%C3%A3o-de-Documentos-Eletr%C3%B4nicos-NFSE-Logs-de-Comunica%C3%A7%C3%A3o

Dúvida
Como realizar a configuração e geração dos métodos e logs de comunicação entre TSS x Prefeitura ou Governo?

Ambiente
Cross Segmento - TOTVS Backoffice (Linha TSS) - Todas as versões

Solução
Segue abaixo o passo a passo para o procedimento:

1. Alterar as chaves já existentes no Appserver.ini do TSS conforme abaixo:

SPED_SAVEWSDL=1 na seção [ENVIRONMENT]
XMLSAVEALL=1 na seção [JOB_WS]

Obs.: Caso não existam, poderão ser criadas. Atentar-se apenas para não haver duplicidades de chaves.

2. Após habilita-las, o serviço do TSS deverá ser reiniciado para que seja acatado.

3. Qualquer tipo de processo, tais como: Transmissão, Cancelamento, Consultas, entre outros, serão gerados e gravados os métodos e logs nas pastas SYSTEM e WSLOGXML do TSS:

---

### Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Recriar tabela do TSS - Open Index error

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360020726352-Cross-Segmentos-TSS-Transmiss%C3%A3o-de-Documentos-Eletr%C3%B4nicos-Recriar-tabela-do-TSS-Open-Index-error

Dúvida
Quando é necessário recriar uma tabela do TSS ou ocorre o erro de OpenIndex no console.log do TSS.

Ambiente
Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Todas as versões

Solução
Para recriar uma tabela, deverão ser realizados os seguintes passos abaixo:

1. IMPORTANTE! Efetuar um backup da tabela em questão;
2. Dropar a tabela que está ocorrendo erro;
3. Apague o conteúdo do parâmetro MV_VERDB na tabela SPED000;
4. Apague a pasta Semáforo do TSS e depois reinicie o serviço do TSS.

Esse processo irá fazer com que o TSS recrie os índices e as tabelas necessárias.
Caso o problema ocorra para outras tabelas repita o processo acima até que não ocorra mais erros.

---

### Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Redefinir senha do smartclient

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360017958372-Cross-Segmentos-TSS-Transmiss%C3%A3o-de-Documentos-Eletr%C3%B4nicos-Redefinir-senha-do-smartclient

Dúvida
Como redefinir a senha do smartclient do TSS?

Ambiente
Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - versões 12.1.2210 e 12.1.2310

Solução
1. Abra a pasta System do TSS;
2. Apagar ou alterar o nome do arquivo smallapppss.spf;
3. Acessar o smartclient e selecionar o Programa inicial TSSMONITOR;



4. Em Usuário informar ADMIN;
5. Em Senha informar ADMIN;



6. Informar uma nova senha para o usuário ADMIN.





OBS: Realizar este processo irá remover os usuários cadastrados anteriormente dentro do smartclient do TSS.
O usuário ADMIN somente é utilizado para cadastrar novos usuários.

---

### Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Versão do arquivo XML não suportada

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360043313513-Cross-Segmentos-TSS-Transmiss%C3%A3o-de-Documentos-Eletr%C3%B4nicos-Vers%C3%A3o-do-arquivo-XML-n%C3%A3o-suportada

Dúvida
Como corrigir a rejeição abaixo, ao transmitir evento Desacorde de CTe?
Rejeição 239: Cabeçalho - Versão do arquivo XML não suportada.

Ambiente
Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Todas as versões

Solução

Para alterar a versão do evento de desacordo do CTE devem acessar a rotina de documentos de entrada Outras ações > Ev. Desacordo > Parâmetros:


É importante que alterem como o exemplo da imagem abaixo:
(FAVOR REFAZER ATÉ CLICAR NO BOTÃO "OK" PARA RECONFIGURAR O TSS)
Além da configuração da rotina de documento de entrada devem confirmar as configurações da versão do CTE na rotina de faturamento como abaixo:
 
Acesse a rotina de Faturamento > Atualizações > Nf-e e Nfs-e > Nf-e Sefaz.

 

Dentro da rotina Parâmetros > Nfe/CTE etc. Verifique se os parâmetros estão corretos, conforme o exemplo abaixo:

 

 

Após informar os parâmetros nas duas rotinas, confirme clicando em + Salvar como grupo administrador e clique em "OK" para confirmar.

---

### Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - WSCERR047 / XML Error Start tag expected, '<' not found

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360039667893-Cross-Segmentos-TSS-Transmiss%C3%A3o-de-Documentos-Eletr%C3%B4nicos-WSCERR047-XML-Error-Start-tag-expected-not-found

Dúvida
WSCERR047 / XML Error Start tag expected, '<' not found

Ambiente
Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Todas as versões


Solução
Verifique o console.log do TSS se apresenta a mensagem:


TOPConnect (INI Protheus Server) Database: ERROR

Esse erro é causado por algum tipo de inconsistência de comunicação entre o TSS e Banco de Dados.

1 - Abra o arquivo appserver.ini do TSS e vá na sessão [TOPCONNECT] e veja qual o alias preenchido;

2 - Verifique se o ALIAS preenchido é o mesmo configurado no ODBC (SQL) ou no arquivo TNSNAMES.ORA (Oracle). Se for diferente o ALIAS no arquivo APPSERVER.INI do TSS, modifique-o para o mesmo nome da conexão ODBC ou TNSNAMES. Feito isso refaça as validações de conexão;

3 - No DBAccess valide a conexão com o banco de dados.

---

### Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Wscerr047 / xml error extra content at the end of the document

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/22313779614359-Cross-Segmentos-TSS-Transmiss%C3%A3o-de-Documentos-Eletr%C3%B4nicos-Wscerr047-xml-error-extra-content-at-the-end-of-the-document

Dúvida

Como corrigir o erro wscerr047 / xml error extra content at the end of the document

Ambiente
Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Todas as versões


Solução

Geralmente esse erro tem relação com problema de conexão entre TSS x DBACCESS. ocorre devido a falta de comunicação do banco de dados com o TSS.

 

Nesse caso deve revisar as suas configurações de ODBC e DBACCESS.


Abaixo segue documentações auxiliando a configuração da fonte de dados do ODBC e DBACCESS:

Cross Segmentos - Backoffice Protheus - TSS - Configuração da fonte de dados ODBC

Cross Segmentos - Backoffice Protheus - TSS - Configuração do DBACCESS para o TSS

 

Em seguida verifique se as bibliotecas do DBAccess se encontram atualizadas com o procedimento abaixo.

Link do gif: https://bit.ly/3CX2aI9


Segue tutorial para atualização da DBApi: (terá que realizar esse processo no Apperver do TSS e do protheus)

TEC - APPSERVER - Instruções para atualização da dbapi

---

### Cross Segmentos - TSS Transmissão de Documentos Eletrônicos -Configuração TSS com autenticação - Chave TSSSECURITY

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/4412593739287-Cross-Segmentos-TSS-Transmiss%C3%A3o-de-Documentos-Eletr%C3%B4nicos-Configura%C3%A7%C3%A3o-TSS-com-autentica%C3%A7%C3%A3o-Chave-TSSSECURITY

Dúvida
Como configurar o TSS com autenticação - Chave TSSSECURITY ?

Ambiente
Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Todas as versões


Solução


 

 

 

Para realizar a configuração da autenticação do TSS, basta seguir o passo a passo abaixo:

1 - Criar a configuração TSSSECURITY na seção JOB_WS.

Esta configuração é habilitada por padrão.

 

Exemplo:

 

 

1 = Ativado

0 = Desativado

 

2- Após isso, reinicie o serviço do TSS.

Saiba mais:

 

Clique Aqui

---

### Cross Segmentos - TSS Transmissão de Documentos Eletrônicos- Como acessar o TSS via APSDU para extração de tabelas

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/1500004954381-Cross-Segmentos-TSS-Transmiss%C3%A3o-de-Documentos-Eletr%C3%B4nicos-Como-acessar-o-TSS-via-APSDU-para-extra%C3%A7%C3%A3o-de-tabelas

Dúvida
Como acessar a APSDU do TSS ?


Ambiente
Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Todas as versões


Solução
Para acessar o banco de dados pelo smartclient para extração de tabelas, acesse a APSDU.

 

1 - Acesse a pasta de instalação do TSS e execute o smartclient.exe:

Diretório: Raiz de instalação do TSS -> BIN -> SMARTCLIENT

 

2 - Dê duplo no atalho no SmartClient, e irá aparecer a seguinte tela. No programa inicial, digite: APSDU e clique em Ok:

Obs: O ambiente do servidor por padrão no TSS é SPED, caso na instalação tenha sido alterado, verifique o arquivo appserver.ini.

Diretório do appserver.ini : Raiz de instalação do TSS -> BIN -> appserver.ini

 

3 - Acesse com admin e senha em branco;

 

4 - Para acessar as tabelas do ambiente do TSS, clique em Arquivo -> Abrir:

 

5 - Seleciona o driver "TopConnect (TOPCONN)":

 

6 - Confirme os dados de conexão com o banco de dados e clique em Ok:

 

7 - Na tela a seguir, informe o nome da tabela que deseja abrir e clique em Ok:

 

8 - Faça o filtro(Ctrl+F ) necessário para localizar o documento ou a entidade em questão.
No exemplo abaixo, filtramos a SPED000 pela entidade que representa a filial, clique incluir e posteriormente em Ok:

Campos = Nome do campo que deseja realizar o filtro

Operadores = Condição para ser usado no filtro

Expressão = Conteúdo a ser filtrado

 

9 - Após filtro, copie o conteúdo filtrado para envio ao suporte em ÚTIL -> Copiar para:

 

10 - No caminho, clique nos três pontos(...) e informe o caminho onde será salvo o arquivo.

Obs: No driver sempre deixe Ctree

 

Após estes passos, localize o arquivo salvo no diretório informado e envie ao suporte para prosseguir com a analise.

---


## Instalacao, Migracao e Atualizacao

### Cross Segmentos - Backoffice Protheus - TSS - Instalação TSS OFFLINE

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/23538725442583-Cross-Segmentos-Backoffice-Protheus-TSS-Instala%C3%A7%C3%A3o-TSS-OFFLINE

Dúvida
Como instalar o TSS OFFLINE.

Ambiente
Cross Segmento - TOTVS Backoffice (Linha Protheus) - TOTVS Documentos Eletrônicos - Todas as versões.

Solução
Se o sistema ERP não conseguir se comunicar com o TSS Online, os processos que dependem do TSS ficarão inativos. Para lidar com essa situação, foi desenvolvido o TSS Offline, que permite a transmissão de documentos eletrônicos em modo offline, como NFC-e e NF-e, disponibilizados pelo Fisco para contingências offline.

Importante: O TSS Offline deve ser usado somente por clientes que utilizam o módulo da loja para a comunicação entre os caixas e a retaguarda.

Instaladores Release 12.1.2410:
- Windows: clique aqui.
- Linux: clique aqui.

Passo a passo da instalação: https://tdn.totvs.com.br/pages/releaseview.action?pageId=274324712

 

Segue abaixo estrutura do TSS Offline:

Configuração do arquivo .INI
Ao realizar o procedimento de instalação do TSS Off-Line será gerado o arquivo INI com a estrutura similar do TSS ON-Line, adicionado com as seguintes seções.

 

Nesta seção do TSS Off-Line deverá ser colocada o endereço do TSS On-Line para que seja feita a correta conexão:

[TSSOFFLINE]

TSSOFFLINE=1

ONLINEURL=localhost (Exemplo de endereço do TSS On-Line)

ONLINEPORT=8080 (Exemplo de endereço do TSS On-Line)

 

O Job responsável pela realização do processo de envio das requisições para o TSS On-Line. Verificará se o serviço do TSS On-Line está disponível, realizando o envio das requisições, consultas, e seus respectivo controle de semáforos.

 

Este procedimento será realizado enquanto a aplicação estiver disponível e a cada dois segundos.

[JOB_OFFLINE]

main=JOB_DLL

environment=SPED

 

Indica o nome da sessão para executar as funções.

[ONSTART]

JOBS=JOB_OFFLINE

refreshrate=10

 

A partir do momento que o TSS Off-Line estiver corretamente configurado, a funcionalidade Off Line será ativada automaticamente caso haja a perda de comunicação com o TSS On-Line.

 

Obs: Após a configuração do TSSOFFLINE será necessário realizar as duas vendas no TSSONLINE , Com isso a carga de Entidade e Parâmetros aconteça no OFFLINE e possa ser utilizado posteriormente.

---

### Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Atualização dos SCHEMAS

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360025103552-Cross-Segmentos-TSS-Transmiss%C3%A3o-de-Documentos-Eletr%C3%B4nicos-Atualiza%C3%A7%C3%A3o-dos-SCHEMAS

Dúvida
Como atualizar os Schemas do TSS?

Ambiente
Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Todas as versões


Solução
Segue o link para download dos SCHEMAS de acordo com a release correspondente:

- Clique aqui para download

Para atualizar os SCHEMAS é preciso copiar todo conteúdo do arquivo baixado e colar dentro da pasta SCHEMAS existente na estrutura onde está instalado o TSS. 

Exemplo:

Substitua os arquivos antigos da pasta pelos novos.

---


## Erros Comuns e Rejeicoes

### Cross Segmentos - Backoffice Protheus - TSS - Mensagem "chave digitada não foi encontrada na Sefaz" na entrada ou consulta de documentos fiscais em momentos de indisponibilidade da Sefaz

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/23325552921623-Cross-Segmentos-Backoffice-Protheus-TSS-Mensagem-chave-digitada-n%C3%A3o-foi-encontrada-na-Sefaz-na-entrada-ou-consulta-de-documentos-fiscais-em-momentos-de-indisponibilidade-da-Sefaz

Dúvida
Mensagem "Chave digitada não encontrada na Sefaz", quando ocorre indisponibilidade da Sefaz.

Ambiente
Cross Segmento - TOTVS Backoffice (Linha Protheus) - TOTVS Documentos Eletrônicos - Todas as versões.

Solução

Nos momentos em que há intermitência, parada ou ativação do ambiente de contingência da Sefaz, as consultas de chave podem resultar na exibição dessa mensagem ou falhar devido à indisponibilidade do serviço de consultas.

- Os serviços da Sefaz podem ser acessados através do site oficial da Secretaria da Fazenda:

https://www.nfe.fazenda.gov.br/portal/principal.aspx 

É importante ressaltar que a Sefaz de alguns Estados, como a Sefaz do RS, é responsável pela transmissão de documentos de outros locais, tais como: AC, AL, AP, CE, DF, ES, PA, PB, PI, RJ, RN, RO, RR, SC, SE e TO. Portanto, a instabilidade nos serviços do RS impacta todos os Estados que dependem dessa Sefaz.

Nesse cenário, é necessário aguardar a normalização da Sefaz para que o serviço de consulta seja restabelecido.

Para realizar a entrada de documentos sem a consulta da chave, é preciso desabilitar o parâmetro MV_CHVNFE.

---

### Cross Segmentos - Backoffice Protheus - TSS - Nota Técnica 2024.001 do MDF-e - Serviço síncrono - Rejeição 996

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/24403982304151-Cross-Segmentos-Backoffice-Protheus-TSS-Nota-T%C3%A9cnica-2024-001-do-MDF-e-Servi%C3%A7o-s%C3%ADncrono-Rejei%C3%A7%C3%A3o-996

Dúvida
Nota Técnica 2024.001 do MDF-e - Serviço síncrono ?


Ambiente
Cross Segmento - TOTVS Backoffice (Linha Protheus) - TOTVS Documentos Eletrônicos - Todas as versões.


Solução
Para a adequação à Nota Técnica 2024.001 do MDF-e. 

Conforme aviso do ENCAT, o serviço assíncrono de MDF-e será desativado em 30/06/2024. Sendo necessário realizar a migração para o serviço síncrono de recepção do documento.

 

 

Solução:

Foi gerado um novo client para o modelo de recepção síncrona e realizada uma tratativa no momento do processamento para chamar o serviço síncrono. 

De acordo com as características deste novo serviço, não será possível o envio de documentos em lote. Agora ocorrerá o envio único de cada MDF-e. Da mesma forma, irá funcionar a consulta do status. 

Vale ressaltar que é essencial estar com as URLs atualizadas para o correto funcionamento do processo.

 

Importante

O pacote citado nesta documentação deve ser aplicado no ambiente do TSS.


1 - Atualizar os schemas do TSS: 
TSS - Atualização dos SCHEMAS

2 - Atualizar as URLs do TSS:
TSS - Atualização das URLs do TSS
Adicionar o arquivo tssatuurl.json de URLs dentro da pasta system e reiniciar o serviço do appserver.

3 - Substituir o RPO do TSS pelo da documentação abaixo:
MP - TSS - Atualização do Repositório (RPO) do TSS

Atenção

Essa alteração não causará impacto no ERP. Apenas no produto TSS (Transmissão de Documentos Eletrônicos).

Para o funcionamento adequado da transmissão utilizando o serviço síncrono do MDF-e, não será necessário realizar mais nenhuma configuração além dos passos citados no card acima (Importante).

Manual MDF-e

---

### Cross Segmentos - Backoffice Protheus - TSS - Rejeição 005 - inffretamento. this element is not expected

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360022390572-Cross-Segmentos-Backoffice-Protheus-TSS-Rejei%C3%A7%C3%A3o-005-inffretamento-this-element-is-not-expected

Dúvida
Transmissão do Cteos -apresentando CTEOS - REJEIÇÃO 005 - infFretamento. This element is not expected


Ambiente
Cross Segmento - TOTVS Backoffice (Linha Protheus) - TOTVS Documentos Eletrônicos - Todas as versões.

Solução



O campo GZH_HSAIDA (Hora Saída), deve ser preenchido no formato HH:MM:SS, conforme imagem abaixo:

---

### Cross Segmentos - TSS - CTE - 402 Rejeição : XML da área de dados com codificação diferente de UTF-8, ao transmitir Desacordo de CTe

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360051661394-Cross-Segmentos-TSS-CTE-402-Rejei%C3%A7%C3%A3o-XML-da-%C3%A1rea-de-dados-com-codifica%C3%A7%C3%A3o-diferente-de-UTF-8-ao-transmitir-Desacordo-de-CTe

Dúvida
Como corrigir a rejeição abaixo, ao transmitir evento de Desacordo de CTe?
Rejeição 402: XML da área de dados com codificação diferente de UTF-8.

Ambiente
Protheus a partir da versão 11.
TSS a partir da versão 11.

Solução
Esta rejeição costuma ocorrer quando está utilizando caracteres especiais na mensagem digitada, que é gravada na tag <xObs> do xml gravado no campo XML_ERP da tabela SPED150 do TSS.
Caso não tenha informado caracteres especiais, é um sinal de que está com o TSS desatualizado.

Com o TSS desatualizado a tag a seguir leva caracteres especiais na descrição <descEvento>Prestação do Serviço em Desacordo</descEvento>. Com o TSS atualizado a partir de 10/2018 este incidente foi corrigido.

Para correção paliativa, deve ajustar os caracteres especiais desta tag e retransmitir o evento de Desacordo.
Para correção permanente, deve atualizar o TSS.

Vale lembrar que caso esteja com o TSS no formato 3.0, não será possível este ajuste manual no xml devido a dinâmica do processo 3.0.

Segue link para atualização do TSS: https://centraldeatendimento.totvs.com/hc/pt-br/articles/360025392671-TSS-Atualiza%C3%A7%C3%B5es-do-TSS-Totvs-Sped-Service-Release-12-1-25-12-1-27

---

### Cross Segmentos - TSS - CTEOS - Rejeição 851: Endereço do site da UF da Consulta via QR Code diverge do previsto

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360043515433-Cross-Segmentos-TSS-CTEOS-Rejei%C3%A7%C3%A3o-851-Endere%C3%A7o-do-site-da-UF-da-Consulta-via-QR-Code-diverge-do-previsto

Dúvida
Como corrigir a rejeição abaixo, na transmissão de CTeos?
Rejeição 851: Endereço do site da UF da Consulta via QR Code diverge do previsto.

Ambiente
Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Todas as versões
Solução
Para correção da rejeição 851, é necessário realizar a atualização do rdmake XMLCTEOS_V3 com data maior ou igual a 09/10/2019.


Este rdmake está contido nos pacotes abaixo:
https://suporte.totvs.com/portal/p/10098/download#detail/1152113  

Basta atualizar apenas o fonte (rdmake) .prw, sem a necessidade de aplicar o patch .ptm.

*Importante: Caso tenha customização neste rdmake, será necessário compatibilizar com o padrão antes da atualização em seu ambiente.

Após a atualização com este rdmake, retransmita o documento rejeitado.

---


## Seguranca, SSL e Certificados

### Cross Segmentos - TSS - Consultar validade de certificado digital

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360058392933-Cross-Segmentos-TSS-Consultar-validade-de-certificado-digital

Dúvida

Como consultar a validade do certificado digital no TSS?

Ambiente

A partir da versão TSS 12.1.17


Solução


Utilize  a ferramenta TSSInterface e acesse a opção Certificado.

 

 

 

Caso nunca tenha acessado as interfaces gráficas do TSS, segue boletim técnico: 

 

http://tdn.totvs.com/pages/releaseview.action?pageId=239016058

---

### Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Abrindo muitas seções no Banco e não fecha

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360037035794-Cross-Segmentos-TSS-Transmiss%C3%A3o-de-Documentos-Eletr%C3%B4nicos-Abrindo-muitas-se%C3%A7%C3%B5es-no-Banco-e-n%C3%A3o-fecha

Dúvida
TSS Abrindo muitas seções no Banco e não fecha.

Ambiente
Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Todas as versões


Solução
Deve ser utilizado o drive(Fonte de dados) recomentado pela Totvs, disponível na documentação abaixo. 
https://tdn.totvs.com/display/public/PROT/5+-+Fonte+de+dados+ODBC

 

Para SQL utilize a documentação abaixo:

https://tdn.totvs.com/display/tec/DBAccess+-+Como+criar+uma+fonte+de+dados+para+uso+com+Microsoft+SQL+Server

---

### Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Mensagem "chave digitada não foi encontrada na Sefaz" na entrada de documentos fiscais

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/20987715786263-Cross-Segmentos-TSS-Transmiss%C3%A3o-de-Documentos-Eletr%C3%B4nicos-Mensagem-chave-digitada-n%C3%A3o-foi-encontrada-na-Sefaz-na-entrada-de-documentos-fiscais

Dúvida


Como resolver o problema da mensagem "Chave digitada não encontrada na Sefaz", quando o documento está autorizado na Secretaria da Fazenda (Sefaz) e dentro do prazo de 6 meses (180 dias) para consulta?


Ambiente
Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Todas as versões


Solução

A rotina de compras utiliza os parâmetros e o certificado do TSS para consultar as chaves. Para corrigir essa mensagem, é necessário verificar se o certificado da filial que está consultando o documento está válido e se os parâmetros estão configurados como indicado abaixo:

 

Acesse a rotina de Faturamento > Atualizações > Nf-e e Nfs-e > Nf-e Sefaz.

 

Dentro da rotina, redefina os parâmetros em Outras ações > Parâmetros > Nfe/CTE/CTEos, etc. Verifique se os parâmetros estão corretos, conforme o exemplo abaixo:

 

 

 

Após informar os parâmetros, confirme clicando em + Salvar como grupo administrador e clique em "OK" para confirmar.

 

Obs: Caso não esteja disponível a versão 4.00 para o CT-e/CTeOS , será necessário atualizar a rotina SPEDNFE aplicando o patch abaixo de acordo com sua versão do Protheus (Deve ser aplicado no RPO do Protheus):

 

Protheus 12.1.2310: Clique aqui para download.
Protheus 12.1.2410: Clique aqui para download.

 

 

É necessário que o RPO do TSS também esteja atualizado devido a correções realizadas recentemente:

RPO TSS 12.1.2210 Download (Somente com garantia extendida)
RPO TSS 12.1.2310 Download
RPO TSS 12.1.2210 Download

 

Importante: As URL's devem estar atualizadas, conforme link abaixo:

Atualização URL

 

Em seguida, acesse Outras ações > Monitor > Consulta NFe pela chave, inserindo a chave da nota em questão.

 

Depois do procedimento teste novamente na rotina onde ocorreu o alerta.

 

Caso o erro persista após as ações acima, devem acionar o time de suporte para uma análise completa.

---

### Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Unificação das URLs SVAN e SVC-AN em Produção

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/28502950918551-Cross-Segmentos-TSS-Transmiss%C3%A3o-de-Documentos-Eletr%C3%B4nicos-Unifica%C3%A7%C3%A3o-das-URLs-SVAN-e-SVC-AN-em-Produ%C3%A7%C3%A3o

Dúvida
Como realizar a atualização da Unificação das URLs SVAN e SVC-AN em Produção

 

Ambiente
Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Todas as versões

 

Solução

Para a adequação à unificação das URLs SVAN e SVC-AN em produção aplicar as atualizações abaixo no TSS:

 

12.1.2310:https://r.totvs.io/p/1183485

12.1.2410:https://r.totvs.io/p/1183482

 

Mais informações: https://tdn.totvs.com/pages/viewpage.action?pageId=908670278

---


## Banco de Dados e Tabelas TSS

### Cross Segmentos - Backoffice Protheus - Doc. Eletrônicos - Como são alimentados os campos DATE_GXML, TIME_GXML e RESP_GXML da SPED050?

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/31662248961047-Cross-Segmentos-Backoffice-Protheus-Doc-Eletr%C3%B4nicos-Como-s%C3%A3o-alimentados-os-campos-DATE-GXML-TIME-GXML-e-RESP-GXML-da-SPED050

Dúvida
Como os campos DATE_GXML,TIME_GXML e RESP_GXML são alimentados na tabela SPED050?

Ambiente
Cross Segmento - TSS Transmissão de Documentos Eletrônicos - Todas as versões

Solução
Os campos DATE_GXML,TIME_GXML e RESP_GXML são alimentadas pelo TSS na tabela SPED050 no momento que a nota é transmitida por um usuário, exemplo:



Importante ressaltar que os campos em questão não são atualizados e/ou sobrescritos em casos em que posteriormente foi realizada a transmissão do cancelamento. Ou seja, permanecerão com os mesmos conteúdos, visto que os campos são destinados para: Data, Hora e Responsável pela Geração do XML, e não do cancelamento.

Do lado do Protheus, caso queira rastrear o usuário responsável pela exclusão do documento de saída, há algumas rotinas de Logs e Auditorias disponibilizadas pela equipe de Framework, as quais se faz necessário o contato com a equipe do próprio Framework.

---

### Cross Segmentos - Backoffice Protheus - TSS - Tabela TSS0012

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/4416967061911-Cross-Segmentos-Backoffice-Protheus-TSS-Tabela-TSS0012

Dúvida
Funcionalidade da tabela TSS0012

Ambiente
TSS -Versão 12.1.33

Solução

Nessa tabela é gravada as Credenciais para geração/validação do token de autenticação, nos campos: CLIENT_ID ("Client Id")
CLIENT_SEC ("Client Secret")

 

Nos campos  DATE_GER" e TIME_GER ficam registradas a Data\hora que foram gerada as Credenciais.

---

### Cross Segmentos - TSS - Processos do TSS 3.0

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360056482174-Cross-Segmentos-TSS-Processos-do-TSS-3-0

Dúvida

Quais são a lista Processos de Cada modelo de documento do TSS 3.0?

Ambiente
A partir da versão TSS 3.0


Solução
Tabela abaixo, Referente aos documentos eletrônicos:

Código

	

CodTipoDoc

	

Descrição

	

FuncName




101

	

001

	

Emissão de NF-e

	

TSSNfeEmissao




101

	

002

	

Emissao de CT-e

	

TSSCteEmissao




101

	

003

	

Emissao de MDF-e

	

TSSMdfeEmissao




101

	

004

	

Emissão de NFS-e

	

TSSNfseEmissao




101

	

005

	

Emissão de NFS-e SPED

	

TSSSNfseEmissao




101

	

006

	

Emissão de GNR-e

	

TSSGnreEmissao




101

	

007

	

Emissão de Eventos do E-Social

	

TSSESocial


101	009	Emissão de NFC-e emitidas em contingência	TSSNfceEmissao


102

	

001

	

Carta de Correção da NF-e (CC-e)

	

TSSCceNfe




102

	

002

	

Carta de Correção do CT-e (CC-e)

	

TSSCceCte




103

	

001

	

Cancelamento da NF-e

	

TSSNfeInutCanc




103

	

002

	

Cancelamento de CT-e

	

TSSCteInutCanc




103

	

003

	

Cancelamento de MDF-e

	

TSSMdfeCancela




103

	

004

	

Cancelamento de NFS-e

	

TSSNfseCancela




103

	

005

	

Cancelamento de NFS-e SPED

	

TSSSNfseCancela


103	009	Cancela ou Inutiliza as NFC-e	TSSNfceCanc


105

	

003

	

Encerramento MDF-e

	

TSSMdfeEncerra




106

	

001

	

Registro de Saída Siare

	

TSSNfeRegSaida




107

	

001

	

Cancelamento Registro de Saída Siare

	

TSSNfeCRegSaida




108

	

008

	

Eventos do MD-e

	

TSSMdeNfe


109	001	Emissão Epec NF-e	TSSNfeEpEmissao
109	002	Emissão Epec CT-e	TSSCteEpEmissao
110	003	Inclusão de Condutor MDF-e	TSSIncConMdfe
111	002	Registro Multi Modal CT-e	TSSRegModCte

---

### Cross Segmentos - TSS - Tabela TSS0010

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/1500003406882-Cross-Segmentos-TSS-Tabela-TSS0010

Dúvida
Qual a funcionalidade da tabela TSS0010 ?

Ambiente
TSS 25 e TSS27


Solução
A tabela TSS0010 é a tabela de schedule do TSS, nela contem todas as rotinas executadas pelo TSSTASKPROC.

---

### Cross Segmentos - TSS - Tabela de contingencia automática

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/1500000099061-Cross-Segmentos-TSS-Tabela-de-contingencia-autom%C3%A1tica

Dúvida
Qual é a tabela de contingencia automática, e qual o campo grava a informação que a contingencia esta Ativa.

Ambiente
Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Todas as versões
Solução
A tabela TSS0007 é de contingência automática.


Campo ATIVO=1   = Habilitada a contingencia automática.
Campo ATIVO= 0  = Desabilita a contingencia automática.


Observação: Campo MODALIDADE=Recebe o conteúdo da modalidade.

---

### Cross Segmentos - TSS - Tabelas do TSS envolvidas no processo do RECOPI

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360055479653-Cross-Segmentos-TSS-Tabelas-do-TSS-envolvidas-no-processo-do-RECOPI

Dúvida

Tabelas do TSS envolvidas no processo do RECOPI


Ambiente
TSS 11 e TSS12  
Protheus – A partir da versão 11.80

Solução
Tabelas TSS:
SPED090 - Solicitações de código de controle de Lote
SPED091 - Inclusão de Notas Fiscais
SPED092 - Confirmação das solicitações

---

### Cross Segmentos - TSS - tabela TSS0002

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360063819793-Cross-Segmentos-TSS-tabela-TSS0002

Dúvida
Funcionalidade da tabela tss0002

Ambiente
TSS25 e TSS27


Solução

Essa tabela tem objetivo de registrar os processos assíncronos do tss para uso interno de processamento.

Como por exemplo temos: Emissão, Cancelamento, Carta de correção etc.

Exemplo dos cadastros abaixo utilizados:

---

### Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - no free working threads for job JOB_WS

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360018011132-Cross-Segmentos-TSS-Transmiss%C3%A3o-de-Documentos-Eletr%C3%B4nicos-no-free-working-threads-for-job-JOB-WS

Dúvida: Como corrigir a mensagem "APW Call Failed - no free working threads for job JOB_WS" apresentada no console do TSS?

 

Ambiente: Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Todas as versões

 

Solução: A mensagem indica que o DBACCESS não possui mais threads disponíveis para execução. Quando algum processo é realizado no sistema, como abrir uma rotina ou uma nova janela, são consumidas threads do DBACCESS.

O TSS fica ativo o tempo todo e seus jobs são executados constantemente, e para cada job existem vários processos, como montagem do lote, assinatura, transmissão e retorno, eventos, e cada um desses processos também consome threads do DBACCESS. Portanto, quando é utilizado um único DBACCESS para o ERP e TSS, em algum momento o DBACCESS ficará sem threads disponíveis e impedirá o acesso.

 

A solução é realizar a instalação de um novo DBACCESS exclusivo para o TSS.

 

Aqui está o link para download do DBACCESS atualizado:

Windows: https://suporte.totvs.com/portal/p/10098/download?e=1168438

Linux: https://suporte.totvs.com/portal/p/10098/download?e=1168438

 

O DBACCESS e TSS não dependem de licença para uso.

 

Caso tenha dúvidas com a instalação, consulte o boletim técnico ou entre em contato com nosso setor do framework.

Guia de instalação do DBACCESS: http://tdn.totvs.com.br/pages/viewpage.action?pageId=6064461

 

Caso já possua um DBACCESS instalado, será necessário adicionar no dbaccess.ini do novo DBACCESS as linhas [GENERAL] e [SERVICE] para diferenciar a porta e o serviço do novo DBACCESS.

Exemplo:

[General]

Port=7891 -> porta diferente da primeira instalação

 

[SERVICE]

NAME=DBACCESS_TSS -> nome do serviço diferente do primeiro

DISPLAYNAME=DBACCESS_TSS

 

Após o procedimento, realize um novo teste.

 

Caso o erro persista, basta aumentar as INSTANCES de todos os Jobs no appserver.ini para 1.10.1.1.

Se necessário, é possível realizar testes usando no máximo 1.40.1.1.

---

### Cross Segmentos- TSS - Tabela TSS0011

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/1500003301041-Cross-Segmentos-TSS-Tabela-TSS0011

Dúvida
Qual a funcionalidade da tabela tss0011  ?

Ambiente
TSS 25 e TSS27


Solução
Faz o controle para limitar o consumo indevido,  para controlar as requisições na tabela tss0011 evitando o excesso no consumo da Sefaz.

---


## Monitoramento e Logs

### Cross Segmentos - Backoffice Protheus - TSS - Nota Técnica 2024.002 do MDF-e

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/23925949152151-Cross-Segmentos-Backoffice-Protheus-TSS-Nota-T%C3%A9cnica-2024-002-do-MDF-e

Dúvida
Quais serão as alterações da Nota Técnica 2024.002 do MDF-e ?

Ambiente
Cross Segmento - TOTVS Backoffice (Linha Protheus) - TOTVS Documentos Eletrônicos - Todas as versões.


Solução
Para a adequação à Nota Técnica 2024.002 do MDF-e.

O prazo previsto para a Nota Técnica 2024.002 do MDF-e é:

Ambiente de Homologação (ambiente de teste das empresas): 02/09/2024

Ambiente de Produção: 07/10/2024

Foi aberto junto ao desenvolvimento a Issue DSERTSS1-23218 para análise do time do produto.

Para ser associado a issue e receber o retorno da equipe é necessário que abram um ticket com a equipe de suporte.

---

### Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Unificação da SVAN e SVC-AN

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/23975395475735-Cross-Segmentos-TSS-Transmiss%C3%A3o-de-Documentos-Eletr%C3%B4nicos-Unifica%C3%A7%C3%A3o-da-SVAN-e-SVC-AN

Dúvida
Quais serão as alterações da unificação da SVAN e SVC-AN ?

 

Ambiente

Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Todas as versões


Solução

A Receita Federal do Brasil (RFB) está atualmente em processo de integrar os sistemas da Secretaria Virtual do Ambiente Nacional (SVAN), com o Sistema de Contingência da Secretaria Virtual do Ambiente Nacional (SVC-AN), utilizado para emitir notas fiscais eletrônicas em situações de contingência.

Os ambientes de HOMOLOGAÇÃO da SVC-AN e SVAN já foram unificados e as novas URLs já foram atualizadas no Portal Nacional da NF-e de HOMOLOGAÇÃO.

 

Ambiente de Homologação (ambiente de teste das empresas): 16/07/2024

 

1. Atualização do ambiente TSS (URL's)

TSS - Atualização das URLs do TSS

 

Saiba mais aqui.

---


## Documentos Fiscais (NFe, CTe, MDFe, NFSe)

### Cross Segmentos - Backoffice Protheus - TSS - MDFE - Imprimir DAMDFE com alteração de condutor

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360051694694-Cross-Segmentos-Backoffice-Protheus-TSS-MDFE-Imprimir-DAMDFE-com-altera%C3%A7%C3%A3o-de-condutor

Dúvida
Como imprimir o DAMDFE com a alteração do novo condutor?

Ambiente
Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Todas as versões
Solução
O Evento de inclusão de Condutor é como se fosse uma carta de correção da NFE, ele não altera o XML e o DAMDFE original. A informação é alterada somente na SEFAZ.

Exemplo, quando entregar o DAMDFE no posto fiscal, eles irão fazer a leitura e verificar que foi alterado o condutor.

Caso queria que um novo condutor apareça no DAMDFE, pode encerrar o MDFE e gerar um novo com a informação já do novo motorista.



Caso não saiba como realizar a inclusão do condutor basta seguir conforme a documentação abaixo:

MP - MDFE - Evento de Inclusão de Condutor

---

### Cross Segmentos - Backoffice Protheus - TSS - Método de encerramento mdfe de cte.

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360060874374-Cross-Segmentos-Backoffice-Protheus-TSS-M%C3%A9todo-de-encerramento-mdfe-de-cte

Dúvida
Qual método utilizado para encerramento de cte, e sua estrutura.

Ambiente
TSS 25 e TSS 27

Solução
O método é remessaevento, onde o erp que envia tags abaixo, para o TSS concluir o fluxo do processo.

 

Estrutura do xml:

<eventos>
 <envEvento>
   <detEvento>
     <tpEvento>110112</tpEvento>
      <chNFe>35210120147617005534580009243200071894145406</chNFe>
      <ambiente>1</ambiente>
      <dtEnc>2021-01-28</dtEnc>
      <cUF>SP</cUF>
      <cMun>3505708</cMun>
   </detEvento>
  </envEvento>
</eventos>

---

### Cross Segmentos - Backoffice Protheus - TSS - Troca Servidor Sefaz MG

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/14972765886359-Cross-Segmentos-Backoffice-Protheus-TSS-Troca-Servidor-Sefaz-MG

Dúvida
Como proceder com a Troca Servidor Sefaz MG?

Ambiente 
Cross Segmento - TOTVS Backoffice (Linha Protheus) - TOTVS Documentos Eletrônicos - Todas as versões.


Solução
Ambiente de Produção: Mudança entre 08/06/2023 e 11/06/2023

1. Atualização do TSS RPO e URL

MP - TSS - Atualização do Repositório (RPO) do TSS

TSS - Atualização das URLs do TSS

 

Informações adicionais:

Na correção foram realizados ajustes necessários para consumir o serviço de NF-e e CT-e para o estado de Minas Gerais, para os ambientes de homologação e produção.

 

Importante: A atualização contempla as versões atuais do TSS, caso a versão do TSS seja inferior a release 12.1.2310 é necessário que seja realizada a migração da release:

MP - TSS - Migração para 12.1.2410 - (Instalação)

Saiba mais:

Para verificar o boletim técnico, Clique Aqui

---

### Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Atualização das URLs do TSS

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360025394911-Cross-Segmentos-TSS-Transmiss%C3%A3o-de-Documentos-Eletr%C3%B4nicos-Atualiza%C3%A7%C3%A3o-das-URLs-do-TSS

Dúvida
Como realizar a atualização das URLS do TSS?

Ambiente
Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Todas as versões


Solução
Segue abaixo um passo a passo de como deverá ser realizado a atualização das URLS do TSS. 


1. Pare o serviço do TSS;

2. Efetue download do arquivo TSSATUURL.JSON clicando no link abaixo:
- Clique aqui para download

3. Acesse a pasta de instalação do TSS e após realizar o download do arquivo extraia o arquivo TSSATUURL.JSON e salve na pasta system do TSS;

4. Clique com o botão direto do mouse no arquivo e acesse as propriedades do arquivo. Desmarque a opção "somente leitura" caso esteja marcada;

5. Reinicie o serviço do TSS para que o arquivo seja apagado da pasta system;

6. Se arquivo não foi apagado da pasta system, entre na pasta SEMAFORO do TSS e exclua o arquivo com a mesma nomenclatura TSSATUURL e refaça o procedimento;

7. Após conclusão, reinicie o TSS.

---

### Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Atualização do Repositório (RPO) do TSS

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/1500004215981-Cross-Segmentos-TSS-Transmiss%C3%A3o-de-Documentos-Eletr%C3%B4nicos-Atualiza%C3%A7%C3%A3o-do-Reposit%C3%B3rio-RPO-do-TSS

Dúvida
Como realizar a atualização do repositório (RPO) do TSS?

Ambiente
Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Todas as versões


Solução
Segue abaixo um passo a passo de como deverá ser realizado a atualização do repositório (RPO) do TSS:

1. Primeiramente deverá parar o serviço do TSS;

2. Para realizar a atualização do repositório do TSS, faça o download em um dos links abaixo de acordo com sua release:

TSS 12.1.2210 - 3.0 (somente para clientes com garantia estendida): Clique aqui para download.
TSS 12.1.2310 - 3.0: (somente para clientes com garantia estendida): Clique aqui para download.
TSS 12.1.2410 - 3.0: Clique aqui para download. 

TSS 12.1.2510 -3.0: Clique aqui para Download

 

*Caso tenha alguma dificuldade no acesso ao link, utilize um outro navegador ou clique com botão direito do mouse e clique em copiar endereço do link e depois cole este endereço em outra aba do navegador:

 

- IMPORTANTE: Após a atualização do RPO é necessário que apliquem também as atualizações abaixo:

TSS - Atualização dos SCHEMAS
TSS - Atualização das URLs do TSS


3. Feito isso, acesse o diretório de instalação do TSS e localize a pasta APO.


4. Faça o backup do arquivo .RPO atual por segurança, e após isso, substitua o arquivo dentro da pasta com o arquivo que foi extraído e baixado pelo link acima. 


Obs.: O repositório acima já contém o último patch acumulado disponibilizado no Portal do Cliente, conforme link. Portanto, não há necessidade de aplicar o patch acumulado no mesmo.

 

Veja abaixo o vídeo com o procedimento para atualização do RPO do TSS:

---

### Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Atualização do SmartClient do TSS

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/1500005242901-Cross-Segmentos-TSS-Transmiss%C3%A3o-de-Documentos-Eletr%C3%B4nicos-Atualiza%C3%A7%C3%A3o-do-SmartClient-do-TSS

Dúvida
Como deverá ser realizada a atualização do Smartclient do TSS?


Ambiente
TSS - Versões 12.1.2210 e 12.1.2310

Solução
Vale lembrar que o smartclient utilizado no TSS é o mesmo do Protheus, pois possuem arquiteturas similares. Portanto, para a atualização deverá seguir os passos detalhados abaixo:

1. Primeiramente deverá parar o serviço do TSS;

2. Faça o download em um dos links abaixo de acordo com seu Sistema Operacional:


 

Releases 12.1.2210 e 12.1.2310

Windows: 32 bits | 64 bits
Linux: 64 bits
MAC: 64 bits

3. Feito isso, acesse o diretório de instalação do TSS e localize a pasta 'bin > smartclient';

4. Faça o backup do conteúdo atual por segurança, e após isso, substitua os arquivos dentro da pasta com os arquivos que foram extraídos e baixados pelo link acima.


 

Obs: O uso do smartclient foi descontinuado na release 2410, desta forma no processo de funcionamento padrão do sistema não será possível utilizar o Smartclient de versões anteriores.

---

### Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Funcionalidades dos JOBs do TSS 3.0

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360018584232-Cross-Segmentos-TSS-Transmiss%C3%A3o-de-Documentos-Eletr%C3%B4nicos-Funcionalidades-dos-JOBs-do-TSS-3-0

Dúvida
Funcionalidades dos JOBs do TSS 3.0


Ambiente
Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Todas as versões


Solução


Os Jobs padrões de instalação do TSS a partir da versão 12 e TSS 3.0 são obrigatórios e não devem ser removidos ou substituídos pelos Jobs antigos usados em outras versões legadas.

Segue a funcionalidade dos mesmos:

JOB_HTTP: Comunicação via Web service
JOB_WS: Threads de Web service do TSS
TSSTASKPROC: JOB responsável pela execução das tarefas do TSS
TSSTASKPROC: Tarefas em execução   
IPC_CONT/IPC_ONDEMAND: Pool de Threads para processamento das tarefas dos documentos (assinatura de xml, transmissão e consulta junto ao fisco) 
IPC_SMTP: Validação SMTP e envio de email

---

### Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - NFSE - Aterações Itajai-SC

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/31144758506263-Cross-Segmentos-TSS-Transmiss%C3%A3o-de-Documentos-Eletr%C3%B4nicos-NFSE-Atera%C3%A7%C3%B5es-Itajai-SC

Dúvida


É necessário alguma alteração no TSS para atender a atualização prevista para Itajaí-SC em 07/04/2025?



Comunicado Completo Aqui.

 

Ambiente
Cross Segmentos - TSS Transmissão de Documentos Eletrônicos - Todas as versões

Solução
No TSS as consultas são de 1 RPS por vez ou de 1 lote (com 50 RPSs) por vez.
O comunicado diz que "Para consultas com menos de 100 registros, nenhuma alteração é necessária."

Sendo assim, não será necessário nenhuma alteração no TSS para atender essa melhoria realizada pela prefeitura de Itajaí-SC.

---


## Jobs e Processos

### Cross Segmentos - TSS - ExpirationDelta

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360043505353-Cross-Segmentos-TSS-ExpirationDelta

Dúvida
Funcionalidade do comando ExpirationDelta

Ambiente
Apartir do TSS 12.1.17 3.0

Solução
Esse comando trabalha em conjunto com o comando ExpirationTime tem como objetivo de fechar as Threads em período estipulado,  e evitar consumo de memoria.

Valor Default= EXPIRATIONDELTA=1

---


## Outros

### Cross Segmentos - Backoffice Protheus - TSS - Monitor apresentando trheads distMail e ipc_distmail

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/360063013933-Cross-Segmentos-Backoffice-Protheus-TSS-Monitor-apresentando-trheads-distMail-e-ipc-distmail

*Conteudo nao disponivel — acessar URL para detalhes.*

---

### Cross Segmentos - TSS - Server returned: Duplicated function

**URL:** https://centraldeatendimento.totvs.com/hc/pt-br/articles/1500008076022-Cross-Segmentos-TSS-Server-returned-Duplicated-function

*Conteudo nao disponivel — acessar URL para detalhes.*

---
