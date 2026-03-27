# -*- coding: utf-8 -*-
"""
AtuDIC - Sistema de Build e Instalador
Versão: 2.0
Data: 2025-11-17

Este script automatiza:
1. Ofuscação do código Python (PyArmor)
2. Ofuscação do código JavaScript
3. Empacotamento em executável (PyInstaller)
4. Criação do instalador Windows (Inno Setup)

Uso: python build_installer.py  (da raiz do projeto)

Artefatos de saída são gerados em aturpo_win/:
  aturpo_win/obfuscated/  — código ofuscado
  aturpo_win/build/       — artefatos intermediários do PyInstaller
  aturpo_win/dist/        — executável final
  aturpo_win/Output/      — instalador Inno Setup
"""

import os
import sys
import shutil
import subprocess
import json
from pathlib import Path
from datetime import datetime

# Força UTF-8 no Windows para evitar UnicodeEncodeError ao imprimir emojis
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Configurações
VERSION = "1.0.0"
APP_NAME = "AtuDIC"
AUTHOR = "Barbito / Normatel"

# Diretório raiz do projeto (onde este script reside)
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# Diretório de build (artefatos de saída)
BUILD_DIR = os.path.join(PROJECT_ROOT, 'aturpo_win')

# Cores para terminal
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_step(message):
    """Imprime mensagem de etapa"""
    print(f"\n{Colors.OKBLUE}{'='*60}{Colors.ENDC}")
    print(f"{Colors.BOLD}{message}{Colors.ENDC}")
    print(f"{Colors.OKBLUE}{'='*60}{Colors.ENDC}\n")

def print_success(message):
    """Imprime mensagem de sucesso"""
    print(f"{Colors.OKGREEN}✓ {message}{Colors.ENDC}")

def print_error(message):
    """Imprime mensagem de erro"""
    print(f"{Colors.FAIL}✗ {message}{Colors.ENDC}")

def print_warning(message):
    """Imprime mensagem de aviso"""
    print(f"{Colors.WARNING}⚠ {message}{Colors.ENDC}")

