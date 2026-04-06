# -*- coding: utf-8 -*-
"""
Benchmark e testes de integridade do merge ExtraiRPO no AtuDIC Supreme.

Cobre:
  1. Import de todos os modulos novos (sem erro)
  2. Integridade da knowledge base (YAML)
  3. Schema do workspace DB (tabelas, colunas, indices)
  4. Registro de rotas no workspace blueprint
  5. Instanciacao de services
  6. Integridade dos templates de processos

Autor: Barbito
"""

import importlib
import json
import time
from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"
TEMPLATES_DIR = PROJECT_ROOT / "templates" / "processos"

# Modulos novos do merge ExtraiRPO
NEW_MODULES = [
    "app.services.workspace.artifact_registry",
    "app.services.workspace.context_window",
    "app.services.workspace.cost_tracker",
    "app.services.workspace.cross_ref_index",
    "app.services.workspace.memory_extractor",
    "app.services.workspace.processo_decomposer",
    "app.services.workspace.processo_orquestrador",
    "app.services.workspace.prompt_composer",
    "app.services.workspace.session_memory",
    "app.services.workspace.tool_validator",
]

# Tabelas que devem existir apos initialize() do workspace DB
EXPECTED_TABLES = [
    "tabelas",
    "campos",
    "grupos_campo",
    "indices",
    "gatilhos",
    "perguntas",
    "tabelas_genericas",
    "parametros",
    "relacionamentos",
    "pastas",
    "consultas",
    "propositos",
    "conceitos_aprendidos",
    "fonte_analise_tecnica",
    "fontes",
    "chat_history",
    "fonte_chunks",
    "operacoes_escrita",
    "ingest_progress",
    "vinculos",
    "menus",
    "padrao_tabelas",
    "padrao_campos",
    "padrao_indices",
    "padrao_gatilhos",
    "padrao_parametros",
    "diff",
    "funcao_docs",
    "anotacoes",
    "jobs",
]

# Indices esperados (subset critico)
EXPECTED_INDEXES = [
    "idx_vinculos_tipo",
    "idx_vinculos_origem",
    "idx_vinculos_destino",
    "idx_fontes_modulo",
    "idx_campos_tabela",
    "idx_campos_custom",
    "idx_diff_tipo_acao",
    "idx_diff_tabela",
    "idx_anotacoes_tipo_chave",
    "idx_oe_tabela",
    "idx_oe_arquivo",
    "idx_menus_rotina",
    "idx_jobs_rotina",
]

# Templates de processos esperados (8 modulos + mapa JSON)
EXPECTED_PROCESS_TEMPLATES = [
    "compras.md",
    "contabilidade.md",
    "estoque.md",
    "faturamento.md",
    "financeiro.md",
    "fiscal.md",
    "pcp.md",
    "rh.md",
]


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture(scope="module")
def workspace_db(tmp_path_factory):
    """Cria workspace DB temporario inicializado."""
    from app.services.workspace.workspace_db import Database

    db_path = tmp_path_factory.mktemp("ws") / "bench.db"
    db = Database(db_path)
    db.initialize()
    return db


@pytest.fixture(scope="module")
def all_yaml_files():
    """Coleta todos os YAML da knowledge base."""
    files = sorted(KNOWLEDGE_DIR.rglob("*.yaml"))
    return files


@pytest.fixture(scope="module")
def flask_test_app():
    """App Flask para testes de rota."""
    from run import app

    app.config["TESTING"] = True
    return app


@pytest.fixture(scope="module")
def test_client(flask_test_app):
    """Client HTTP de teste."""
    return flask_test_app.test_client()


# ===========================================================================
# 1. IMPORT TESTS — Modulos novos carregam sem erro
# ===========================================================================

