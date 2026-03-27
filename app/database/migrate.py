# -*- coding: utf-8 -*-
"""
Sistema de migrations para o banco de dados AtuDIC Supreme.

Executa migrations incrementais a partir de arquivos Python em app/database/migrations/.
Cada migration e um modulo com funcoes upgrade() e downgrade().
O controle de versao e feito pela tabela schema_migrations.

Origem: AtuDIC (Barbito) adaptado para AtuDIC Supreme.
"""

import os
import sys
import importlib
import traceback
from datetime import datetime


MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "migrations")

# Lista fixa de migrations para ambientes onde os.listdir() nao funciona (PyInstaller)
_KNOWN_MIGRATIONS = [
    "001_baseline.py",
]


def _ensure_migrations_table(cursor):
    """Cria a tabela de controle de migrations se nao existir."""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id SERIAL PRIMARY KEY,
            version VARCHAR(50) UNIQUE NOT NULL,
            name VARCHAR(255) NOT NULL,
            applied_at TIMESTAMP NOT NULL
        )
    """)


def get_applied_versions(cursor):
    """Retorna set com as versoes ja aplicadas."""
    _ensure_migrations_table(cursor)
    cursor.execute("SELECT version FROM schema_migrations ORDER BY version")
    return {row["version"] for row in cursor.fetchall()}


def get_pending_migrations(cursor):
    """Retorna lista de migrations pendentes, ordenadas por versao."""
    applied = get_applied_versions(cursor)
    pending = []

    is_frozen = getattr(sys, 'frozen', False)
    if is_frozen:
        migration_files = sorted(_KNOWN_MIGRATIONS)
    else:
        migration_files = sorted(
            f for f in os.listdir(MIGRATIONS_DIR)
            if f.endswith(".py") and not f.startswith("_")
        )

    for filename in migration_files:
        version = filename.split("_", 1)[0]
        name = filename[:-3]

        if version not in applied:
            pending.append({
                "version": version,
                "name": name,
                "filename": filename,
            })

    return pending


def run_migrations(conn, cursor):
    """Executa todas as migrations pendentes. Retorna quantidade aplicada."""
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
                print(f"  [WARN] Migration {migration['filename']} sem funcao upgrade(), pulando")
                continue

            print(f"  [UP] Aplicando migration {migration['version']}: {migration['name']}...")

            cursor.execute(f"SAVEPOINT migration_{migration['version']}")
            try:
                mod.upgrade(cursor)
                cursor.execute(f"RELEASE SAVEPOINT migration_{migration['version']}")
            except Exception as upgrade_err:
                cursor.execute(f"ROLLBACK TO SAVEPOINT migration_{migration['version']}")
                err_str = str(upgrade_err).lower()
                if 'does not exist' in err_str or 'undefined' in err_str:
                    try:
                        conn.commit()
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

            cursor.execute(
                "INSERT INTO schema_migrations (version, name, applied_at) VALUES (%s, %s, %s)",
                (migration["version"], migration["name"], datetime.now()),
            )
            conn.commit()
            applied_count += 1
            print(f"  [OK] Migration {migration['version']} aplicada com sucesso")

        except Exception as e:
            print(f"  [ERRO] Erro na migration {migration['version']}: {e}")
            traceback.print_exc()
            conn.rollback()
            raise RuntimeError(f"Migration {migration['version']} falhou: {e}") from e

    return applied_count