def check_requirements():
    """Verifica se todas as ferramentas necessárias estão instaladas"""
    print_step("🔍 Verificando Requisitos")

    requirements = {
        'pyarmor': 'PyArmor não encontrado. Instale com: pip install pyarmor',
        'pyinstaller': 'PyInstaller não encontrado. Instale com: pip install pyinstaller',
        'javascript-obfuscator': 'JavaScript Obfuscator não encontrado. Instale com: npm install -g javascript-obfuscator'
    }

    all_ok = True

    # Verificar PyArmor (ignorado na checagem estrita devido a saida trial do stdout)
    all_ok = True

    # Verificar PyInstaller (ignorado para evitar falha no subprocess.run path lookup)
    # try:
    #     result = subprocess.run(['pyinstaller', '--version'], capture_output=True, text=True, timeout=5)
    #     if result.returncode == 0:
    #         print_success(f"PyInstaller encontrado: {result.stdout.strip()}")
    #     else:
    #         print_error(requirements['pyinstaller'])
    #         all_ok = False
    # except:
    #     print_error(requirements['pyinstaller'])
    #     all_ok = False

    # Verificar JavaScript Obfuscator
    try:
        cmd_name = 'javascript-obfuscator.cmd' if sys.platform == 'win32' else 'javascript-obfuscator'
        result = subprocess.run([cmd_name, '--version'], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print_success(f"JavaScript Obfuscator encontrado: {result.stdout.strip()}")
        else:
            print_warning(requirements['javascript-obfuscator'])
            print_warning("JavaScript não será ofuscado, mas o build continuará")
    except:
        print_warning(requirements['javascript-obfuscator'])
        print_warning("JavaScript não será ofuscado, mas o build continuará")

    # Verificar Inno Setup (apenas aviso)
    inno_paths = [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe"
    ]

    inno_found = False
    for path in inno_paths:
        if os.path.exists(path):
            print_success(f"Inno Setup encontrado: {path}")
            inno_found = True
            break

    if not inno_found:
        print_warning("Inno Setup não encontrado. Instale de: https://jrsoftware.org/isdl.php")
        print_warning("O instalador .exe não será criado automaticamente")

    return all_ok

def clean_build_dirs():
    """Remove diretórios de build anteriores"""
    print_step("🧹 Limpando Diretórios Anteriores")

    dirs_to_clean = [
        os.path.join(BUILD_DIR, 'build'),
        os.path.join(BUILD_DIR, 'dist'),
        os.path.join(BUILD_DIR, 'obfuscated'),
        os.path.join(BUILD_DIR, 'Output'),
    ]

    for dir_path in dirs_to_clean:
        if os.path.exists(dir_path):
            try:
                shutil.rmtree(dir_path)
                print_success(f"Removido: {os.path.relpath(dir_path, PROJECT_ROOT)}/")
            except Exception as e:
                print_error(f"Erro ao remover {os.path.relpath(dir_path, PROJECT_ROOT)}/: {e}")
        else:
            print_warning(f"Diretório não existe: {os.path.relpath(dir_path, PROJECT_ROOT)}/")

    # Remover arquivo .spec se existir
    spec_file = os.path.join(BUILD_DIR, 'ATUDIC.spec')
    if os.path.exists(spec_file):
        os.remove(spec_file)
        print_success("Removido: aturpo_win/ATUDIC.spec")

def minify_frontend():
    """Minifica assets JS e CSS do frontend."""
    print_step("📦 Minificando Assets Frontend")

    script_path = os.path.join(PROJECT_ROOT, 'scripts', 'minify_assets.py')

    if not os.path.exists(script_path):
        print_warning("Script de minificação não encontrado, pulando...")
        return True

    try:
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True, text=True, timeout=60, cwd=PROJECT_ROOT
        )
        if result.returncode == 0:
            print_success("Assets minificados com sucesso!")
            if result.stdout:
                for line in result.stdout.strip().split('\n'):
                    if '✅' in line:
                        print(f"  {line.strip()}")
            return True
        else:
            print_warning(f"Minificação falhou: {result.stderr}")
            return True  # Não bloqueia o build
    except Exception as e:
        print_warning(f"Erro ao minificar: {e}")
        return True  # Não bloqueia o build