class TestModuleImports:
    """Todos os modulos do merge ExtraiRPO devem importar sem erro."""

    @pytest.mark.parametrize("module_name", NEW_MODULES)
    def test_import_module(self, module_name):
        """Importa modulo e verifica que nao levanta excecao."""
        t0 = time.perf_counter()
        mod = importlib.import_module(module_name)
        elapsed = time.perf_counter() - t0

        assert mod is not None, f"Modulo {module_name} retornou None"
        # benchmark: import nao deve demorar mais que 5s
        assert elapsed < 5.0, f"Import de {module_name} demorou {elapsed:.2f}s"

    def test_all_modules_have_docstring_or_classes(self):
        """Cada modulo deve ter ao menos um atributo publico."""
        for module_name in NEW_MODULES:
            mod = importlib.import_module(module_name)
            public_attrs = [a for a in dir(mod) if not a.startswith("_")]
            assert len(public_attrs) > 0, (
                f"Modulo {module_name} nao tem atributos publicos"
            )


# ===========================================================================
# 2. KNOWLEDGE BASE INTEGRITY — YAMLs parseiam e tem campos obrigatorios
# ===========================================================================

class TestKnowledgeBaseIntegrity:
    """Valida integridade de todos os YAMLs da knowledge base."""

    def test_yaml_file_count(self, all_yaml_files):
        """Knowledge base deve ter ao menos 80 YAML files."""
        count = len(all_yaml_files)
        assert count >= 80, (
            f"Esperado >= 80 YAMLs na knowledge base, encontrados {count}"
        )

    @pytest.mark.parametrize(
        "yaml_file",
        sorted(KNOWLEDGE_DIR.rglob("*.yaml")),
        ids=lambda p: str(p.relative_to(KNOWLEDGE_DIR)),
    )
    def test_yaml_parses_correctly(self, yaml_file):
        """Cada YAML deve parsear sem erro."""
        t0 = time.perf_counter()
        with open(yaml_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        elapsed = time.perf_counter() - t0

        assert data is not None, f"YAML vazio ou invalido: {yaml_file.name}"
        assert elapsed < 2.0, f"Parse de {yaml_file.name} demorou {elapsed:.2f}s"

    def test_capabilities_yaml_structure(self):
        """capabilities.yaml deve ter secoes tools, recipes, heuristics ou maps."""
        cap_file = KNOWLEDGE_DIR / "capabilities.yaml"
        assert cap_file.exists(), "capabilities.yaml nao encontrado"

        with open(cap_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        assert isinstance(data, dict), "capabilities.yaml deve ser um dict"
        # Deve ter ao menos tools
        assert "tools" in data, "capabilities.yaml deve ter secao 'tools'"
        assert isinstance(data["tools"], list), "tools deve ser uma lista"
        assert len(data["tools"]) > 0, "tools nao pode estar vazia"

    def test_capabilities_tools_have_required_fields(self):
        """Cada tool em capabilities.yaml deve ter id, file, summary."""
        cap_file = KNOWLEDGE_DIR / "capabilities.yaml"
        with open(cap_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        for tool in data.get("tools", []):
            assert "id" in tool, f"Tool sem 'id': {tool}"
            assert "file" in tool, f"Tool {tool.get('id')} sem 'file'"
            assert "summary" in tool, f"Tool {tool.get('id')} sem 'summary'"

    @pytest.mark.parametrize(
        "recipe_file",
        sorted((KNOWLEDGE_DIR / "recipes").glob("*.yaml")),
        ids=lambda p: p.stem,
    )
    def test_recipe_has_required_fields(self, recipe_file):
        """Cada recipe deve ter name, description, steps."""
        with open(recipe_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        assert "name" in data, f"Recipe {recipe_file.stem} sem 'name'"
        assert "description" in data, f"Recipe {recipe_file.stem} sem 'description'"
        assert "steps" in data, f"Recipe {recipe_file.stem} sem 'steps'"
        assert isinstance(data["steps"], list), (
            f"Recipe {recipe_file.stem}: steps deve ser lista"
        )
        assert len(data["steps"]) > 0, (
            f"Recipe {recipe_file.stem}: steps vazio"
        )

    @pytest.mark.parametrize(
        "heuristic_file",
        sorted((KNOWLEDGE_DIR / "heuristics").glob("*.yaml")),
        ids=lambda p: p.stem,
    )
    def test_heuristic_has_required_fields(self, heuristic_file):
        """Cada heuristica deve ter id e name (ou description)."""
        with open(heuristic_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # INDEX.yaml pode ter estrutura diferente
        if heuristic_file.stem == "INDEX":
            assert isinstance(data, (dict, list)), "INDEX.yaml deve ser dict ou list"
            return

        assert "id" in data, f"Heuristic {heuristic_file.stem} sem 'id'"
        assert "name" in data or "description" in data, (
            f"Heuristic {heuristic_file.stem} sem 'name' nem 'description'"
        )

    @pytest.mark.parametrize(
        "tool_file",
        sorted((KNOWLEDGE_DIR / "tools").glob("*.yaml")),
        ids=lambda p: p.stem,
    )
    def test_tool_definition_has_required_fields(self, tool_file):
        """Cada tool definition deve ter id/name, description."""
        with open(tool_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # _summarizers.yaml pode ter estrutura diferente
        if tool_file.stem.startswith("_"):
            assert isinstance(data, (dict, list)), (
                f"{tool_file.stem} deve ser dict ou list"
            )
            return

        assert "id" in data or "name" in data, (
            f"Tool {tool_file.stem} sem 'id' nem 'name'"
        )
        assert "description" in data, f"Tool {tool_file.stem} sem 'description'"

    def test_knowledge_parse_benchmark(self, all_yaml_files):
        """Benchmark: parsear todos os YAMLs em menos de 10 segundos."""
        t0 = time.perf_counter()
        for yf in all_yaml_files:
            with open(yf, "r", encoding="utf-8") as f:
                yaml.safe_load(f)
        elapsed = time.perf_counter() - t0

        assert elapsed < 10.0, (
            f"Parse de todos os {len(all_yaml_files)} YAMLs demorou {elapsed:.2f}s"
        )
        # Apenas informativo
        print(f"\n  [BENCH] {len(all_yaml_files)} YAMLs parseados em {elapsed:.3f}s")


# ===========================================================================
# 3. WORKSPACE DB SCHEMA — Tabelas, colunas e indices
# ===========================================================================

class TestWorkspaceDBSchema:
    """Schema do workspace SQLite deve criar todas as tabelas e indices."""

    def test_initialize_benchmark(self, tmp_path):
        """Benchmark: initialize() deve completar em menos de 2s."""
        from app.services.workspace.workspace_db import Database

        db_path = tmp_path / "bench_init.db"
        t0 = time.perf_counter()
        db = Database(db_path)
        db.initialize()
        elapsed = time.perf_counter() - t0

        assert elapsed < 2.0, f"initialize() demorou {elapsed:.2f}s"
        print(f"\n  [BENCH] workspace_db.initialize() em {elapsed:.3f}s")

    @pytest.mark.parametrize("table_name", EXPECTED_TABLES)
    def test_table_exists(self, workspace_db, table_name):
        """Tabela deve existir no schema."""
        result = workspace_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        assert result is not None, f"Tabela '{table_name}' nao encontrada"

    def test_total_table_count(self, workspace_db):
        """Schema deve ter ao menos 27 tabelas (excluindo sqlite internals)."""
        rows = workspace_db.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'"
        ).fetchone()
        count = rows[0]
        assert count >= 27, f"Esperado >= 27 tabelas, encontradas {count}"

    @pytest.mark.parametrize("index_name", EXPECTED_INDEXES)
    def test_index_exists(self, workspace_db, index_name):
        """Indice deve existir no schema."""
        result = workspace_db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
            (index_name,),
        ).fetchone()
        assert result is not None, f"Indice '{index_name}' nao encontrado"

    def test_total_index_count(self, workspace_db):
        """Schema deve ter ao menos 19 indices explicitos."""
        rows = workspace_db.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='index' "
            "AND name NOT LIKE 'sqlite_%'"
        ).fetchone()
        count = rows[0]
        assert count >= 19, f"Esperado >= 19 indices, encontrados {count}"

    def test_tabelas_columns(self, workspace_db):
        """Tabela 'tabelas' deve ter colunas essenciais."""
        cols = workspace_db.execute("PRAGMA table_info(tabelas)").fetchall()
        col_names = {c[1] for c in cols}
        for expected in ("codigo", "nome", "modo", "custom"):
            assert expected in col_names, (
                f"Coluna '{expected}' ausente na tabela 'tabelas'"
            )

    def test_campos_columns(self, workspace_db):
        """Tabela 'campos' deve ter colunas essenciais."""
        cols = workspace_db.execute("PRAGMA table_info(campos)").fetchall()
        col_names = {c[1] for c in cols}
        for expected in ("tabela", "campo", "tipo", "tamanho", "titulo", "custom"):
            assert expected in col_names, (
                f"Coluna '{expected}' ausente na tabela 'campos'"
            )

    def test_vinculos_columns(self, workspace_db):
        """Tabela 'vinculos' deve ter colunas de referencia cruzada."""
        cols = workspace_db.execute("PRAGMA table_info(vinculos)").fetchall()
        col_names = {c[1] for c in cols}
        for expected in ("tipo", "origem", "destino"):
            assert expected in col_names, (
                f"Coluna '{expected}' ausente na tabela 'vinculos'"
            )

    def test_fontes_columns(self, workspace_db):
        """Tabela 'fontes' deve ter colunas de analise de fonte."""
        cols = workspace_db.execute("PRAGMA table_info(fontes)").fetchall()
        col_names = {c[1] for c in cols}
        for expected in ("arquivo", "tipo", "modulo", "funcoes", "lines_of_code"):
            assert expected in col_names, (
                f"Coluna '{expected}' ausente na tabela 'fontes'"
            )

    def test_operacoes_escrita_columns(self, workspace_db):
        """Tabela 'operacoes_escrita' deve ter colunas de rastreamento."""
        cols = workspace_db.execute(
            "PRAGMA table_info(operacoes_escrita)"
        ).fetchall()
        col_names = {c[1] for c in cols}
        for expected in ("tabela", "arquivo", "tipo_operacao"):
            assert expected in col_names, (
                f"Coluna '{expected}' ausente na tabela 'operacoes_escrita'"
            )

    def test_diff_columns(self, workspace_db):
        """Tabela 'diff' deve ter colunas de comparacao."""
        cols = workspace_db.execute("PRAGMA table_info(diff)").fetchall()
        col_names = {c[1] for c in cols}
        for expected in ("tabela", "tipo_sx", "acao"):
            assert expected in col_names, (
                f"Coluna '{expected}' ausente na tabela 'diff'"
            )

    def test_double_initialize_idempotent(self, tmp_path):
        """Chamar initialize() duas vezes nao deve dar erro."""
        from app.services.workspace.workspace_db import Database

        db = Database(tmp_path / "idem.db")
        db.initialize()
        db.initialize()  # segunda vez

        count = db.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
        assert count > 0


# ===========================================================================
# 4. ROUTE REGISTRATION — Endpoints do workspace blueprint
# ===========================================================================

class TestWorkspaceRoutes:
    """Workspace blueprint deve ter todos os endpoints registrados."""

    # Endpoints de workspace que devem estar registrados
    WORKSPACE_ENDPOINTS = [
        "/api/workspace/workspaces",
        "/api/workspace/connections",
    ]

    # Endpoints parametrizados (usam slug placeholder)
    SLUG_ENDPOINTS = [
        "/api/workspace/workspaces/test-ws/stats",
        "/api/workspace/workspaces/test-ws/ingest/csv",
        "/api/workspace/workspaces/test-ws/ingest/fontes",
        "/api/workspace/workspaces/test-ws/ingest/live",
        "/api/workspace/workspaces/test-ws/ingest/hybrid",
        "/api/workspace/workspaces/test-ws/ingest/rest",
        "/api/workspace/workspaces/test-ws/ingest/rest/test",
        "/api/workspace/workspaces/test-ws/rest-config",
        "/api/workspace/workspaces/test-ws/explorer/tabelas",
        "/api/workspace/workspaces/test-ws/explorer/fontes",
        "/api/workspace/workspaces/test-ws/explorer/vinculos",
        "/api/workspace/workspaces/test-ws/explorer/summary",
        "/api/workspace/workspaces/test-ws/explorer/stats",
        "/api/workspace/workspaces/test-ws/explorer/tree",
        "/api/workspace/workspaces/test-ws/explorer/search",
        "/api/workspace/workspaces/test-ws/build-vinculos",
        "/api/workspace/workspaces/test-ws/dashboard",
        "/api/workspace/workspaces/test-ws/processos/descobrir",
        "/api/workspace/workspaces/test-ws/processos",
        "/api/workspace/workspaces/test-ws/processos/registrar",
        "/api/workspace/workspaces/test-ws/analista/ask",
        "/api/workspace/workspaces/test-ws/analista/history",
        "/api/workspace/workspaces/test-ws/padrao/modulos",
    ]

    def test_route_count(self, flask_test_app):
        """Workspace blueprint deve ter ao menos 24 regras de rota."""
        with flask_test_app.app_context():
            workspace_rules = [
                rule for rule in flask_test_app.url_map.iter_rules()
                if rule.rule.startswith("/api/workspace/")
            ]
        assert len(workspace_rules) >= 24, (
            f"Esperado >= 24 rotas workspace, encontradas {len(workspace_rules)}"
        )

    @pytest.mark.parametrize("endpoint", WORKSPACE_ENDPOINTS)
    def test_workspace_endpoint_not_404(self, test_client, endpoint):
        """Endpoint deve retornar algo diferente de 404 (registrado)."""
        resp = test_client.get(endpoint)
        assert resp.status_code != 404, (
            f"Endpoint {endpoint} retornou 404 (nao registrado)"
        )

    @pytest.mark.parametrize("endpoint", SLUG_ENDPOINTS)
    def test_slug_endpoint_not_404(self, test_client, endpoint):
        """Endpoints parametrizados devem existir (nao 404)."""
        resp = test_client.get(endpoint)
        # 401 (sem auth) ou 400/500 sao aceitos — mas nao 404
        assert resp.status_code != 404, (
            f"Endpoint {endpoint} retornou 404 (nao registrado)"
        )

    def test_delete_workspace_endpoint(self, test_client):
        """DELETE /workspaces/<slug> deve estar registrado."""
        resp = test_client.delete("/api/workspace/workspaces/test-ws")
        assert resp.status_code != 404

    def test_post_endpoints_accept_post(self, test_client):
        """Endpoints de ingest devem aceitar POST."""
        post_endpoints = [
            "/api/workspace/workspaces/test-ws/ingest/csv",
            "/api/workspace/workspaces/test-ws/ingest/fontes",
            "/api/workspace/workspaces/test-ws/ingest/live",
            "/api/workspace/workspaces/test-ws/build-vinculos",
        ]
        for ep in post_endpoints:
            resp = test_client.post(ep, json={})
            # 405 (method not allowed) significaria que POST nao e aceito
            assert resp.status_code != 405, (
                f"Endpoint {ep} nao aceita POST (405)"
            )


# ===========================================================================
# 5. SERVICE INSTANTIATION — Smoke tests
# ===========================================================================

class TestServiceInstantiation:
    """Servicos novos e modificados devem instanciar sem erro."""

    def test_artifact_registry_instantiate(self):
        """ArtifactRegistry deve instanciar."""
        from app.services.workspace.artifact_registry import ArtifactRegistry

        reg = ArtifactRegistry()
        assert reg is not None

    def test_context_window_manager_instantiate(self):
        """ContextWindowManager deve instanciar."""
        from app.services.workspace.context_window import ContextWindowManager

        cw = ContextWindowManager()
        assert cw is not None

    def test_cost_tracker_instantiate(self):
        """CostTracker deve instanciar."""
        from app.services.workspace.cost_tracker import CostTracker

        ct = CostTracker()
        assert ct is not None

    def test_cross_ref_index_instantiate(self):
        """CrossRefIndex deve instanciar."""
        from app.services.workspace.cross_ref_index import CrossRefIndex

        cri = CrossRefIndex()
        assert cri is not None

    def test_memory_extractor_instantiate(self):
        """MemoryExtractor deve instanciar."""
        from app.services.workspace.memory_extractor import MemoryExtractor

        me = MemoryExtractor()
        assert me is not None

    def test_session_memory_instantiate(self):
        """SessionMemory deve instanciar."""
        from app.services.workspace.session_memory import SessionMemory

        sm = SessionMemory()
        assert sm is not None

    def test_tool_validator_functions(self):
        """tool_validator deve exportar validate_tool_args e fix_common_arg_issues."""
        from app.services.workspace.tool_validator import (
            validate_tool_args,
            fix_common_arg_issues,
        )

        assert callable(validate_tool_args)
        assert callable(fix_common_arg_issues)

    def test_prompt_composer_function(self):
        """prompt_composer deve exportar compose_system_prompt."""
        from app.services.workspace.prompt_composer import compose_system_prompt

        assert callable(compose_system_prompt)

    def test_processo_decomposer_functions(self):
        """processo_decomposer deve exportar decompor_processo e analisar_complexidade."""
        from app.services.workspace.processo_decomposer import (
            decompor_processo,
            analisar_complexidade,
        )

        assert callable(decompor_processo)
        assert callable(analisar_complexidade)

    def test_processo_orquestrador_functions(self):
        """processo_orquestrador deve exportar funcoes de orquestracao."""
        from app.services.workspace.processo_orquestrador import (
            calcular_hash_inputs,
            persistir_resultado_hierarquico,
        )

        assert callable(calcular_hash_inputs)
        assert callable(persistir_resultado_hierarquico)

    def test_knowledge_service_with_db(self, workspace_db):
        """KnowledgeService deve funcionar com DB inicializado."""
        from app.services.workspace.knowledge import KnowledgeService

        ks = KnowledgeService(workspace_db)
        assert ks is not None
        # Smoke test: get_custom_summary sem dados deve retornar dict
        summary = ks.get_custom_summary()
        assert isinstance(summary, dict)

    def test_workspace_db_database_class(self, tmp_path):
        """Database class deve inicializar e criar schema."""
        from app.services.workspace.workspace_db import Database

        db = Database(tmp_path / "smoke.db")
        db.initialize()

        # execute deve funcionar
        result = db.execute("SELECT 1").fetchone()
        assert result[0] == 1


# ===========================================================================
# 6. TEMPLATE INTEGRITY — Processos e mapa-modulos
# ===========================================================================

class TestTemplateIntegrity:
    """Templates de processos e mapa-modulos devem existir e ser validos."""

    @pytest.mark.parametrize("template_name", EXPECTED_PROCESS_TEMPLATES)
    def test_process_template_exists(self, template_name):
        """Template de processo deve existir."""
        template_path = TEMPLATES_DIR / template_name
        assert template_path.exists(), (
            f"Template '{template_name}' nao encontrado em {TEMPLATES_DIR}"
        )

    @pytest.mark.parametrize("template_name", EXPECTED_PROCESS_TEMPLATES)
    def test_process_template_is_valid_markdown(self, template_name):
        """Template deve ser markdown nao-vazio com cabecalho."""
        template_path = TEMPLATES_DIR / template_name
        content = template_path.read_text(encoding="utf-8")

        assert len(content.strip()) > 0, (
            f"Template '{template_name}' esta vazio"
        )
        # Markdown deve ter ao menos um heading
        assert "#" in content, (
            f"Template '{template_name}' nao tem heading markdown"
        )

    def test_process_template_count(self):
        """Deve haver ao menos 8 templates de processo."""
        md_files = list(TEMPLATES_DIR.glob("*.md"))
        assert len(md_files) >= 8, (
            f"Esperado >= 8 templates .md, encontrados {len(md_files)}"
        )

    def test_mapa_modulos_exists(self):
        """mapa-modulos.json deve existir."""
        mapa_path = TEMPLATES_DIR / "mapa-modulos.json"
        assert mapa_path.exists(), "mapa-modulos.json nao encontrado"

    def test_mapa_modulos_is_valid_json(self):
        """mapa-modulos.json deve ser JSON valido."""
        mapa_path = TEMPLATES_DIR / "mapa-modulos.json"
        content = mapa_path.read_text(encoding="utf-8")
        data = json.loads(content)

        assert isinstance(data, (dict, list)), (
            "mapa-modulos.json deve ser dict ou list"
        )

    def test_mapa_modulos_not_empty(self):
        """mapa-modulos.json nao deve estar vazio."""
        mapa_path = TEMPLATES_DIR / "mapa-modulos.json"
        content = mapa_path.read_text(encoding="utf-8")
        data = json.loads(content)

        if isinstance(data, dict):
            assert len(data) > 0, "mapa-modulos.json esta vazio (dict)"
        else:
            assert len(data) > 0, "mapa-modulos.json esta vazio (list)"

    def test_template_parse_benchmark(self):
        """Benchmark: ler e validar todos os templates em menos de 1s."""
        t0 = time.perf_counter()
        for md_file in TEMPLATES_DIR.glob("*.md"):
            content = md_file.read_text(encoding="utf-8")
            assert len(content) > 0

        mapa = TEMPLATES_DIR / "mapa-modulos.json"
        if mapa.exists():
            json.loads(mapa.read_text(encoding="utf-8"))

        elapsed = time.perf_counter() - t0
        assert elapsed < 1.0, f"Parse de templates demorou {elapsed:.2f}s"
        print(f"\n  [BENCH] Templates parseados em {elapsed:.3f}s")


# ===========================================================================
# 7. CROSS-CUTTING BENCHMARKS
# ===========================================================================

class TestCrossCuttingBenchmarks:
    """Benchmarks que cruzam multiplos subsistemas."""

    def test_full_schema_plus_yaml_benchmark(self, tmp_path, all_yaml_files):
        """Benchmark combinado: DB init + parse de todos YAMLs."""
        from app.services.workspace.workspace_db import Database

        t0 = time.perf_counter()

        # DB init
        db = Database(tmp_path / "combined.db")
        db.initialize()

        # Parse YAMLs
        for yf in all_yaml_files:
            with open(yf, "r", encoding="utf-8") as f:
                yaml.safe_load(f)

        elapsed = time.perf_counter() - t0
        assert elapsed < 15.0, (
            f"Schema + YAML parse combinado demorou {elapsed:.2f}s"
        )
        print(f"\n  [BENCH] Schema + {len(all_yaml_files)} YAMLs em {elapsed:.3f}s")

    def test_all_new_module_imports_benchmark(self):
        """Benchmark: importar todos os modulos novos sequencialmente."""
        t0 = time.perf_counter()
        for mod_name in NEW_MODULES:
            importlib.import_module(mod_name)
        elapsed = time.perf_counter() - t0

        assert elapsed < 30.0, (
            f"Import de todos os modulos demorou {elapsed:.2f}s"
        )
        print(f"\n  [BENCH] {len(NEW_MODULES)} modulos importados em {elapsed:.3f}s")
