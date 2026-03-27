"""
Servico de politicas de branch-ambiente.

Gerencia vinculacao de branches a ambientes com regras de protecao
(permitir/bloquear push, pull, commit, criacao de branch).
"""

import logging

logger = logging.getLogger(__name__)


def create_policy(cursor, environment_id, repo_name, branch_name, rules):
    """Cria uma politica de branch para um ambiente."""
    cursor.execute(
        """
        INSERT INTO branch_policies
            (environment_id, repo_name, branch_name,
             allow_push, allow_pull, allow_commit, allow_create_branch,
             require_approval, is_default, created_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """,
        (
            environment_id,
            repo_name,
            branch_name,
            rules.get("allow_push", True),
            rules.get("allow_pull", True),
            rules.get("allow_commit", True),
            rules.get("allow_create_branch", False),
            rules.get("require_approval", False),
            rules.get("is_default", False),
            rules.get("created_by"),
        ),
    )
    row = cursor.fetchone()
    return row["id"] if row else None


def update_policy(cursor, policy_id, rules):
    """Atualiza regras de uma politica existente."""
    fields = []
    values = []
    allowed = ["allow_push", "allow_pull", "allow_commit", "allow_create_branch", "require_approval", "is_default"]
    for key in allowed:
        if key in rules:
            fields.append(f"{key} = %s")
            values.append(rules[key])

    if not fields:
        return False

    fields.append("updated_at = NOW()")
    values.append(policy_id)

    cursor.execute(f"UPDATE branch_policies SET {', '.join(fields)} WHERE id = %s", values)
    return cursor.rowcount > 0


def delete_policy(cursor, policy_id):
    """Remove uma politica."""
    cursor.execute("DELETE FROM branch_policies WHERE id = %s", (policy_id,))
    return cursor.rowcount > 0


def list_policies(cursor, environment_id=None):
    """Lista politicas, opcionalmente filtrando por ambiente."""
    if environment_id:
        cursor.execute(
            """
            SELECT bp.*, e.name as environment_name, u.name as creator_name
            FROM branch_policies bp
            LEFT JOIN environments e ON e.id = bp.environment_id
            LEFT JOIN users u ON u.id = bp.created_by
            WHERE bp.environment_id = %s
            ORDER BY bp.repo_name, bp.branch_name
        """,
            (environment_id,),
        )
    else:
        cursor.execute("""
            SELECT bp.*, e.name as environment_name, u.name as creator_name
            FROM branch_policies bp
            LEFT JOIN environments e ON e.id = bp.environment_id
            LEFT JOIN users u ON u.id = bp.created_by
            ORDER BY bp.environment_id, bp.repo_name, bp.branch_name
        """)
    return [dict(row) for row in cursor.fetchall()]


def get_policy(cursor, environment_id, repo_name, branch_name):
    """Busca politica especifica para um ambiente/repo/branch."""
    cursor.execute(
        """
        SELECT * FROM branch_policies
        WHERE environment_id = %s AND repo_name = %s AND branch_name = %s
    """,
        (environment_id, repo_name, branch_name),
    )
    row = cursor.fetchone()
    return dict(row) if row else None


def get_policy_by_id(cursor, policy_id):
    """Busca politica por ID."""
    cursor.execute(
        """
        SELECT bp.*, e.name as environment_name
        FROM branch_policies bp
        LEFT JOIN environments e ON e.id = bp.environment_id
        WHERE bp.id = %s
    """,
        (policy_id,),
    )
    row = cursor.fetchone()
    return dict(row) if row else None


def validate_operation(cursor, environment_id, repo_name, branch_name, operation):
    """
    Valida se uma operacao Git eh permitida pela politica do ambiente.

    Args:
        cursor: cursor do banco
        environment_id: ID do ambiente
        repo_name: nome do repositorio
        branch_name: nome da branch
        operation: 'push', 'pull', 'commit' ou 'create_branch'

    Returns:
        dict com 'allowed' (bool) e 'reason' (str se bloqueado)
    """
    if not environment_id:
        return {"allowed": True, "reason": None}

    policy = get_policy(cursor, environment_id, repo_name, branch_name)

    if not policy:
        # Sem politica definida = operacao permitida
        return {"allowed": True, "reason": None}

    field_map = {
        "push": "allow_push",
        "pull": "allow_pull",
        "commit": "allow_commit",
        "create_branch": "allow_create_branch",
    }

    field = field_map.get(operation)
    if not field:
        return {"allowed": True, "reason": None}

    allowed = policy.get(field, True)
    if not allowed:
        op_labels = {"push": "Push", "pull": "Pull", "commit": "Commit", "create_branch": "Criacao de branch"}
        op_label = op_labels.get(operation, operation)
        return {
            "allowed": False,
            "reason": f"{op_label} bloqueado pela politica do ambiente para {repo_name}/{branch_name}",
        }

    return {"allowed": True, "reason": None}


def get_bound_environments(cursor, repo_name, branch_name):
    """Retorna ambientes vinculados a uma branch."""
    cursor.execute(
        """
        SELECT bp.*, e.name as environment_name
        FROM branch_policies bp
        JOIN environments e ON e.id = bp.environment_id
        WHERE bp.repo_name = %s AND bp.branch_name = %s
    """,
        (repo_name, branch_name),
    )
    return [dict(row) for row in cursor.fetchall()]