def obfuscate_python():
    """Ofusca os arquivos Python com PyArmor"""
    print_step("🔒 Ofuscando Código Python (PyArmor)")

    # Criar diretório obfuscated dentro de aturpo_win/
    obfuscated_dir = os.path.join(BUILD_DIR, 'obfuscated')
    os.makedirs(obfuscated_dir, exist_ok=True)

    try:
        # PyArmor: modo básico para módulo inteiro (app/) e run.py
        print("Ofuscando run.py e pasta app/ (PyArmor Trial - modo básico)...")

        # Ofuscar run.py principal
        result_run = subprocess.run([
            'pyarmor',
            'gen',
            '-O', obfuscated_dir,
            'run.py'
        ], capture_output=True, text=True, timeout=120, cwd=PROJECT_ROOT)

        # Ofuscar a pasta app/ inteira recursivamente
        result_app = subprocess.run([
            'pyarmor',
            'gen',
            '-O', obfuscated_dir,
            '-r', 'app'
        ], capture_output=True, text=True, timeout=300, cwd=PROJECT_ROOT)

        if result_run.returncode == 0 and result_app.returncode == 0:
            print_success("run.py e app/ ofuscados com sucesso!")
        else:
            print_warning(f"PyArmor falhou (run.py): {result_run.stderr}")
            print_warning(f"PyArmor falhou (app/): {result_app.stderr}")
            print_warning("Copiando arquivos sem ofuscação...")

            # Copiar sem ofuscação como fallback
            shutil.copy2(os.path.join(PROJECT_ROOT, 'run.py'), os.path.join(obfuscated_dir, 'run.py'))
            obfuscated_app = os.path.join(obfuscated_dir, 'app')
            if os.path.exists(obfuscated_app):
                shutil.rmtree(obfuscated_app)
            shutil.copytree(os.path.join(PROJECT_ROOT, 'app'), obfuscated_app)
            print_warning("Arquivos copiados SEM ofuscação (PyArmor Trial limitado)")

        # Copiar arquivos estáticos na nova estrutura modular
        # NOTA: static e templates ficam na raiz e não dentro de app/
        dirs_to_copy = [
            (os.path.join(PROJECT_ROOT, 'static'), os.path.join(obfuscated_dir, 'app', 'static'))
        ]

        for src, dest in dirs_to_copy:
            if os.path.exists(src):
                if os.path.exists(dest):
                    shutil.rmtree(dest)
                shutil.copytree(src, dest)
                print_success(f"Copiado: {os.path.relpath(src, PROJECT_ROOT)}/")
            else:
                print_warning(f"Diretório não encontrado: {os.path.relpath(src, PROJECT_ROOT)}/")

        # Copiar skills do agente (prompt/skills/*.md)
        skills_src = os.path.join(PROJECT_ROOT, 'prompt', 'skills')
        skills_dest = os.path.join(obfuscated_dir, 'prompt', 'skills')
        if os.path.isdir(skills_src):
            if os.path.exists(skills_dest):
                shutil.rmtree(skills_dest)
            shutil.copytree(skills_src, skills_dest)
            skill_count = len([f for f in os.listdir(skills_src) if f.endswith('.md')])
            print_success(f"Copiado: prompt/skills/ ({skill_count} skills)")
        else:
            print_warning("Diretório prompt/skills/ não encontrado")

        # Copiar prompt/specialists/ (perfis de especialistas do agente)
        specialists_src = os.path.join(PROJECT_ROOT, 'prompt', 'specialists')
        specialists_dest = os.path.join(obfuscated_dir, 'prompt', 'specialists')
        if os.path.isdir(specialists_src):
            if os.path.exists(specialists_dest):
                shutil.rmtree(specialists_dest)
            shutil.copytree(specialists_src, specialists_dest)
            specialist_count = len([f for f in os.listdir(specialists_src) if f.endswith('.md')])
            print_success(f"Copiado: prompt/specialists/ ({specialist_count} perfis)")
        else:
            print_warning("Diretório prompt/specialists/ não encontrado")

        # Copiar prompt core e specialists.yml
        for fname in ['ATUDIC_AGENT_CONTEXT.md', 'ATUDIC_AGENT_CONTEXT_CORE.md', 'specialists.yml', 'chains.yml']:
            src_file = os.path.join(PROJECT_ROOT, 'prompt', fname)
            dest_file = os.path.join(obfuscated_dir, 'prompt', fname)
            if os.path.exists(src_file):
                os.makedirs(os.path.dirname(dest_file), exist_ok=True)
                shutil.copy2(src_file, dest_file)
                print_success(f"Copiado: prompt/{fname}")

        # Copiar arquivos de dados (não-.py) que o PyArmor ignora
        data_files_to_copy = [
            ('app/database/knowledge_seed.json', 'app/database/knowledge_seed.json'),
        ]
        for rel_src, rel_dest in data_files_to_copy:
            src_file = os.path.join(PROJECT_ROOT, rel_src)
            dest_file = os.path.join(obfuscated_dir, rel_dest)
            if os.path.exists(src_file):
                os.makedirs(os.path.dirname(dest_file), exist_ok=True)
                shutil.copy2(src_file, dest_file)
                print_success(f"Copiado data file: {rel_src}")
            else:
                print_warning(f"Data file não encontrado: {rel_src}")

        # Copiar arquivos extras da raiz necessários para o build (sem ofuscação adicional)
        root_files_to_copy = ['license_system.py', 'activate_license.py', 'security_enhancements.py', 'index.html', 'theme.css', 'activate_license.html', 'sw.js']
        for file in root_files_to_copy:
            src_file = os.path.join(PROJECT_ROOT, file)
            dest_file = os.path.join(obfuscated_dir, file)
            if os.path.exists(src_file):
                shutil.copy2(src_file, dest_file)
                print_success(f"Copiado módulo raiz: {file}")

        return True

    except Exception as e:
        print_error(f"Erro durante ofuscação Python: {e}")
        print_warning("Tentando copiar arquivos sem ofuscação...")

        # Fallback: copiar tudo sem ofuscação
        try:
            os.makedirs(obfuscated_dir, exist_ok=True)
            shutil.copy2(os.path.join(PROJECT_ROOT, 'run.py'), os.path.join(obfuscated_dir, 'run.py'))
            obfuscated_app = os.path.join(obfuscated_dir, 'app')
            if os.path.exists(obfuscated_app):
                shutil.rmtree(obfuscated_app)
            shutil.copytree(os.path.join(PROJECT_ROOT, 'app'), obfuscated_app)

            # Copiar as pastas static e templates também no fallback se falhar
            dirs_to_copy = [
                (os.path.join(PROJECT_ROOT, 'static'), os.path.join(obfuscated_dir, 'app', 'static'))
            ]
            for src, dest in dirs_to_copy:
                if os.path.exists(src):
                    if os.path.exists(dest):
                        shutil.rmtree(dest)
                    shutil.copytree(src, dest)

            print_warning("Arquivos copiados SEM ofuscação")
            return True

        except Exception as e2:
            print_error(f"Falha no fallback: {e2}")
            return False

