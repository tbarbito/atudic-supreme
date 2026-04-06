"""
Testes do RBAC hibrido: perfil base + overrides por usuario.

Valida a ordem de resolucao de permissoes:
1. Root admin (username='admin')    -> ALLOW sempre
2. Usuario inativo                  -> DENY sempre
3. DENY explicito                   -> vence tudo (exceto root)
4. GRANT explicito                  -> adiciona fora do perfil
5. Perfil base                      -> concede default
6. Default                          -> DENY

Testes nao tocam o banco: usam o modulo puro app.utils.permissions.
"""
import pytest

from app.utils.permissions import (
    DEFAULT_ROLE_PERMISSIONS,
    VALID_PERMISSION_KEYS,
    EFFECT_GRANT,
    EFFECT_DENY,
    FALLBACK_PROFILE,
    get_base_permissions,
    resolve_effective_keys,
    keys_to_nested_dict,
    is_valid_permission_key,
    catalog_for_api,
)


class TestCatalog:
    def test_catalog_tem_keys_unicas(self):
        keys = [entry[0] for entry in catalog_for_api() for _ in [None]]
        assert len(keys) == len(set(keys)), "Catalogo tem permission_keys duplicadas"

    def test_valid_keys_match_catalog(self):
        catalog_keys = {entry["key"] for entry in catalog_for_api()}
        assert catalog_keys == set(VALID_PERMISSION_KEYS)

    def test_is_valid_permission_key(self):
        assert is_valid_permission_key("pipelines:execute") is True
        assert is_valid_permission_key("foo:bar") is False
        assert is_valid_permission_key("") is False

    def test_formato_resource_action(self):
        for key in VALID_PERMISSION_KEYS:
            assert ":" in key, f"Key {key!r} nao segue formato resource:action"


class TestBasePermissions:
    def test_admin_tem_acesso_amplo(self):
        keys = get_base_permissions("admin")
        assert "users:create" in keys
        assert "pipelines:execute" in keys
        assert "github_settings:edit" in keys

    def test_operator_nao_gerencia_users(self):
        keys = get_base_permissions("operator")
        assert "users:view" not in keys
        assert "users:create" not in keys
        assert "users:delete" not in keys

    def test_operator_executa_pipelines(self):
        keys = get_base_permissions("operator")
        assert "pipelines:execute" in keys
        assert "pipelines:release" in keys

    def test_viewer_acesso_restrito(self):
        keys = get_base_permissions("viewer")
        # viewer nao cria/edita/deleta — so view, chat, search
        allowed_actions = {"view", "chat", "search"}
        for key in keys:
            action = key.split(":")[1]
            assert action in allowed_actions, f"Viewer tem permissao inesperada: {key}"

    def test_profile_desconhecido_cai_em_viewer(self):
        keys = get_base_permissions("xpto_role_inexistente")
        assert keys == DEFAULT_ROLE_PERMISSIONS[FALLBACK_PROFILE]


class TestResolveEffectiveKeys:
    def test_sem_overrides_retorna_perfil(self):
        keys = resolve_effective_keys("viewer", [])
        assert keys == set(DEFAULT_ROLE_PERMISSIONS["viewer"])

    def test_grant_adiciona_permissao_fora_do_perfil(self):
        overrides = [{"permission_key": "pipelines:execute", "effect": EFFECT_GRANT}]
        keys = resolve_effective_keys("viewer", overrides)
        assert "pipelines:execute" in keys
        assert "pipelines:view" in keys  # preserva perfil

    def test_deny_vence_permissao_do_perfil(self):
        overrides = [{"permission_key": "pipelines:execute", "effect": EFFECT_DENY}]
        keys = resolve_effective_keys("operator", overrides)
        assert "pipelines:execute" not in keys
        # mas nao remove outras do perfil
        assert "pipelines:view" in keys

    def test_deny_vence_grant_no_mesmo_user(self):
        # DENY sempre vence (mesmo se houvesse GRANT — caso teorico, unique constraint
        # no banco impede ambos, mas o resolver deve estar seguro)
        overrides = [
            {"permission_key": "users:delete", "effect": EFFECT_GRANT},
            {"permission_key": "users:delete", "effect": EFFECT_DENY},
        ]
        keys = resolve_effective_keys("admin", overrides)
        assert "users:delete" not in keys

    def test_grant_de_key_invalida_e_ignorado(self):
        overrides = [
            {"permission_key": "foo:bar", "effect": EFFECT_GRANT},
            {"permission_key": "nao_existe:action", "effect": EFFECT_GRANT},
        ]
        keys = resolve_effective_keys("viewer", overrides)
        assert "foo:bar" not in keys
        assert "nao_existe:action" not in keys

    def test_override_sem_effect_valido_e_ignorado(self):
        overrides = [{"permission_key": "pipelines:execute", "effect": "MAYBE"}]
        keys = resolve_effective_keys("viewer", overrides)
        assert "pipelines:execute" not in keys

    def test_multiplos_grants_acumulam(self):
        overrides = [
            {"permission_key": "users:view", "effect": EFFECT_GRANT},
            {"permission_key": "users:edit", "effect": EFFECT_GRANT},
        ]
        keys = resolve_effective_keys("operator", overrides)
        assert "users:view" in keys
        assert "users:edit" in keys
        assert "users:delete" not in keys  # nao concedida

    def test_cenario_real_operator_nao_deleta_producao(self):
        """Operator pode tudo exceto deletar pipelines (restricao pontual)."""
        overrides = [{"permission_key": "pipelines:delete", "effect": EFFECT_DENY}]
        keys = resolve_effective_keys("operator", overrides)
        assert "pipelines:execute" in keys
        assert "pipelines:create" in keys
        assert "pipelines:delete" not in keys

    def test_cenario_real_viewer_com_execucao_temporaria(self):
        """Viewer recebe execucao pontual via GRANT."""
        overrides = [{"permission_key": "pipelines:execute", "effect": EFFECT_GRANT}]
        keys = resolve_effective_keys("viewer", overrides)
        assert "pipelines:view" in keys
        assert "pipelines:execute" in keys
        assert "pipelines:delete" not in keys


