
import os
import sys
import json
from datetime import datetime
from .core import get_db, release_db_connection, DB_CONFIG, release_db_connection
from app.utils.security import hash_password
import psycopg2
from psycopg2 import IntegrityError, Error as PsycopgError

def create_database_if_not_exists():
    """
    Verifica se o banco de dados existe e cria se necessario.
    """
    # Forçar mensagens do libpq em ASCII para evitar UnicodeDecodeError
    # no Windows com locale pt-BR (mensagens em cp1252 vs psycopg2 esperando UTF-8)
    os.environ.setdefault('LC_MESSAGES', 'C')

    db_name = DB_CONFIG['database']

    print(f"[INFO] Verificando se o banco '{db_name}' existe...")
    
    # Tentativa 1: Conectar diretamente ao banco alvo
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.close()  # conexão direta (não do pool), fechar normalmente
        print(f"[OK] Banco '{db_name}' ja existe")
        return True
    except UnicodeDecodeError:
        # PostgreSQL no Windows com locale pt-BR retorna mensagens de erro
        # em cp1252 (ex: "não existe"), psycopg2 falha ao decodificar como UTF-8.
        # Tratar como banco inexistente e prosseguir com a criação.
        print(f"[AVISO] Erro de encoding na resposta do PostgreSQL (locale Windows)")
    except psycopg2.OperationalError as e:
        error_msg = str(e).lower()
        if 'does not exist' not in error_msg:
            # Erro diferente de banco inexistente, propagar
            print(f"[ERRO] Erro de conexao ao banco: {e}")
            return False
            
    # Se chegamos aqui, banco nao existe. Precisamos conectar a um banco padrao para criar.
    print(f"[INFO] Banco '{db_name}' nao existe, tentando criar...")
    
    # Tentativa 2: Conectar ao banco 'postgres' (padrao de instalacoes locais) ou 'defaultdb' (Aiven)
    maintenance_dbs = ['postgres', 'defaultdb']
    
    created = False
    
    for maint_db in maintenance_dbs:
        admin_config = DB_CONFIG.copy()
        admin_config['database'] = maint_db
        admin_config['client_encoding'] = 'UTF8'
        
        try:
            conn = psycopg2.connect(**admin_config)
            conn.autocommit = True
            cursor = conn.cursor()
            
            # SQL para criar banco com encoding UTF8
            create_sql = f"""
                CREATE DATABASE {db_name}
                WITH OWNER = {DB_CONFIG['user']}
                ENCODING = 'UTF8'
                LC_COLLATE = 'C'
                LC_CTYPE = 'C'
                TEMPLATE = template0
            """
            
            cursor.execute(create_sql)
            print(f"[OK] Banco '{db_name}' criado com sucesso usando '{maint_db}'")
            
            cursor.close()
            conn.close()  # conexão direta (não do pool), fechar normalmente
            created = True
            break
            
        except UnicodeDecodeError:
            # Mesmo problema de encoding do locale Windows, tentar proximo banco
            print(f"[AVISO] Erro de encoding ao conectar em '{maint_db}' (locale Windows)")
            continue
        except psycopg2.OperationalError as e:
            error_msg = str(e).lower()
            if 'does not exist' in error_msg:
                # Esse banco de manutencao nao existe, tentar o proximo
                continue
            else:
                print(f"[ERRO] Erro ao tentar criar banco com '{maint_db}': {e}")
        except Exception as e:
            print(f"[ERRO] Erro ao tentar criar banco com '{maint_db}': {e}")
            
    if not created:
         print(f"[ERRO] Nao foi possivel encontrar um banco administrativo ('postgres', 'defaultdb') para criar o '{db_name}'")
         return False
         
    return True