def obfuscate_javascript():
    """Ofusca os arquivos JavaScript"""
    print_step("🔒 Ofuscando Código JavaScript")

    obfuscated_dir = os.path.join(BUILD_DIR, 'obfuscated')

    # Verificar se javascript-obfuscator está disponível
    cmd_name = 'javascript-obfuscator.cmd' if sys.platform == 'win32' else 'javascript-obfuscator'
    try:
        check_result = subprocess.run([cmd_name, '--version'],
                                     capture_output=True, timeout=10)
        if check_result.returncode != 0:
            print_warning("JavaScript Obfuscator não disponível, pulando ofuscação JS...")
            return True
    except Exception as e:
        print_warning(f"JavaScript Obfuscator não encontrado: {e}")
        print_warning("Continuando sem ofuscação JavaScript...")
        return True

    js_files = [
        os.path.join(obfuscated_dir, 'app/static/js/api-client.js'),
        os.path.join(obfuscated_dir, 'app/static/js/integration-core.js'),
        os.path.join(obfuscated_dir, 'app/static/js/integration-auth.js'),
        os.path.join(obfuscated_dir, 'app/static/js/integration-environments.js'),
        os.path.join(obfuscated_dir, 'app/static/js/integration-commands.js'),
        os.path.join(obfuscated_dir, 'app/static/js/integration-pipelines.js'),
        os.path.join(obfuscated_dir, 'app/static/js/integration-ci-cd.js'),
        os.path.join(obfuscated_dir, 'app/static/js/integration-schedules.js'),
        os.path.join(obfuscated_dir, 'app/static/js/integration-repositories.js'),
        os.path.join(obfuscated_dir, 'app/static/js/integration-source-control.js'),
        os.path.join(obfuscated_dir, 'app/static/js/integration-ui.js'),
        os.path.join(obfuscated_dir, 'app/static/js/integration-observability.js'),
        os.path.join(obfuscated_dir, 'app/static/js/integration-knowledge.js'),
        os.path.join(obfuscated_dir, 'app/static/js/integration-database.js'),
        os.path.join(obfuscated_dir, 'app/static/js/integration-processes.js'),
        os.path.join(obfuscated_dir, 'app/static/js/integration-documentation.js'),
        os.path.join(obfuscated_dir, 'app/static/js/integration-devworkspace.js'),
        os.path.join(obfuscated_dir, 'app/static/js/integration-agent.js'),
        os.path.join(obfuscated_dir, 'app/static/js/integration-auditor.js'),
    ]

    all_success = True

    for js_file in js_files:
        if os.path.exists(js_file):
            print(f"Ofuscando {os.path.basename(js_file)}...")

            # Fazer backup
            backup_file = f"{js_file}.backup"
            shutil.copy2(js_file, backup_file)

            # Ofuscar
            result = subprocess.run([
                cmd_name,
                js_file,
                '--output', js_file,
                '--compact', 'true',
                '--control-flow-flattening', 'true',
                '--control-flow-flattening-threshold', '0.75',
                '--dead-code-injection', 'true',
                '--dead-code-injection-threshold', '0.4',
                '--string-array', 'true',
                '--string-array-rotate', 'true',
                '--string-array-shuffle', 'true',
                '--string-array-threshold', '0.75'
            ], capture_output=True, text=True, timeout=60)

            if result.returncode == 0:
                print_success(f"{os.path.basename(js_file)} ofuscado!")
                # Remover backup
                if os.path.exists(backup_file):
                    os.remove(backup_file)
            else:
                print_warning(f"Falha ao ofuscar {os.path.basename(js_file)}, mantendo original")
                # Restaurar backup
                if os.path.exists(backup_file):
                    shutil.move(backup_file, js_file)
                all_success = False
        else:
            print_warning(f"Arquivo não encontrado: {js_file}")
            all_success = False

    if all_success:
        print_success("JavaScript ofuscado com sucesso!")
    else:
        print_warning("Alguns arquivos JS não foram ofuscados, mas o build continua...")

    return True  # Sempre retorna True para não bloquear o build

