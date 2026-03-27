"""
Sistema de migrations para o banco de dados AtuDIC.

Executa migrations incrementais a partir de arquivos Python em app/database/migrations/.
Cada migration é um módulo com funções upgrade() e downgrade().
O controle de versão é feito pela tabela schema_migrations.
"""
import os
import sys
import importlib
import traceback
from datetime import datetime


MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "migrations")

# Lista fixa de migrations para ambientes onde os.listdir() não funciona (PyInstaller)
_KNOWN_MIGRATIONS = [
    "001_baseline.py",
    "002_variable_audit.py",
    "003_webhooks.py",
    "004_observability.py",
    "005_user_environments.py",
    "006_knowledge_base.py",
    "007_database_integration.py",
    "008_business_processes.py",
    "009_documentation.py",
    "010_devworkspace.py",
    "011_db_connection_ref_env.py",
    "012_fix_dbconn_unique.py",
    "013_dictionary_history.py",
    "014_agent_settings.py",
    "015_llm_providers.py",
    "016_react_agent.py",
    "017_rest_url.py",
    "018_ini_auditor.py",
    "019_sandbox_unique.py",
    "020_tdn_knowledge.py",
    "021_token_economy.py",
]


def _ensure_migrations_table(cursor):
    """Cria a tabela de controle de migrations se não existir."""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id SERIAL PRIMARY KEY,
            version VARCHAR(50) UNIQUE NOT NULL,
            name VARCHAR(255) NOT NULL,
            applied_at TIMESTAMP NOT NULL
        )
    """)


def get_applied_versions(cursor):
    """Retorna set com as versões já aplicadas."""
    _ensure_migrations_table(cursor)
    cursor.execute("SELECT version FROM schema_migrations ORDER BY version")
    return {row["version"] for row in cursor.fetchall()}


def get_pending_migrations(cursor):
    """Retorna lista de migrations pendentes (não aplicadas), ordenadas por versão."""
    applied = get_applied_versions(cursor)
    pending = []

    # Em PyInstaller, a pasta migrations/ não existe no filesystem — usar lista fixa
    is_frozen = getattr(sys, 'frozen', False)
    if is_frozen:
        migration_files = sorted(_KNOWN_MIGRATIONS)
    else:
        migration_files = sorted(
            f for f in os.listdir(MIGRATIONS_DIR)
            if f.endswith(".py") and not f.startswith("_")
        )

    for filename in migration_files:

        # Formato esperado: 001_nome_da_migration.py
        version = filename.split("_", 1)[0]
        name = filename[:-3]  # remove .py

        if version not in applied:
            pending.append({
                "version": version,
                "name": name,
                "filename": filename,
            })

    return pending


def run_migrations(conn, cursor):
    """Executa todas as migrations pendentes. Retorna quantidade aplicada."""
    # Garantir estado limpo: commit qualquer transação aberta antes de iniciar
    # Isso assegura que as migrations enxerguem todos os dados commitados pelo init_db()
    try:
        conn.commit()
    except Exception:
        pass

    pending = get_pending_migrations(cursor)

    if not pending:
        return 0

    applied_count = 0
    for migration in pending:
        module_name = f"app.database.migrations.{migration['name']}"
        try:
            mod = importlib.import_module(module_name)

            if not hasattr(mod, "upgrade"):
                print(f"  ⚠️ Migration {migration['filename']} sem função upgrade(), pulando")
                continue

            print(f"  ⬆️  Aplicando migration {migration['version']}: {migration['name']}...")

            # Executa upgrade dentro de um savepoint para segurança
            cursor.execute(f"SAVEPOINT migration_{migration['version']}")
            try:
                mod.upgrade(cursor)
                cursor.execute(f"RELEASE SAVEPOINT migration_{migration['version']}")
            except Exception as upgrade_err:
                cursor.execute(f"ROLLBACK TO SAVEPOINT migration_{migration['version']}")
                # Se o erro for de FK/tabela não encontrada, tenta novamente com
                # uma transação fresca que enxerga todos os dados commitados
                err_str = str(upgrade_err).lower()
                if 'does not exist' in err_str or 'undefined' in err_str or 'relação' in err_str:
                    try:
                        conn.commit()  # inicia transação limpa com visão atualizada do banco
                        cursor.execute(f"SAVEPOINT migration_{migration['version']}")
                        mod.upgrade(cursor)
                        cursor.execute(f"RELEASE SAVEPOINT migration_{migration['version']}")
                    except Exception:
                        try:
                            cursor.execute(f"ROLLBACK TO SAVEPOINT migration_{migration['version']}")
                        except Exception:
                            pass
                        raise
                else:
                    raise

            # Registra que foi aplicada
            cursor.execute(
                "INSERT INTO schema_migrations (version, name, applied_at) VALUES (%s, %s, %s)",
                (migration["version"], migration["name"], datetime.now()),
            )
            conn.commit()
            applied_count += 1
            print(f"  ✅ Migration {migration['version']} aplicada com sucesso")

        except Exception as e:
            print(f"  ❌ Erro na migration {migration['version']}: {e}")
            traceback.print_exc()
            conn.rollback()
            # Para na primeira falha — não aplica migrations subsequentes
            raise RuntimeError(f"Migration {migration['version']} falhou: {e}") from e

    return applied_count
