"""
Migration 022: User Permission Overrides - RBAC hibrido.

Cria tabela de overrides (GRANT/DENY) por usuario sobre as permissoes
concedidas pelo perfil base. Permite concessao ou revogacao granular
sem alterar o perfil do usuario.

Resolucao de permissao (implementada em app.utils.security):
1. Root admin (username='admin')    -> ALLOW
2. Usuario inativo                  -> DENY
3. DENY explicito no override       -> DENY
4. GRANT explicito no override      -> ALLOW
5. Permissao presente no perfil     -> ALLOW
6. Default                          -> DENY

Observacoes:
- UNIQUE (user_id, permission_key): um usuario tem no maximo 1 override por key
- expires_at opcional: override com validade (acesso temporario / JIT)
- reason: obrigatorio no endpoint de admin para auditoria
"""


def upgrade(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_permission_overrides (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            permission_key VARCHAR(100) NOT NULL,
            effect VARCHAR(10) NOT NULL CHECK (effect IN ('GRANT', 'DENY')),
            granted_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            reason TEXT,
            expires_at TIMESTAMP NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE (user_id, permission_key)
        )
    """)

    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_upo_user ON user_permission_overrides (user_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_upo_expires "
        "ON user_permission_overrides (expires_at) "
        "WHERE expires_at IS NOT NULL"
    )


def downgrade(cursor):
    cursor.execute("DROP TABLE IF EXISTS user_permission_overrides")