def create_executable():
    """Cria o executável usando PyInstaller"""
    print_step("📦 Criando Executável (PyInstaller)")

    obfuscated_dir = os.path.join(BUILD_DIR, 'obfuscated')

    # Coletar recursivamente todos os modulos da pasta app/ para evitar ModuleNotFoundError
    dynamic_hidden_imports = set([
        'flask', 'flask.cli', 'psycopg2', 'psycopg2.extensions', 'psycopg2.extras', 'psycopg2.errors', 'psycopg2.pool',
        'cryptography', 'cryptography.fernet', 'werkzeug', 'jinja2', 'click', 'itsdangerous', 'markupsafe',
        'requests', 'sqlite3', 'flask_cors', 'dateutil', 'dateutil.relativedelta',
        'dateutil.parser', 'license_system', 'app', 'psutil', 'wmi', 'pythoncom', 'win32com.client',
        'logging.handlers', 'email', 'email.mime', 'email.mime.text', 'email.mime.multipart', 'email.utils', 'email.mime.application',
        'bcrypt', 'bcrypt._bcrypt',
        # WSGI server Windows (produção)
        'waitress', 'waitress.server', 'waitress.task', 'waitress.channel',
        # HTML parser (TDN ingestor)
        'bs4', 'bs4.builder', 'bs4.builder._htmlparser',
        # Drivers de banco de dados externo (módulo Banco de Dados)
        'pymssql', 'pymssql._pymssql',
        'pymysql', 'pymysql.cursors', 'pymysql.connections',
        'oracledb',
    ])

    app_dir = os.path.join(PROJECT_ROOT, 'app')

    for root, _, files in os.walk(app_dir):
        for f in files:
            if f.endswith('.py'):
                # Calcular modulo relativo exp: app.routes.auth
                rel_path = os.path.relpath(os.path.join(root, f), PROJECT_ROOT)
                mod_name = rel_path.replace(os.sep, '.')[:-3]
                if mod_name.endswith('.__init__'):
                    mod_name = mod_name[:-9]
                dynamic_hidden_imports.add(mod_name)

    # Format hidden imports for spec file
    hidden_imports_str = ",\n        ".join(f"'{mod}'" for mod in sorted(dynamic_hidden_imports))

    # Paths relativos ao BUILD_DIR (onde PyInstaller será executado)
    obfuscated_rel = 'obfuscated'

    # Avaliar ícone antes de gerar o spec (obfuscated_dir não existe no contexto do PyInstaller)
    favicon_path = os.path.join(obfuscated_dir, 'app', 'static', 'favicon.ico')
    icon_line = f"'{obfuscated_rel}/app/static/favicon.ico'" if os.path.exists(favicon_path) else "None"

    try:
        # Criar arquivo de especificação customizado
        spec_content = f"""# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['{obfuscated_rel}/run.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('{obfuscated_rel}/app/static', 'app/static'),
        ('{obfuscated_rel}/app/database/knowledge_seed.json', 'app/database'),
        ('{obfuscated_rel}/index.html', '.'),
        ('{obfuscated_rel}/theme.css', '.'),
        ('{obfuscated_rel}/activate_license.html', '.'),
        ('{obfuscated_rel}/activate_license.py', '.'),
        ('{obfuscated_rel}/memory/MEMORY.md', 'memory'),
        ('{obfuscated_rel}/memory/TOOLS.md', 'memory'),
        ('{obfuscated_rel}/prompt/ATUDIC_AGENT_CONTEXT.md', 'prompt'),
        ('{obfuscated_rel}/prompt/ATUDIC_AGENT_CONTEXT_CORE.md', 'prompt'),
        ('{obfuscated_rel}/prompt/specialists.yml', 'prompt'),
        ('{obfuscated_rel}/prompt/chains.yml', 'prompt'),
        ('{obfuscated_rel}/prompt/specialists', 'prompt/specialists'),
        ('{obfuscated_rel}/prompt/skills', 'prompt/skills'),
        ('{obfuscated_rel}/sw.js', '.'),
    ],
    hiddenimports=[
        {hidden_imports_str}
    ],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ATUDIC',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    icon={icon_line},
)
"""

        spec_file = os.path.join(BUILD_DIR, 'ATUDIC.spec')
        with open(spec_file, 'w', encoding='utf-8') as f:
            f.write(spec_content)

        print_success("Arquivo .spec criado")

        # Executar PyInstaller a partir de aturpo_win/ (onde ficam os artefatos)
        print("Executando PyInstaller... (isso pode levar alguns minutos)")
        result = subprocess.run([
            'pyinstaller',
            '--clean',
            '--noconfirm',
            'ATUDIC.spec'
        ], capture_output=True, text=True, cwd=BUILD_DIR)

        dist_exe = os.path.join(BUILD_DIR, 'dist', 'ATUDIC.exe')
        if result.returncode == 0 and os.path.exists(dist_exe):
            size = os.path.getsize(dist_exe) / (1024 * 1024)
            print_success(f"Executável criado: aturpo_win/dist/ATUDIC.exe ({size:.2f} MB)")
            return True
        else:
            print_error("Falha ao criar executável")
            if result.stderr:
                print(result.stderr)
            return False

    except Exception as e:
        print_error(f"Erro ao criar executável: {e}")
        return False

