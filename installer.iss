; BiizHubOps - Script de Instalação Inno Setup
; Versão: 3.0 (Simplificado - 2 páginas de configuração)
; Data: 2026-01-03
; Encoding: UTF-8

#define MyAppName "BiizHubOps"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "BiizHub"
#define MyAppURL "https://www.biizhubflow.com.br"
#define MyAppExeName "BiizHubOps.exe"
#define MyAppServiceName "BiizHubOpsService"

[Setup]
AppId={{A7B8C9D0-E1F2-4567-8901-ABCDEF123456}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DisableDirPage=no
UsePreviousAppDir=no
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=aturpo_win\Output
OutputBaseFilename=BiizHubOps_Setup_{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
; SetupIconFile=static\favicon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
DisableProgramGroupPage=yes
ArchitecturesInstallIn64BitMode=x64
WizardSizePercent=100,150

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[CustomMessages]
brazilianportuguese.WelcomeLabel2=Este assistente irá instalar o [name/ver] no seu computador.%n%nO sistema requer PostgreSQL instalado. O usuário e senha serão configurados durante a instalação.%n%nIMPORTANTE: Na primeira utilização, use o "Primeiro Acesso" na tela de login para criar seu administrador.%n%nÉ recomendado que você feche todos os outros aplicativos antes de continuar.

[Files]
Source: "aturpo_win\dist\BiizHubOps.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "aturpo_win\dist\nssm.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "aturpo_win\dist\install_service.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "aturpo_win\dist\uninstall_service.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "aturpo_win\dist\version.json"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
Name: "{autopf}\{#MyAppName}\logs"; Permissions: users-modify

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos:"; Flags: unchecked
Name: "installservice"; Description: "Instalar como Serviço do Windows (recomendado)"; GroupDescription: "Opções de Instalação:"; Flags: checkedonce
Name: "startservice"; Description: "Iniciar o serviço automaticamente"; GroupDescription: "Opções de Instalação:"; Flags: checkedonce

[Run]
Filename: "{app}\install_service.bat"; Parameters: """{app}\{#MyAppExeName}"" ""{code:GetAppPort}"" ""{code:GetEnvFilePath}"""; StatusMsg: "Instalando serviço do Windows..."; Flags: runhidden waituntilterminated; Tasks: installservice
Filename: "{app}\nssm.exe"; Parameters: "start {#MyAppServiceName}"; StatusMsg: "Iniciando serviço..."; Flags: runhidden waituntilterminated; Tasks: startservice

[UninstallRun]
Filename: "{app}\uninstall_service.bat"; Flags: runhidden waituntilterminated

[Code]
var
  // Páginas do Instalador
  DBTypePage: TInputOptionWizardPage;
  LocalDBPage: TInputQueryWizardPage;
  CloudDBPage: TInputQueryWizardPage;
  AppConfigPage: TInputQueryWizardPage;
  LogsDirPage: TInputDirWizardPage;

// ============================================================================
// INICIALIZAÇÃO DAS PÁGINAS CUSTOMIZADAS
// ============================================================================

procedure InitializeWizard;
begin
  // ========================================
  // PÁGINA 1: Tipo de Banco de Dados
  // ========================================
  DBTypePage := CreateInputOptionPage(wpLicense,
    'Tipo de Instalação do Banco de Dados',
    'Onde o banco de dados PostgreSQL está ou será hospedado?',
    'Selecione se o banco de dados será executado nesta máquina (Local) ou em um servidor em Nuvem (Ex: Aiven, Supabase, etc).',
    True, False);

  DBTypePage.Add('Banco de Dados Local (Instalado nesta máquina - Padrão)');
  DBTypePage.Add('Banco de Dados em Nuvem ou Servidor Remoto (Aiven, RDS, etc)');
  DBTypePage.SelectedValueIndex := 0; // Padrão Local

  // ========================================
  // PÁGINA 2: Configuração Local
  // ========================================
  LocalDBPage := CreateInputQueryPage(DBTypePage.ID,
    'Configuração do PostgreSQL Local',
    'Informe os dados de conexão do banco de dados local',
    'Preencha as informações para o PostgreSQL local.' + #13#10 + #13#10 +
    'IMPORTANTE: O usuário informado DEVE existir no PostgreSQL com permissão CREATEDB.' + #13#10 +
    'Se precisar criar, execute no psql como superusuário:' + #13#10 +
    'CREATE ROLE <usuario> WITH LOGIN PASSWORD ''<senha>'' CREATEDB;');

  LocalDBPage.Add('Host do PostgreSQL:', False);
  LocalDBPage.Values[0] := 'localhost';

  LocalDBPage.Add('Porta do PostgreSQL:', False);
  LocalDBPage.Values[1] := '5432';

  LocalDBPage.Add('Nome do Banco de Dados:', False);
  LocalDBPage.Values[2] := 'biizhubops';

  LocalDBPage.Add('Usuário do PostgreSQL:', False);
  LocalDBPage.Values[3] := 'biizhubops';

  LocalDBPage.Add('Senha do PostgreSQL:', True);
  LocalDBPage.Values[4] := 'biizhubops';

  // ========================================
  // PÁGINA 3: Configuração Nuvem
  // ========================================
  CloudDBPage := CreateInputQueryPage(LocalDBPage.ID,
    'Configuração do PostgreSQL em Nuvem',
    'Informe os dados de conexão do servidor remoto',
    'Preencha as credenciais fornecidas pelo seu provedor de nuvem.' + #13#10 + #13#10 +
    'IMPORTANTE: O usuário informado deve ter permissão CREATEDB para que o banco seja criado automaticamente.');

  CloudDBPage.Add('URI / Host (Ex: biizhubops-proj.aivencloud.com):', False);
  CloudDBPage.Values[0] := '';

  CloudDBPage.Add('Porta (Ex: 19132):', False);
  CloudDBPage.Values[1] := '5432';

  CloudDBPage.Add('Nome do Banco de Dados:', False);
  CloudDBPage.Values[2] := 'biizhubops';

  CloudDBPage.Add('Usuário (Ex: avnadmin):', False);
  CloudDBPage.Values[3] := 'biizhubops';

  CloudDBPage.Add('Senha:', True); // Campo com asteriscos
  CloudDBPage.Values[4] := '';

  CloudDBPage.Add('SSL Mode (Ex: require, prefer, disable, allow, verify-ca):', False);
  CloudDBPage.Values[5] := 'require';

  // ========================================
  // PÁGINA 4: Configuração da Aplicação
  // ========================================
  AppConfigPage := CreateInputQueryPage(CloudDBPage.ID,
    'Configuração da Aplicação Web',
    'Configure as portas e informações da empresa',
    'Preencha as informações gerais do BiizHubOps.' + #13#10 + #13#10 +
    'PRIMEIRO ACESSO: Após a instalação, use a opção "Primeiro Acesso" na tela de login da Web para criar seu administrador.');

  AppConfigPage.Add('Porta da Aplicação Web:', False);
  AppConfigPage.Values[0] := '5000';

  AppConfigPage.Add('Nome da Empresa/Organização:', False);
  AppConfigPage.Values[1] := 'Minha Empresa';

  // ========================================
  // PÁGINA 5: Diretório de Logs
  // ========================================
  LogsDirPage := CreateInputDirPage(AppConfigPage.ID,
    'Diretório de Logs',
    'Selecione o local para armazenar os logs',
    'Escolha o diretório onde serão salvos os arquivos de log do sistema.' + #13#10 + #13#10 +
    'Recomendação: Utilize o diretório padrão, a menos que tenha uma necessidade específica.',
    False, '');
  
  LogsDirPage.Add('');
  LogsDirPage.Values[0] := ExpandConstant('{autopf}\BiizHubOps\logs');
end;

// ============================================================================
// VALIDAÇÃO DAS PÁGINAS E LÓGICA DE EXIBIÇÃO
// ============================================================================

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;

  // Pular configuração Cloud se escolheu Local (index 0)
  if (PageID = CloudDBPage.ID) and (DBTypePage.SelectedValueIndex = 0) then
    Result := True;

  // Pular configuração Local se escolheu Cloud (index 1)
  if (PageID = LocalDBPage.ID) and (DBTypePage.SelectedValueIndex = 1) then
    Result := True;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  ErrorMsg: String;
  Port: Integer;
begin
  Result := True;
  ErrorMsg := '';

  // Validar Página DB Local
  if CurPageID = LocalDBPage.ID then
  begin
    if Trim(LocalDBPage.Values[0]) = '' then
      ErrorMsg := 'O Host do PostgreSQL é obrigatório!'
    else if Trim(LocalDBPage.Values[1]) = '' then
      ErrorMsg := 'A Porta do PostgreSQL é obrigatória!'
    else if Trim(LocalDBPage.Values[2]) = '' then
      ErrorMsg := 'O Nome do Banco de Dados é obrigatório!'
    else if Trim(LocalDBPage.Values[3]) = '' then
      ErrorMsg := 'O Usuário do PostgreSQL é obrigatório!'
    else if Trim(LocalDBPage.Values[4]) = '' then
      ErrorMsg := 'A Senha do PostgreSQL é obrigatória!'
    else
    begin
      try
        Port := StrToInt(Trim(LocalDBPage.Values[1]));
        if (Port < 1) or (Port > 65535) then
          ErrorMsg := 'A porta do PostgreSQL deve estar entre 1 e 65535!';
      except
        ErrorMsg := 'A porta do PostgreSQL deve ser um número válido!';
      end;
    end;
  end;

  // Validar Página DB Nuvem
  if CurPageID = CloudDBPage.ID then
  begin
    if Trim(CloudDBPage.Values[0]) = '' then
      ErrorMsg := 'O URI / Host é obrigatório!'
    else if Trim(CloudDBPage.Values[1]) = '' then
      ErrorMsg := 'A Porta é obrigatória!'
    else if Trim(CloudDBPage.Values[2]) = '' then
      ErrorMsg := 'O Nome do Banco de Dados é obrigatório!'
    else if Trim(CloudDBPage.Values[3]) = '' then
      ErrorMsg := 'O Usuário é obrigatório!'
    else if Trim(CloudDBPage.Values[4]) = '' then
      ErrorMsg := 'A Senha é obrigatória!'
    else
    begin
      try
        Port := StrToInt(Trim(CloudDBPage.Values[1]));
        if (Port < 1) or (Port > 65535) then
          ErrorMsg := 'A porta deve estar entre 1 e 65535!';
      except
        ErrorMsg := 'A porta deve ser um número válido!';
      end;
    end;
  end;

  // Validar Configuração da App
  if CurPageID = AppConfigPage.ID then
  begin
    if Trim(AppConfigPage.Values[0]) = '' then
      ErrorMsg := 'A Porta da Aplicação é obrigatória!'
    else
    begin
      try
        Port := StrToInt(Trim(AppConfigPage.Values[0]));
        if (Port < 1024) or (Port > 65535) then
          ErrorMsg := 'A porta da aplicação deve estar entre 1024 e 65535!';
      except
        ErrorMsg := 'A porta da aplicação deve ser um número válido!';
      end;
    end;

    if ErrorMsg = '' then
    begin
      if Trim(AppConfigPage.Values[1]) = '' then
        ErrorMsg := 'O Nome da Empresa é obrigatório!';
    end;
  end;

  // Validar Página de Diretório de Logs
  if CurPageID = LogsDirPage.ID then
  begin
    if Trim(LogsDirPage.Values[0]) = '' then
      ErrorMsg := 'O Diretório de Logs é obrigatório!';
  end;

  // Mostrar erro se houver
  if ErrorMsg <> '' then
  begin
    MsgBox(ErrorMsg, mbError, MB_OK);
    Result := False;
  end;
end;

// ============================================================================
// FUNÇÕES AUXILIARES PARA OBTER VALORES
// ============================================================================

function IsCloudDB: Boolean;
begin
  Result := (DBTypePage.SelectedValueIndex = 1);
end;

function GetPostgresHost(Param: String): String;
begin
  if IsCloudDB then
    Result := CloudDBPage.Values[0]
  else
    Result := LocalDBPage.Values[0];
end;

function GetPostgresPort(Param: String): String;
begin
  if IsCloudDB then
    Result := CloudDBPage.Values[1]
  else
    Result := LocalDBPage.Values[1];
end;

function GetPostgresDB(Param: String): String;
begin
  if IsCloudDB then
    Result := CloudDBPage.Values[2]
  else
    Result := LocalDBPage.Values[2];
end;

function GetPostgresUser(Param: String): String;
begin
  if IsCloudDB then
    Result := CloudDBPage.Values[3]
  else
    Result := LocalDBPage.Values[3];
end;

function GetPostgresPassword(Param: String): String;
begin
  if IsCloudDB then
    Result := CloudDBPage.Values[4]
  else
    Result := LocalDBPage.Values[4];
end;

function GetPostgresSSLMode(Param: String): String;
begin
  if IsCloudDB then
    Result := CloudDBPage.Values[5]
  else
    Result := ''; // Vazio para local
end;

function GetAppPort(Param: String): String;
begin
  Result := AppConfigPage.Values[0];
end;

function GetCompanyName(Param: String): String;
begin
  Result := AppConfigPage.Values[1];
end;

function GetLogsDir(Param: String): String;
begin
  Result := LogsDirPage.Values[0];
end;

function GetEnvironmentMode(Param: String): String;
begin
  Result := 'production';  // Valor fixo
end;

function ConvertBackslashToSlash(Path: String): String;
var
  I: Integer;
begin
  Result := Path;
  for I := 1 to Length(Result) do
  begin
    if Result[I] = '\' then
      Result[I] := '/';
  end;
end;

function GetEnvFilePath(Param: String): String;
begin
  Result := ExpandConstant('{app}\config.env');
end;

// ============================================================================
// CRIAÇÃO DO ARQUIVO .ENV
// ============================================================================

procedure CreateEnvFile;
var
  EnvFile: String;
  EnvContent: TStringList;
begin
  EnvFile := ExpandConstant('{app}\config.env');
  EnvContent := TStringList.Create;
  try
    EnvContent.Add('# BiizHubOps - Arquivo de Configuracao');
    EnvContent.Add('# Gerado automaticamente pelo instalador em: ' + GetDateTimeString('dd/mm/yyyy hh:nn:ss', #0, #0));
    EnvContent.Add('');
    EnvContent.Add('# === CONFIGURACAO DO BANCO DE DADOS ===');
    EnvContent.Add('DB_HOST=' + GetPostgresHost(''));
    EnvContent.Add('DB_PORT=' + GetPostgresPort(''));
    EnvContent.Add('DB_NAME=' + GetPostgresDB(''));
    EnvContent.Add('DB_USER=' + GetPostgresUser(''));
    EnvContent.Add('DB_PASSWORD=' + GetPostgresPassword(''));
    
    // Adicionar modo SSL do BD se existir
    if GetPostgresSSLMode('') <> '' then
      EnvContent.Add('DB_SSLMODE=' + GetPostgresSSLMode(''));
      
    EnvContent.Add('');
    EnvContent.Add('# === CONFIGURACAO DA APLICACAO ===');
    EnvContent.Add('APP_PORT=' + GetAppPort(''));
    EnvContent.Add('FLASK_ENV=' + GetEnvironmentMode(''));
    EnvContent.Add('');
    EnvContent.Add('# === CONFIGURACOES ADICIONAIS ===');
    EnvContent.Add('COMPANY_NAME=' + GetCompanyName(''));
    EnvContent.Add('LOGS_DIR=' + ConvertBackslashToSlash(GetLogsDir('')));
    EnvContent.Add('SECRET_KEY=' + GetMD5OfString(GetDateTimeString('yyyymmddhhnnss', #0, #0)));
    EnvContent.Add('');
    EnvContent.Add('# === CONFIGURACAO DE LICENCA ===');
    EnvContent.Add('# (Sera configurado posteriormente via interface)');
    EnvContent.Add('LICENSE_SERVER=');
    EnvContent.Add('LICENSE_KEY=');
    
    EnvContent.SaveToFile(EnvFile);
  finally
    EnvContent.Free;
  end;
end;

// ============================================================================
// VERIFICAÇÃO DO USUÁRIO BIIZHUBOPS NO POSTGRESQL (Apenas para Local)
// ============================================================================

function SetupDatabaseViaSQL: Boolean;
var
  ResultCode: Integer;
  BatchFile: String;
  BatchContent: TStringList;
  DBHost, DBPort, DBUser, DBPass: String;
begin
  Result := True; // Assume sucesso por padrão (não bloqueia instalação)

  if IsCloudDB then
  begin
    Log('Configuracao em Nuvem selecionada. Ignorando teste de conexao local via psql...');
    Exit;
  end;

  DBHost := GetPostgresHost('');
  DBPort := GetPostgresPort('');
  DBUser := GetPostgresUser('');
  DBPass := GetPostgresPassword('');

  Log('Verificando conexão com usuário ' + DBUser + '...');

  BatchFile := ExpandConstant('{tmp}\test_pgconn.bat');

  // Criar arquivo batch para testar conexão com o usuário informado
  BatchContent := TStringList.Create;
  try
    BatchContent.Add('@echo off');
    BatchContent.Add('REM Teste de conexão com PostgreSQL');
    BatchContent.Add('');
    BatchContent.Add('SET PGPASSWORD=' + DBPass);
    BatchContent.Add('');
    BatchContent.Add('psql.exe -h ' + DBHost + ' -p ' + DBPort + ' -U ' + DBUser + ' -d postgres -c "SELECT 1" >nul 2>&1');
    BatchContent.Add('');
    BatchContent.Add('SET PGPASSWORD=');
    BatchContent.Add('exit /b %ERRORLEVEL%');

    BatchContent.SaveToFile(BatchFile);
  finally
    BatchContent.Free;
  end;

  Log('Executando teste de conexão: ' + BatchFile);

  if Exec('cmd.exe', '/c "' + BatchFile + '"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    if ResultCode = 0 then
    begin
      Log('Usuário ' + DBUser + ' conectou com sucesso!');
      MsgBox('Conexão com PostgreSQL verificada com sucesso!' + #13#10 +
             'Usuário "' + DBUser + '" autenticado.' + #13#10 +
             'O banco será criado automaticamente na primeira execução.' + #13#10 + #13#10 +
             'PRÓXIMO PASSO: Após iniciar o sistema, use o "Primeiro Acesso" para criar seu administrador.',
             mbInformation, MB_OK);
      Result := True;
    end
    else
    begin
      Log('Aviso: Usuário ' + DBUser + ' não conseguiu conectar');
      MsgBox('ATENÇÃO: Não foi possível conectar com o usuário "' + DBUser + '" no PostgreSQL!' + #13#10 + #13#10 +
             'Verifique se o usuário existe e tem permissão CREATEDB.' + #13#10 +
             'Para criar, execute no psql como superusuário postgres:' + #13#10 + #13#10 +
             'CREATE ROLE ' + DBUser + ' WITH LOGIN PASSWORD ''<senha>'' CREATEDB;' + #13#10 + #13#10 +
             'A instalação continuará, mas o sistema não funcionará até corrigir.',
             mbError, MB_OK);
      Result := True; // Não bloqueia instalação
    end;
  end
  else
  begin
    Log('Aviso: Não foi possível executar psql. PostgreSQL pode não estar no PATH.');
    MsgBox('PostgreSQL (psql) não encontrado no PATH do sistema.' + #13#10 + #13#10 +
           'Certifique-se de que o usuário "' + DBUser + '" existe no PostgreSQL com permissão CREATEDB.' + #13#10 +
           'Se precisar criar, execute como superusuário postgres:' + #13#10 + #13#10 +
           'CREATE ROLE ' + DBUser + ' WITH LOGIN PASSWORD ''<senha>'' CREATEDB;',
           mbInformation, MB_OK);
    Result := True; // Não bloqueia instalação
  end;

  // Limpar arquivo batch temporário
  if FileExists(BatchFile) then
    DeleteFile(BatchFile);
end;

// ============================================================================
// EVENTOS DO INSTALADOR
// ============================================================================

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // Verificar usuário no PostgreSQL (apenas local)
    SetupDatabaseViaSQL;
    
    // Criar arquivo config.env
    CreateEnvFile;
    
    // Criar diretório de logs se não existir
    if not DirExists(GetLogsDir('')) then
      CreateDir(GetLogsDir(''));
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  EnvFile: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    // Remover arquivo config.env
    EnvFile := ExpandConstant('{app}\config.env');
    if FileExists(EnvFile) then
      DeleteFile(EnvFile);
  end;
end;
