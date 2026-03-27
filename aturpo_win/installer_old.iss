; ATURPO DevOps - Script de Instalação Inno Setup
; Versão: 3.0 (Simplificado - 2 páginas de configuração)
; Data: 2026-01-03
; Encoding: UTF-8

#define MyAppName "ATURPO DevOps"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "AtuRPO"
#define MyAppURL "https://www.aturpo.com.br"
#define MyAppExeName "ATURPO.exe"
#define MyAppServiceName "ATURPODevOpsService"

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
OutputDir=Output
OutputBaseFilename=ATURPO_Setup_{#MyAppVersion}
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
brazilianportuguese.WelcomeLabel2=Este assistente irá instalar o [name/ver] no seu computador.%n%nO sistema requer PostgreSQL instalado com o usuário "aturpo" criado.%n%nIMPORTANTE: Na primeira utilização, use o "Primeiro Acesso" na tela de login para criar seu administrador.%n%nÉ recomendado que você feche todos os outros aplicativos antes de continuar.

[Files]
Source: "dist\ATURPO.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\nssm.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\install_service.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\uninstall_service.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\version.json"; DestDir: "{app}"; Flags: ignoreversion

; Arquivos estáticos (JS, CSS, HTML, etc)
Source: "static\*"; DestDir: "{app}\static"; Flags: ignoreversion recursesubdirs createallsubdirs

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
  // Página 1: Configuração do Sistema (PostgreSQL + Aplicação)
  ConfigPage: TInputQueryWizardPage;
  
  // Página 2: Diretório de Logs
  LogsDirPage: TInputDirWizardPage;

// ============================================================================
// INICIALIZAÇÃO DAS PÁGINAS CUSTOMIZADAS
// ============================================================================

procedure InitializeWizard;
begin
  // ========================================
  // PÁGINA 1: Configuração do Sistema
  // ========================================
  ConfigPage := CreateInputQueryPage(wpLicense,
    'Configuração do Sistema',
    'Configure o banco de dados e a aplicação',
    'Preencha as informações abaixo para configurar o ATURPO DevOps.' + #13#10 + #13#10 +
    'BANCO DE DADOS: O usuário "aturpo" deve existir no PostgreSQL.' + #13#10 +
    'Se não existir, execute: CREATE ROLE aturpo WITH LOGIN PASSWORD ''aturpo'' CREATEDB;' + #13#10 + #13#10 +
    'PRIMEIRO ACESSO: Após a instalação, use o "Primeiro Acesso" na tela de login para criar seu administrador.');

  // Host do PostgreSQL
  ConfigPage.Add('Host do PostgreSQL:', False);
  ConfigPage.Values[0] := 'localhost';

  // Porta do PostgreSQL
  ConfigPage.Add('Porta do PostgreSQL:', False);
  ConfigPage.Values[1] := '5432';

  // Porta da Aplicação
  ConfigPage.Add('Porta da Aplicação Web:', False);
  ConfigPage.Values[2] := '5000';

  // Nome da Empresa/Organização
  ConfigPage.Add('Nome da Empresa/Organização:', False);
  ConfigPage.Values[3] := 'Minha Empresa';

  // ========================================
  // PÁGINA 2: Diretório de Logs
  // ========================================
  LogsDirPage := CreateInputDirPage(ConfigPage.ID,
    'Diretório de Logs',
    'Selecione o local para armazenar os logs',
    'Escolha o diretório onde serão salvos os arquivos de log do sistema.' + #13#10 + #13#10 +
    'Recomendação: Utilize o diretório padrão, a menos que tenha uma necessidade específica.',
    False, '');
  
  LogsDirPage.Add('');
  LogsDirPage.Values[0] := ExpandConstant('{autopf}\ATURPO DevOps\logs');
end;

// ============================================================================
// VALIDAÇÃO DAS PÁGINAS
// ============================================================================

function NextButtonClick(CurPageID: Integer): Boolean;
var
  ErrorMsg: String;
  Port: Integer;
begin
  Result := True;
  ErrorMsg := '';

  // Validar Página de Configuração
  if CurPageID = ConfigPage.ID then
  begin
    // Validar Host PostgreSQL
    if Trim(ConfigPage.Values[0]) = '' then
      ErrorMsg := 'O Host do PostgreSQL é obrigatório!'
    
    // Validar Porta PostgreSQL
    else if Trim(ConfigPage.Values[1]) = '' then
      ErrorMsg := 'A Porta do PostgreSQL é obrigatória!'
    else
    begin
      try
        Port := StrToInt(Trim(ConfigPage.Values[1]));
        if (Port < 1) or (Port > 65535) then
          ErrorMsg := 'A porta do PostgreSQL deve estar entre 1 e 65535!';
      except
        ErrorMsg := 'A porta do PostgreSQL deve ser um número válido!';
      end;
    end;

    // Validar Porta da Aplicação
    if ErrorMsg = '' then
    begin
      if Trim(ConfigPage.Values[2]) = '' then
        ErrorMsg := 'A Porta da Aplicação é obrigatória!'
      else
      begin
        try
          Port := StrToInt(Trim(ConfigPage.Values[2]));
          if (Port < 1024) or (Port > 65535) then
            ErrorMsg := 'A porta da aplicação deve estar entre 1024 e 65535!';
        except
          ErrorMsg := 'A porta da aplicação deve ser um número válido!';
        end;
      end;
    end;

    // Validar Nome da Empresa
    if ErrorMsg = '' then
    begin
      if Trim(ConfigPage.Values[3]) = '' then
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

function GetPostgresHost(Param: String): String;
begin
  Result := ConfigPage.Values[0];
end;

function GetPostgresPort(Param: String): String;
begin
  Result := ConfigPage.Values[1];
end;

function GetPostgresDB(Param: String): String;
begin
  Result := 'aturpo';  // Valor fixo
end;

function GetPostgresUser(Param: String): String;
begin
  Result := 'aturpo';  // Valor fixo
end;

function GetPostgresPassword(Param: String): String;
begin
  Result := 'aturpo';  // Valor fixo
end;

function GetAppPort(Param: String): String;
begin
  Result := ConfigPage.Values[2];
end;

function GetCompanyName(Param: String): String;
begin
  Result := ConfigPage.Values[3];
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
    EnvContent.Add('# ATURPO DevOps - Arquivo de Configuracao');
    EnvContent.Add('# Gerado automaticamente pelo instalador em: ' + GetDateTimeString('dd/mm/yyyy hh:nn:ss', #0, #0));
    EnvContent.Add('');
    EnvContent.Add('# === CONFIGURACAO DO BANCO DE DADOS ===');
    EnvContent.Add('DB_HOST=' + GetPostgresHost(''));
    EnvContent.Add('DB_PORT=' + GetPostgresPort(''));
    EnvContent.Add('DB_NAME=' + GetPostgresDB(''));
    EnvContent.Add('DB_USER=' + GetPostgresUser(''));
    EnvContent.Add('DB_PASSWORD=' + GetPostgresPassword(''));
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
// VERIFICAÇÃO DO USUÁRIO ATURPO NO POSTGRESQL
// ============================================================================

function SetupDatabaseViaSQL: Boolean;
var
  ResultCode: Integer;
  BatchFile: String;
  BatchContent: TStringList;
  DBHost, DBPort, DBUser, DBName: String;
begin
  Result := True; // Assume sucesso por padrão (não bloqueia instalação)
  
  Log('Verificando conexão com usuário aturpo...');
  
  DBHost := GetPostgresHost('');
  DBPort := GetPostgresPort('');
  DBUser := GetPostgresUser('');
  DBName := GetPostgresDB('');
  
  BatchFile := ExpandConstant('{tmp}\test_aturpo.bat');
  
  // Criar arquivo batch para testar conexão com usuário aturpo
  BatchContent := TStringList.Create;
  try
    BatchContent.Add('@echo off');
    BatchContent.Add('REM Teste de conexão com usuário aturpo');
    BatchContent.Add('');
    BatchContent.Add('SET PGPASSWORD=aturpo');
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
      Log('Usuário aturpo conectou com sucesso!');
      MsgBox('Conexão com PostgreSQL verificada com sucesso!' + #13#10 +
             'O banco será criado automaticamente na primeira execução.' + #13#10 + #13#10 +
             'PRÓXIMO PASSO: Após iniciar o sistema, use o "Primeiro Acesso" para criar seu administrador.', 
             mbInformation, MB_OK);
      Result := True;
    end
    else
    begin
      Log('Aviso: Usuário aturpo não conseguiu conectar');
      MsgBox('ATENÇÃO: Usuário "aturpo" não encontrado no PostgreSQL!' + #13#10 + #13#10 +
             'Execute o comando abaixo no psql como superusuário postgres:' + #13#10 + #13#10 +
             'CREATE ROLE aturpo WITH LOGIN PASSWORD ''aturpo'' CREATEDB;' + #13#10 + #13#10 +
             'A instalação continuará, mas o sistema não funcionará até criar o usuário.',
             mbError, MB_OK);
      Result := True; // Não bloqueia instalação
    end;
  end
  else
  begin
    Log('Aviso: Não foi possível executar psql. PostgreSQL pode não estar no PATH.');
    MsgBox('PostgreSQL (psql) não encontrado no PATH do sistema.' + #13#10 + #13#10 +
           'Certifique-se de que o usuário "aturpo" existe no PostgreSQL.' + #13#10 +
           'Se não existir, execute como superusuário postgres:' + #13#10 + #13#10 +
           'CREATE ROLE aturpo WITH LOGIN PASSWORD ''aturpo'' CREATEDB;',
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
    // Verificar usuário aturpo no PostgreSQL
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