def init_db():
    """Inicializa o banco de dados com as tabelas necessárias"""
    
    # Verificar/criar banco de dados antes de tentar conectar
    if not create_database_if_not_exists():
        print("❌ [ERRO] Nao foi possivel criar o banco de dados!")
        print("💡 [DICA] Crie o banco manualmente ou verifique permissoes do usuario")
        raise Exception("Banco de dados nao existe e nao pode ser criado")
    
    conn = get_db()
    cursor = conn.cursor()

    # (NOVO) Tabela de Ambientes
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS environments (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            created_at TIMESTAMP NOT NULL
        )
        """
    )

    # Adiciona ambientes padrão se não existirem
    cursor.execute("SELECT COUNT(*) FROM environments")
    if cursor.fetchone()['count'] == 0:
        now = datetime.now()
        default_environments = [
            ('Produção', 'Ambiente de produção principal', now),
            ('Homologação', 'Ambiente de homologação para validações', now),
            ('Desenvolvimento', 'Ambiente para desenvolvimento de novas features', now),
            ('Testes', 'Ambiente para testes e QA', now)
        ]
        cursor.executemany(
            "INSERT INTO environments (name, description, created_at) VALUES (%s, %s, %s)",
            default_environments
        )
        print("✅ Ambientes padrão criados: Produção, Homologação, Desenvolvimento, Testes")

    # Tabela de Variáveis do Servidor
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS server_variables (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            value TEXT NOT NULL,
            description TEXT,
            is_protected BOOLEAN DEFAULT FALSE,
            is_password BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP NOT NULL
        )
        """
    )
    # Adiciona a variável BASE_DIR como padrão
    cursor.execute("SELECT COUNT(*) FROM server_variables")
    if cursor.fetchone()['count'] == 0:
        now = datetime.now()
        cursor.execute(
            "INSERT INTO server_variables (name, value, description, created_at) VALUES (%s, %s, %s, %s)",
            ('BASE_DIR', 'cloned_repos', 'Pasta raiz no servidor onde os repositórios são clonados.', now)
        )

    # =====================================================================
    # INSERIR VARIÁVEIS PADRÃO DO PROTHEUS
    # =====================================================================
    cursor.execute("SELECT COUNT(*) FROM server_variables WHERE name LIKE '%_PRD' OR name LIKE '%_HOM' OR name LIKE '%_DEV' OR name LIKE '%_TST'")
    
    if cursor.fetchone()['count'] == 0:
        now = datetime.now()
        
        # Lista de variáveis base
        base_variables = [
            ('BASE_DIR', 'Diretório base para clone de repositórios Git'),
            ('BUILD_DIR', 'Diretório de build/compilação'),
            ('FONTES_DIR', 'Diretório dos fontes .prw, .tlpp, .prx'),
            ('INCLUDE_DIR', 'Diretório de includes do Protheus'),
            ('LOG_DIR', 'Diretório de logs'),
            ('BASE_DIR_PATCHES', 'Diretório base para patches'),
            ('PASTA_APO', 'Pasta onde ficam os RPOs dos servidores'),
            ('PASTA_CMP', 'Pasta de compilação onde está o RPO compilado'),
            ('PASTA_BIN', 'Pasta dos binários do Protheus (appserver.ini)'),
            ('PROTHEUS_SERVER', 'Servidor Protheus (ex: localhost ou IP)'),
            ('PROTHEUS_PORT', 'Porta do servidor Protheus (ex: 1234)'),
            ('PROTHEUS_SECURE', 'Conexão segura: 0 para não, 1 para sim'),
            ('PROTHEUS_BUILD', 'Build do Protheus (ex: 7.00.240223P)'),
            ('PROTHEUS_ENV', 'Ambiente do Protheus (ex: protheus_cmp)'),
            ('PROTHEUS_USER', 'Usuário do Protheus para compilação'),
            ('PROTHEUS_PASSWORD', 'Senha do usuário Protheus'),
            ('SSH_HOST_WINDOWS', 'Host/IP do servidor Windows para conexão SSH'),
            ('SSH_USER_WINDOWS', 'Usuário SSH para conectar no servidor Windows'),
            ('SSH_PORT_WINDOWS', 'Porta SSH do servidor Windows (padrão: 22)'),
        ]
        
        # Sufixos dos ambientes
        environments_suffixes = [
            ('PRD', 'Produção', '/producao', '\\\\servidor-prd'),
            ('HOM', 'Homologação', '/homologacao', '\\\\servidor-hom'),
            ('DEV', 'Desenvolvimento', '/desenvolvimento', '\\\\servidor-dev'),
            ('TST', 'Testes', '/testes', '\\\\servidor-tst'),
        ]
        
        def get_placeholder_value(var_name, suffix, linux_path, windows_path):
            if var_name == 'BASE_DIR': return f"{linux_path}/git-repos"
            elif var_name in ['BUILD_DIR', 'FONTES_DIR', 'INCLUDE_DIR', 'LOG_DIR', 'BASE_DIR_PATCHES', 'PASTA_CMP']:
                return f"{linux_path}/{var_name.lower().replace('_dir', '').replace('_', '-')}"
            elif var_name == 'PASTA_APO': return f"{windows_path}\\apo"
            elif var_name == 'PASTA_BIN': return f"{windows_path}\\bin"
            elif var_name == 'PROTHEUS_SERVER': return f"servidor-{suffix.lower()}" if suffix != 'PRD' else 'localhost'
            elif var_name == 'PROTHEUS_PORT':
                port_map = {'PRD': '1234', 'HOM': '1235', 'DEV': '1236', 'TST': '1237'}
                return port_map[suffix]
            elif var_name == 'PROTHEUS_SECURE': return '0'
            elif var_name == 'PROTHEUS_BUILD': return '7.00.240223P'
            elif var_name == 'PROTHEUS_ENV':
                env_map = {'PRD': 'protheus_prd', 'HOM': 'protheus_hom', 'DEV': 'protheus_dev', 'TST': 'protheus_tst'}
                return env_map[suffix]
            elif var_name == 'PROTHEUS_USER': return 'admin'
            elif var_name == 'PROTHEUS_PASSWORD': return 'senha123'
            elif var_name == 'SSH_HOST_WINDOWS':
                host_map = {'PRD': '192.168.0.1', 'HOM': '192.168.0.2', 'DEV': '192.168.0.3', 'TST': '192.168.0.4'}
                return host_map[suffix]
            elif var_name == 'SSH_USER_WINDOWS': return 'administrador'
            elif var_name == 'SSH_PORT_WINDOWS': return '22'
            return f"/caminho/para/{var_name.lower()}"
        
        all_variables = []
        for suffix, env_name, linux_path, windows_path in environments_suffixes:
            for var_name, var_description in base_variables:
                full_var_name = f"{var_name}_{suffix}"
                placeholder_value = get_placeholder_value(var_name, suffix, linux_path, windows_path)
                full_description = f"[{env_name}] {var_description}"
                is_password_field = (var_name == 'PROTHEUS_PASSWORD')
                all_variables.append((full_var_name, placeholder_value, full_description, True, is_password_field, now))
        
        cursor.executemany(
            "INSERT INTO server_variables (name, value, description, is_protected, is_password, created_at) VALUES (%s, %s, %s, %s, %s, %s)",
            all_variables
        )
        print(f"✅ {len(all_variables)} variáveis padrão do Protheus inseridas com sucesso!")
        
    # (NOVA) Tabela de Serviços do Servidor
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS server_services (
            id SERIAL PRIMARY KEY,
            environment_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            display_name TEXT,
            server_name TEXT NOT NULL,
            description TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL,
            FOREIGN KEY (environment_id) REFERENCES environments(id) ON DELETE CASCADE
        )
        """
    )

    # Tabela de Usuários
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(255) UNIQUE NOT NULL,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255) NOT NULL,
            password VARCHAR(255) NOT NULL,
            password_salt VARCHAR(255),
            profile VARCHAR(50) NOT NULL,
            active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL,
            last_login TIMESTAMP,
            session_token VARCHAR(255),
            last_activity TIMESTAMP,
            session_timeout_minutes INTEGER DEFAULT 0,
            reset_token VARCHAR(255),
            reset_token_expires TIMESTAMP
        )
    """
    )

    # (ATUALIZADO) Tabela de Repositórios
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS repositories (
            id SERIAL PRIMARY KEY,
            environment_id INTEGER NOT NULL,
            github_id INTEGER, name VARCHAR(255) NOT NULL, full_name VARCHAR(255), description TEXT,
            private BOOLEAN, html_url TEXT, clone_url TEXT, language VARCHAR(100),
            default_branch VARCHAR(100), size INTEGER, updated_at TIMESTAMP, created_at TIMESTAMP,
            FOREIGN KEY (environment_id) REFERENCES environments (id) ON DELETE CASCADE
        )
        """
    )

    # (ATUALIZADO) Tabela de Comandos
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS commands (
            id SERIAL PRIMARY KEY,
            environment_id INTEGER NOT NULL,
            name VARCHAR(255) NOT NULL,
            command_category VARCHAR(50) NOT NULL DEFAULT 'build',
            type VARCHAR(50) NOT NULL,
            description TEXT,
            script TEXT NOT NULL,
            is_protected BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP,
            last_executed TIMESTAMP,
            FOREIGN KEY (environment_id) REFERENCES environments (id) ON DELETE CASCADE,
            CHECK (command_category IN ('build', 'deploy'))
        )
        """
    )

    # (ATUALIZADO) Tabela de Deploys
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS deploys (
            id SERIAL PRIMARY KEY,
            environment_id INTEGER NOT NULL,
            name VARCHAR(255) NOT NULL, description TEXT, command_id INTEGER NOT NULL,
            created_at TIMESTAMP,
            FOREIGN KEY (environment_id) REFERENCES environments (id) ON DELETE CASCADE,
            FOREIGN KEY (command_id) REFERENCES commands (id) ON DELETE CASCADE
        )
        """
    )
    
    # =====================================================================
    # INSERIR COMANDOS PADRÃO
    # =====================================================================
    cursor.execute("SELECT id, name FROM environments ORDER BY name")
    environments_map = {row['name']: row['id'] for row in cursor.fetchall()}
    
    suffix_map = {
        'Produção': 'PRD',
        'Homologação': 'HOM',
        'Desenvolvimento': 'DEV',
        'Testes': 'TST'
    }
    
    cursor.execute("SELECT COUNT(*) FROM commands WHERE name LIKE '%Apply Patches%' OR name LIKE '%Compilar Fontes%' OR name LIKE '%Troca Quente%'")
    
    if cursor.fetchone()['count'] == 0:
        now = datetime.now()
        


        # ===== SCRIPT 1: apply_patch.ps1 (BUILD) =====
        apply_patch_ps1_template = '''# ==============================================================================
# Script de aplicação de patches Protheus para ambiente Windows (PowerShell)
# ==============================================================================

# --- CONFIGURAÇÕES DE DIRETÓRIOS ---
$BASE_DIR_PATCHES = "${BASE_DIR_PATCHES_{{SUFFIX}}}"
$BUILD_DIR = "${BUILD_DIR_{{SUFFIX}}}"

# --- CONFIGURAÇÕES DO SERVIDOR PROTHEUS ---
$PROTHEUS_SERVER = "${PROTHEUS_SERVER_{{SUFFIX}}}"
$PROTHEUS_PORT = "${PROTHEUS_PORT_{{SUFFIX}}}"
$PROTHEUS_SECURE = "${PROTHEUS_SECURE_{{SUFFIX}}}"
$PROTHEUS_BUILD = "${PROTHEUS_BUILD_{{SUFFIX}}}"
$PROTHEUS_ENV = "${PROTHEUS_ENV_{{SUFFIX}}}"
$PROTHEUS_USER = "${PROTHEUS_USER_{{SUFFIX}}}"
$PROTHEUS_PASSWORD = "${PROTHEUS_PASSWORD_{{SUFFIX}}}"

# --- DEFINIÇÃO DAS PASTAS ---
$PENDENTES_DIR = "$BASE_DIR_PATCHES\\pendentes"
$ZIPS_PROCESSADOS_DIR = "$BASE_DIR_PATCHES\\zips_processados"
$APLICADOS_DIR = "$BASE_DIR_PATCHES\\aplicados"
$OUTPUT_INI_FILE = "$BUILD_DIR\\apply_patches.ini"
$LOG_FILE = "$BUILD_DIR\\apply_patch.log"
$ADVPLS_EXECUTABLE = "$BUILD_DIR\\advpls.exe"

# --- INÍCIO DO SCRIPT ---
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "📦 Extraindo arquivos ZIP da pasta pendentes..." -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

$zip_files = Get-ChildItem -Path $PENDENTES_DIR -Filter "*.zip" -File

if ($zip_files.Count -gt 0) {
    Write-Host "✅ Encontrados $($zip_files.Count) arquivos ZIP para extração" -ForegroundColor Green
    if (-not (Test-Path $ZIPS_PROCESSADOS_DIR)) {
        New-Item -ItemType Directory -Path $ZIPS_PROCESSADOS_DIR -Force | Out-Null
    }
    foreach ($zip_file in $zip_files) {
        Write-Host "📄 Extraindo: $($zip_file.Name)" -ForegroundColor Yellow
        Expand-Archive -Path $zip_file.FullName -DestinationPath $PENDENTES_DIR -Force
        Move-Item -Path $zip_file.FullName -Destination $ZIPS_PROCESSADOS_DIR -Force
    }
    Write-Host "🎉 Extração de arquivos ZIP concluída" -ForegroundColor Green
} else {
    Write-Host "⚠️ Nenhum arquivo ZIP encontrado para extração" -ForegroundColor Yellow
}

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "📄 Gerando script com lista de patches..." -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

if (-not (Test-Path $PENDENTES_DIR)) {
    Write-Host "❌ Pasta de patches não encontrada: $PENDENTES_DIR" -ForegroundColor Red
    Write-Host "🔨 Criando a pasta..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $PENDENTES_DIR -Force | Out-Null
    Write-Host "📁 Pasta criada. Por favor, coloque os arquivos de patch na pasta e execute novamente." -ForegroundColor Green
    exit 1
}

$patch_files = Get-ChildItem -Path $PENDENTES_DIR -Filter "*.PTM" -File | Sort-Object Name

if ($patch_files.Count -eq 0) {
    Write-Host "⚠️ Nenhum arquivo de patch PTM encontrado na pasta: $PENDENTES_DIR" -ForegroundColor Yellow
    exit 0
}

Write-Host "📋 Encontrados $($patch_files.Count) arquivos de patch" -ForegroundColor Green

$iniContent = @"
logToFile=$LOG_FILE
showConsoleOutput=true

;Sessão de Autenticação
[authentication]
action=authentication
server=$PROTHEUS_SERVER
port=$PROTHEUS_PORT
secure=$PROTHEUS_SECURE
build=$PROTHEUS_BUILD
environment=$PROTHEUS_ENV
user=$PROTHEUS_USER
psw=$PROTHEUS_PASSWORD

;Sessões para aplicar os patches no rpo, geradas automaticamente
"@

$session_number = 1
foreach ($patch_file in $patch_files) {
    $iniContent += @"

[patchApply_$session_number]
action=patchApply
patchFile=$($patch_file.FullName)
localPatch=True
applyOldProgram=False
"@
    $session_number++
}

$iniContent += @"

;Sessão que faz defrag do rpo
[defragRPO]
action=defragRPO
"@

$iniContent | Out-File -FilePath $OUTPUT_INI_FILE -Encoding Default -Force

Write-Host "✅ Arquivo INI gerado com sucesso: $OUTPUT_INI_FILE" -ForegroundColor Green
Write-Host "📊 Total de sessões de patch: $($patch_files.Count)" -ForegroundColor Green

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "🔧 Aplicando patches..." -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

if (-not (Test-Path $ADVPLS_EXECUTABLE)) {
    Write-Host "❌ Executável não encontrado em: $ADVPLS_EXECUTABLE" -ForegroundColor Red
    Write-Host "Verifique a variável BUILD_DIR no sistema." -ForegroundColor Yellow
    exit 1
}

& $ADVPLS_EXECUTABLE cli $OUTPUT_INI_FILE

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "=========================================" -ForegroundColor Red
    Write-Host "❌ ERRO ao aplicar patches! O advpls retornou código de erro." -ForegroundColor Red
    Write-Host "Verifique os logs acima para mais detalhes." -ForegroundColor Yellow
    Write-Host "=========================================" -ForegroundColor Red
    exit 1
}

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "🧹 Limpando arquivos de patches..." -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

if (-not (Test-Path $APLICADOS_DIR)) {
    New-Item -ItemType Directory -Path $APLICADOS_DIR -Force | Out-Null
}

Get-ChildItem -Path $PENDENTES_DIR -Filter "*.ptm" -File | Move-Item -Destination $APLICADOS_DIR -Force
Write-Host "Arquivos .ptm movidos para $APLICADOS_DIR" -ForegroundColor Green

Get-ChildItem -Path $PENDENTES_DIR -Recurse | Remove-Item -Force -Recurse
Write-Host "Arquivos restantes em $PENDENTES_DIR foram removidos." -ForegroundColor Green

Write-Host "✅ Processo concluído." -ForegroundColor Green'''

        # ===== SCRIPT 2: apply_patch.sh (BUILD) =====
        apply_patch_sh_template = '''#!/bin/bash

# ==============================================================================
# Script de aplicação de patches Protheus para ambiente Linux (Bash)
# ==============================================================================

# --- CONFIGURAÇÕES DE DIRETÓRIOS ---
BASE_DIR_PATCHES="${BASE_DIR_PATCHES_{{SUFFIX}}}"
BUILD_DIR="${BUILD_DIR_{{SUFFIX}}}"

# --- CONFIGURAÇÕES DO SERVIDOR PROTHEUS ---
PROTHEUS_SERVER="${PROTHEUS_SERVER_{{SUFFIX}}}"
PROTHEUS_PORT="${PROTHEUS_PORT_{{SUFFIX}}}"
PROTHEUS_SECURE="${PROTHEUS_SECURE_{{SUFFIX}}}"
PROTHEUS_BUILD="${PROTHEUS_BUILD_{{SUFFIX}}}"
PROTHEUS_ENV="${PROTHEUS_ENV_{{SUFFIX}}}"
PROTHEUS_USER="${PROTHEUS_USER_{{SUFFIX}}}"
PROTHEUS_PASSWORD="${PROTHEUS_PASSWORD_{{SUFFIX}}}"

# --- DEFINIÇÃO DAS PASTAS ---
PENDENTES_DIR="$BASE_DIR_PATCHES/pendentes"
ZIPS_PROCESSADOS_DIR="$BASE_DIR_PATCHES/zips_processados"
APLICADOS_DIR="$BASE_DIR_PATCHES/aplicados"
OUTPUT_INI_FILE="$BUILD_DIR/apply_patches.ini"
LOG_FILE="$BUILD_DIR/apply_patch.log"
ADVPLS_EXECUTABLE="$BUILD_DIR/advpls"

# --- INÍCIO DO SCRIPT ---
echo "========================================="
echo "📦 Extraindo arquivos ZIP da pasta pendentes..."
echo "========================================="

zip_files=$(find "$PENDENTES_DIR" -maxdepth 1 -type f -iname "*.zip")

if [ -n "$zip_files" ]; then
    file_count=$(echo "$zip_files" | wc -l)
    echo "✅ Encontrados $file_count arquivos ZIP para extração"
    mkdir -p "$ZIPS_PROCESSADOS_DIR"
    echo "$zip_files" | while read -r zip_file; do
        filename=$(basename "$zip_file")
        echo "📄 Extraindo: $filename"
        unzip -o "$zip_file" -d "$PENDENTES_DIR"
        mv "$zip_file" "$ZIPS_PROCESSADOS_DIR/"
    done
    echo "🎉 Extração de arquivos ZIP concluída"
else
    echo "⚠️ Nenhum arquivo ZIP encontrado para extração"
fi

echo "========================================="
echo "📄 Gerando script com lista de patches..."
echo "========================================="

if [ ! -d "$PENDENTES_DIR" ]; then
    echo "❌ Pasta de patches não encontrada: $PENDENTES_DIR"
    echo "🔨 Criando a pasta..."
    mkdir -p "$PENDENTES_DIR"
    echo "📁 Pasta criada. Por favor, coloque os arquivos de patch na pasta e execute novamente."
    exit 1
fi

patch_files=$(find "$PENDENTES_DIR" -maxdepth 1 -type f -iname "*.PTM" | sort)

if [ -z "$patch_files" ]; then
    echo "⚠️ Nenhum arquivo de patch PTM encontrado na pasta: $PENDENTES_DIR"
    exit 0
fi

patch_count=$(echo "$patch_files" | wc -l)
echo "📋 Encontrados $patch_count arquivos de patch"

cat > "$OUTPUT_INI_FILE" << EOF
logToFile=$LOG_FILE
showConsoleOutput=true

;Sessão de Autenticação
[authentication]
action=authentication
server=$PROTHEUS_SERVER
port=$PROTHEUS_PORT
secure=$PROTHEUS_SECURE
build=$PROTHEUS_BUILD
environment=$PROTHEUS_ENV
user=$PROTHEUS_USER
psw=$PROTHEUS_PASSWORD

;Sessões para aplicar os patches no rpo, geradas automaticamente
EOF

session_number=1
echo "$patch_files" | while read -r patch_file; do
    cat >> "$OUTPUT_INI_FILE" << EOF

[patchApply_$session_number]
action=patchApply
patchFile=$patch_file
localPatch=True
applyOldProgram=False
EOF
    ((session_number++))
done

cat >> "$OUTPUT_INI_FILE" << EOF

;Sessão que faz defrag do rpo
[defragRPO]
action=defragRPO
EOF

echo "✅ Arquivo INI gerado com sucesso: $OUTPUT_INI_FILE"
echo "📊 Total de sessões de patch: $patch_count"

echo "========================================="
echo "🔧 Aplicando patches..."
echo "========================================="

if [ ! -f "$ADVPLS_EXECUTABLE" ]; then
    echo "❌ Executável não encontrado em: $ADVPLS_EXECUTABLE"
    echo "Verifique a variável BUILD_DIR no sistema."
    exit 1
fi

"$ADVPLS_EXECUTABLE" cli "$OUTPUT_INI_FILE"

if [ $? -ne 0 ]; then
    echo ""
    echo "========================================="
    echo "❌ ERRO ao aplicar patches! O advpls retornou código de erro."
    echo "Verifique os logs acima para mais detalhes."
    echo "========================================="
    exit 1
fi

echo "========================================="
echo "🧹 Limpando arquivos de patches..."
echo "========================================="

mkdir -p "$APLICADOS_DIR"

find "$PENDENTES_DIR" -maxdepth 1 -type f -iname "*.ptm" -exec mv -t "$APLICADOS_DIR/" {} +
echo "Arquivos .ptm movidos para $APLICADOS_DIR"

rm -R -f "$PENDENTES_DIR"/*
echo "Arquivos restantes em $PENDENTES_DIR foram removidos."

echo "✅ Processo concluído."'''

        # ===== SCRIPT 3: compila.ps1 (BUILD) =====
        compila_ps1_template = '''# ==============================================================================
# Script de compilação de fontes Protheus para ambiente Windows (PowerShell)
# ==============================================================================

# --- CONFIGURAÇÕES DE DIRETÓRIOS ---
$BUILD_DIR = "${BUILD_DIR_{{SUFFIX}}}"
$FONTES_DIR = "${FONTES_DIR_{{SUFFIX}}}"
$INCLUDE_DIR = "${INCLUDE_DIR_{{SUFFIX}}}"
$LOG_DIR = "${LOG_DIR_{{SUFFIX}}}"

# --- CONFIGURAÇÕES DO SERVIDOR PROTHEUS ---
$PROTHEUS_SERVER = "${PROTHEUS_SERVER_{{SUFFIX}}}"
$PROTHEUS_PORT = "${PROTHEUS_PORT_{{SUFFIX}}}"
$PROTHEUS_SECURE = "${PROTHEUS_SECURE_{{SUFFIX}}}"
$PROTHEUS_BUILD = "${PROTHEUS_BUILD_{{SUFFIX}}}"
$PROTHEUS_ENV = "${PROTHEUS_ENV_{{SUFFIX}}}"
$PROTHEUS_USER = "${PROTHEUS_USER_{{SUFFIX}}}"
$PROTHEUS_PASSWORD = "${PROTHEUS_PASSWORD_{{SUFFIX}}}"

# --- DEFINIÇÃO DE ARQUIVOS ---
$LST_FILE = "$BUILD_DIR\\compila.txt"
$INI_FILE = "$BUILD_DIR\\compila.ini"
$LOG_FILE = "$LOG_DIR\\compila.log"
$ADVPLS_EXE = "$BUILD_DIR\\advpls.exe"

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host " 🔄 GERANDO LISTA DE FONTES" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

if (Test-Path $LST_FILE) {
    Remove-Item $LST_FILE -Force
}

# Verifica variações de extensão automaticamente
Get-ChildItem -Path "$FONTES_DIR\\*.prw", "$FONTES_DIR\\*.tlpp", "$FONTES_DIR\\*.prx" | 
    Select-Object -ExpandProperty Name | 
    Out-File -FilePath $LST_FILE -Encoding Default

Write-Host "✅ Lista de fontes gerada: $LST_FILE" -ForegroundColor Green

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host " 📄 GERANDO ARQUIVO DE CONFIGURAÇÃO" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

$iniContent = @"
logToFile=$LOG_FILE
showConsoleOutput=true

[user]
INCLUDE_DIR=$INCLUDE_DIR
LOG_DIR=$LOG_DIR
BUILD_DIR=$BUILD_DIR

[authentication]
action=authentication
server=$PROTHEUS_SERVER
port=$PROTHEUS_PORT
secure=$PROTHEUS_SECURE
build=$PROTHEUS_BUILD
environment=$PROTHEUS_ENV
user=$PROTHEUS_USER
psw=$PROTHEUS_PASSWORD

;Compila somente fontes diferentes do rpo
[compile]
action=compile
recompile=F
programlist=$LST_FILE
includes=$INCLUDE_DIR

;faz defrag do rpo
[defragRPO]
action=defragRPO
"@

$iniContent | Out-File -FilePath $INI_FILE -Encoding Default -Force

Write-Host "✅ Arquivo INI gerado com sucesso: $INI_FILE" -ForegroundColor Green

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host " 🔧 COMPILANDO FONTES" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

if (-not (Test-Path $ADVPLS_EXE)) {
    Write-Host "❌ Executável não encontrado: $ADVPLS_EXE" -ForegroundColor Red
    Write-Host "Verifique a variável BUILD_DIR no sistema." -ForegroundColor Yellow
    exit 1
}

Push-Location -Path "$FONTES_DIR"
& $ADVPLS_EXE cli $INI_FILE
Pop-Location

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "=========================================" -ForegroundColor Red
    Write-Host "❌ ERRO na compilação! O advpls retornou código de erro." -ForegroundColor Red
    Write-Host "Verifique os logs acima para mais detalhes." -ForegroundColor Yellow
    Write-Host "=========================================" -ForegroundColor Red
    exit 1
}

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "✅ Processo de compilação concluído! 🎉" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Cyan'''

        # ===== SCRIPT 4: compila.sh (BUILD) =====
        compila_sh_template = '''#!/bin/bash

# ==============================================================================
# Script de compilação de fontes Protheus para ambiente Linux (Bash)
# ==============================================================================

# --- CONFIGURAÇÕES DE DIRETÓRIOS ---
BUILD_DIR="${BUILD_DIR_{{SUFFIX}}}"
FONTES_DIR="${FONTES_DIR_{{SUFFIX}}}"
INCLUDE_DIR="${INCLUDE_DIR_{{SUFFIX}}}"
LOG_DIR="${LOG_DIR_{{SUFFIX}}}"

# --- CONFIGURAÇÕES DO SERVIDOR PROTHEUS ---
PROTHEUS_SERVER="${PROTHEUS_SERVER_{{SUFFIX}}}"
PROTHEUS_PORT="${PROTHEUS_PORT_{{SUFFIX}}}"
PROTHEUS_SECURE="${PROTHEUS_SECURE_{{SUFFIX}}}"
PROTHEUS_BUILD="${PROTHEUS_BUILD_{{SUFFIX}}}"
PROTHEUS_ENV="${PROTHEUS_ENV_{{SUFFIX}}}"
PROTHEUS_USER="${PROTHEUS_USER_{{SUFFIX}}}"
PROTHEUS_PASSWORD="${PROTHEUS_PASSWORD_{{SUFFIX}}}"

# --- DEFINIÇÃO DE ARQUIVOS ---
LST_FILE="$BUILD_DIR/compila.txt"
INI_FILE="$BUILD_DIR/compila.ini"
LOG_FILE="$LOG_DIR/compila.log"
ADVPLS_EXE="$BUILD_DIR/advpls"

echo "========================================="
echo " 🔄 GERANDO LISTA DE FONTES"
echo "========================================="

rm -f "$LST_FILE"

cd "$FONTES_DIR" || exit 1
find . -maxdepth 1 -type f \\( -iname "*.prw" -o -iname "*.tlpp" -o -iname "*.prx" \\) -printf "%f\\n" > "$LST_FILE"

echo "✅ Lista de fontes gerada: $LST_FILE"

echo "========================================="
echo " 📄 GERANDO ARQUIVO DE CONFIGURAÇÃO"
echo "========================================="

cat > "$INI_FILE" << EOF
logToFile=$LOG_FILE
showConsoleOutput=true

[user]
INCLUDE_DIR=$INCLUDE_DIR
LOG_DIR=$LOG_DIR
BUILD_DIR=$BUILD_DIR

[authentication]
action=authentication
server=$PROTHEUS_SERVER
port=$PROTHEUS_PORT
secure=$PROTHEUS_SECURE
build=$PROTHEUS_BUILD
environment=$PROTHEUS_ENV
user=$PROTHEUS_USER
psw=$PROTHEUS_PASSWORD

;Compila somente fontes diferentes do rpo
[compile]
action=compile
recompile=F
programlist=$LST_FILE
includes=$INCLUDE_DIR

;faz defrag do rpo
[defragRPO]
action=defragRPO
EOF

echo "✅ Arquivo INI gerado com sucesso: $INI_FILE"

echo "========================================="
echo " 🔧 COMPILANDO FONTES"
echo "========================================="

if [ ! -f "$ADVPLS_EXE" ]; then
    echo "❌ Executável não encontrado: $ADVPLS_EXE"
    echo "Verifique a variável BUILD_DIR no sistema."
    exit 1
fi

"$ADVPLS_EXE" cli "$INI_FILE"

if [ $? -ne 0 ]; then
    echo ""
    echo "========================================="
    echo "❌ ERRO na compilação! O advpls retornou código de erro."
    echo "Verifique os logs acima para mais detalhes."
    echo "========================================="
    exit 1
fi

echo "========================================="
echo "✅ Processo de compilação concluído! 🎉"
echo "========================================="'''

        # ===== SCRIPT 5: tq.ps1 (DEPLOY) =====
        tq_ps1_template = '''# ==============================================================================
# Script de Troca Quente (TQ) do RPO Protheus para ambiente Windows (PowerShell)
# ==============================================================================

Write-Host "--------------------------------------------------------------------------" -ForegroundColor Yellow
Write-Host "ATENCAO: Toda vez que esse script for executado, a pasta destino do RPO" -ForegroundColor Yellow
Write-Host "sempre sera criada pois ele busca a data e hora atual do sistema para" -ForegroundColor Yellow
Write-Host "nomear a pasta e busca a pasta atual do RPO para substituicao nos appserver.ini" -ForegroundColor Yellow
Write-Host "Execute com precisao e cuidado!" -ForegroundColor Yellow
Write-Host "--------------------------------------------------------------------------" -ForegroundColor Yellow

# --- CONFIGURAÇÕES DE DIRETÓRIOS ---
$PASTA_APO = "${PASTA_APO_{{SUFFIX}}}"
$PASTA_CMP = "${PASTA_CMP_{{SUFFIX}}}"
$PASTA_BIN = "${PASTA_BIN_{{SUFFIX}}}"

# Verifica se a pasta alvo existe
if (-not (Test-Path $PASTA_APO)) {
    Write-Host "Erro: O diretório PASTA_APO não foi encontrado em: $PASTA_APO" -ForegroundColor Red
    exit 1
}

# Procura o diretório mais recente que começa com '202'
Write-Host "Procurando o diretorio mais recente em: $PASTA_APO" -ForegroundColor Cyan

$anoAtual = (Get-Date).Year.ToString().Substring(0, 3) # Pega "202" ou "203" etc
$diretorios = Get-ChildItem -Path $PASTA_APO -Directory -Filter "${anoAtual}*" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $diretorios) {
    Write-Host "Erro: Nenhum diretório começando com '202' foi encontrado em $PASTA_APO" -ForegroundColor Red
    exit 1
}

$ORIGEM = $diretorios.Name

# Obtém a data e hora atual no formato desejado
$DESTINO = Get-Date -Format "yyyyMMdd_HHmm"

# Mostra em tela as pastas que serão atualizadas
Write-Host "-------------------------------------------" -ForegroundColor Cyan
Write-Host "Pasta de ORIGEM: $ORIGEM" -ForegroundColor Green
Write-Host "-------------------------------------------" -ForegroundColor Cyan
Write-Host "-------------------------------------------" -ForegroundColor Cyan
Write-Host "Pasta de DESTINO: $DESTINO" -ForegroundColor Green
Write-Host "-------------------------------------------" -ForegroundColor Cyan

Write-Host "REALIZANDO COPIA DO RPO COMPILACAO PARA SERVIDORES PROTHEUS..." -ForegroundColor Yellow

# Cria o diretório de destino
$PASTA_DESTINO = Join-Path $PASTA_APO $DESTINO
New-Item -ItemType Directory -Path $PASTA_DESTINO -Force | Out-Null

# Copia os arquivos RPO para o novo diretório de destino
Copy-Item -Path "$PASTA_CMP\\tttm120.rpo" -Destination $PASTA_DESTINO -Force
Copy-Item -Path "$PASTA_CMP\\custom.rpo" -Destination $PASTA_DESTINO -Force

Write-Host "Arquivos RPO copiados com sucesso!" -ForegroundColor Green

Write-Host "REALIZANDO TQ..." -ForegroundColor Yellow
Write-Host "Buscando arquivos appserver*.ini em $PASTA_BIN e subdiretórios..." -ForegroundColor Cyan

# Localiza os arquivos .ini RECURSIVAMENTE e substitui a string
$arquivosEncontrados = Get-ChildItem -Path $PASTA_BIN -Filter "appserver*.ini" -File -Recurse

if ($arquivosEncontrados) {
    Write-Host "Arquivos encontrados: $($arquivosEncontrados.Count)" -ForegroundColor Cyan
    
    $arquivosEncontrados | ForEach-Object {
        Write-Host "`nProcessando: $($_.FullName)" -ForegroundColor Yellow
        
        $conteudo = Get-Content $_.FullName -Raw
        
        # Verifica se encontrou a string de origem
        if ($conteudo -match [regex]::Escape($ORIGEM)) {
            Write-Host "  Substituindo '$ORIGEM' por '$DESTINO'" -ForegroundColor Yellow
            $conteudo = $conteudo -replace [regex]::Escape($ORIGEM), $DESTINO
            $conteudo | Set-Content $_.FullName -Force
            Write-Host "  Atualizado com sucesso!" -ForegroundColor Green
        } else {
            Write-Host "  String '$ORIGEM' nao encontrada (arquivo pode ja estar atualizado)" -ForegroundColor Gray
        }
    }
} else {
    Write-Host "NENHUM arquivo appserver*.ini encontrado!" -ForegroundColor Red
    Write-Host "Verifique o caminho: $PASTA_BIN" -ForegroundColor Yellow
}

Write-Host "`nPROCESSO CONCLUIDO!" -ForegroundColor Green'''

        # ===== SCRIPT 6: tq.sh (DEPLOY) =====
        tq_sh_template = '''#!/bin/bash

# ==============================================================================
# Script de Troca Quente (TQ) do RPO Protheus para ambiente Linux (Bash)
# ==============================================================================

echo "--------------------------------------------------------------------------"
echo "ATENCAO: Toda vez que esse script for executado, a pasta destino do RPO"
echo "sempre sera criada pois ele busca a data e hora atual do sistema para"
echo "nomear a pasta e busca a pasta atual do RPO para substituicao nos appserver.ini"
echo "Execute com precisao e cuidado!"
echo "--------------------------------------------------------------------------"

# --- CONFIGURAÇÕES DE DIRETÓRIOS ---
PASTA_APO="${PASTA_APO_{{SUFFIX}}}"
PASTA_CMP="${PASTA_CMP_{{SUFFIX}}}"
PASTA_BIN="${PASTA_BIN_{{SUFFIX}}}"

if [ ! -d "$PASTA_APO" ]; then
    echo "Erro: O diretório PASTA_APO não foi encontrado em: $PASTA_APO"
    exit 1
fi

echo "Procurando o diretorio mais recente em: $PASTA_APO"
ANO_ATUAL=$(date +'%Y' | cut -c1-3)  # Pega "202" ou "203" etc
DIRETORIO_MAIS_RECENTE=$(ls -td "$PASTA_APO"/${ANO_ATUAL}*/ 2>/dev/null | head -n 1)

if [ -z "$DIRETORIO_MAIS_RECENTE" ]; then
    echo "Erro: Nenhum diretório começando com '202' foi encontrado em $PASTA_APO"
    exit 1
fi

ORIGEM=$(basename "$DIRETORIO_MAIS_RECENTE")
DESTINO=$(date +'%Y%m%d_%H%M')

echo "-------------------------------------------"
echo "Pasta de ORIGEM: ${ORIGEM}"
echo "-------------------------------------------"
echo "-------------------------------------------"
echo "Pasta de DESTINO: ${DESTINO}"
echo "-------------------------------------------"

echo "REALIZANDO COPIA DO RPO COMPILACAO PARA SERVIDORES PROTHEUS..."

mkdir -p "${PASTA_APO}/${DESTINO}"

cp -p "${PASTA_CMP}/tttm120.rpo" "${PASTA_CMP}/custom.rpo" "${PASTA_APO}/${DESTINO}/"

echo "✅ Arquivos RPO copiados com sucesso!"

echo "REALIZANDO TQ..."

find "$PASTA_BIN" -type f -iname "appserver*.ini" -exec sed -i "s#${ORIGEM}#${DESTINO}#g" {} +

echo "PROCESSO CONCLUIDO!"'''
        
        scripts_metadata = [
            ('Apply Patches (PowerShell)', 'powershell', 'build', 'Aplica patches PTM no RPO usando advpls (Windows)', apply_patch_ps1_template),
            ('Apply Patches (Bash)', 'bash', 'build', 'Aplica patches PTM no RPO usando advpls (Linux)', apply_patch_sh_template),
            ('Compilar Fontes (PowerShell)', 'powershell', 'build', 'Compila fontes .prw, .tlpp, .prx no RPO (Windows)', compila_ps1_template),
            ('Compilar Fontes (Bash)', 'bash', 'build', 'Compila fontes .prw, .tlpp, .prx no RPO (Linux)', compila_sh_template),
            ('Troca Quente - TQ (PowerShell)', 'powershell', 'deploy', 'Realiza troca quente do RPO nos servidores (Windows)', tq_ps1_template),
            ('Troca Quente - TQ (Bash)', 'bash', 'deploy', 'Realiza troca quente do RPO nos servidores (Linux)', tq_sh_template),
        ]
        
        all_commands = []
        for env_name, env_id in environments_map.items():
            suffix = suffix_map[env_name]
            for script_name, script_type, script_category, script_description, script_template in scripts_metadata:
                final_script = script_template.replace('{{SUFFIX}}', suffix)
                full_command_name = f"{script_name} - {env_name}"
                all_commands.append((
                    env_id, full_command_name, script_category, script_type, 
                    f"{script_description} [Ambiente: {env_name}]", final_script, True, now
                ))
        
        cursor.executemany(
            """
            INSERT INTO commands (environment_id, name, command_category, type, description, script, is_protected, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            all_commands
        )
        print(f"✅ {len(all_commands)} comandos padrão inseridos com sucesso!")

    # (ATUALIZADO) Tabela de Pipelines
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS pipelines (
            id SERIAL PRIMARY KEY,
            environment_id INTEGER NOT NULL,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            deploy_command_id INTEGER,
            status VARCHAR(50),
            last_run VARCHAR(100),
            duration VARCHAR(100),
            is_protected BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP,
            FOREIGN KEY (environment_id) REFERENCES environments (id) ON DELETE CASCADE,
            FOREIGN KEY (deploy_command_id) REFERENCES commands (id) ON DELETE SET NULL
        )
        """
    )

    # Tabela de relacionamento Pipeline-Comandos
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS pipeline_commands (
            id SERIAL PRIMARY KEY,
            pipeline_id INTEGER NOT NULL,
            command_id INTEGER NOT NULL,
            sequence_order INTEGER NOT NULL,
            FOREIGN KEY (pipeline_id) REFERENCES pipelines (id) ON DELETE CASCADE,
            FOREIGN KEY (command_id) REFERENCES commands (id) ON DELETE CASCADE
        )
    """
    )
    
    # Outras tabelas essenciais (resumidas)
    tabelas_adicionais = [
        """CREATE TABLE IF NOT EXISTS github_settings (id INTEGER PRIMARY KEY CHECK (id = 1), token TEXT, username VARCHAR(255), saved_at TIMESTAMP)""",
        """CREATE TABLE IF NOT EXISTS pipeline_runs (id SERIAL PRIMARY KEY, pipeline_id INTEGER NOT NULL, run_number INTEGER NOT NULL, status VARCHAR(50) DEFAULT 'running', started_at TIMESTAMP NOT NULL, finished_at TIMESTAMP, started_by INTEGER, environment_id INTEGER, trigger_type VARCHAR(50) DEFAULT 'manual', error_message TEXT, FOREIGN KEY (pipeline_id) REFERENCES pipelines(id) ON DELETE CASCADE, FOREIGN KEY (started_by) REFERENCES users(id), FOREIGN KEY (environment_id) REFERENCES environments(id))""",
        """CREATE TABLE IF NOT EXISTS pipeline_run_logs (id SERIAL PRIMARY KEY, run_id INTEGER NOT NULL, command_id INTEGER, command_order INTEGER, output TEXT, status VARCHAR(50) DEFAULT 'running', started_at TIMESTAMP NOT NULL, finished_at TIMESTAMP, FOREIGN KEY (run_id) REFERENCES pipeline_runs(id) ON DELETE CASCADE)""",
        """CREATE TABLE IF NOT EXISTS releases (id SERIAL PRIMARY KEY, pipeline_id INTEGER NOT NULL, run_id INTEGER, release_number INTEGER NOT NULL, status VARCHAR(50) DEFAULT 'running', started_at TIMESTAMP NOT NULL, finished_at TIMESTAMP, deployed_by INTEGER, environment_id INTEGER, deploy_command_id INTEGER, deploy_script TEXT, error_message TEXT, FOREIGN KEY (pipeline_id) REFERENCES pipelines(id) ON DELETE CASCADE, FOREIGN KEY (run_id) REFERENCES pipeline_runs(id), FOREIGN KEY (deployed_by) REFERENCES users(id), FOREIGN KEY (environment_id) REFERENCES environments(id))""",
        """CREATE TABLE IF NOT EXISTS release_logs (id SERIAL PRIMARY KEY, release_id INTEGER NOT NULL, output TEXT, log_type VARCHAR(50) DEFAULT 'info', created_at TIMESTAMP NOT NULL, FOREIGN KEY (release_id) REFERENCES releases(id) ON DELETE CASCADE)""",
        """CREATE TABLE IF NOT EXISTS pipeline_run_output_logs (id SERIAL PRIMARY KEY, run_id INTEGER NOT NULL, output TEXT, log_type VARCHAR(50) DEFAULT 'output', created_at TIMESTAMP NOT NULL, FOREIGN KEY (run_id) REFERENCES pipeline_runs(id) ON DELETE CASCADE)""",
        """CREATE TABLE IF NOT EXISTS execution_logs (id SERIAL PRIMARY KEY, pipeline_id INTEGER, command_id INTEGER, status VARCHAR(50), output TEXT, error TEXT, started_at TEXT, finished_at TIMESTAMP, environment_id INTEGER, executed_by VARCHAR(255), FOREIGN KEY (pipeline_id) REFERENCES pipelines (id) ON DELETE CASCADE, FOREIGN KEY (command_id) REFERENCES commands (id) ON DELETE CASCADE)""",
        """CREATE TABLE IF NOT EXISTS rpo_versions (id SERIAL PRIMARY KEY, environment_id INTEGER NOT NULL, filename VARCHAR(255) NOT NULL, version_hash VARCHAR(64) NOT NULL, file_path TEXT NOT NULL, status VARCHAR(50) DEFAULT 'active', created_by INTEGER, created_at TIMESTAMP NOT NULL, FOREIGN KEY (environment_id) REFERENCES environments(id), FOREIGN KEY (created_by) REFERENCES users(id))"""
    ]
    
    for sql in tabelas_adicionais:
        cursor.execute(sql)

    # Tabela de Agendamentos de Pipelines
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_schedules (
            id SERIAL PRIMARY KEY,
            pipeline_id INTEGER NOT NULL,
            environment_id INTEGER NOT NULL,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            schedule_type VARCHAR(50) NOT NULL,
            schedule_config TEXT NOT NULL,
            is_active BOOLEAN DEFAULT FALSE,
            created_by INTEGER NOT NULL,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP,
            last_run_at TIMESTAMP,
            next_run_at TIMESTAMP,
            FOREIGN KEY (pipeline_id) REFERENCES pipelines(id) ON DELETE CASCADE,
            FOREIGN KEY (environment_id) REFERENCES environments(id),
            FOREIGN KEY (created_by) REFERENCES users(id)
        )
    """)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS service_actions (
            id SERIAL PRIMARY KEY,
            environment_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            action_type TEXT NOT NULL CHECK (action_type IN ('start', 'stop', 'restart')),
            os_type TEXT NOT NULL CHECK (os_type IN ('windows', 'linux')),
            force_stop BOOLEAN DEFAULT FALSE,
            service_ids TEXT NOT NULL,
            schedule_type TEXT CHECK (schedule_type IN ('once', 'daily', 'weekly', 'monthly')),
            schedule_config TEXT,
            is_active BOOLEAN DEFAULT FALSE,
            next_run_at TIMESTAMP,
            last_run_at TIMESTAMP,
            created_by INTEGER NOT NULL,
            created_at TIMESTAMP NOT NULL,
            FOREIGN KEY (environment_id) REFERENCES environments(id) ON DELETE CASCADE,
            FOREIGN KEY (created_by) REFERENCES users(id)
        )
        """
    )

    # Tabela de Logs de Execução de Ações de Serviços
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS service_action_logs (
            id SERIAL PRIMARY KEY,
            action_id INTEGER NOT NULL,
            environment_id INTEGER NOT NULL,
            status VARCHAR(50) NOT NULL,
            results JSONB,
            executed_by INTEGER,
            executed_at TIMESTAMP NOT NULL,
            FOREIGN KEY (action_id) REFERENCES service_actions(id) ON DELETE CASCADE,
            FOREIGN KEY (executed_by) REFERENCES users(id)
        )
        """
    )

    # Tabela de Chaves de API Externas
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS api_keys (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            key VARCHAR(255) UNIQUE NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            created_by INTEGER,
            created_at TIMESTAMP NOT NULL,
            last_used_at TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users(id)
        )
        """
    )

    # Tabela de Configurações Globais de Notificação
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS notification_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            smtp_server VARCHAR(255),
            smtp_port INTEGER,
            smtp_user VARCHAR(255),
            smtp_password VARCHAR(255),
            smtp_from_email VARCHAR(255),
            whatsapp_api_url VARCHAR(255),
            whatsapp_api_method VARCHAR(10) DEFAULT 'POST',
            whatsapp_api_headers TEXT,
            whatsapp_api_body TEXT
        )
        """
    )
    cursor.execute("SELECT id FROM notification_settings WHERE id = 1")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO notification_settings (id, whatsapp_api_method) VALUES (1, 'POST')")

    # Migrações e Colunas Adicionais
    migracoes = [
        ("releases", "deploy_command_id", "INTEGER"),
        ("server_services", "environment_id", "INTEGER"),
        ("server_services", "server_name", "TEXT DEFAULT 'localhost'"),
        ("server_services", "display_name", "TEXT"),
        ("server_services", "is_active", "BOOLEAN DEFAULT TRUE"),
        ("service_actions", "force_stop", "BOOLEAN DEFAULT FALSE"),
        ("server_variables", "is_protected", "BOOLEAN DEFAULT FALSE"),
        ("server_variables", "is_password", "BOOLEAN DEFAULT FALSE"),
        ("commands", "is_protected", "BOOLEAN DEFAULT FALSE"),
        ("pipelines", "is_protected", "BOOLEAN DEFAULT FALSE"),
        ("pipeline_schedules", "notify_emails", "TEXT"),
        ("pipeline_schedules", "notify_whatsapp", "TEXT"),
        ("service_actions", "notify_emails", "TEXT"),
        ("service_actions", "notify_whatsapp", "TEXT"),
        ("log_monitor_configs", "notify_emails", "TEXT"),
        ("users", "reset_token", "VARCHAR(255)"),
        ("users", "reset_token_expires", "TIMESTAMP")
    ]
    
    for table, col, type_def in migracoes:
        # Verificar se a tabela existe antes de tentar alterar
        cursor.execute(f"SELECT 1 FROM information_schema.tables WHERE table_name='{table}'")
        if not cursor.fetchone():
            continue  # Tabela ainda não criada pelas migrations, será tratada depois
        cursor.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name='{table}' AND column_name='{col}'")
        if not cursor.fetchone():
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {type_def}")
            print(f"  ✅ Coluna {col} adicionada à tabela {table}")

    # Tabela de Pipeline Run Output Logs (streaming de output)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_run_output_logs (
            id SERIAL PRIMARY KEY,
            run_id INTEGER NOT NULL,
            output TEXT,
            log_type VARCHAR(50) DEFAULT 'info',
            created_at TIMESTAMP NOT NULL,
            FOREIGN KEY (run_id) REFERENCES pipeline_runs(id) ON DELETE CASCADE
        )
    """)

    # Índices para performance
    indices = [
        ("idx_pipeline_runs_pipeline", "pipeline_runs", "pipeline_id"),
        ("idx_pipeline_runs_status", "pipeline_runs", "status"),
        ("idx_pipeline_runs_started", "pipeline_runs", "started_at"),
        ("idx_releases_pipeline", "releases", "pipeline_id"),
        ("idx_releases_run", "releases", "run_id"),
        ("idx_releases_status", "releases", "status"),
        ("idx_releases_started", "releases", "started_at"),
    ]
    
    for idx_name, table, column in indices:
        cursor.execute(f"SAVEPOINT sp_idx_{idx_name}")
        try:
            cursor.execute(f"""
                CREATE INDEX IF NOT EXISTS {idx_name}
                ON {table}({column})
            """)
            cursor.execute(f"RELEASE SAVEPOINT sp_idx_{idx_name}")
        except Exception:
            cursor.execute(f"ROLLBACK TO SAVEPOINT sp_idx_{idx_name}")

    # Atualizações de dados protegidos
    cursor.execute("UPDATE server_variables SET is_protected = TRUE WHERE name LIKE '%_PRD' OR name LIKE '%_HOM' OR name LIKE '%_DEV' OR name LIKE '%_TST'")
    cursor.execute("UPDATE server_variables SET is_password = TRUE WHERE name LIKE 'PROTHEUS_PASSWORD_%'")
    cursor.execute("UPDATE commands SET is_protected = TRUE WHERE name LIKE 'Apply Patches%' OR name LIKE 'Compilar Fontes%' OR name LIKE 'Troca Quente%'")
    cursor.execute("UPDATE pipelines SET is_protected = TRUE WHERE name LIKE '🔨%' OR name LIKE '🚀%'")

    # Criar usuário admin padrão
    cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
    if cursor.fetchone()['count'] == 0:
        hashed_password, salt = hash_password("4dm1n@4TURP0")
        cursor.execute(
            """
            INSERT INTO users (username, name, email, password, password_salt, profile, active, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            ("admin", "Administrador", "admin@company.com", hashed_password, salt, "admin", True, datetime.now())
        )

    # =====================================================================
    # INSERIR PIPELINES PADRÃO (48 pipelines = 6 tipos × 4 ambientes × 2 scripts)
    # =====================================================================
    
    cursor.execute("SELECT COUNT(*) FROM pipelines WHERE name LIKE '🔨%' OR name LIKE '🚀%'")
    
    if cursor.fetchone()['count'] == 0:
        now = datetime.now()
        
        print("\n🔧 Criando pipelines padrão...")
        
        # Buscar mapa de ambientes
        cursor.execute("SELECT id, name FROM environments")
        environments_map = {row['name']: row['id'] for row in cursor.fetchall()}
        
        # Definição das pipelines (6 tipos)
        pipeline_templates = [
            {
                'name': '🚀 Compilar fontes com deploy',
                'description': 'Compila fontes .prw, .tlpp, .prx e realiza troca quente (TQ) no ambiente',
                'build_commands': ['Compilar Fontes'],
                'deploy_command': 'Troca Quente - TQ'
            },
            {
                'name': '🚀 Aplicar patch com deploy',
                'description': 'Aplica patches PTM no RPO e realiza troca quente (TQ) no ambiente',
                'build_commands': ['Apply Patches'],
                'deploy_command': 'Troca Quente - TQ'
            },
            {
                'name': '🚀 Aplicar patch e compilar fonte com deploy',
                'description': 'Compila fontes, aplica patches PTM e realiza troca quente (TQ) no ambiente',
                'build_commands': ['Compilar Fontes', 'Apply Patches'],
                'deploy_command': 'Troca Quente - TQ'
            },
            {
                'name': '🔨 Compilar fontes sem deploy',
                'description': 'Compila fontes .prw, .tlpp, .prx no RPO (sem deploy)',
                'build_commands': ['Compilar Fontes'],
                'deploy_command': None
            },
            {
                'name': '🔨 Aplicar patch sem deploy',
                'description': 'Aplica patches PTM no RPO (sem deploy)',
                'build_commands': ['Apply Patches'],
                'deploy_command': None
            },
            {
                'name': '🔨 Aplicar patch e compilar fonte sem deploy',
                'description': 'Compila fontes e aplica patches PTM no RPO (sem deploy)',
                'build_commands': ['Compilar Fontes', 'Apply Patches'],
                'deploy_command': None
            }
        ]
        
        # Tipos de script
        script_types = [
            ('PowerShell', 'powershell'),
            ('Bash', 'bash')
        ]
        
        pipelines_created = 0
        
        for env_name, env_id in environments_map.items():
            for script_display_name, script_type in script_types:
                
                # Busca os IDs dos comandos para este ambiente e tipo de script
                commands_cache = {}
                
                for cmd_base_name in ['Apply Patches', 'Compilar Fontes', 'Troca Quente - TQ']:
                    full_cmd_name = f"{cmd_base_name} ({script_display_name}) - {env_name}"
                    
                    cursor.execute(
                        "SELECT id FROM commands WHERE name = %s AND environment_id = %s AND type = %s",
                        (full_cmd_name, env_id, script_type)
                    )
                    
                    cmd_result = cursor.fetchone()
                    if cmd_result:
                        commands_cache[cmd_base_name] = cmd_result['id']
                
                # Se não encontrou os comandos necessários, pula
                if len(commands_cache) < 3:
                    print(f"  ⚠️  Comandos não encontrados para {env_name} - {script_display_name}")
                    continue
                
                # Cria cada pipeline para este ambiente e tipo de script
                for pipeline_template in pipeline_templates:
                    
                    pipeline_full_name = f"{pipeline_template['name']} ({script_display_name}) - {env_name}"
                    
                    deploy_command_id = None
                    if pipeline_template['deploy_command'] and pipeline_template['deploy_command'] in commands_cache:
                        deploy_command_id = commands_cache[pipeline_template['deploy_command']]
                    
                    cursor.execute(
                        """
                        INSERT INTO pipelines (
                            environment_id, name, description, deploy_command_id, 
                            status, last_run, is_protected, created_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (
                            env_id,
                            pipeline_full_name,
                            pipeline_template['description'],
                            deploy_command_id,
                            'queued',
                            'Nunca executada',
                            True,
                            now
                        )
                    )
                    
                    pipeline_id = cursor.fetchone()['id']
                    
                    for sequence_order, cmd_base_name in enumerate(pipeline_template['build_commands']):
                        if cmd_base_name in commands_cache:
                            cursor.execute(
                                """
                                INSERT INTO pipeline_commands (pipeline_id, command_id, sequence_order)
                                VALUES (%s, %s, %s)
                                """,
                                (pipeline_id, commands_cache[cmd_base_name], sequence_order)
                            )
                    
                    pipelines_created += 1
        
        print(f"✅ {pipelines_created} pipelines padrão criadas com sucesso!")
        print(f"   • 3 pipelines COM deploy por ambiente/script")
        print(f"   • 3 pipelines SEM deploy por ambiente/script")

    # =====================================================================
    # SEED: BASE DE CONHECIMENTO (erros Protheus)
    # =====================================================================
    cursor.execute("SAVEPOINT sp_kb_seed")
    try:
        cursor.execute("SELECT COUNT(*) FROM knowledge_articles")
        if cursor.fetchone()['count'] == 0:
            # Compatível com PyInstaller (.exe) e modo console
            if getattr(sys, 'frozen', False):
                base_dir = os.path.join(sys._MEIPASS, 'app', 'database')
            else:
                base_dir = os.path.dirname(os.path.abspath(__file__))
            seed_file = os.path.join(base_dir, "knowledge_seed.json")
            if os.path.exists(seed_file):
                with open(seed_file, "r", encoding="utf-8") as f:
                    kb_articles = json.load(f)

                now = datetime.now()
                kb_count = 0
                for article in kb_articles:
                    cursor.execute(
                        """
                        INSERT INTO knowledge_articles
                            (title, category, error_pattern, description, causes,
                             solution, code_snippet, reference_url, tags, source,
                             created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            article["title"],
                            article["category"],
                            article.get("error_pattern", ""),
                            article.get("description", ""),
                            article.get("causes", ""),
                            article.get("solution", ""),
                            article.get("code_snippet", ""),
                            article.get("reference_url", ""),
                            article.get("tags", article["category"]),
                            "erros_protheus",
                            now,
                        ),
                    )
                    kb_count += 1
                print(f"✅ {kb_count} artigos da base de conhecimento importados automaticamente!")
            else:
                print("⚠️  Arquivo knowledge_seed.json não encontrado, pulando seed da base de conhecimento")
        cursor.execute("RELEASE SAVEPOINT sp_kb_seed")
    except Exception as e:
        cursor.execute("ROLLBACK TO SAVEPOINT sp_kb_seed")
        print(f"⚠️  Erro ao popular base de conhecimento (tabela pode não existir ainda): {e}")

    # Finalização
    try:
        conn.commit()
        print("✓ Banco de dados inicializado com sucesso!")
    except Exception as e:
        conn.rollback()
        print(f"⚠️  Erro ao inicializar banco (ignorando em reload): {e}")
    finally:
        release_db_connection(conn)
