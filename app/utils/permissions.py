"""
Catalogo de permissoes do BiizHubOps.

Define o conjunto canonico de permission_keys (formato "resource:action"),
a matriz default por perfil e funcoes utilitarias para conversao entre
o formato granular (resource:action) e o formato aninhado legado
({resource: {action: bool}}) usado pelo frontend.

Usado por:
- app.utils.security.get_user_permissions() — resolucao efetiva
- app.utils.security.has_permission() — verificacao granular
- app.routes.users (CRUD de overrides) — validacao de keys
"""

# ============================================================================
# CATALOGO DE PERMISSION_KEYS
# ============================================================================
# Formato: "resource:action"
# Cada entrada: (key, resource, action, description)

PERMISSION_CATALOG = [
    # users
    ("users:view",              "users",            "view",     "Visualizar usuarios"),
    ("users:create",            "users",            "create",   "Criar usuarios"),
    ("users:edit",              "users",            "edit",     "Editar usuarios"),
    ("users:delete",            "users",            "delete",   "Excluir usuarios"),

    # environments
    ("environments:view",       "environments",     "view",     "Visualizar ambientes"),
    ("environments:create",     "environments",     "create",   "Criar ambientes"),
    ("environments:edit",       "environments",     "edit",     "Editar ambientes"),
    ("environments:delete",     "environments",     "delete",   "Excluir ambientes"),

    # repositories
    ("repositories:view",       "repositories",     "view",     "Visualizar repositorios"),
    ("repositories:create",     "repositories",     "create",   "Criar repositorios"),
    ("repositories:edit",       "repositories",     "edit",     "Editar repositorios"),
    ("repositories:delete",     "repositories",     "delete",   "Excluir repositorios"),
    ("repositories:sync",       "repositories",     "sync",     "Sincronizar repositorios"),

    # commands
    ("commands:view",           "commands",         "view",     "Visualizar comandos"),
    ("commands:create",         "commands",         "create",   "Criar comandos"),
    ("commands:edit",           "commands",         "edit",     "Editar comandos"),
    ("commands:delete",         "commands",         "delete",   "Excluir comandos"),

    # pipelines
    ("pipelines:view",          "pipelines",        "view",     "Visualizar pipelines"),
    ("pipelines:create",        "pipelines",        "create",   "Criar pipelines"),
    ("pipelines:edit",          "pipelines",        "edit",     "Editar pipelines"),
    ("pipelines:delete",        "pipelines",        "delete",   "Excluir pipelines"),
    ("pipelines:execute",       "pipelines",        "execute",  "Executar pipelines"),
    ("pipelines:release",       "pipelines",        "release",  "Liberar release de pipeline"),

    # schedules
    ("schedules:view",          "schedules",        "view",     "Visualizar agendamentos"),
    ("schedules:create",        "schedules",        "create",   "Criar agendamentos"),
    ("schedules:edit",          "schedules",        "edit",     "Editar agendamentos"),
    ("schedules:delete",        "schedules",        "delete",   "Excluir agendamentos"),

    # service_actions
    ("service_actions:view",    "service_actions",  "view",     "Visualizar acoes de servico"),
    ("service_actions:create",  "service_actions",  "create",   "Criar acoes de servico"),
    ("service_actions:edit",    "service_actions",  "edit",     "Editar acoes de servico"),
    ("service_actions:delete",  "service_actions",  "delete",   "Excluir acoes de servico"),
    ("service_actions:execute", "service_actions",  "execute",  "Executar acoes de servico"),

    # variables
    ("variables:view",          "variables",        "view",     "Visualizar variaveis"),
    ("variables:create",        "variables",        "create",   "Criar variaveis"),
    ("variables:edit",          "variables",        "edit",     "Editar variaveis"),
    ("variables:delete",        "variables",        "delete",   "Excluir variaveis"),

    # services
    ("services:view",           "services",         "view",     "Visualizar servicos"),
    ("services:create",         "services",         "create",   "Criar servicos"),
    ("services:edit",           "services",         "edit",     "Editar servicos"),
    ("services:delete",         "services",         "delete",   "Excluir servicos"),

    # github_settings
    ("github_settings:view",    "github_settings",  "view",     "Visualizar configuracoes GitHub"),
    ("github_settings:edit",    "github_settings",  "edit",     "Editar configuracoes GitHub"),

    # can_edit_protected (flag especial preservada por compat)
    ("system:edit_protected",   "system",           "edit_protected", "Editar itens protegidos"),
]


# Set de todas as keys validas, para validacao rapida
VALID_PERMISSION_KEYS = frozenset(entry[0] for entry in PERMISSION_CATALOG)


# ============================================================================
# MATRIZ DEFAULT POR PERFIL
# ============================================================================
# Set de permission_keys concedidas por perfil.
# Extraido da matriz hardcoded legada em security.get_user_permissions().
# Mantem semantica identica aos 3 perfis atuais.