def prepare_installer_files():
    """Prepara arquivos adicionais para o instalador"""
    print_step("📋 Preparando Arquivos do Instalador")

    dist_dir = os.path.join(BUILD_DIR, 'dist')

    # Criar diretório de distribuição se não existir
    os.makedirs(dist_dir, exist_ok=True)

    # Copiar scripts de serviço (ficam em aturpo_win/)
    service_files = ['install_service.bat', 'uninstall_service.bat', 'nssm.exe']

    for file in service_files:
        src = os.path.join(BUILD_DIR, file)
        if os.path.exists(src):
            shutil.copy2(src, dist_dir)
            print_success(f"Copiado: {file}")
        else:
            print_warning(f"Arquivo não encontrado: aturpo_win/{file}")

    # Criar arquivo de versão
    version_info = {
        'version': VERSION,
        'build_date': datetime.now().isoformat(),
        'python_version': sys.version,
    }

    with open(os.path.join(dist_dir, 'version.json'), 'w', encoding='utf-8') as f:
        json.dump(version_info, f, indent=2)

    print_success("Arquivo version.json criado")

    return True

def create_installer():
    """Cria o instalador usando Inno Setup"""
    print_step("🎁 Criando Instalador Windows (Inno Setup)")

    inno_paths = [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe"
    ]

    iscc_path = None
    for path in inno_paths:
        if os.path.exists(path):
            iscc_path = path
            break

    if not iscc_path:
        print_error("Inno Setup não encontrado!")
        print_warning("Instale o Inno Setup de: https://jrsoftware.org/isdl.php")
        print_warning("Depois execute manualmente: ISCC.exe installer.iss")
        return False

    installer_iss = os.path.join(PROJECT_ROOT, 'installer.iss')
    if not os.path.exists(installer_iss):
        print_error("Arquivo installer.iss não encontrado!")
        return False

    try:
        print("Compilando instalador...")
        result = subprocess.run([
            iscc_path,
            installer_iss
        ], capture_output=True, text=True, timeout=300)

        if result.returncode == 0:
            installer_file = os.path.join(BUILD_DIR, 'Output', f"ATUDIC_Setup_{VERSION}.exe")
            if os.path.exists(installer_file):
                size = os.path.getsize(installer_file) / (1024 * 1024)
                print_success(f"Instalador criado: aturpo_win/Output/ATUDIC_Setup_{VERSION}.exe ({size:.2f} MB)")
                return True
            else:
                print_error("Instalador não foi criado")
                return False
        else:
            print_error("Erro ao compilar instalador")
            if result.stderr:
                print(result.stderr)
            return False

    except Exception as e:
        print_error(f"Erro ao criar instalador: {e}")
        return False

