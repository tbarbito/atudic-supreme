"""
Configuração da aplicação: carregamento de variáveis de ambiente e paths.
"""
import sys
import io
import os
import locale


def configure_encoding():
    """Configura encoding UTF-8 para PyInstaller e ambientes Windows."""
    os.environ['PYTHONUNBUFFERED'] = '1'

    if hasattr(sys, 'frozen'):
        print("[INFO] Detectado ambiente PyInstaller, aplicando fixes de encoding...")
        try:
            # write_through=True força escrita imediata (essencial para NSSM capturar logs)
            # line_buffering=True flush a cada newline
            sys.stdout = io.TextIOWrapper(
                sys.stdout.buffer, encoding='utf-8', errors='replace',
                write_through=True, line_buffering=True
            )
            sys.stderr = io.TextIOWrapper(
                sys.stderr.buffer, encoding='utf-8', errors='replace',
                write_through=True, line_buffering=True
            )
            print("[OK] stdout/stderr configurados para UTF-8 (write_through)")
        except Exception as e:
            print(f"[AVISO] Erro ao configurar stdout/stderr: {e}")

        os.environ['PGCLIENTENCODING'] = 'UTF8'
        os.environ['PYTHONIOENCODING'] = 'utf-8'
        # Forçar mensagens do libpq em ASCII para evitar UnicodeDecodeError
        # quando PostgreSQL no Windows retorna mensagens em cp1252 (locale pt-BR)
        os.environ.setdefault('LC_MESSAGES', 'C')
        print("[OK] Variaveis de ambiente configuradas: PGCLIENTENCODING=UTF8, LC_MESSAGES=C")

        try:
            locale.setlocale(locale.LC_ALL, 'C.UTF-8')
            print("[OK] Locale configurado: C.UTF-8")
        except Exception:
            try:
                locale.setlocale(locale.LC_ALL, '')
                print("[OK] Locale configurado: default")
            except Exception as e:
                print(f"[AVISO] Nao foi possivel configurar locale: {e}")


def load_env_file(env_file='.env'):
    """Carrega variaveis do arquivo de configuracao manualmente."""
    possible_paths = []

    if hasattr(sys, 'frozen'):
        exe_dir = os.path.dirname(sys.executable)
        possible_paths = [
            os.path.join(exe_dir, 'config.env'),
            os.path.join(exe_dir, '.env'),
            'config.env',
            '.env'
        ]
    else:
        possible_paths = [env_file, 'config.env', '.env']

    for path in possible_paths:
        if os.path.exists(path):
            env_file = path
            break
    else:
        print(f"[AVISO] Arquivo de configuracao nao encontrado")
        print(f"[DEBUG] Caminhos tentados: {possible_paths}")
        return

    if os.path.exists(env_file):
        try:
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ[key.strip()] = value.strip()
            print(f"[OK] Variaveis carregadas de: {env_file}")
        except Exception as e:
            print(f"[ERRO] Erro ao carregar {env_file}: {e}")
    else:
        print(f"[AVISO] Arquivo {env_file} nao encontrado")


def get_base_directory():
    """
    Retorna o diretório base correto dependendo do modo de execução.
    - Executável PyInstaller: diretório do .exe
    - Script Python: diretório do script
    """
    if hasattr(sys, 'frozen'):
        return os.path.dirname(sys.executable)
    else:
        # Sobe um nível pois este arquivo está em app/
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


CLONE_DIR = "cloned_repos"