DEFAULT_ROLE_PERMISSIONS = {
    "admin": frozenset([
        "users:view", "users:create", "users:edit", "users:delete",
        "environments:view",
        "repositories:view", "repositories:create", "repositories:edit", "repositories:delete", "repositories:sync",
        "commands:view", "commands:create", "commands:edit", "commands:delete",
        "pipelines:view", "pipelines:create", "pipelines:edit", "pipelines:delete", "pipelines:execute", "pipelines:release",
        "schedules:view", "schedules:create", "schedules:edit", "schedules:delete",
        "service_actions:view", "service_actions:create", "service_actions:edit", "service_actions:delete", "service_actions:execute",
        "variables:view", "variables:create", "variables:edit", "variables:delete",
        "services:view", "services:create", "services:edit", "services:delete",
        "github_settings:view", "github_settings:edit",
    ]),
    "operator": frozenset([
        "repositories:view", "repositories:create", "repositories:edit",
        "commands:view",
        "pipelines:view", "pipelines:create", "pipelines:edit", "pipelines:delete", "pipelines:execute", "pipelines:release",
        "schedules:view", "schedules:create", "schedules:edit", "schedules:delete",
        "service_actions:view", "service_actions:create", "service_actions:edit", "service_actions:delete", "service_actions:execute",
        "variables:view", "variables:create", "variables:edit", "variables:delete",
        "services:view", "services:create", "services:edit", "services:delete",
    ]),
    "viewer": frozenset([
        "repositories:view",
        "pipelines:view",
        "schedules:view",
    ]),
}

# Perfil padrao quando o valor armazenado nao e reconhecido
FALLBACK_PROFILE = "viewer"


# ============================================================================
# EFFECTS DE OVERRIDE
# ============================================================================

EFFECT_GRANT = "GRANT"
EFFECT_DENY = "DENY"
VALID_EFFECTS = frozenset([EFFECT_GRANT, EFFECT_DENY])


# ============================================================================
# UTILITARIOS
# ============================================================================

def get_base_permissions(profile):
    """
    Retorna o set de permission_keys concedidas pelo perfil base.

    Args:
        profile (str): 'admin', 'operator', 'viewer' ou outro

    Returns:
        frozenset[str]: keys concedidas pelo perfil (ou viewer como fallback)
    """
    return DEFAULT_ROLE_PERMISSIONS.get(profile, DEFAULT_ROLE_PERMISSIONS[FALLBACK_PROFILE])


def resolve_effective_keys(profile, overrides):
    """
    Calcula o set efetivo de permission_keys aplicando overrides sobre o perfil.

    Ordem de resolucao (sem considerar root, que deve ser tratado no chamador):
    1. DENY explicito vence tudo
    2. GRANT explicito adiciona permissao
    3. Perfil concede as permissoes default
    4. Default: permissao nao listada = negada

    Args:
        profile (str): perfil base do usuario
        overrides (list[dict]): lista de {permission_key, effect} ja filtrada
                                de expirados

    Returns:
        set[str]: permission_keys efetivas do usuario
    """
    base = set(get_base_permissions(profile))

    grants = {o["permission_key"] for o in overrides if o.get("effect") == EFFECT_GRANT}
    denies = {o["permission_key"] for o in overrides if o.get("effect") == EFFECT_DENY}

    effective = (base | grants) - denies
    # Mantem apenas keys do catalogo (defense in depth contra lixo no banco)
    effective &= VALID_PERMISSION_KEYS
    return effective


def keys_to_nested_dict(keys, is_root=False, can_edit_protected=False):
    """
    Converte um set de permission_keys para o formato aninhado legado:
    { 'pipelines': {'view': True, 'execute': True, ...}, ... }

    Necessario para compatibilidade com frontend (canPerformAction) e
    com a API publica de get_user_permissions().

    Args:
        keys (set[str]): permission_keys efetivas
        is_root (bool): adiciona flag 'is_root' no dict
        can_edit_protected (bool): flag especial de edicao de protegidos

    Returns:
        dict: estrutura aninhada {resource: {action: bool}}
    """
    nested = {}

    # Inicializa todos os recursos com todas as actions em False
    # (garante estrutura completa para o frontend)
    for _, resource, action, _ in PERMISSION_CATALOG:
        if resource == "system":
            continue  # system:edit_protected e tratado via flag
        nested.setdefault(resource, {})[action] = False

    # Aplica as keys concedidas
    for key in keys:
        if ":" not in key:
            continue
        resource, action = key.split(":", 1)
        if resource == "system":
            continue
        nested.setdefault(resource, {})[action] = True

    nested["can_edit_protected"] = bool(can_edit_protected) or ("system:edit_protected" in keys)
    if is_root:
        nested["is_root"] = True

    return nested


def is_valid_permission_key(key):
    """Valida se uma string e uma permission_key reconhecida."""
    return key in VALID_PERMISSION_KEYS


def catalog_for_api():
    """
    Retorna o catalogo em formato serializavel para o endpoint publico.

    Returns:
        list[dict]: [{key, resource, action, description}, ...]
    """
    return [
        {
            "key": key,
            "resource": resource,
            "action": action,
            "description": description,
        }
        for key, resource, action, description in PERMISSION_CATALOG
    ]