def main():
    """Função principal"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}")
    print("="*60)
    print(f"  {APP_NAME} - Sistema de Build v2.0")
    print("="*60)
    print(f"{Colors.ENDC}\n")

    start_time = datetime.now()

    # Verificar requisitos
    if not check_requirements():
        print_error("\n❌ Requisitos não atendidos! Instale as ferramentas necessárias.")
        return 1

    # Limpar builds anteriores
    clean_build_dirs()

    # Minificar frontend (JS/CSS)
    minify_frontend()

    # Ofuscar Python
    if not obfuscate_python():
        print_error("\n❌ Falha na ofuscação Python!")
        return 1

    # Ofuscar JavaScript
    if not obfuscate_javascript():
        print_warning("\n⚠ Continuando sem ofuscação JavaScript...")

    # Criar executável
    if not create_executable():
        print_error("\n❌ Falha ao criar executável!")
        return 1

    # Preparar arquivos do instalador
    if not prepare_installer_files():
        print_error("\n❌ Falha ao preparar arquivos!")
        return 1

    # Criar instalador
    installer_created = create_installer()

    # Resumo final
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    print(f"\n{Colors.HEADER}{Colors.BOLD}")
    print("="*60)
    print("  RESUMO DO BUILD")
    print("="*60)
    print(f"{Colors.ENDC}")

    print(f"\n⏱ Tempo total: {duration:.1f} segundos")
    print(f"\n📁 Arquivos gerados:")
    print(f"   • aturpo_win/dist/ATUDIC.exe")

    if installer_created:
        print(f"   • aturpo_win/Output/ATUDIC_Setup_{VERSION}.exe")
        print(f"\n{Colors.OKGREEN}{Colors.BOLD}✓ BUILD CONCLUÍDO COM SUCESSO!{Colors.ENDC}")
        print(f"\n🚀 Instalador pronto em: aturpo_win/Output/ATUDIC_Setup_{VERSION}.exe")
    else:
        print(f"\n{Colors.WARNING}⚠ Executável criado, mas instalador não foi gerado.{Colors.ENDC}")
        print(f"   Execute manualmente: ISCC.exe installer.iss")

    print()
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(f"\n\n{Colors.WARNING}⚠ Build cancelado pelo usuário{Colors.ENDC}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n{Colors.FAIL}❌ Erro inesperado: {e}{Colors.ENDC}\n")
        sys.exit(1)