class TestNestedDict:
    def test_formato_aninhado_completo(self):
        keys = {"pipelines:view", "pipelines:execute"}
        nested = keys_to_nested_dict(keys)
        assert nested["pipelines"]["view"] is True
        assert nested["pipelines"]["execute"] is True
        assert nested["pipelines"]["delete"] is False  # presente mas False

    def test_can_edit_protected_flag(self):
        nested = keys_to_nested_dict(set(), can_edit_protected=True)
        assert nested["can_edit_protected"] is True

    def test_is_root_flag(self):
        nested = keys_to_nested_dict(set(), is_root=True)
        assert nested["is_root"] is True

    def test_root_nao_aplicado_quando_false(self):
        nested = keys_to_nested_dict({"pipelines:view"}, is_root=False)
        assert "is_root" not in nested

    def test_system_keys_nao_aparecem_no_nested(self):
        # system:edit_protected e flag, nao recurso
        nested = keys_to_nested_dict({"system:edit_protected"})
        assert "system" not in nested
        assert nested["can_edit_protected"] is True


class TestMatrixLegacyCompat:
    """Valida que a matriz default mantem a mesma semantica do codigo legado."""

    def test_admin_acesso_completo(self):
        keys = get_base_permissions("admin")
        assert "users:view" in keys
        assert "users:create" in keys
        assert "environments:view" in keys
        assert "environments:create" not in keys  # admin nao cria ambientes (legado)
        assert "pipelines:release" in keys
        # Novos modulos
        assert "agent:manage" in keys
        assert "observability:manage" in keys
        assert "dictionary:equalize" in keys
        assert "devworkspace:delete" in keys
        assert "settings:edit" in keys
        assert "license:manage" in keys

    def test_operator_acesso_operacional(self):
        keys = get_base_permissions("operator")
        assert "repositories:delete" not in keys  # operator nao deleta repo
        assert "repositories:sync" not in keys
        assert "commands:view" in keys
        assert "commands:create" not in keys  # operator so ve comandos
        assert "pipelines:delete" in keys
        # Novos modulos: operator opera mas nao gerencia admin
        assert "agent:chat" in keys
        assert "agent:manage" not in keys
        assert "observability:view" in keys
        assert "observability:manage" not in keys
        assert "devworkspace:analyze" in keys
        assert "dictionary:compare" in keys
        assert "dictionary:equalize" not in keys  # operator nao equaliza
        assert "settings:view" not in keys  # operator nao ve settings

    def test_viewer_tem_modulos_de_leitura(self):
        keys = get_base_permissions("viewer")
        # Viewer ve todos os modulos mas nao gerencia
        assert "pipelines:view" in keys
        assert "repositories:view" in keys
        assert "observability:view" in keys
        assert "agent:view" in keys
        assert "agent:chat" in keys
        assert "devworkspace:view" in keys
        assert "dictionary:view" in keys
        assert "tdn:view" in keys
        assert "tdn:search" in keys
        # Viewer nunca cria/edita/deleta
        assert "pipelines:create" not in keys
        assert "users:view" not in keys
        assert "settings:view" not in keys
