# -*- coding: utf-8 -*-
"""
Rotas Flask — Workspace (Engenharia Reversa Protheus)

Endpoints para gerenciar workspaces, ingestao de CSVs/fontes,
explorar dicionario e consultar vinculos.
"""

import json
import logging
import re
from pathlib import Path
from flask import Blueprint, request, jsonify, Response, stream_with_context

from app.services.workspace.workspace_populator import WorkspacePopulator
from app.services.workspace.workspace_db import Database
from app.services.workspace.knowledge import KnowledgeService
from app.utils.security import require_auth, require_permission

logger = logging.getLogger(__name__)

workspace_bp = Blueprint("workspace", __name__)


class WorkspaceLLMError(Exception):
    """Erro de LLM com mensagem amigavel para o frontend."""
    pass


@workspace_bp.errorhandler(WorkspaceLLMError)
def _handle_workspace_llm_error(e):
    """Tratamento global de LLM errors — retorna 503 com mensagem amigavel."""
    return jsonify({"error": str(e)}), 503


def _get_llm_provider():
    """Retorna LLMProvider via AgentChatEngine singleton."""
    from app.services.agent_chat import get_chat_engine
    engine = get_chat_engine()
    if not engine._llm_provider:
        raise RuntimeError("Nenhum LLM provider configurado")
    return engine._llm_provider


def _llm_chat_text(provider, messages):
    """Chama LLMProvider.chat() e retorna texto da resposta.

    Trata automaticamente o role 'system': APIs como Anthropic nao aceitam
    'system' no array de messages — converte para prefixo no primeiro user msg.
    """
    # Normalizar messages: extrair system e prefixar no primeiro user msg
    system_parts = []
    clean_msgs = []
    for m in messages:
        if m.get("role") == "system":
            system_parts.append(m["content"])
        else:
            clean_msgs.append(m)

    if system_parts and clean_msgs:
        system_text = "\n".join(system_parts)
        # Prefixar system no primeiro user message
        for i, m in enumerate(clean_msgs):
            if m["role"] == "user":
                clean_msgs[i] = {
                    "role": "user",
                    "content": f"[CONTEXTO DO SISTEMA]\n{system_text}\n\n[PERGUNTA]\n{m['content']}"
                }
                break
        messages = clean_msgs
    elif system_parts:
        # Sem user msg — converter system em user
        messages = [{"role": "user", "content": "\n".join(system_parts)}]

    try:
        result = provider.chat(messages)
    except Exception as e:
        err_msg = str(e)
        if "rate_limit" in err_msg.lower() or "rate limit" in err_msg.lower():
            raise WorkspaceLLMError("LLM temporariamente indisponivel (rate limit). Tente novamente em alguns segundos.")
        if "auth" in err_msg.lower() or "api_key" in err_msg.lower():
            raise WorkspaceLLMError("Erro de autenticacao LLM. Verifique a API key em Configuracoes > LLM/IA.")
        raise WorkspaceLLMError(f"Erro LLM: {err_msg[:200]}")
    if isinstance(result, str):
        return result
    return result.get("content", result.get("response", ""))

# Mapa de normalizacao SIGA* → nome curto do modulo
_SIGA_TO_MODULE = {
    # Modulos principais
    "sigacom": "compras", "sigafat": "faturamento", "sigafin": "financeiro",
    "sigaest": "estoque", "sigafis": "fiscal", "sigactb": "contabilidade",
    "sigagpe": "rh", "sigapcp": "pcp", "sigamnt": "manutencao",
    "sigatms": "logistica", "sigaqie": "qualidade", "sigacrm": "crm",
    "sigaloja": "loja", "sigataf": "taf", "sigapls": "plano_saude",
    # Modulos secundarios → agrupados nos principais
    "sigajuri": "financeiro", "sigaorg": "rh", "sigaoms": "estoque",
    "sigagpr": "pcp", "sigapco": "contabilidade", "sigaofi": "manutencao",
    "sigapon": "rh", "sigaqdo": "qualidade", "sigappap": "qualidade",
    "sigaqnc": "qualidade", "sigaqmt": "qualidade",
    "sigatmk": "faturamento", "sigaapt": "rh", "sigaeec": "rh",
    "sigagct": "contabilidade", "sigamdi": "rh",
}


# Prefixos de perfis de menu → modulo
_MENU_PREFIX_TO_MODULE = {
    "fat_": "faturamento", "faturamento": "faturamento",
    "cap_": "financeiro", "cre_": "financeiro", "tsr_": "financeiro", "finan": "financeiro",
    "fis_": "fiscal",
    "sup_": "compras", "compra": "compras", "rpa_compras": "compras",
    "est_": "estoque", "estoque": "estoque",
    "log_": "logistica",
    "pcp_": "pcp", "planej": "pcp", "prd_": "pcp", "ind_": "pcp",
    "rh_": "rh", "sesmt_": "rh", "adm_": "rh",
    "ctb_": "contabilidade", "rpa_contabilidade": "contabilidade",
    "jur_": "financeiro",
    "exp_": "faturamento", "imp_": "compras",
    "lab_": "qualidade", "cq_": "qualidade",
    "vdp_": "faturamento", "mfg_": "estoque",
    "aud_": "financeiro",
    "pcm_": "manutencao",
    "ti_": "outros", "monitor": "outros", "teste_": "outros",
    "key_": "logistica",
    "rpa_": "outros",
}


def _normalize_menu_module(mod_name: str) -> str:
    """Normaliza nome de modulo/perfil do menu → modulo Protheus.
    Perfis como FAT_ANALISTA → faturamento, CRE_GERENTE → financeiro."""
    clean = mod_name.strip().lower()
    # 1. Mapa SIGA* direto
    mapped = _SIGA_TO_MODULE.get(clean)
    if mapped:
        return mapped
    # SIGA* com sufixo (ex: "sigacom - sem item")
    if clean.startswith("siga"):
        base = clean.split(" ")[0].split("-")[0].strip()
        mapped = _SIGA_TO_MODULE.get(base)
        if mapped:
            return mapped
        return "outros"
    # 2. Prefixo de perfil
    for prefix, mod in _MENU_PREFIX_TO_MODULE.items():
        if clean.startswith(prefix):
            return mod
    # 3. Fallback
    return "outros"


# Diretorio base para workspaces
WORKSPACE_BASE = Path("workspace/clients")


def _get_workspace_path(slug: str) -> Path:
    """Retorna path do workspace por slug."""
    return WORKSPACE_BASE / slug


def _get_db(slug: str) -> Database:
    """Retorna Database inicializado para o workspace."""
    ws_path = _get_workspace_path(slug)
    db = Database(ws_path / "workspace.db")
    db.initialize()
    return db


def _save_rest_config_to_workspace(slug: str, rest_url: str, user: str, password: str):
    """Salva credenciais REST criptografadas no SQLite do workspace."""
    from app.utils import crypto
    db = _get_db(slug)
    try:
        encrypted_pwd = ""
        if password and crypto.token_encryption:
            encrypted_pwd = crypto.token_encryption.encrypt_token(password)

        for chave, valor in [
            ("rest_url", rest_url),
            ("rest_user", user),
            ("rest_password_encrypted", encrypted_pwd),
        ]:
            db.execute(
                "INSERT OR REPLACE INTO workspace_config (chave, valor, updated_at) "
                "VALUES (?, ?, datetime('now'))", (chave, valor))
        db.commit()
        logger.info(f"REST config salva (criptografada) no workspace {slug}")
    except Exception as e:
        logger.warning(f"Falha ao salvar REST config no workspace {slug}: {e}")
    finally:
        db.close()


def _load_rest_config_from_workspace(slug: str) -> dict | None:
    """Carrega credenciais REST do workspace SQLite (descriptografa senha)."""
    from app.utils import crypto
    db = _get_db(slug)
    try:
        rows = db.execute(
            "SELECT chave, valor FROM workspace_config WHERE chave IN "
            "('rest_url', 'rest_user', 'rest_password_encrypted')"
        ).fetchall()
        if not rows:
            return None
        cfg = {r[0]: r[1] for r in rows}
        rest_url = cfg.get("rest_url", "").strip()
        if not rest_url:
            return None

        password = ""
        encrypted = cfg.get("rest_password_encrypted", "")
        if encrypted and crypto.token_encryption:
            try:
                password = crypto.token_encryption.decrypt_token(encrypted)
            except Exception:
                logger.warning(f"Falha ao descriptografar senha REST do workspace {slug}")

        return {"rest_url": rest_url, "user": cfg.get("rest_user", ""), "password": password}
    except Exception:
        return None
    finally:
        db.close()


def _get_rest_credentials(connection_id: int) -> dict:
    """Resolve credenciais REST a partir de uma database_connection.

    Retorna {"rest_url": "...", "user": "...", "password": "..."} ou levanta erro.
    """
    from app.database.core import get_db_connection, release_db_connection
    from app.utils import crypto

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT rest_url, username, password_encrypted "
            "FROM database_connections WHERE id = %s AND is_active = TRUE",
            (connection_id,)
        )
        row = cursor.fetchone()
    finally:
        release_db_connection(conn)

    if not row:
        raise ValueError(f"Conexao {connection_id} nao encontrada ou inativa")

    rest_url = (row["rest_url"] or "").strip()
    if not rest_url:
        raise ValueError(f"Conexao {connection_id} nao possui URL REST configurada")

    username = row["username"] or ""
    password = ""
    if row["password_encrypted"] and crypto.token_encryption:
        try:
            password = crypto.token_encryption.decrypt_token(row["password_encrypted"])
        except Exception:
            raise ValueError("Falha ao descriptografar senha da conexao")

    return {"rest_url": rest_url, "user": username, "password": password}


# ========================================================================
# WORKSPACE CRUD
# ========================================================================

@workspace_bp.route("/workspaces", methods=["GET"])
@require_permission("devworkspace:view")
def list_workspaces():
    """Lista workspaces existentes."""
    if not WORKSPACE_BASE.exists():
        return jsonify([])

    workspaces = []
    for d in sorted(WORKSPACE_BASE.iterdir()):
        if d.is_dir() and (d / "workspace.db").exists():
            pop = WorkspacePopulator(d)
            pop.initialize()
            stats = pop.get_stats()
            pop.close()
            workspaces.append({
                "slug": d.name,
                "path": str(d),
                "stats": stats,
            })
    return jsonify(workspaces)


@workspace_bp.route("/workspaces/<slug>", methods=["DELETE"])
@require_permission("devworkspace:delete")
def delete_workspace(slug):
    """Exclui workspace e todos os dados."""
    import shutil
    ws_path = _get_workspace_path(slug)
    if not ws_path.exists():
        return jsonify({"error": "Workspace nao encontrado"}), 404
    try:
        shutil.rmtree(ws_path)
        # Limpar cache de DBs inicializados para permitir re-criacao
        from app.services.workspace.workspace_db import _initialized_dbs
        keys_to_remove = [k for k in _initialized_dbs if slug in k]
        for k in keys_to_remove:
            _initialized_dbs.discard(k)
        logger.info("Workspace %s excluido: %s", slug, ws_path)
        return jsonify({"success": True, "slug": slug})
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500


@workspace_bp.route("/workspaces/<slug>/stats", methods=["GET"])
@require_permission("devworkspace:view")
def workspace_stats(slug):
    """Retorna estatisticas do workspace."""
    ws_path = _get_workspace_path(slug)
    if not (ws_path / "workspace.db").exists():
        return jsonify({"error": "Workspace nao encontrado"}), 404

    pop = WorkspacePopulator(ws_path)
    pop.initialize()
    stats = pop.get_stats()
    pop.close()
    return jsonify(stats)


def _ingest_padrao_if_provided(data: dict, db) -> dict | None:
    """Se padrao_csv_dir foi fornecido, ingere CSVs padrao e calcula diff."""
    padrao_csv_dir = data.get("padrao_csv_dir", "")
    if not padrao_csv_dir:
        return None

    padrao_path = Path(padrao_csv_dir)
    if not padrao_path.exists():
        logger.warning("Diretorio padrao nao encontrado: %s", padrao_path)
        return None

    try:
        from app.services.workspace.workspace_populator import ingest_padrao_sxs, calculate_diff
        padrao_summary = ingest_padrao_sxs(db, padrao_path)
        diff_summary = calculate_diff(db)
        return {"padrao": padrao_summary, "diff": diff_summary}
    except Exception as e:
        logger.warning("Erro ao processar CSV padrao: %s", e)
        return {"padrao": {"error": str(e)}, "diff": {}}


_padrao_db_failed = False  # Cache para evitar retry em toda requisicao

def _auto_calculate_diff(db) -> dict | None:
    """Calcula diff automaticamente usando banco_padrao.db se disponivel.

    Chamado apos ingestao e lazy no dashboard/explorer quando tabela diff esta vazia.
    Cacheia falha para nao spammar logs em toda requisicao.
    """
    global _padrao_db_failed
    if _padrao_db_failed:
        return None
    from app.services.workspace.workspace_populator import calculate_diff, _get_padrao_db_path
    padrao_path = _get_padrao_db_path()
    if not padrao_path.exists():
        _padrao_db_failed = True
        return None
    try:
        result = calculate_diff(db)
        # Verificar se padrao_campos foi populada (ATTACH pode ter falhado silenciosamente)
        try:
            count = db.execute("SELECT COUNT(*) FROM padrao_campos").fetchone()[0]
            if count == 0:
                logger.warning("banco_padrao.db existe mas padrao_campos ficou vazia — arquivo pode estar corrompido")
                _padrao_db_failed = True
                return None
        except Exception:
            pass
        return result
    except Exception as e:
        logger.warning("Erro ao calcular diff com banco_padrao.db: %s", e)
        _padrao_db_failed = True
        return None


# ========================================================================
# INGESTAO
# ========================================================================

@workspace_bp.route("/workspaces/<slug>/ingest/csv", methods=["POST"])
@require_permission("devworkspace:ingest")
def ingest_csv(slug):
    """Ingere CSVs SX no workspace.

    Body JSON: {"csv_dir": "/path/to/csvs", "padrao_csv_dir": "/path/to/csvs_padrao"}
    """
    data = request.get_json()
    csv_dir = Path(data.get("csv_dir", ""))

    if not csv_dir.exists():
        return jsonify({"error": f"Diretorio nao encontrado: {csv_dir}"}), 400

    ws_path = _get_workspace_path(slug)
    pop = WorkspacePopulator(ws_path)
    pop.initialize()

    try:
        stats = pop.populate_from_csv(csv_dir)
        # Ingerir CSV padrao e calcular diff se fornecido
        padrao_stats = _ingest_padrao_if_provided(data, pop.db)
        if padrao_stats:
            stats["padrao"] = padrao_stats["padrao"]
            stats["diff"] = padrao_stats["diff"]
        else:
            # Auto-diff com banco_padrao.db se disponivel
            diff_result = _auto_calculate_diff(pop.db)
            if diff_result:
                stats["diff"] = diff_result
        return jsonify({"success": True, "stats": stats})
    except Exception as e:
        logger.exception(f"Erro na ingestao CSV: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        pop.close()


@workspace_bp.route("/workspaces/<slug>/ingest/fontes", methods=["POST"])
@require_permission("devworkspace:ingest")
def ingest_fontes(slug):
    """Parseia fontes ADVPL/TLPP e popula workspace.

    Body JSON: {"fontes_dir": "/path/to/fontes", "mapa_modulos": "/path/to/mapa.json"}
    """
    data = request.get_json()
    fontes_dir = Path(data.get("fontes_dir", ""))
    mapa_path = data.get("mapa_modulos")

    if not fontes_dir.exists():
        return jsonify({"error": f"Diretorio nao encontrado: {fontes_dir}"}), 400

    ws_path = _get_workspace_path(slug)
    pop = WorkspacePopulator(ws_path)
    pop.initialize()

    try:
        mapa = Path(mapa_path) if mapa_path else None
        stats = pop.parse_fontes(fontes_dir, mapa)
        return jsonify({"success": True, "stats": stats})
    except Exception as e:
        logger.exception(f"Erro no parse de fontes: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        pop.close()


@workspace_bp.route("/workspaces/<slug>/ingest/live", methods=["POST"])
@require_permission("devworkspace:ingest")
def ingest_live(slug):
    """Popula workspace lendo SX* diretamente do banco Protheus.

    Body JSON: {"connection_id": 1, "company_code": "01", "environment_id": 1, "padrao_csv_dir": "..."}
    """
    data = request.get_json()
    connection_id = data.get("connection_id")
    company_code = data.get("company_code", "01")
    environment_id = data.get("environment_id")

    if not connection_id:
        return jsonify({"error": "connection_id e obrigatorio"}), 400

    ws_path = _get_workspace_path(slug)
    pop = WorkspacePopulator(ws_path)
    pop.initialize()

    try:
        stats = pop.populate_from_db(connection_id, company_code, environment_id)
        padrao_stats = _ingest_padrao_if_provided(data, pop.db)
        if padrao_stats:
            stats["padrao"] = padrao_stats["padrao"]
            stats["diff"] = padrao_stats["diff"]
        else:
            diff_result = _auto_calculate_diff(pop.db)
            if diff_result:
                stats["diff"] = diff_result
        return jsonify({"success": True, "stats": stats})
    except Exception as e:
        logger.exception(f"Erro na ingestao live: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        pop.close()


@workspace_bp.route("/workspaces/<slug>/ingest/hybrid", methods=["POST"])
@require_permission("devworkspace:ingest")
def ingest_hybrid(slug):
    """Modo hibrido: dicionario do DB + fontes do filesystem.

    Body JSON: {"connection_id": 1, "company_code": "01", "fontes_dir": "/path", "environment_id": 1}
    """
    data = request.get_json()
    connection_id = data.get("connection_id")
    company_code = data.get("company_code", "01")
    fontes_dir = Path(data.get("fontes_dir", ""))
    environment_id = data.get("environment_id")
    mapa_path = data.get("mapa_modulos")

    if not connection_id:
        return jsonify({"error": "connection_id e obrigatorio"}), 400
    if not fontes_dir.exists():
        return jsonify({"error": f"Diretorio nao encontrado: {fontes_dir}"}), 400

    ws_path = _get_workspace_path(slug)
    pop = WorkspacePopulator(ws_path)
    pop.initialize()

    try:
        mapa = Path(mapa_path) if mapa_path else None
        stats = pop.populate_hybrid(connection_id, company_code, fontes_dir, mapa, environment_id)
        padrao_stats = _ingest_padrao_if_provided(data, pop.db)
        if padrao_stats:
            stats["padrao"] = padrao_stats["padrao"]
            stats["diff"] = padrao_stats["diff"]
        else:
            diff_result = _auto_calculate_diff(pop.db)
            if diff_result:
                stats["diff"] = diff_result
        return jsonify({"success": True, "stats": stats})
    except Exception as e:
        logger.exception(f"Erro na ingestao hibrida: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        pop.close()


@workspace_bp.route("/workspaces/<slug>/ingest/rest", methods=["POST"])
@require_permission("devworkspace:ingest")
def ingest_rest(slug):
    """Popula workspace via API REST do Protheus.

    Body JSON (modo conexao): {"connection_id": 1}
    Body JSON (modo manual):  {"rest_url": "...", "rest_user": "...", "rest_password": "..."}
    Ambos aceitam "padrao_csv_dir" opcional.
    """
    import asyncio
    data = request.get_json()
    connection_id = data.get("connection_id")

    if connection_id:
        # Modo conexao cadastrada
        try:
            creds = _get_rest_credentials(int(connection_id))
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
    else:
        # Modo manual — credenciais no body ou salvas no workspace
        rest_url = data.get("rest_url", "").strip()
        rest_user = data.get("rest_user", "").strip()
        rest_password = data.get("rest_password", "")

        if not rest_url or not rest_user:
            return jsonify({"error": "Informe connection_id ou rest_url + rest_user"}), 400

        # Se senha nao veio, tentar carregar a salva no workspace
        if not rest_password:
            saved = _load_rest_config_from_workspace(slug)
            if saved and saved["rest_url"] == rest_url and saved["user"] == rest_user:
                rest_password = saved["password"]

        if not rest_password:
            return jsonify({"error": "Senha e obrigatoria na primeira configuracao manual"}), 400

        creds = {"rest_url": rest_url, "user": rest_user, "password": rest_password}

        # Salvar credenciais criptografadas no workspace para reutilizacao
        _save_rest_config_to_workspace(slug, rest_url, rest_user, rest_password)

    from app.services.workspace.rest_client import ProtheusRESTClient
    from app.services.workspace.rest_ingestor import RESTIngestor

    # Testar conexao primeiro
    client = ProtheusRESTClient(creds["rest_url"], creds["user"], creds["password"])
    test = client.test_connection()
    if not test.get("ok"):
        return jsonify({"error": f"Falha na conexao REST: {test.get('message', 'erro desconhecido')}"}), 400

    ws_path = _get_workspace_path(slug)
    db = Database(ws_path / "workspace.db")
    db.initialize()

    try:
        ingestor = RESTIngestor(db, client)

        # Executar ingestao sincrona (run_fase1 e async mas executamos no loop)
        loop = asyncio.new_event_loop()
        stats = {"tabelas": {}, "total_items": 0, "errors": []}

        async def _run():
            async for progress in ingestor.run_fase1():
                item = progress.get("item", "")
                status = progress.get("status", "")
                if status == "done":
                    count = progress.get("count", 0)
                    stats["tabelas"][item] = count
                    stats["total_items"] += count
                    logger.info(f"REST ingest {slug}: {item} = {count} registros")
                elif status == "error":
                    stats["errors"].append(f"{item}: {progress.get('msg', '')}")
                    logger.error(f"REST ingest {slug}: {item} erro = {progress.get('msg', '')}")

        loop.run_until_complete(_run())
        loop.close()

        # Ingerir CSV padrao e calcular diff se fornecido
        padrao_dir = data.get("padrao_csv_dir")
        if padrao_dir:
            padrao_stats = _ingest_padrao_if_provided(data, db)
            if padrao_stats:
                stats["padrao"] = padrao_stats["padrao"]
                stats["diff"] = padrao_stats["diff"]
        else:
            diff_result = _auto_calculate_diff(db)
            if diff_result:
                stats["diff"] = diff_result

        return jsonify({"success": True, "mode": "rest", "stats": stats})
    except Exception as e:
        logger.exception(f"Erro na ingestao REST: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@workspace_bp.route("/workspaces/<slug>/ingest/rest/test", methods=["POST"])
@require_permission("devworkspace:ingest")
def ingest_rest_test(slug):
    """Testa conexao REST.

    Body JSON (conexao): {"connection_id": 1}
    Body JSON (manual):  {"rest_url": "...", "rest_user": "...", "rest_password": "..."}
    """
    data = request.get_json()
    connection_id = data.get("connection_id")

    if connection_id:
        try:
            creds = _get_rest_credentials(int(connection_id))
        except ValueError as e:
            return jsonify({"ok": False, "message": str(e)})
    else:
        rest_url = data.get("rest_url", "").strip()
        rest_user = data.get("rest_user", "").strip()
        rest_password = data.get("rest_password", "")
        if not rest_url or not rest_user:
            return jsonify({"ok": False, "message": "Informe connection_id ou rest_url + rest_user"})
        # Se senha nao veio, tentar carregar a salva
        if not rest_password:
            saved = _load_rest_config_from_workspace(slug)
            if saved and saved["rest_url"] == rest_url and saved["user"] == rest_user:
                rest_password = saved["password"]
        if not rest_password:
            return jsonify({"ok": False, "message": "Senha e obrigatoria na primeira configuracao manual"})
        creds = {"rest_url": rest_url, "user": rest_user, "password": rest_password}

    from app.services.workspace.rest_client import ProtheusRESTClient
    client = ProtheusRESTClient(creds["rest_url"], creds["user"], creds["password"])
    result = client.test_connection()
    return jsonify(result)


@workspace_bp.route("/workspaces/<slug>/rest-config", methods=["GET"])
@require_permission("devworkspace:view")
def get_rest_config(slug):
    """Retorna config REST salva no workspace (sem expor senha)."""
    saved = _load_rest_config_from_workspace(slug)
    if saved:
        return jsonify({"saved": True, "rest_url": saved["rest_url"], "rest_user": saved["user"]})
    return jsonify({"saved": False})


@workspace_bp.route("/connections", methods=["GET"])
@require_permission("devworkspace:view")
def list_connections():
    """Lista conexoes de banco disponiveis para modo live."""
    try:
        from app.database.core import get_db_connection, release_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, driver, host, port, database_name, environment_id, rest_url "
            "FROM database_connections WHERE is_active = TRUE ORDER BY name"
        )
        rows = cursor.fetchall()
        release_db_connection(conn)
        result = []
        for r in rows:
            d = dict(r)
            d["has_rest"] = bool(d.get("rest_url", "").strip())
            result.append(d)
        return jsonify(result)
    except Exception as e:
        return jsonify([])


# ========================================================================
# EXPLORER — Navegacao no dicionario
# ========================================================================

@workspace_bp.route("/workspaces/<slug>/explorer/tabelas", methods=["GET"])
@require_permission("devworkspace:view")
def explorer_tabelas(slug):
    """Lista todas as tabelas do workspace."""
    db = _get_db(slug)
    rows = db.execute(
        "SELECT codigo, nome, modo, custom FROM tabelas ORDER BY codigo"
    ).fetchall()
    return jsonify([
        {"codigo": r[0], "nome": r[1], "modo": r[2], "custom": bool(r[3])}
        for r in rows
    ])


@workspace_bp.route("/workspaces/<slug>/explorer/tabela/<codigo>", methods=["GET"])
@require_permission("devworkspace:view")
def explorer_tabela_detail(slug, codigo):
    """Retorna informacoes completas de uma tabela (campos, indices, gatilhos, fontes vinculados).
    Enriquece campos com status diff (padrao/adicionado/alterado)."""
    db = _get_db(slug)
    ks = KnowledgeService(db)
    info = ks.get_table_info(codigo.upper())
    if not info:
        return jsonify({"error": "Tabela nao encontrada"}), 404

    # Enriquecer campos com status diff
    try:
        diff_rows = db.execute(
            "SELECT chave, acao, campo_diff, valor_padrao, valor_cliente "
            "FROM diff WHERE tipo_sx IN ('campo', 'SX3') AND tabela = ?",
            (codigo.upper(),)
        ).fetchall()
        diff_added = set()
        diff_altered = {}
        for r in diff_rows:
            if r[1] == "adicionado":
                diff_added.add(r[0])
            elif r[1] == "alterado":
                diff_altered.setdefault(r[0], []).append({
                    "campo_diff": r[2], "valor_padrao": r[3], "valor_cliente": r[4]
                })

        # Verificar se padrao_campos tem dados (diff so e confiavel se sim)
        padrao_global_count = 0
        try:
            padrao_global_count = db.execute("SELECT COUNT(*) FROM padrao_campos").fetchone()[0]
        except Exception:
            pass

        has_diff = len(diff_rows) > 0 and padrao_global_count > 0

        # Carregar dados padrao para comparacao inline (quando diff existe ou como fallback)
        padrao_map = {}
        if padrao_global_count > 0:
            try:
                padrao_rows = db.execute(
                    "SELECT campo, tipo, tamanho, validacao, titulo, f3 "
                    "FROM padrao_campos WHERE tabela = ?",
                    (codigo.upper(),)
                ).fetchall()
                for pr in padrao_rows:
                    padrao_map[pr[0]] = {
                        "tipo": pr[1] or "", "tamanho": pr[2] or 0,
                        "validacao": pr[3] or "", "titulo": pr[4] or "", "f3": pr[5] or ""
                    }
            except Exception:
                pass

        has_padrao = len(padrao_map) > 0

        for campo in info.get("campos", []):
            nome = campo["campo"]
            if has_diff:
                # Usar tabela diff como fonte primaria
                if nome in diff_added:
                    campo["status"] = "adicionado"
                elif nome in diff_altered:
                    campo["status"] = "alterado"
                    campo["alteracoes"] = diff_altered[nome]
                else:
                    campo["status"] = "padrao"
            elif has_padrao:
                # Fallback: comparar diretamente com padrao_campos
                if nome not in padrao_map:
                    campo["status"] = "adicionado"
                else:
                    pad = padrao_map[nome]
                    diffs = []
                    if str(campo.get("tipo", "")) != str(pad["tipo"]):
                        diffs.append({"campo_diff": "tipo", "valor_padrao": pad["tipo"], "valor_cliente": campo.get("tipo", "")})
                    if int(campo.get("tamanho", 0)) != int(pad["tamanho"] or 0):
                        diffs.append({"campo_diff": "tamanho", "valor_padrao": str(pad["tamanho"]), "valor_cliente": str(campo.get("tamanho", ""))})
                    cli_valid = (campo.get("validacao") or "").strip()
                    pad_valid = (pad["validacao"] or "").strip()
                    if cli_valid != pad_valid:
                        diffs.append({"campo_diff": "validacao", "valor_padrao": pad_valid[:80], "valor_cliente": cli_valid[:80]})
                    if diffs:
                        campo["status"] = "alterado"
                        campo["alteracoes"] = diffs
                    else:
                        campo["status"] = "padrao"
            else:
                # Sem diff e sem padrao: usar flag custom do campo
                campo["status"] = "adicionado" if campo.get("custom") else "padrao"
    except Exception:
        pass

    # Fontes vinculados a esta tabela
    try:
        tab = codigo.upper()
        fontes_rows = db.execute(
            "SELECT arquivo, modulo, tabelas_ref, write_tables, lines_of_code "
            "FROM fontes WHERE tabelas_ref LIKE ? OR write_tables LIKE ?",
            (f'%"{tab}"%', f'%"{tab}"%')
        ).fetchall()
        fontes_vinculados = []
        for f in fontes_rows:
            writes = json.loads(f[3]) if f[3] else []
            modo = "Leitura/Escrita" if tab in [w.upper() for w in writes] else "Leitura"
            fontes_vinculados.append({
                "arquivo": f[0], "modulo": f[1] or "", "loc": f[4] or 0, "modo": modo
            })
        info["fontes_vinculados"] = fontes_vinculados
    except Exception:
        info["fontes_vinculados"] = []

    return jsonify(info)


@workspace_bp.route("/workspaces/<slug>/explorer/fontes", methods=["GET"])
@require_permission("devworkspace:view")
def explorer_fontes(slug):
    """Lista fontes parseados no workspace."""
    db = _get_db(slug)
    modulo = request.args.get("modulo")

    if modulo:
        rows = db.execute(
            "SELECT arquivo, tipo, modulo, lines_of_code FROM fontes WHERE lower(modulo) = ? ORDER BY arquivo",
            (modulo.lower(),)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT arquivo, tipo, modulo, lines_of_code FROM fontes ORDER BY arquivo"
        ).fetchall()

    return jsonify([
        {"arquivo": r[0], "tipo": r[1], "modulo": r[2], "lines_of_code": r[3]}
        for r in rows
    ])


@workspace_bp.route("/workspaces/<slug>/explorer/vinculos", methods=["GET"])
@require_permission("devworkspace:view")
def explorer_vinculos(slug):
    """Lista vinculos do workspace, opcionalmente filtrados por modulo."""
    db = _get_db(slug)
    ks = KnowledgeService(db)
    modulo = request.args.get("modulo", "")

    if modulo:
        vinculos = ks.get_vinculos_for_module(modulo)
    else:
        rows = db.execute(
            "SELECT tipo, COUNT(*) FROM vinculos GROUP BY tipo ORDER BY COUNT(*) DESC"
        ).fetchall()
        vinculos = [{"tipo": r[0], "count": r[1]} for r in rows]

    return jsonify(vinculos)


@workspace_bp.route("/workspaces/<slug>/explorer/summary", methods=["GET"])
@require_permission("devworkspace:view")
def explorer_summary(slug):
    """Retorna resumo de customizacoes do workspace."""
    db = _get_db(slug)
    ks = KnowledgeService(db)
    return jsonify(ks.get_custom_summary())


def _compute_diff_stats(db, _c):
    """Calcula stats de diff com fallback para campos.custom quando tabela diff esta vazia."""
    # Verificar se padrao_campos tem dados — sem isso, diff nao e confiavel
    padrao_count = _c("SELECT COUNT(*) FROM padrao_campos")

    if padrao_count == 0:
        # Sem base padrao: auto-diff para tentar popular via banco_padrao.db
        _auto_calculate_diff(db)
        padrao_count = _c("SELECT COUNT(*) FROM padrao_campos")

    if padrao_count > 0:
        # Base padrao disponivel — diff confiavel
        diff_add = _c("SELECT COUNT(DISTINCT chave) FROM diff WHERE tipo_sx IN ('campo','SX3') AND acao='adicionado'")
        diff_alt = _c("SELECT COUNT(DISTINCT chave) FROM diff WHERE tipo_sx IN ('campo','SX3') AND acao='alterado'")
        diff_rem = _c("SELECT COUNT(DISTINCT chave) FROM diff WHERE tipo_sx IN ('campo','SX3') AND acao='removido'")
        if (diff_add + diff_alt + diff_rem) > 0:
            return {"adicionados": diff_add, "alterados": diff_alt, "removidos": diff_rem}

    # Fallback: usar campos.custom (sem base padrao ou diff vazio apos tentativa)
    custom_total = _c("SELECT COUNT(*) FROM campos WHERE custom = 1")
    return {"adicionados": custom_total, "alterados": 0, "removidos": 0}


@workspace_bp.route("/workspaces/<slug>/explorer/stats", methods=["GET"])
@require_permission("devworkspace:view")
def explorer_stats(slug):
    """Retorna estatisticas resumidas para a barra de stats do Explorer."""
    db = _get_db(slug)

    def _c(q, p=()):
        try:
            return db.execute(q, p).fetchone()[0]
        except Exception:
            return 0

    return jsonify({
        "tabelas": {"total": _c("SELECT COUNT(*) FROM tabelas"), "custom": _c("SELECT COUNT(*) FROM tabelas WHERE custom=1")},
        "campos": {"total": _c("SELECT COUNT(*) FROM campos"), "custom": _c("SELECT COUNT(*) FROM campos WHERE custom=1")},
        "fontes": {"total": _c("SELECT COUNT(*) FROM fontes"), "com_pe": _c("SELECT COUNT(*) FROM fontes WHERE pontos_entrada IS NOT NULL AND pontos_entrada != '[]'")},
        "indices": {"total": _c("SELECT COUNT(*) FROM indices"), "custom": _c("SELECT COUNT(*) FROM indices WHERE custom=1")},
        "gatilhos": {"total": _c("SELECT COUNT(*) FROM gatilhos"), "custom": _c("SELECT COUNT(*) FROM gatilhos WHERE custom=1")},
        "parametros": {"total": _c("SELECT COUNT(*) FROM parametros"), "custom": _c("SELECT COUNT(*) FROM parametros WHERE custom=1")},
        "vinculos": {"total": _c("SELECT COUNT(*) FROM vinculos")},
        "menus": {"total": _c("SELECT COUNT(*) FROM menus")},
        "diff": _compute_diff_stats(db, _c),
        "jobs": {"total": _c("SELECT COUNT(*) FROM jobs")},
        "schedules": {"total": _c("SELECT COUNT(*) FROM schedules"), "ativos": _c("SELECT COUNT(*) FROM schedules WHERE status='Ativo'")}
    })


@workspace_bp.route("/workspaces/<slug>/explorer/tree", methods=["GET"])
@require_permission("devworkspace:view")
def explorer_tree(slug):
    """Retorna arvore hierarquica de modulos com contagens por categoria."""
    db = _get_db(slug)

    # Build module -> tables map from mapa_modulos
    modulos = {}

    # From mapa_modulos (standard mapping)
    try:
        mapa_rows = db.execute("SELECT modulo, tabelas, rotinas FROM mapa_modulos").fetchall()
        for mr in mapa_rows:
            mod = mr[0]
            tabs = json.loads(mr[1]) if mr[1] else []
            modulos[mod] = {"tabelas": set(t.upper() for t in tabs), "fontes": 0, "pes": 0, "menus_cliente": 0, "menus_padrao": 0}
    except Exception:
        pass

    # Count fontes per module AND enriquecer tabelas com fontes.tabelas_ref
    try:
        rows = db.execute(
            "SELECT modulo, COUNT(*) FROM fontes WHERE modulo IS NOT NULL AND modulo != '' GROUP BY modulo"
        ).fetchall()
        for r in rows:
            mod = r[0].lower()
            if mod not in modulos:
                modulos[mod] = {"tabelas": set(), "fontes": 0, "pes": 0, "menus_cliente": 0, "menus_padrao": 0}
            modulos[mod]["fontes"] = r[1]
    except Exception:
        pass

    # Enriquecer tabelas por modulo usando fontes.tabelas_ref (real)
    try:
        rows = db.execute(
            "SELECT modulo, tabelas_ref, write_tables FROM fontes WHERE modulo IS NOT NULL AND modulo != ''"
        ).fetchall()
        for r in rows:
            mod = r[0].lower()
            if mod not in modulos:
                continue
            for field in [r[1], r[2]]:
                try:
                    refs = json.loads(field) if field else []
                    for t in refs:
                        if isinstance(t, str) and t.strip():
                            modulos[mod]["tabelas"].add(t.strip().upper())
                except (json.JSONDecodeError, TypeError):
                    pass
    except Exception:
        pass

    # Count PEs per module (from fontes.pontos_entrada JSON)
    try:
        rows = db.execute("SELECT modulo, pontos_entrada FROM fontes WHERE pontos_entrada IS NOT NULL AND pontos_entrada != '[]'").fetchall()
        for r in rows:
            mod = (r[0] or "outros").lower()
            pes = json.loads(r[1]) if r[1] else []
            if mod not in modulos:
                modulos[mod] = {"tabelas": set(), "fontes": 0, "pes": 0, "menus_cliente": 0, "menus_padrao": 0}
            modulos[mod]["pes"] += len(pes)
    except Exception:
        pass

    # Count menus per module (normaliza SIGA* → nome curto)
    try:
        rows = db.execute("SELECT modulo, COUNT(*) FROM menus WHERE modulo IS NOT NULL GROUP BY modulo").fetchall()
        for r in rows:
            mod = _normalize_menu_module(r[0])
            if mod in modulos:
                modulos[mod]["menus_cliente"] += r[1]
            else:
                modulos.setdefault("outros", {"tabelas": set(), "fontes": 0, "pes": 0, "menus_cliente": 0, "menus_padrao": 0})
                modulos["outros"]["menus_cliente"] += r[1]
    except Exception:
        pass

    # Assign tables to modules (check which tables belong to which module)
    all_tabelas = set()
    try:
        rows = db.execute("SELECT codigo FROM tabelas").fetchall()
        all_tabelas = {r[0].upper() for r in rows}
    except Exception:
        pass

    assigned_tabelas = set()
    for mod_data in modulos.values():
        assigned_tabelas |= mod_data["tabelas"]

    # Tables not assigned to any module go to "outros"
    unassigned = all_tabelas - assigned_tabelas
    if unassigned:
        modulos.setdefault("outros", {"tabelas": set(), "fontes": 0, "pes": 0, "menus_cliente": 0, "menus_padrao": 0})
        modulos["outros"]["tabelas"] |= unassigned

    # Build tree
    tree = []
    for mod_name in sorted(modulos.keys()):
        mod = modulos[mod_name]
        tab_count = len(mod["tabelas"] & all_tabelas)  # Only count tables that actually exist
        children = []
        if tab_count > 0:
            children.append({"key": mod_name + "_tabelas", "label": "Tabelas", "type": "category", "data": {"cat": "tabelas", "count": tab_count, "modulo": mod_name}})
        if mod["pes"] > 0:
            children.append({"key": mod_name + "_pes", "label": "Pontos de Entrada", "type": "category", "data": {"cat": "pes", "count": mod["pes"], "modulo": mod_name}})
        if mod["menus_cliente"] > 0:
            children.append({"key": mod_name + "_menus", "label": "Menus Cliente", "type": "category", "data": {"cat": "menus_cliente", "count": mod["menus_cliente"], "modulo": mod_name}})
        if mod["fontes"] > 0:
            children.append({"key": mod_name + "_fontes", "label": "Fontes Custom", "type": "category", "data": {"cat": "fontes", "count": mod["fontes"], "modulo": mod_name}})

        tree.append({
            "key": mod_name,
            "label": mod_name.capitalize(),
            "type": "modulo",
            "data": {"fontes": mod["fontes"], "tabelas": tab_count, "menus": mod["menus_cliente"], "pes": mod["pes"]},
            "children": children
        })

    # Add Jobs and Schedules at root level
    try:
        jobs_count = db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        if jobs_count > 0:
            tree.append({"key": "_jobs", "label": "Jobs (" + str(jobs_count) + ")", "type": "leaf_category", "data": {"cat": "jobs", "count": jobs_count}})
    except Exception:
        pass
    try:
        sched_count = db.execute("SELECT COUNT(*) FROM schedules").fetchone()[0]
        if sched_count > 0:
            tree.append({"key": "_schedules", "label": "Schedules (" + str(sched_count) + ")", "type": "leaf_category", "data": {"cat": "schedules", "count": sched_count}})
    except Exception:
        pass

    return jsonify(tree)


@workspace_bp.route("/workspaces/<slug>/explorer/category/<modulo>/<cat>", methods=["GET"])
@require_permission("devworkspace:view")
def explorer_category_items(slug, modulo, cat):
    """Retorna itens de uma categoria dentro de um modulo."""
    db = _get_db(slug)

    if cat == "tabelas":
        # Combinar mapa_modulos (seed) + fontes.tabelas_ref (real) para pegar TODAS as tabelas
        tab_set = set()

        # Fonte 1: mapa_modulos (tabelas seed)
        try:
            row = db.execute("SELECT tabelas FROM mapa_modulos WHERE modulo = ?", (modulo,)).fetchone()
            if row:
                for t in json.loads(row[0]):
                    tab_set.add(t.upper())
        except Exception:
            pass

        # Fonte 2: fontes.tabelas_ref (tabelas reais referenciadas por fontes do modulo)
        try:
            rows = db.execute(
                "SELECT tabelas_ref, write_tables FROM fontes WHERE lower(modulo) = ?",
                (modulo.lower(),)
            ).fetchall()
            for r in rows:
                for field in [r[0], r[1]]:
                    try:
                        refs = json.loads(field) if field else []
                        for t in refs:
                            if isinstance(t, str) and t.strip():
                                tab_set.add(t.strip().upper())
                    except (json.JSONDecodeError, TypeError):
                        pass
        except Exception:
            pass

        # Buscar info de cada tabela e contar campos custom + alterados
        diff_alt_map = {}
        try:
            diff_rows = db.execute(
                "SELECT tabela, COUNT(DISTINCT chave) FROM diff "
                "WHERE tipo_sx IN ('campo','SX3') AND acao='alterado' GROUP BY tabela"
            ).fetchall()
            diff_alt_map = {r[0]: r[1] for r in diff_rows}
        except Exception:
            pass

        items = []
        for tc in sorted(tab_set):
            row = db.execute("SELECT codigo, nome, custom FROM tabelas WHERE upper(codigo) = ?", (tc,)).fetchone()
            if row:
                add_count = 0
                try:
                    add_count = db.execute("SELECT COUNT(*) FROM campos WHERE tabela = ? AND custom = 1", (row[0],)).fetchone()[0]
                except Exception:
                    pass
                alt_count = diff_alt_map.get(row[0], 0)
                items.append({
                    "codigo": row[0], "nome": row[1], "custom": bool(row[2]),
                    "campos_add": add_count, "campos_alt": alt_count
                })
        return jsonify(items)

    elif cat == "pes":
        # PEs from fontes in this module
        items = []
        try:
            rows = db.execute(
                "SELECT arquivo, pontos_entrada FROM fontes WHERE lower(modulo) = ? AND pontos_entrada IS NOT NULL AND pontos_entrada != '[]'",
                (modulo.lower(),)
            ).fetchall()
            for r in rows:
                pes = json.loads(r[1]) if r[1] else []
                for pe in pes:
                    if isinstance(pe, str) and pe.strip():
                        items.append({"pe": pe.strip(), "fonte": r[0]})
        except Exception:
            pass
        items.sort(key=lambda x: x["pe"])
        return jsonify(items)

    elif cat == "menus_cliente":
        items = []
        try:
            # Buscar menus: por nome curto OU pelo nome SIGA* original
            siga_names = [k for k, v in _SIGA_TO_MODULE.items() if v == modulo.lower()]
            placeholders = ",".join(["?"] * (len(siga_names) + 1))
            params = [modulo.lower()] + siga_names
            rows = db.execute(
                f"SELECT rotina, nome, menu FROM menus WHERE lower(TRIM(modulo)) IN ({placeholders}) ORDER BY rotina",
                params
            ).fetchall()
            # Try to find matching fonte
            for r in rows:
                fonte = ""
                try:
                    f = db.execute("SELECT arquivo FROM fontes WHERE upper(arquivo) LIKE ?", (r[0].upper() + '%',)).fetchone()
                    if f:
                        fonte = f[0]
                except Exception:
                    pass
                items.append({"rotina": r[0], "nome": r[1], "menu": r[2] or "", "fonte": fonte})
        except Exception:
            pass
        return jsonify(items)

    elif cat == "fontes":
        items = []
        try:
            rows = db.execute(
                "SELECT arquivo, funcoes, lines_of_code FROM fontes WHERE lower(modulo) = ? ORDER BY arquivo",
                (modulo.lower(),)
            ).fetchall()
            for r in rows:
                funcs = json.loads(r[1]) if r[1] else []
                items.append({"arquivo": r[0], "funcoes": len(funcs), "loc": r[2] or 0})
        except Exception:
            pass
        return jsonify(items)

    elif cat == "jobs":
        items = []
        try:
            rows = db.execute("SELECT arquivo_ini, sessao, rotina, refresh_rate, parametros FROM jobs ORDER BY rotina").fetchall()
            for r in rows:
                items.append({"arquivo": r[0], "sessao": r[1], "rotina": r[2], "refresh_rate": r[3], "parametros": r[4] or ""})
        except Exception:
            pass
        return jsonify(items)

    elif cat == "schedules":
        items = []
        try:
            rows = db.execute(
                "SELECT codigo, rotina, empresa_filial, status, tipo_recorrencia, execucoes_dia, hora_inicio FROM schedules ORDER BY rotina"
            ).fetchall()
            for r in rows:
                items.append({"codigo": r[0], "rotina": r[1], "empresa_filial": r[2], "status": r[3], "tipo_recorrencia": r[4], "execucoes_dia": r[5], "hora_inicio": r[6] or ""})
        except Exception:
            pass
        return jsonify(items)

    return jsonify([])


@workspace_bp.route("/workspaces/<slug>/explorer/fonte/<arquivo>", methods=["GET"])
@require_permission("devworkspace:view")
def explorer_fonte_detail(slug, arquivo):
    """Retorna detalhe de um fonte (funcoes, tabelas, PEs, operacoes de escrita)."""
    db = _get_db(slug)

    row = db.execute(
        "SELECT arquivo, caminho, tipo, modulo, funcoes, user_funcs, pontos_entrada, "
        "tabelas_ref, write_tables, includes, calls_u, calls_execblock, fields_ref, "
        "lines_of_code, hash "
        "FROM fontes WHERE arquivo = ?", (arquivo,)
    ).fetchone()

    if not row:
        return jsonify({"error": "Fonte nao encontrado"}), 404

    def _j(val):
        try:
            return json.loads(val) if val else []
        except Exception:
            return []

    result = {
        "arquivo": row[0],
        "caminho": row[1] or "",
        "tipo": row[2] or "",
        "modulo": row[3] or "",
        "funcoes": _j(row[4]),
        "user_funcs": _j(row[5]),
        "pontos_entrada": _j(row[6]),
        "tabelas_ref": _j(row[7]),
        "write_tables": _j(row[8]),
        "includes": _j(row[9]),
        "calls_u": _j(row[10]),
        "calls_execblock": _j(row[11]),
        "fields_ref": _j(row[12]),
        "lines_of_code": row[13] or 0,
    }

    # Operacoes de escrita deste fonte
    try:
        ops = db.execute(
            "SELECT funcao, tipo, tabela, campos, condicao, linha "
            "FROM operacoes_escrita WHERE arquivo = ? ORDER BY linha",
            (arquivo,)
        ).fetchall()
        result["operacoes_escrita"] = [
            {"funcao": o[0], "tipo": o[1], "tabela": o[2],
             "campos": json.loads(o[3]) if o[3] else [], "condicao": o[4] or "", "linha": o[5]}
            for o in ops
        ]
    except Exception:
        result["operacoes_escrita"] = []

    # Vinculos deste fonte
    try:
        vinc = db.execute(
            "SELECT tipo, origem, destino, contexto FROM vinculos "
            "WHERE origem = ? OR destino = ? LIMIT 50",
            (arquivo, arquivo)
        ).fetchall()
        result["vinculos"] = [
            {"tipo": v[0], "origem": v[1], "destino": v[2], "contexto": v[3] or ""}
            for v in vinc
        ]
    except Exception:
        result["vinculos"] = []

    # Funcao docs (resumos gerados)
    try:
        docs = db.execute(
            "SELECT funcao, tipo, assinatura, resumo, tabelas_ref, chama, chamada_por, retorno "
            "FROM funcao_docs WHERE arquivo = ?",
            (arquivo,)
        ).fetchall()
        result["funcao_docs"] = [
            {"funcao": d[0], "tipo": d[1], "assinatura": d[2] or "", "resumo": d[3] or "",
             "tabelas_ref": d[4] or "", "chama": d[5] or "", "chamada_por": d[6] or "", "retorno": d[7] or ""}
            for d in docs
        ]
    except Exception:
        result["funcao_docs"] = []

    return jsonify(result)


@workspace_bp.route("/workspaces/<slug>/explorer/diff/<tabela>", methods=["GET"])
@require_permission("devworkspace:view")
def explorer_diff_detail(slug, tabela):
    """Retorna diff detalhado padrao vs cliente para uma tabela."""
    db = _get_db(slug)
    tab = tabela.upper()

    # Check if padrao data exists
    padrao_count = 0
    try:
        padrao_count = db.execute("SELECT COUNT(*) FROM padrao_campos WHERE tabela = ?", (tab,)).fetchone()[0]
    except Exception:
        pass

    if padrao_count == 0:
        return jsonify({"available": False, "tabela": tab, "message": "Dados padrao nao ingeridos para esta tabela"})

    # Adicionados: no cliente mas nao no padrao
    adicionados = []
    try:
        rows = db.execute(
            "SELECT c.campo, c.tipo, c.tamanho, c.titulo, c.validacao "
            "FROM campos c LEFT JOIN padrao_campos p ON c.tabela = p.tabela AND c.campo = p.campo "
            "WHERE c.tabela = ? AND p.campo IS NULL ORDER BY c.campo", (tab,)
        ).fetchall()
        adicionados = [{"campo": r[0], "tipo": r[1], "tamanho": r[2], "titulo": r[3] or "", "validacao": r[4] or ""} for r in rows]
    except Exception:
        pass

    # Removidos: no padrao mas nao no cliente
    removidos = []
    try:
        rows = db.execute(
            "SELECT p.campo, p.tipo, p.tamanho, p.titulo, p.validacao "
            "FROM padrao_campos p LEFT JOIN campos c ON p.tabela = c.tabela AND p.campo = c.campo "
            "WHERE p.tabela = ? AND c.campo IS NULL ORDER BY p.campo", (tab,)
        ).fetchall()
        removidos = [{"campo": r[0], "tipo": r[1], "tamanho": r[2], "titulo": r[3] or "", "validacao": r[4] or ""} for r in rows]
    except Exception:
        pass

    # Alterados: existe nos dois mas difere
    alterados = []
    try:
        rows = db.execute(
            "SELECT c.campo, p.tipo, c.tipo, p.tamanho, c.tamanho, p.titulo, c.titulo, p.validacao, c.validacao "
            "FROM campos c INNER JOIN padrao_campos p ON c.tabela = p.tabela AND c.campo = p.campo "
            "WHERE c.tabela = ? AND (c.tipo != p.tipo OR c.tamanho != p.tamanho OR c.validacao != p.validacao) "
            "ORDER BY c.campo", (tab,)
        ).fetchall()
        for r in rows:
            diffs = {}
            if r[1] != r[2]:
                diffs["tipo"] = {"padrao": r[1], "cliente": r[2]}
            if r[3] != r[4]:
                diffs["tamanho"] = {"padrao": str(r[3]), "cliente": str(r[4])}
            if r[7] != r[8]:
                diffs["validacao"] = {"padrao": r[7] or "", "cliente": r[8] or ""}
            if r[5] != r[6]:
                diffs["titulo"] = {"padrao": r[5] or "", "cliente": r[6] or ""}
            if diffs:
                alterados.append({"campo": r[0], "diferencas": diffs})
    except Exception:
        pass

    return jsonify({
        "available": True,
        "tabela": tab,
        "adicionados": adicionados,
        "alterados": alterados,
        "removidos": removidos,
        "resumo": {
            "adicionados": len(adicionados),
            "alterados": len(alterados),
            "removidos": len(removidos)
        }
    })


@workspace_bp.route("/workspaces/<slug>/explorer/search", methods=["GET"])
@require_permission("devworkspace:view")
def explorer_search(slug):
    """Busca global no workspace: tabelas, fontes, menus, campos."""
    db = _get_db(slug)
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify({"results": [], "total": 0})

    q_upper = q.upper()
    q_like = f"%{q_upper}%"
    results = []

    # Search tabelas
    try:
        rows = db.execute(
            "SELECT codigo, nome FROM tabelas WHERE upper(codigo) LIKE ? OR upper(nome) LIKE ? LIMIT 15",
            (q_like, q_like)
        ).fetchall()
        for r in rows:
            results.append({"type": "tabela", "key": r[0], "label": r[0] + " — " + (r[1] or ""), "action": "wsSelectTable", "params": {"codigo": r[0]}})
    except Exception:
        pass

    # Search fontes
    try:
        rows = db.execute(
            "SELECT arquivo, modulo FROM fontes WHERE upper(arquivo) LIKE ? LIMIT 15",
            (q_like,)
        ).fetchall()
        for r in rows:
            results.append({"type": "fonte", "key": r[0], "label": r[0] + " (" + (r[1] or "") + ")", "action": "wsOpenFonte", "params": {"arquivo": r[0]}})
    except Exception:
        pass

    # Search menus
    try:
        rows = db.execute(
            "SELECT rotina, nome FROM menus WHERE upper(rotina) LIKE ? OR upper(nome) LIKE ? LIMIT 10",
            (q_like, q_like)
        ).fetchall()
        for r in rows:
            results.append({"type": "menu", "key": r[0], "label": r[0] + " — " + (r[1] or "")})
    except Exception:
        pass

    # Search campos
    try:
        rows = db.execute(
            "SELECT tabela, campo, titulo FROM campos WHERE upper(campo) LIKE ? LIMIT 10",
            (q_like,)
        ).fetchall()
        for r in rows:
            results.append({"type": "campo", "key": r[0] + "." + r[1], "label": r[1] + " (" + r[0] + ") — " + (r[2] or ""), "action": "wsSelectTable", "params": {"codigo": r[0]}})
    except Exception:
        pass

    return jsonify({"results": results[:30], "total": len(results)})


# ---------------------------------------------------------------------------
#  Explorer — IA Overview, Funcao Resumir/Codigo, Anotacoes
# ---------------------------------------------------------------------------


@workspace_bp.route("/workspaces/<slug>/explorer/fonte/<arquivo>/overview", methods=["POST"])
@require_permission("devworkspace:analyze")
def explorer_fonte_overview(slug, arquivo):
    """Gera overview IA do fonte (resumo do programa)."""
    db = _get_db(slug)
    force = request.args.get("force", "false").lower() == "true"

    row = db.execute(
        "SELECT arquivo, modulo, funcoes, pontos_entrada, tabelas_ref, write_tables, lines_of_code "
        "FROM fontes WHERE arquivo = ?", (arquivo,)
    ).fetchone()
    if not row:
        return jsonify({"error": "Fonte nao encontrado"}), 404

    def _j(v):
        try:
            return json.loads(v) if v else []
        except Exception:
            return []

    # Check cache in funcao_docs
    if not force:
        try:
            cached = db.execute(
                "SELECT resumo FROM funcao_docs WHERE arquivo = ? AND funcao = '__overview__'",
                (arquivo,)
            ).fetchone()
            if cached and cached[0]:
                return jsonify({"arquivo": arquivo, "overview": cached[0], "cached": True})
        except Exception:
            pass

    try:
        llm = _get_llm_provider()
    except Exception as e:
        return jsonify({"error": f"LLM nao disponivel: {str(e)[:200]}"}), 500

    funcoes = _j(row[2])
    pes = _j(row[3])
    tabs_ref = _j(row[4])
    tabs_write = _j(row[5])

    # Buscar operacoes de escrita
    ops = []
    try:
        ops_rows = db.execute(
            "SELECT funcao, tipo, tabela, condicao FROM operacoes_escrita WHERE arquivo = ? LIMIT 30",
            (arquivo,)
        ).fetchall()
        ops = [f"{r[0]}: {r[1]} em {r[2]}" + (f" (cond: {r[3]})" if r[3] else "") for r in ops_rows]
    except Exception:
        pass

    prompt = f"""Analise o fonte Protheus ADVPL/TLPP "{arquivo}" e gere um overview tecnico.

Modulo: {row[1] or 'desconhecido'}
Funcoes: {', '.join(funcoes[:20])}
Pontos de Entrada: {', '.join(pes) if pes else 'Nenhum'}
Tabelas leitura: {', '.join(tabs_ref[:15])}
Tabelas escrita: {', '.join(tabs_write[:10])}
Linhas de codigo: {row[6]}
Operacoes de escrita: {chr(10).join(ops[:15]) if ops else 'Nenhuma detectada'}

Gere um overview TECNICO em markdown com:
## Ecossistema
## Cadeia de Chamadas
## Write Points
## Pontos de Atencao
## Resumo

Baseie-se APENAS nos dados fornecidos. Seja conciso."""

    text = _llm_chat_text(llm, [{"role": "user", "content": prompt}])

    # Cache
    try:
        db.execute(
            "INSERT OR REPLACE INTO funcao_docs (arquivo, funcao, tipo, resumo, fonte) VALUES (?, '__overview__', 'overview', ?, 'auto')",
            (arquivo, text)
        )
        db.commit()
    except Exception:
        pass

    return jsonify({"arquivo": arquivo, "overview": text, "cached": False})


@workspace_bp.route("/workspaces/<slug>/explorer/funcao/<arquivo>/<funcao>/resumir", methods=["POST"])
@require_permission("devworkspace:analyze")
def explorer_funcao_resumir(slug, arquivo, funcao):
    """Gera resumo IA de uma funcao especifica."""
    db = _get_db(slug)

    # Check cache
    try:
        cached = db.execute(
            "SELECT resumo FROM funcao_docs WHERE arquivo = ? AND funcao = ?",
            (arquivo, funcao)
        ).fetchone()
        if cached and cached[0]:
            return jsonify({"arquivo": arquivo, "funcao": funcao, "resumo": cached[0], "cached": True})
    except Exception:
        pass

    # Get function context from chunks
    chunk_content = ""
    try:
        row = db.execute(
            "SELECT content FROM fonte_chunks WHERE arquivo = ? AND funcao = ?",
            (arquivo, funcao)
        ).fetchone()
        if row:
            chunk_content = row[0][:3000]  # Limit to 3000 chars
    except Exception:
        pass

    if not chunk_content:
        return jsonify({"error": "Codigo da funcao nao encontrado nos chunks"}), 404

    try:
        llm = _get_llm_provider()
    except Exception as e:
        return jsonify({"error": f"LLM nao disponivel: {str(e)[:200]}"}), 500

    prompt = f"""Analise a funcao ADVPL/TLPP "{funcao}" do arquivo "{arquivo}" e gere um resumo tecnico.

CODIGO:
{chunk_content}

Retorne um resumo conciso (2-3 frases) explicando:
- O que a funcao faz
- Quais tabelas manipula
- Se tem condicoes especiais ou tratamento de erro
Seja direto e tecnico."""

    text = _llm_chat_text(llm, [{"role": "user", "content": prompt}])

    # Cache
    try:
        db.execute(
            "INSERT OR REPLACE INTO funcao_docs (arquivo, funcao, tipo, resumo, fonte) VALUES (?, ?, 'function', ?, 'auto')",
            (arquivo, funcao, text)
        )
        db.commit()
    except Exception:
        pass

    return jsonify({"arquivo": arquivo, "funcao": funcao, "resumo": text, "cached": False})


@workspace_bp.route("/workspaces/<slug>/explorer/funcao/<arquivo>/<funcao>/codigo", methods=["GET"])
@require_permission("devworkspace:view")
def explorer_funcao_codigo(slug, arquivo, funcao):
    """Retorna codigo fonte de uma funcao (do chunk)."""
    db = _get_db(slug)

    try:
        row = db.execute(
            "SELECT content FROM fonte_chunks WHERE arquivo = ? AND funcao = ?",
            (arquivo, funcao)
        ).fetchone()
        if not row:
            return jsonify({"error": "Chunk nao encontrado"}), 404
        return jsonify({"arquivo": arquivo, "funcao": funcao, "codigo": row[0]})
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500


@workspace_bp.route("/workspaces/<slug>/explorer/anotacoes/<tipo>/<chave>", methods=["GET"])
@require_permission("devworkspace:view")
def explorer_listar_anotacoes(slug, tipo, chave):
    """Lista anotacoes de uma tabela/fonte/campo."""
    db = _get_db(slug)
    try:
        rows = db.execute(
            "SELECT id, texto, autor, tags, data FROM anotacoes WHERE tipo = ? AND chave = ? ORDER BY data DESC",
            (tipo, chave)
        ).fetchall()
        return jsonify([
            {"id": r[0], "texto": r[1], "autor": r[2], "tags": json.loads(r[3]) if r[3] else [], "data": r[4]}
            for r in rows
        ])
    except Exception:
        return jsonify([])


@workspace_bp.route("/workspaces/<slug>/explorer/anotacoes", methods=["POST"])
@require_permission("devworkspace:edit")
def explorer_criar_anotacao(slug):
    """Cria anotacao em tabela/fonte/campo."""
    db = _get_db(slug)
    data = request.get_json()
    tipo = data.get("tipo", "")
    chave = data.get("chave", "")
    texto = data.get("texto", "")
    if not tipo or not chave or not texto:
        return jsonify({"error": "tipo, chave e texto obrigatorios"}), 400

    try:
        db.execute(
            "INSERT INTO anotacoes (tipo, chave, texto, autor, tags) VALUES (?, ?, ?, 'consultor', '[]')",
            (tipo, chave, texto)
        )
        db.commit()
        new_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        return jsonify({"id": new_id, "success": True})
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500


@workspace_bp.route("/workspaces/<slug>/explorer/anotacoes/<int:anotacao_id>", methods=["DELETE"])
@require_permission("devworkspace:delete")
def explorer_deletar_anotacao(slug, anotacao_id):
    """Deleta anotacao."""
    db = _get_db(slug)
    try:
        db.execute("DELETE FROM anotacoes WHERE id = ?", (anotacao_id,))
        db.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500


@workspace_bp.route("/workspaces/<slug>/dashboard", methods=["GET"])
@require_permission("devworkspace:view")
def workspace_dashboard(slug):
    """Retorna dados ricos para dashboard do workspace (similar ao ExtraiRPO)."""
    try:
        db = _get_db(slug)
    except Exception as e:
        logger.error("Erro ao abrir workspace %s: %s", slug, e)
        return jsonify({"error": "Workspace nao encontrado"}), 404

    def _count(query, params=()):
        try:
            row = db.execute(query, params).fetchone()
            return row[0] if row else 0
        except Exception:
            return 0

    # --- RESUMO ---
    # Auto-diff lazy: tentar popular padrao_campos via banco_padrao.db se necessario
    padrao_count = _count("SELECT COUNT(*) FROM padrao_campos")
    if padrao_count == 0:
        _auto_calculate_diff(db)
        padrao_count = _count("SELECT COUNT(*) FROM padrao_campos")

    tabelas_total = _count("SELECT COUNT(*) FROM tabelas")
    tabelas_custom = _count("SELECT COUNT(*) FROM tabelas WHERE custom = 1")
    campos_total = _count("SELECT COUNT(*) FROM campos")
    campos_custom = _count("SELECT COUNT(*) FROM campos WHERE custom = 1")
    # Diff so e confiavel se padrao_campos foi populada
    if padrao_count > 0:
        campos_adicionados = _count("SELECT COUNT(DISTINCT chave) FROM diff WHERE tipo_sx = 'SX3' AND acao = 'adicionado'")
        campos_alterados = _count("SELECT COUNT(DISTINCT chave) FROM diff WHERE tipo_sx = 'SX3' AND acao = 'alterado'")
        diff_removidos = _count("SELECT COUNT(DISTINCT chave) FROM diff WHERE tipo_sx = 'SX3' AND acao = 'removido'")
    else:
        campos_adicionados = campos_custom
        campos_alterados = 0
        diff_removidos = 0
    indices_total = _count("SELECT COUNT(*) FROM indices")
    indices_custom = _count("SELECT COUNT(*) FROM indices WHERE custom = 1")
    gatilhos_total = _count("SELECT COUNT(*) FROM gatilhos")
    gatilhos_custom = _count("SELECT COUNT(*) FROM gatilhos WHERE custom = 1")
    fontes_total = _count("SELECT COUNT(*) FROM fontes")
    vinculos_total = _count("SELECT COUNT(*) FROM vinculos")
    menus_total = _count("SELECT COUNT(*) FROM menus")
    jobs_total = _count("SELECT COUNT(*) FROM jobs")
    schedules_total = _count("SELECT COUNT(*) FROM schedules")
    schedules_ativos = _count("SELECT COUNT(*) FROM schedules WHERE status = 'Ativo'")

    resumo = {
        "tabelas_total": tabelas_total,
        "tabelas_custom": tabelas_custom,
        "campos_total": campos_total,
        "campos_custom": campos_custom,
        "campos_adicionados": campos_adicionados,
        "campos_alterados": campos_alterados,
        "indices_total": indices_total,
        "indices_custom": indices_custom,
        "gatilhos_total": gatilhos_total,
        "gatilhos_custom": gatilhos_custom,
        "fontes_total": fontes_total,
        "vinculos": vinculos_total,
        "menus_total": menus_total,
        "jobs_total": jobs_total,
        "schedules_total": schedules_total,
        "schedules_ativos": schedules_ativos,
        "diff_removidos": diff_removidos,
    }

    # --- DISTRIBUICAO DE RISCO ---
    # Se tabela diff esta vazia, usar campos.custom como fallback
    has_diff = (campos_adicionados + campos_alterados + diff_removidos) > 0
    if has_diff:
        campos_so_padrao = max(0, campos_total - campos_adicionados - campos_alterados)
        distribuicao_risco = {
            "campos_so_padrao": campos_so_padrao,
            "campos_adicionados": campos_adicionados,
            "campos_alterados": campos_alterados,
            "campos_removidos": diff_removidos,
        }
    else:
        # Fallback: usar flag custom dos campos (quando base padrao nao foi ingerida)
        # custom=1 vem do parser: campo com prefixo X_ ou X3_PROPRI != 'S' ou tabela Z/SZ/Q
        # Campos em tabelas custom (Z*, SZ*, Q*) → adicionados (tabela inteira e custom)
        campos_em_tab_custom = _count(
            "SELECT COUNT(*) FROM campos WHERE custom = 1 AND ("
            "  tabela LIKE 'Z%' OR tabela LIKE 'SZ%' OR tabela LIKE 'Q%'"
            ")"
        )
        # Campos custom em tabelas padrao (campo X_ ou proprietario != S) → alterados/adicionados ao padrao
        campos_custom_em_tab_padrao = _count(
            "SELECT COUNT(*) FROM campos WHERE custom = 1 AND NOT ("
            "  tabela LIKE 'Z%' OR tabela LIKE 'SZ%' OR tabela LIKE 'Q%'"
            ")"
        )
        campos_so_padrao = max(0, campos_total - campos_em_tab_custom - campos_custom_em_tab_padrao)
        distribuicao_risco = {
            "campos_so_padrao": campos_so_padrao,
            "campos_adicionados": campos_em_tab_custom,
            "campos_alterados": campos_custom_em_tab_padrao,
            "campos_removidos": 0,
        }

    # --- TOP TABELAS (mais customizadas) ---
    top_tabelas = []
    try:
        rows = db.execute("""
            SELECT c.tabela,
                   COALESCE(t.nome, '') AS nome,
                   SUM(CASE WHEN c.custom = 1 THEN 1 ELSE 0 END) AS campos_add
            FROM campos c
            LEFT JOIN tabelas t ON t.codigo = c.tabela
            GROUP BY c.tabela
            HAVING campos_add > 0
            ORDER BY campos_add DESC
        """).fetchall()

        # Complementar com dados de diff (alterados por tabela)
        diff_alt_map = {}
        try:
            diff_rows = db.execute("""
                SELECT tabela, COUNT(DISTINCT chave) AS cnt
                FROM diff
                WHERE tipo_sx = 'SX3' AND acao = 'alterado'
                GROUP BY tabela
            """).fetchall()
            diff_alt_map = {r[0]: r[1] for r in diff_rows}
        except Exception:
            pass

        for r in rows:
            tabela, nome, campos_add = r[0], r[1], r[2]
            campos_alt = diff_alt_map.get(tabela, 0)
            score = campos_add * 2 + campos_alt
            top_tabelas.append({
                "tabela": tabela,
                "nome": nome,
                "campos_add": campos_add,
                "campos_alt": campos_alt,
                "score": score,
            })

        top_tabelas.sort(key=lambda x: x["score"], reverse=True)
        top_tabelas = top_tabelas[:10]
    except Exception as e:
        logger.warning("Erro ao calcular top_tabelas: %s", e)

    # --- TOP INTERACAO (tabelas mais referenciadas em fontes) ---
    top_interacao = []
    try:
        fontes_rows = db.execute(
            "SELECT arquivo, tabelas_ref, write_tables FROM fontes"
        ).fetchall()

        leitura_map = {}
        escrita_map = {}
        for row in fontes_rows:
            # tabelas_ref - leitura
            try:
                refs = json.loads(row[1]) if row[1] else []
                for tab in refs:
                    if isinstance(tab, str) and tab.strip():
                        leitura_map[tab.strip().upper()] = leitura_map.get(tab.strip().upper(), 0) + 1
            except (json.JSONDecodeError, TypeError):
                pass
            # write_tables - escrita
            try:
                writes = json.loads(row[2]) if row[2] else []
                for tab in writes:
                    if isinstance(tab, str) and tab.strip():
                        escrita_map[tab.strip().upper()] = escrita_map.get(tab.strip().upper(), 0) + 1
            except (json.JSONDecodeError, TypeError):
                pass

        all_tabs = set(leitura_map.keys()) | set(escrita_map.keys())
        interacao_list = []
        for tab in all_tabs:
            leit = leitura_map.get(tab, 0)
            escr = escrita_map.get(tab, 0)
            interacao_list.append({
                "tabela": tab,
                "leitura": leit,
                "escrita": escr,
                "total": leit + escr,
            })
        interacao_list = [x for x in interacao_list if x["total"] >= 5]
        interacao_list.sort(key=lambda x: x["total"], reverse=True)
        top_interacao = interacao_list[:10]
        # Enriquecer com nome da tabela
        for item in top_interacao:
            try:
                row = db.execute("SELECT nome FROM tabelas WHERE upper(codigo) = ?", (item["tabela"],)).fetchone()
                item["nome"] = row[0] if row else ""
            except Exception:
                item["nome"] = ""
    except Exception as e:
        logger.warning("Erro ao calcular top_interacao: %s", e)

    # --- MODULOS ---
    modulos = []
    try:
        mod_rows = db.execute("""
            SELECT modulo, COUNT(*) AS fontes_count
            FROM fontes
            WHERE modulo IS NOT NULL AND modulo != ''
            GROUP BY modulo
            ORDER BY fontes_count DESC
        """).fetchall()

        # Buscar contagem de tabelas do mapa_modulos
        mapa_tab_map = {}
        try:
            mapa_rows = db.execute("SELECT modulo, tabelas FROM mapa_modulos").fetchall()
            for mr in mapa_rows:
                try:
                    tabs = json.loads(mr[1]) if mr[1] else []
                    mapa_tab_map[mr[0].lower()] = len(tabs)
                except (json.JSONDecodeError, TypeError):
                    mapa_tab_map[mr[0].lower()] = 0
        except Exception:
            pass

        for mr in mod_rows:
            mod_name = mr[0]
            modulos.append({
                "modulo": mod_name.capitalize(),
                "fontes": mr[1],
                "tabelas": mapa_tab_map.get(mod_name.lower(), 0),
                "menus": 0,  # populated below
            })

        # Enriquecer modulos com contagem de menus
        try:
            menu_rows = db.execute("SELECT modulo, COUNT(*) FROM menus WHERE modulo IS NOT NULL GROUP BY modulo").fetchall()
            for mr in menu_rows:
                mod_normalized = _normalize_menu_module(mr[0])
                for m in modulos:
                    if m["modulo"].lower() == mod_normalized:
                        m["menus"] += mr[1]
                        break
        except Exception:
            pass
    except Exception as e:
        logger.warning("Erro ao calcular modulos: %s", e)

    # --- TOP FONTES (maiores por LOC) ---
    top_fontes = []
    try:
        rows = db.execute(
            "SELECT arquivo, funcoes, lines_of_code, modulo FROM fontes "
            "WHERE lines_of_code > 0 ORDER BY lines_of_code DESC LIMIT 10"
        ).fetchall()
        for r in rows:
            funcs = json.loads(r[1]) if r[1] else []
            top_fontes.append({"arquivo": r[0], "funcoes": len(funcs), "loc": r[2], "modulo": (r[3] or "").capitalize()})
    except Exception:
        pass

    return jsonify({
        "resumo": resumo,
        "distribuicao_risco": distribuicao_risco,
        "top_tabelas": top_tabelas,
        "top_interacao": top_interacao,
        "top_fontes": top_fontes,
        "modulos": modulos,
    })


# ========================================================================
# CONTEXTO PARA AGENTE IA
# ========================================================================

@workspace_bp.route("/workspaces/<slug>/context/module/<modulo>", methods=["GET"])
@require_permission("devworkspace:view")
def context_module(slug, modulo):
    """Gera contexto estruturado (markdown) de um modulo para o agente IA."""
    db = _get_db(slug)
    ks = KnowledgeService(db)
    context = ks.build_context_for_module(modulo)
    return jsonify({"modulo": modulo, "context": context, "chars": len(context)})


@workspace_bp.route("/workspaces/<slug>/context/table/<tabela>", methods=["GET"])
@require_permission("devworkspace:view")
def context_table(slug, tabela):
    """Gera analise profunda de uma tabela para o agente IA."""
    db = _get_db(slug)
    ks = KnowledgeService(db)
    analysis = ks.build_deep_field_analysis(tabela.upper())
    if not analysis:
        return jsonify({"error": "Tabela nao encontrada"}), 404
    return jsonify({"tabela": tabela.upper(), "analysis": analysis, "chars": len(analysis)})


# ========================================================================
# DOCUMENTACAO IA
# ========================================================================

@workspace_bp.route("/workspaces/<slug>/docs/modules", methods=["GET"])
@require_permission("devworkspace:view")
def docs_modules(slug):
    """Lista modulos disponiveis para geracao de docs."""
    db = _get_db(slug)
    from app.services.workspace.doc_pipeline import DocPipeline
    pipeline = DocPipeline(db)
    return jsonify(pipeline.get_available_modules())


@workspace_bp.route("/workspaces/<slug>/docs/generate/<modulo>", methods=["POST"])
@require_permission("devworkspace:analyze")
def docs_generate(slug, modulo):
    """Gera documentacao para um modulo (sem LLM = apenas contexto)."""
    db = _get_db(slug)
    from app.services.workspace.doc_pipeline import DocPipeline
    pipeline = DocPipeline(db, llm_provider=None)  # TODO: injetar LLM provider

    try:
        result = pipeline.generate_for_module(modulo)
        return jsonify({
            "success": True,
            "modulo": modulo,
            "context_chars": result.get("context_chars"),
            "elapsed_seconds": result.get("elapsed_seconds"),
            "has_llm": False,
        })
    except Exception as e:
        logger.exception(f"Erro ao gerar docs: {e}")
        return jsonify({"error": str(e)}), 500


# ========================================================================
# EXPORT
# ========================================================================

@workspace_bp.route("/workspaces/<slug>/export/campos", methods=["GET"])
@require_permission("devworkspace:export")
def export_campos(slug):
    """Exporta campos customizados em CSV."""
    db = _get_db(slug)
    from app.services.workspace.exporter import WorkspaceExporter
    exporter = WorkspaceExporter(db)
    tabela = request.args.get("tabela")
    csv_data = exporter.export_campos_custom_csv(tabela)
    return csv_data, 200, {"Content-Type": "text/csv; charset=utf-8",
                           "Content-Disposition": "attachment; filename=campos_custom.csv"}


@workspace_bp.route("/workspaces/<slug>/export/indices", methods=["GET"])
@require_permission("devworkspace:export")
def export_indices(slug):
    """Exporta indices customizados em CSV."""
    db = _get_db(slug)
    from app.services.workspace.exporter import WorkspaceExporter
    exporter = WorkspaceExporter(db)
    tabela = request.args.get("tabela")
    csv_data = exporter.export_indices_custom_csv(tabela)
    return csv_data, 200, {"Content-Type": "text/csv; charset=utf-8",
                           "Content-Disposition": "attachment; filename=indices_custom.csv"}


@workspace_bp.route("/workspaces/<slug>/export/gatilhos", methods=["GET"])
@require_permission("devworkspace:export")
def export_gatilhos(slug):
    """Exporta gatilhos customizados em CSV."""
    db = _get_db(slug)
    from app.services.workspace.exporter import WorkspaceExporter
    exporter = WorkspaceExporter(db)
    csv_data = exporter.export_gatilhos_custom_csv()
    return csv_data, 200, {"Content-Type": "text/csv; charset=utf-8",
                           "Content-Disposition": "attachment; filename=gatilhos_custom.csv"}


@workspace_bp.route("/workspaces/<slug>/export/atudic", methods=["GET"])
@require_permission("devworkspace:export")
def export_atudic(slug):
    """Exporta em formato AtuDic JSON."""
    db = _get_db(slug)
    from app.services.workspace.exporter import WorkspaceExporter
    exporter = WorkspaceExporter(db)
    tabela = request.args.get("tabela")
    data = exporter.export_atudic_json(tabela)
    return jsonify(data)


@workspace_bp.route("/workspaces/<slug>/export/diff", methods=["GET"])
@require_permission("devworkspace:export")
def export_diff(slug):
    """Exporta diff padrao x cliente em CSV."""
    db = _get_db(slug)
    from app.services.workspace.exporter import WorkspaceExporter
    exporter = WorkspaceExporter(db)
    tipo_sx = request.args.get("tipo_sx")
    csv_data = exporter.export_diff_csv(tipo_sx)
    return csv_data, 200, {"Content-Type": "text/csv; charset=utf-8",
                           "Content-Disposition": "attachment; filename=diff.csv"}


# ========================================================================
# PROCESSOS DO CLIENTE — Detecçao, analise, chat e registro
# ========================================================================

@workspace_bp.route("/workspaces/<slug>/build-vinculos", methods=["POST"])
@require_permission("devworkspace:analyze")
def rebuild_vinculos(slug):
    """Reconstroi grafo de vinculos do workspace (11 tipos de relacionamento)."""
    ws_path = _get_workspace_path(slug)
    db_path = ws_path / "workspace.db"
    if not db_path.exists():
        return jsonify({"error": "Workspace nao encontrado"}), 404

    try:
        from app.services.workspace.build_vinculos import build_vinculos
        build_vinculos(db_path)
        # Contar vinculos criados
        db = _get_db(slug)
        count = db.execute("SELECT COUNT(*) FROM vinculos").fetchone()[0]
        tipos = db.execute("SELECT tipo, COUNT(*) FROM vinculos GROUP BY tipo ORDER BY COUNT(*) DESC").fetchall()
        return jsonify({
            "success": True,
            "total": count,
            "por_tipo": {r[0]: r[1] for r in tipos}
        })
    except Exception as e:
        logger.exception(f"Erro ao construir vinculos: {e}")
        return jsonify({"error": str(e)[:300]}), 500


@workspace_bp.route("/workspaces/<slug>/processos/descobrir", methods=["POST"])
@require_permission("devworkspace:analyze")
def descobrir_processos_endpoint(slug):
    """Roda pipeline de descoberta automatica de processos (5 passos SQL + LLM)."""
    data = request.get_json() or {}
    force = data.get("force", False)

    db = _get_db(slug)

    try:
        llm = _get_llm_provider()
    except Exception as e:
        return jsonify({"error": f"LLM nao disponivel: {str(e)[:200]}"}), 500

    try:
        from app.services.workspace.descoberta_processos import descobrir_processos
        processos = descobrir_processos(db, llm, force=force)
        return jsonify({"total": len(processos), "processos": processos})
    except Exception as e:
        logger.exception(f"Erro na descoberta de processos: {e}")
        return jsonify({"error": str(e)[:300]}), 500


@workspace_bp.route("/workspaces/<slug>/processos", methods=["GET"])
@require_permission("devworkspace:view")
def listar_processos(slug):
    """Lista processos de negocio detectados no workspace."""
    db = _get_db(slug)
    try:
        rows = db.execute(
            "SELECT id, nome, tipo, descricao, criticidade, tabelas, score, "
            "fluxo_mermaid, validado, created_at, updated_at "
            "FROM processos_detectados ORDER BY score DESC"
        ).fetchall()
    except Exception:
        return jsonify([])

    tabela_filter = request.args.get("tabela", "").upper()
    tipo_filter = request.args.get("tipo", "")

    processos = []
    for r in rows:
        tabs = json.loads(r[5]) if r[5] else []
        if tabela_filter and tabela_filter not in [t.upper() for t in tabs]:
            continue
        if tipo_filter and r[2] != tipo_filter:
            continue
        processos.append({
            "id": r[0], "nome": r[1], "tipo": r[2], "descricao": r[3],
            "criticidade": r[4], "tabelas": tabs, "score": r[6],
            "fluxo_mermaid": r[7], "validado": bool(r[8]),
            "created_at": r[9], "updated_at": r[10],
        })
    return jsonify(processos)


@workspace_bp.route("/workspaces/<slug>/processos/<int:processo_id>/fluxo", methods=["POST"])
@require_permission("devworkspace:analyze")
def gerar_fluxo_processo(slug, processo_id):
    """Gera (ou retorna cache) diagrama Mermaid de um processo via LLM."""
    db = _get_db(slug)
    force = request.args.get("force", "false").lower() == "true"

    row = db.execute(
        "SELECT id, nome, tipo, descricao, criticidade, tabelas, score, fluxo_mermaid "
        "FROM processos_detectados WHERE id = ?",
        (processo_id,),
    ).fetchone()

    if not row:
        return jsonify({"error": "Processo nao encontrado"}), 404

    # Cache hit
    if row[7] and not force:
        return jsonify({"fluxo_mermaid": row[7]})

    # Gather write operations for real flow data
    ks = KnowledgeService(db)
    flow_context_parts = []
    tabelas_list = json.loads(row[5]) if row[5] else []
    for tab in tabelas_list[:5]:
        ops = db.execute(
            "SELECT DISTINCT arquivo, funcao, tipo FROM operacoes_escrita WHERE upper(tabela) = ?",
            (tab.upper(),)
        ).fetchall()
        if ops:
            flow_context_parts.append(f"Tabela {tab}: " + ", ".join(
                [f"{o[0]}:{o[1]}({o[2]})" for o in ops[:10]]
            ))
    flow_context = "\n".join(flow_context_parts)

    # Gerar via LLM
    try:
        llm = _get_llm_provider()
    except Exception as e:
        return jsonify({"error": f"LLM nao disponivel: {str(e)[:200]}"}), 500

    prompt = (
        f'Gere um diagrama Mermaid `flowchart TD` para o processo "{row[1]}" do tipo "{row[2]}".\n'
        f"Descricao: {row[3]}\n"
        f"Tabelas envolvidas: {row[5]}\n"
        f"Criticidade: {row[4]}\n"
        + (f"Operacoes de escrita reais:\n{flow_context}\n" if flow_context else "")
        + "Represente as etapas principais do processo de forma clara. "
        + "Retorne APENAS o codigo Mermaid, sem explicacoes."
    )

    try:
        text = _llm_chat_text(llm, [{"role": "user", "content": prompt}])

        match = re.search(r"```(?:mermaid)?\s*([\s\S]*?)```", text)
        if match:
            mermaid_str = match.group(1).strip()
        elif text.strip().startswith(("flowchart", "graph")):
            mermaid_str = text.strip()
        else:
            return jsonify({"error": "Resposta do LLM nao e um diagrama Mermaid valido"}), 500

        db.execute(
            "UPDATE processos_detectados SET fluxo_mermaid = ? WHERE id = ?",
            (mermaid_str, processo_id),
        )
        db.commit()
        return jsonify({"fluxo_mermaid": mermaid_str})
    except Exception as e:
        logger.exception(f"Erro ao gerar fluxo: {e}")
        return jsonify({"error": str(e)[:300]}), 500


@workspace_bp.route("/workspaces/<slug>/processos/<int:processo_id>/analise", methods=["GET"])
@require_permission("devworkspace:view")
def get_analise_processo(slug, processo_id):
    """Gera (ou retorna cache) analise tecnica de um processo via investigacao + LLM."""
    db = _get_db(slug)
    force = request.args.get("force", "false").lower() == "true"

    row = db.execute(
        "SELECT id, nome, tipo, descricao, criticidade, tabelas, score, "
        "analise_markdown, analise_json, analise_updated_at "
        "FROM processos_detectados WHERE id = ?",
        (processo_id,),
    ).fetchone()

    if not row:
        return jsonify({"error": "Processo nao encontrado"}), 404

    # Cache hit
    if row[7] and not force and row[9] != 'generating':
        return jsonify({
            "analise_markdown": row[7],
            "analise_json": json.loads(row[8]) if row[8] else {},
            "analise_updated_at": row[9],
        })

    # Concurrency guard
    if row[9] == 'generating' and not force:
        return jsonify({"error": "Analise em geracao por outra requisicao"}), 409

    # Mark as generating
    db.execute(
        "UPDATE processos_detectados SET analise_updated_at = 'generating' WHERE id = ?",
        (processo_id,),
    )
    db.commit()

    try:
        tabelas = json.loads(row[5]) if row[5] else []
        nome = row[1]
        tipo = row[2]
        descricao = row[3]

        # Fase 1: Investigar usando knowledge service
        ks = KnowledgeService(db)
        tool_results_parts = []

        for tab in tabelas[:8]:
            try:
                info = ks.get_table_info(tab)
                if info:
                    tool_results_parts.append(f"### Tabela {tab}\n{json.dumps(info, ensure_ascii=False, indent=2)}")
            except Exception:
                pass

            # Operacoes de escrita por tabela
            try:
                ops_rows = db.execute(
                    "SELECT arquivo, funcao, tipo, campos, condicao, linha "
                    "FROM operacoes_escrita WHERE upper(tabela) = ?", (tab.upper(),)
                ).fetchall()
                if ops_rows:
                    ops_details = [{"arquivo": r[0], "funcao": r[1], "tipo": r[2], "campos": r[3], "condicao": r[4], "linha": r[5]} for r in ops_rows]
                    tool_results_parts.append(
                        f"### Operacoes {tab}\nTotal: {len(ops_rows)} operacoes\n{json.dumps(ops_details, ensure_ascii=False)}"
                    )
            except Exception:
                pass

            # Fontes que escrevem na tabela
            try:
                fontes_rows = db.execute(
                    "SELECT arquivo, modulo, lines_of_code FROM fontes WHERE write_tables LIKE ?",
                    (f'%"{tab}"%',)
                ).fetchall()
                if fontes_rows:
                    fontes_list = [{"arquivo": r[0], "modulo": r[1], "loc": r[2]} for r in fontes_rows]
                    tool_results_parts.append(f"### Fontes escrita {tab}\n{json.dumps(fontes_list, ensure_ascii=False)}")
            except Exception:
                pass

        # Parametros relacionados (SX6)
        try:
            for tab in tabelas[:4]:
                param_rows = db.execute(
                    "SELECT variavel, tipo, descricao, conteudo FROM parametros "
                    "WHERE upper(descricao) LIKE ? OR upper(variavel) LIKE ? LIMIT 10",
                    (f'%{tab}%', f'%{tab}%')
                ).fetchall()
                if param_rows:
                    params_list = [{"variavel": r[0], "tipo": r[1], "descricao": r[2], "conteudo": r[3]} for r in param_rows]
                    tool_results_parts.append(f"### Parametros {tab}\n{json.dumps(params_list, ensure_ascii=False)}")
        except Exception:
            pass

        tool_results_text = "\n\n".join(tool_results_parts) or "Nenhum dado de investigacao encontrado."

        # Fase 2: LLM gera markdown + JSON
        try:
            llm = _get_llm_provider()
        except Exception as e:
            db.execute(
                "UPDATE processos_detectados SET analise_updated_at = NULL WHERE id = ?",
                (processo_id,),
            )
            db.commit()
            return jsonify({"error": f"LLM nao disponivel: {str(e)[:200]}"}), 500

        prompt = f"""Analise o processo "{nome}" (tipo: {tipo}, criticidade: {row[4]}).
Descricao: {descricao}
Tabelas envolvidas: {', '.join(tabelas)}

DADOS DE INVESTIGACAO:
{tool_results_text}

Gere DUAS saidas:

1. ANALISE EM MARKDOWN — relatorio tecnico completo com secoes:
## Write Points
## Triggers e Gatilhos
## Entry Points (PEs)
## Parametros Relacionados
## Fontes Envolvidas
## Condicoes Criticas
## Resumo do Processo

2. JSON ESTRUTURADO — no formato abaixo (dentro de um bloco ```json):
```json
{{
  "tabelas": [
    {{
      "codigo": "XXX",
      "write_points": [
        {{ "fonte": "ARQUIVO.PRW", "funcao": "Funcao", "campos": ["CAMPO1"], "condicao": "cond" }}
      ],
      "triggers": [
        {{ "campo": "CAMPO", "gatilho": "U_FUNC", "tipo": "change" }}
      ],
      "operacoes": [
        {{ "tipo": "reclock", "funcao": "Funcao", "modo": "inclusao" }}
      ]
    }}
  ],
  "entry_points": [
    {{ "pe": "NOME_PE", "fonte": "ARQUIVO.PRW", "descricao": "desc" }}
  ],
  "parametros": [
    {{ "nome": "MV_XXXX", "conteudo": "valor", "descricao": "desc" }}
  ],
  "fontes_envolvidas": ["ARQUIVO1.PRW", "ARQUIVO2.PRW"],
  "condicoes_criticas": [
    {{ "condicao": "expr", "impacto": "desc", "fonte": "ARQUIVO.PRW" }}
  ]
}}
```

Retorne PRIMEIRO o markdown completo, depois o bloco JSON.
Baseie-se APENAS nos dados de investigacao fornecidos. Nao invente dados."""

        text = _llm_chat_text(llm, [{"role": "user", "content": prompt}])

        # Fase 3: Parse response
        json_match = re.search(r"```json\s*([\s\S]*?)```", text)
        analise_json_str = "{}"
        if json_match:
            try:
                analise_json_obj = json.loads(json_match.group(1).strip())
                analise_json_str = json.dumps(analise_json_obj, ensure_ascii=False)
            except json.JSONDecodeError:
                analise_json_str = "{}"

        # Extrair apenas o markdown — cortar antes do JSON estruturado
        # Estrategia: encontrar onde comeca o JSON e pegar so o que vem antes
        analise_md = text
        # 1. Cortar no bloco ```json (fechado ou nao)
        json_start = re.search(r"```json", analise_md)
        if json_start:
            analise_md = analise_md[:json_start.start()]
        # 2. Cortar em "JSON ESTRUTURADO" ou "**JSON Estruturado**" (qualquer variacao)
        json_header = re.search(r"(?:^|\n)\s*[-#*]*\s*JSON\s+ESTRUTURADO", analise_md, re.IGNORECASE)
        if json_header:
            analise_md = analise_md[:json_header.start()]
        # 3. Remover separadores finais (---)
        analise_md = re.sub(r"\n---\s*$", "", analise_md).strip()

        # Fase 4: Salvar
        from datetime import datetime
        now = datetime.utcnow().isoformat()
        db.execute(
            "UPDATE processos_detectados SET analise_markdown=?, analise_json=?, analise_updated_at=? WHERE id=?",
            (analise_md, analise_json_str, now, processo_id),
        )
        db.commit()

        return jsonify({
            "analise_markdown": analise_md,
            "analise_json": json.loads(analise_json_str),
            "analise_updated_at": now,
        })

    except Exception as e:
        db.execute(
            "UPDATE processos_detectados SET analise_updated_at = NULL WHERE id = ? AND analise_updated_at = 'generating'",
            (processo_id,),
        )
        db.commit()
        logger.exception(f"Erro ao gerar analise: {e}")
        return jsonify({"error": str(e)[:300]}), 500


@workspace_bp.route("/workspaces/<slug>/processos/<int:processo_id>/chat", methods=["POST"])
@require_permission("devworkspace:chat")
def chat_processo(slug, processo_id):
    """SSE streaming chat escopado a um processo — usa modo duvida com contexto do processo."""
    db = _get_db(slug)

    row = db.execute(
        "SELECT id, nome, tipo, descricao, tabelas, analise_json "
        "FROM processos_detectados WHERE id = ?",
        (processo_id,),
    ).fetchone()
    if not row:
        return jsonify({"error": "Processo nao encontrado"}), 404

    data = request.get_json()
    message = data.get("message", "")
    if not message:
        return jsonify({"error": "Mensagem vazia"}), 400

    proc_nome = row[1]
    proc_tabelas = json.loads(row[4]) if row[4] else []
    analise_json = row[5] or "{}"

    # Salvar mensagem do usuario
    db.execute(
        "INSERT INTO processo_mensagens (processo_id, role, content) VALUES (?, 'user', ?)",
        (processo_id, message),
    )
    db.commit()

    # Carregar historico (ultimas 30)
    hist_rows = db.execute(
        "SELECT role, content FROM processo_mensagens WHERE processo_id = ? ORDER BY id DESC LIMIT 30",
        (processo_id,),
    ).fetchall()
    hist_rows = list(reversed(hist_rows))

    def generate():
        yield f"data: {json.dumps({'event': 'status', 'step': 'Investigando contexto do processo...'}, ensure_ascii=False)}\n\n"

        # Fase 1: Contexto do processo
        ks = KnowledgeService(db)
        tool_results_parts = []
        for tab in proc_tabelas[:5]:
            try:
                info = ks.get_table_info(tab)
                if info:
                    tool_results_parts.append(f"Info {tab}: {json.dumps(info, ensure_ascii=False)}")
            except Exception:
                pass

        # Operacoes de escrita
        for tab in proc_tabelas[:5]:
            try:
                ops_rows = db.execute(
                    "SELECT arquivo, funcao, tipo, campos, condicao FROM operacoes_escrita WHERE upper(tabela) = ? LIMIT 20",
                    (tab.upper(),)
                ).fetchall()
                if ops_rows:
                    ops_list = [{"arquivo": r[0], "funcao": r[1], "tipo": r[2], "campos": r[3], "condicao": r[4]} for r in ops_rows]
                    tool_results_parts.append(f"Operacoes escrita {tab}: {json.dumps(ops_list, ensure_ascii=False)}")
            except Exception:
                pass

        tool_results_text = "\n".join(tool_results_parts)

        context = f"""PROCESSO: {proc_nome}
Tabelas: {', '.join(proc_tabelas)}
Analise tecnica existente (JSON): {analise_json}
"""

        system_prompt = (
            "Voce e um consultor tecnico senior de ambientes TOTVS Protheus.\n"
            "Use APENAS os dados do CONTEXTO abaixo. Nao invente dados.\n"
            "Responda com informacoes CONCRETAS.\n\n"
            f"CONTEXTO DO AMBIENTE:\n{context}\n\n"
            f"DADOS DE INVESTIGACAO:\n{tool_results_text}\n"
        )

        non_system_msgs = []
        for h_role, h_content in hist_rows:
            non_system_msgs.append({"role": h_role, "content": h_content})

        # Prefixar system no primeiro user msg (Anthropic nao aceita role system)
        if non_system_msgs:
            for i, m in enumerate(non_system_msgs):
                if m["role"] == "user":
                    non_system_msgs[i] = {
                        "role": "user",
                        "content": f"[CONTEXTO]\n{system_prompt}\n\n[PERGUNTA]\n{m['content']}"
                    }
                    break
            messages = non_system_msgs
        else:
            messages = [{"role": "user", "content": system_prompt}]

        # Fase 2: Stream LLM
        yield f"data: {json.dumps({'event': 'status', 'step': 'Gerando resposta...'}, ensure_ascii=False)}\n\n"

        full_text = ""
        try:
            llm = _get_llm_provider()

            if hasattr(llm, 'chat_stream'):
                for chunk_data in llm.chat_stream(messages):
                    chunk_text = chunk_data.get("chunk", "") if isinstance(chunk_data, dict) else str(chunk_data)
                    if chunk_text:
                        full_text += chunk_text
                        yield f"data: {json.dumps({'event': 'content', 'text': chunk_text}, ensure_ascii=False)}\n\n"
            else:
                full_text = _llm_chat_text(llm, messages)
                yield f"data: {json.dumps({'event': 'content', 'text': full_text}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'event': 'error', 'error': str(e)[:300]}, ensure_ascii=False)}\n\n"
            return

        # Fase 3: Salvar resposta do assistente
        try:
            db2 = _get_db(slug)
            db2.execute(
                "INSERT INTO processo_mensagens (processo_id, role, content) VALUES (?, 'assistant', ?)",
                (processo_id, full_text),
            )
            db2.commit()

            # Fase 4: Enriquecimento heuristico (max 3 complementos)
            existing_analysis = json.loads(analise_json) if analise_json and analise_json != "{}" else None
            if existing_analysis and any(kw in full_text.lower() for kw in ["reclock", "gatilho", "trigger", "ponto de entrada", "pe_", "u_"]):
                existing_md = db2.execute(
                    "SELECT analise_markdown FROM processos_detectados WHERE id = ?",
                    (processo_id,),
                ).fetchone()
                enrichment_count = (existing_md[0] or "").count("## Complemento via Chat") if existing_md else 0
                if enrichment_count < 3:
                    db2.execute(
                        """UPDATE processos_detectados
                        SET analise_markdown = COALESCE(analise_markdown, '') || char(10) || char(10) || '## Complemento via Chat' || char(10) || ?,
                            analise_updated_at = datetime('now')
                        WHERE id = ?""",
                        (full_text[:2000], processo_id),
                    )
                    db2.commit()
            db2.close()
        except Exception as e:
            logger.warning("Erro ao salvar resposta do chat de processo: %s", e)

        yield f"data: {json.dumps({'event': 'done', 'status': 'ok'}, ensure_ascii=False)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )


@workspace_bp.route("/workspaces/<slug>/processos/<int:processo_id>/mensagens", methods=["GET"])
@require_permission("devworkspace:view")
def listar_mensagens_processo(slug, processo_id):
    """Lista mensagens de chat de um processo."""
    db = _get_db(slug)
    limit = request.args.get("limit", 30, type=int)
    offset = request.args.get("offset", 0, type=int)

    try:
        total = db.execute(
            "SELECT COUNT(*) FROM processo_mensagens WHERE processo_id = ?",
            (processo_id,),
        ).fetchone()[0]
        rows = db.execute(
            "SELECT id, role, content, created_at FROM processo_mensagens "
            "WHERE processo_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
            (processo_id, limit, offset),
        ).fetchall()
        mensagens = [
            {"id": r[0], "role": r[1], "content": r[2], "created_at": r[3]}
            for r in reversed(rows)
        ]
        return jsonify({"total": total, "mensagens": mensagens})
    except Exception:
        return jsonify({"total": 0, "mensagens": []})


@workspace_bp.route("/workspaces/<slug>/processos/registrar", methods=["POST"])
@require_permission("devworkspace:edit")
def registrar_processo(slug):
    """Registra ou enriquece um processo a partir de descricao livre (usa LLM para classificar)."""
    data = request.get_json()
    descricao = data.get("descricao", "")
    if not descricao:
        return jsonify({"error": "Descricao vazia"}), 400

    # Fase 1: Extrair info via LLM
    try:
        llm = _get_llm_provider()
    except Exception as e:
        return jsonify({"error": f"LLM nao disponivel: {str(e)[:200]}"}), 500

    extract_prompt = f"""Extraia as informacoes de processo de negocio do texto abaixo.
Retorne APENAS um JSON:
{{"nome": "Nome do Processo", "tipo": "workflow|integracao|logistica|fiscal|automacao|qualidade|outro", "descricao": "descricao limpa", "tabelas": ["TAB1", "TAB2"], "criticidade": "alta|media|baixa"}}

Texto: {descricao}"""

    try:
        text = _llm_chat_text(llm, [{"role": "user", "content": extract_prompt}])
        json_match = re.search(r'\{[\s\S]*\}', text)
        if not json_match:
            return jsonify({"error": "LLM nao retornou JSON valido"}), 500
        extracted = json.loads(json_match.group())
    except Exception as e:
        return jsonify({"error": f"Erro ao classificar processo: {str(e)[:200]}"}), 500

    # Fase 2: Registrar via handler do agent_tools
    from app.services.workspace.agent_tools import _handle_registrar_processo
    result = _handle_registrar_processo({
        "workspace_slug": slug,
        "nome": extracted.get("nome", descricao[:80]),
        "tipo": extracted.get("tipo", "outro"),
        "descricao": extracted.get("descricao", descricao),
        "tabelas": ",".join(extracted.get("tabelas", [])),
        "criticidade": extracted.get("criticidade", "media"),
    })

    if result.get("success"):
        return jsonify(result["data"])
    return jsonify({"error": result.get("error", "Erro desconhecido")}), 500


# ========================================================================
# ANALISTA — Perguntas sobre o workspace com contexto IA
# ========================================================================

@workspace_bp.route("/workspaces/<slug>/analista/ask", methods=["POST"])
@require_permission("devworkspace:chat")
def analista_ask(slug):
    """Envia pergunta ao analista do workspace."""
    data = request.get_json()
    question = (data or {}).get("question", "").strip()
    if not question:
        return jsonify({"error": "Pergunta vazia"}), 400

    db = _get_db(slug)
    ks = KnowledgeService(db)

    # Construir contexto do workspace
    try:
        summary = ks.get_custom_summary()
    except Exception:
        summary = {}

    # Buscar modulos disponiveis
    modulos_list = []
    try:
        rows = db.execute(
            "SELECT DISTINCT modulo FROM fontes WHERE modulo IS NOT NULL AND modulo != '' ORDER BY modulo"
        ).fetchall()
        modulos_list = [r[0] for r in rows]
    except Exception:
        pass

    # Buscar tabelas mencionadas na pergunta para contexto extra
    sources = []
    q_upper = question.upper()
    try:
        tab_rows = db.execute(
            "SELECT codigo, nome FROM tabelas WHERE upper(codigo) LIKE ? OR upper(nome) LIKE ? LIMIT 5",
            (f"%{q_upper[:20]}%", f"%{q_upper[:30]}%")
        ).fetchall()
        for r in tab_rows:
            info = ks.get_table_info(r[0])
            if info:
                sources.append({"tipo": "tabela", "codigo": r[0], "nome": r[1]})
    except Exception:
        pass

    # Montar prompt com contexto
    context_parts = [f"Resumo do workspace: {json.dumps(summary, ensure_ascii=False)}"]
    if modulos_list:
        context_parts.append(f"Modulos disponiveis: {', '.join(modulos_list)}")
    if sources:
        context_parts.append(f"Tabelas relacionadas: {json.dumps(sources, ensure_ascii=False)}")

    context_text = "\n".join(context_parts)

    system_prompt = (
        "Voce e um analista tecnico senior de ambientes TOTVS Protheus.\n"
        "Use APENAS os dados do CONTEXTO abaixo e o historico de conversa. Nao invente dados.\n"
        "Responda de forma tecnica e concisa em portugues.\n\n"
        f"CONTEXTO DO WORKSPACE:\n{context_text}\n"
    )

    # Carregar historico recente para continuidade da conversa
    history = []
    try:
        hist_rows = db.execute(
            "SELECT role, content FROM chat_history ORDER BY id DESC LIMIT 10"
        ).fetchall()
        history = [{"role": r[0], "content": r[1]} for r in reversed(hist_rows)]
    except Exception:
        pass

    try:
        llm = _get_llm_provider()
    except Exception as e:
        return jsonify({"error": f"LLM nao disponivel: {str(e)[:200]}"}), 500

    messages = [{"role": "system", "content": system_prompt}]
    for h in history[-8:]:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": question})

    answer = _llm_chat_text(llm, messages)

    # Salvar no historico (chat_history do workspace SQLite)
    try:
        db.execute(
            "INSERT INTO chat_history (role, content, sources) VALUES ('user', ?, NULL)",
            (question,)
        )
        db.execute(
            "INSERT INTO chat_history (role, content, sources) VALUES ('assistant', ?, ?)",
            (answer, json.dumps(sources, ensure_ascii=False))
        )
        db.commit()
    except Exception as e:
        logger.warning("Erro ao salvar historico do analista: %s", e)

    return jsonify({
        "answer": answer,
        "sources": sources,
        "modulos": modulos_list,
    })


@workspace_bp.route("/workspaces/<slug>/analista/history", methods=["GET"])
@require_permission("devworkspace:view")
def analista_history(slug):
    """Historico de perguntas do analista."""
    db = _get_db(slug)
    limit = request.args.get("limit", 50, type=int)

    try:
        rows = db.execute(
            "SELECT id, role, content, sources, created_at "
            "FROM chat_history ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        items = [
            {
                "id": r[0],
                "role": r[1],
                "content": r[2],
                "sources": json.loads(r[3]) if r[3] else [],
                "created_at": r[4],
            }
            for r in reversed(rows)
        ]
        return jsonify(items)
    except Exception:
        return jsonify([])


# ========================================================================
# BASE PADRAO — Modulos, PEs e TDN da base padrao
# ========================================================================

# Diretorio da base padrao (relativo a raiz da aplicacao)
_PADRAO_DIR = Path("processoPadrao")


@workspace_bp.route("/workspaces/<slug>/padrao/modulos", methods=["GET"])
@require_permission("devworkspace:view")
def padrao_modulos(slug):
    """Lista modulos da base padrao."""
    # Validar que o workspace existe
    ws_path = _get_workspace_path(slug)
    if not (ws_path / "workspace.db").exists():
        return jsonify({"error": "Workspace nao encontrado"}), 404

    if not _PADRAO_DIR.exists():
        return jsonify([])

    modulos = []
    for f in sorted(_PADRAO_DIR.iterdir()):
        if f.is_file() and f.suffix.lower() == ".md":
            modulo_name = f.stem
            modulos.append({
                "modulo": modulo_name,
                "nome": modulo_name.replace("_", " ").capitalize(),
                "arquivo": f.name,
            })
    return jsonify(modulos)


@workspace_bp.route("/workspaces/<slug>/padrao/modulos/<modulo>", methods=["GET"])
@require_permission("devworkspace:view")
def padrao_modulo_detail(slug, modulo):
    """Conteudo de um modulo padrao."""
    ws_path = _get_workspace_path(slug)
    if not (ws_path / "workspace.db").exists():
        return jsonify({"error": "Workspace nao encontrado"}), 404

    # Buscar arquivo .md do modulo
    md_file = _PADRAO_DIR / f"{modulo}.md"
    if not md_file.exists():
        # Tentar case-insensitive
        found = None
        if _PADRAO_DIR.exists():
            for f in _PADRAO_DIR.iterdir():
                if f.stem.lower() == modulo.lower() and f.suffix.lower() == ".md":
                    found = f
                    break
        if not found:
            return jsonify({"error": f"Modulo padrao '{modulo}' nao encontrado"}), 404
        md_file = found

    try:
        conteudo = md_file.read_text(encoding="utf-8")
    except Exception as e:
        return jsonify({"error": f"Erro ao ler arquivo: {str(e)[:200]}"}), 500

    return jsonify({"modulo": modulo, "conteudo": conteudo})


@workspace_bp.route("/workspaces/<slug>/padrao/pes", methods=["GET"])
@require_permission("devworkspace:view")
def padrao_pes(slug):
    """Lista pontos de entrada da base padrao.

    Fontes de dados (em ordem de prioridade):
    1. Tabela padrao_pes no workspace (se populada)
    2. padrao.db (fontes padrao) — extrai User Functions com pattern de PE
    """
    db = _get_db(slug)

    # 1. Tentar tabela padrao_pes local
    try:
        rows = db.execute(
            "SELECT nome, rotina, modulo, objetivo FROM padrao_pes ORDER BY nome"
        ).fetchall()
        if rows:
            return jsonify([
                {"nome": r[0], "rotina": r[1], "modulo": r[2], "objetivo": r[3] or ""}
                for r in rows
            ])
    except Exception:
        pass

    # 2. Fallback: extrair PEs do padrao.db (fontes padrao)
    from app.services.workspace.workspace_populator import _get_fontes_padrao_db_path
    padrao_db_path = _get_fontes_padrao_db_path()
    if not padrao_db_path.exists():
        return jsonify([])

    import sqlite3 as _sqlite3
    try:
        pconn = _sqlite3.connect(str(padrao_db_path))
        # User Functions com pattern de Ponto de Entrada Protheus
        pe_rows = pconn.execute("""
            SELECT f.nome, f.arquivo, COALESCE(fo.modulo, '') AS modulo
            FROM funcoes f
            JOIN fontes fo ON f.arquivo = fo.arquivo
            WHERE f.tipo = 'user_function'
              AND (
                f.nome GLOB '[A-Z][A-Z][0-9][0-9][0-9][A-Z]*'
                OR f.nome GLOB 'MT[A0-9][0-9][0-9][0-9][A-Z]*'
                OR f.nome GLOB 'MTA[0-9][0-9][0-9][A-Z]*'
                OR f.nome GLOB '[A-Z][0-9][0-9][0-9][A-Z][A-Z]*'
                OR f.nome GLOB '[A-Z][A-Z][A-Z][A-Z][0-9][0-9][0-9][A-Z]*'
              )
            ORDER BY f.nome
        """).fetchall()
        pconn.close()

        return jsonify([
            {"nome": r[0], "rotina": r[1].replace(".prw", "").replace(".PRW", ""), "modulo": r[2], "objetivo": ""}
            for r in pe_rows
        ])
    except Exception as e:
        logger.warning("Erro ao extrair PEs do padrao.db: %s", e)
        return jsonify([])


@workspace_bp.route("/workspaces/<slug>/padrao/tdn", methods=["GET"])
@require_permission("devworkspace:view")
def padrao_tdn(slug):
    """Referencia TDN."""
    ws_path = _get_workspace_path(slug)
    if not (ws_path / "workspace.db").exists():
        return jsonify({"error": "Workspace nao encontrado"}), 404

    tdn_dir = _PADRAO_DIR / "TDN"
    if not tdn_dir.exists():
        return jsonify({"tree": [], "message": "Diretorio TDN nao encontrado"})

    # Montar arvore de arquivos JSON/MD no diretorio TDN
    tree = []
    try:
        for f in sorted(tdn_dir.iterdir()):
            if f.is_file() and f.suffix.lower() in (".json", ".md", ".yml", ".yaml"):
                node = {"nome": f.stem, "arquivo": f.name, "tipo": f.suffix.lstrip(".")}
                # Se JSON, tentar carregar estrutura
                if f.suffix.lower() == ".json":
                    try:
                        data = json.loads(f.read_text(encoding="utf-8"))
                        if isinstance(data, dict):
                            node["keys"] = list(data.keys())[:20]
                        elif isinstance(data, list):
                            node["total_items"] = len(data)
                    except Exception:
                        pass
                tree.append(node)
            elif f.is_dir():
                children = []
                for child in sorted(f.iterdir()):
                    if child.is_file():
                        children.append({"nome": child.stem, "arquivo": child.name, "tipo": child.suffix.lstrip(".")})
                tree.append({"nome": f.name, "tipo": "dir", "children": children[:50]})
    except Exception as e:
        logger.warning("Erro ao listar TDN: %s", e)

    return jsonify({"tree": tree})


# ========================================================================
# GERAR DOCS — Busca, resumo e geracao de documentacao IA
# ========================================================================

@workspace_bp.route("/workspaces/<slug>/docs/search", methods=["GET"])
@require_permission("devworkspace:view")
def docs_search(slug):
    """Busca tabelas e fontes para geracao de docs."""
    db = _get_db(slug)
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify({"tabelas": [], "fontes": []})

    q_like = f"%{q.upper()}%"

    # Buscar tabelas
    tabelas = []
    try:
        rows = db.execute(
            "SELECT codigo, nome, custom FROM tabelas "
            "WHERE upper(codigo) LIKE ? OR upper(nome) LIKE ? LIMIT 20",
            (q_like, q_like)
        ).fetchall()
        tabelas = [{"codigo": r[0], "nome": r[1] or "", "custom": bool(r[2])} for r in rows]
    except Exception:
        pass

    # Buscar fontes
    fontes = []
    try:
        rows = db.execute(
            "SELECT arquivo, modulo, lines_of_code FROM fontes "
            "WHERE upper(arquivo) LIKE ? LIMIT 20",
            (q_like,)
        ).fetchall()
        fontes = [{"arquivo": r[0], "modulo": r[1] or "", "loc": r[2] or 0} for r in rows]
    except Exception:
        pass

    return jsonify({"tabelas": tabelas, "fontes": fontes})


@workspace_bp.route("/workspaces/<slug>/docs/summary", methods=["GET"])
@require_permission("devworkspace:view")
def docs_summary(slug):
    """Resumo de dados do workspace para geracao de docs."""
    db = _get_db(slug)

    def _c(q):
        try:
            return db.execute(q).fetchone()[0]
        except Exception:
            return 0

    return jsonify({
        "tabelas": _c("SELECT COUNT(*) FROM tabelas"),
        "campos_custom": _c("SELECT COUNT(*) FROM campos WHERE custom = 1"),
        "gatilhos": _c("SELECT COUNT(*) FROM gatilhos"),
        "fontes": _c("SELECT COUNT(*) FROM fontes"),
    })


@workspace_bp.route("/workspaces/<slug>/docs/generate", methods=["POST"])
@require_permission("devworkspace:analyze")
def docs_generate_v2(slug):
    """Gera documentacao IA para um modulo."""
    data = request.get_json()
    modulo = (data or {}).get("modulo", "").strip()
    if not modulo:
        return jsonify({"error": "Parametro 'modulo' obrigatorio"}), 400

    db = _get_db(slug)

    # Tentar usar DocPipelineV3 (com LLM) se disponivel, senao fallback para DocPipeline
    try:
        llm = _get_llm_provider()
    except Exception as e:
        return jsonify({"error": f"LLM nao disponivel: {str(e)[:200]}"}), 500

    try:
        from app.services.workspace.doc_pipeline_v3 import DocPipelineV3
        pipeline = DocPipelineV3(db, llm)
        # DocPipelineV3.generate_module_doc e async — executar em loop
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(pipeline.generate_module_doc(modulo))
        finally:
            loop.close()
        return jsonify({
            "success": True,
            "modulo": modulo,
            "conteudo_humano": result.get("markdown", ""),
            "conteudo_ia": result.get("sections", {}),
            "slug": slug,
        })
    except ImportError:
        pass
    except Exception as e:
        logger.warning("DocPipelineV3 falhou, tentando DocPipeline: %s", e)

    # Fallback: DocPipeline (sem LLM completo)
    try:
        from app.services.workspace.doc_pipeline import DocPipeline
        pipeline = DocPipeline(db, llm_provider=llm)
        result = pipeline.generate_for_module(modulo)
        return jsonify({
            "success": True,
            "modulo": modulo,
            "conteudo_humano": result.get("context", ""),
            "conteudo_ia": result,
            "slug": slug,
        })
    except Exception as e:
        logger.exception("Erro ao gerar docs para modulo %s: %s", modulo, e)
        return jsonify({"error": str(e)[:300]}), 500


# ========================================================================
# CHAT — Chat focado no workspace
# ========================================================================

# ========================================================================
# Endpoints migrados do ExtraiRPO — helpers e rotas adicionais
# ========================================================================

# --- Helpers auxiliares (migrados) ---

def _table_exists(db, table_name: str) -> bool:
    """Verifica se tabela existe no SQLite."""
    row = db.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row[0] > 0


def _safe_json(val):
    """Parse JSON string, retornando [] em caso de falha."""
    if not val:
        return []
    if isinstance(val, list):
        return val
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return []


def _load_diff_counts(db) -> dict:
    """Carrega contagens de diff por tabela."""
    result = {}
    try:
        rows = db.execute(
            "SELECT tabela, acao, COUNT(DISTINCT chave) FROM diff "
            "WHERE tipo_sx IN ('campo','SX3') GROUP BY tabela, acao"
        ).fetchall()
        for r in rows:
            tab = r[0]
            if tab not in result:
                result[tab] = {"adicionados": 0, "alterados": 0}
            if r[1] == "adicionado":
                result[tab]["adicionados"] = r[2]
            elif r[1] == "alterado":
                result[tab]["alterados"] = r[2]
    except Exception:
        pass
    return result


def _load_anotacoes(db, tipo: str, chave: str) -> list:
    """Carrega anotacoes de um item."""
    try:
        if not _table_exists(db, "anotacoes"):
            return []
        rows = db.execute(
            "SELECT id, texto, autor, tags, data FROM anotacoes WHERE tipo=? AND chave=? ORDER BY data DESC",
            (tipo, chave),
        ).fetchall()
        return [
            {"id": r[0], "texto": r[1] or "", "autor": r[2] or "consultor",
             "tags": _safe_json(r[3]), "data": r[4] or ""}
            for r in rows
        ]
    except Exception:
        return []


def _load_menus_lookup(db) -> dict:
    """Carrega lookup de menus por rotina."""
    lookup = {}
    try:
        if _table_exists(db, "menus"):
            for r in db.execute("SELECT rotina, nome, menu FROM menus").fetchall():
                lookup[(r[0] or "").upper()] = {"nome": r[1] or "", "menu_path": r[2] or ""}
    except Exception:
        pass
    return lookup


def _load_mapa_modulos() -> dict:
    """Carrega mapa-modulos.json."""
    mapa_path = Path("templates/processos/mapa-modulos.json")
    if not mapa_path.exists():
        return {}
    try:
        return json.loads(mapa_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _pe_to_rotina(pe_name: str) -> str:
    """Tenta derivar rotina padrao a partir do nome do PE."""
    clean = pe_name.upper().replace("_PE", "")
    m = re.match(r'^MT(\d{3})', clean)
    if m:
        return f"MATA{m.group(1)}"
    m = re.match(r'^A(\d{3})', clean)
    if m:
        return f"MATA{m.group(1)}"
    m = re.match(r'^FA(\d{3})', clean)
    if m:
        return f"FATA{m.group(1)}"
    return ""


_MODULO_NORMALIZE_MAP = {
    "compras": "SIGACOM", "faturamento": "SIGAFAT", "financeiro": "SIGAFIN",
    "estoque": "SIGAEST", "fiscal": "SIGAFIS", "contabilidade": "SIGACTB",
    "sigacom": "SIGACOM", "sigafat": "SIGAFAT", "sigafin": "SIGAFIN",
    "sigaest": "SIGAEST", "sigafis": "SIGAFIS", "sigactb": "SIGACTB",
}


def _normalize_modulo_ext(mod: str) -> str:
    """Normaliza nome de modulo: 'compras' -> 'SIGACOM'."""
    if not mod:
        return ""
    low = mod.strip().lower()
    if low in _MODULO_NORMALIZE_MAP:
        return _MODULO_NORMALIZE_MAP[low]
    if " - " in low:
        base = low.split(" - ")[0].strip()
        if base in _MODULO_NORMALIZE_MAP:
            return _MODULO_NORMALIZE_MAP[base]
        return base.upper()
    return mod.upper()


_INTEGRATION_PATTERNS = re.compile(r'(WSS|INT|WS[^A-Z]|API|REST)', re.IGNORECASE)
_ALTERACAO_LABELS = {
    "obrigatorio": "Tornar obrigatorio", "validacao": "Alterar validacao",
    "tamanho": "Alterar tamanho", "tipo": "Alterar tipo",
    "novo_campo": "Novo campo", "excluir_campo": "Excluir campo",
}
_RISK_ORDER = {"alto": 0, "medio": 1, "baixo": 2, "info": 3}


# ========================================================================
# ENRIQUECER — Enrichment com LLM para tabela/fonte
# ========================================================================

@workspace_bp.route("/workspaces/<slug>/explorer/enriquecer", methods=["POST"])
@require_permission("devworkspace:analyze")
def explorer_enriquecer(slug):
    """Enriquece tabela ou fonte com LLM (proposito, tags, classificacao)."""
    data = request.get_json()
    tipo = data.get("tipo")
    chave = data.get("chave")
    pergunta = data.get("pergunta", "")

    if tipo not in ("tabela", "fonte"):
        return jsonify({"error": "tipo deve ser 'tabela' ou 'fonte'"}), 400
    if not chave:
        return jsonify({"error": "chave e obrigatoria"}), 400

    db = _get_db(slug)
    try:
        context = ""
        if tipo == "tabela":
            row = db.execute("SELECT codigo, nome FROM tabelas WHERE upper(codigo)=?", (chave.upper(),)).fetchone()
            if not row:
                return jsonify({"error": f"Tabela '{chave}' nao encontrada"}), 404
            campos_rows = db.execute(
                "SELECT campo, tipo, tamanho, titulo, custom FROM campos WHERE upper(tabela)=? LIMIT 50",
                (chave.upper(),),
            ).fetchall()
            campos_desc = "\n".join(
                f"  {c[0]} ({c[1]}/{c[2]}) - {c[3]} {'[CUSTOM]' if c[4] else ''}"
                for c in campos_rows
            )
            context = f"Tabela: {row[0]} - {row[1]}\nCampos:\n{campos_desc}"
        else:
            row = db.execute(
                "SELECT arquivo, modulo, funcoes, pontos_entrada, tabelas_ref, lines_of_code FROM fontes WHERE arquivo=?",
                (chave,),
            ).fetchone()
            if not row:
                return jsonify({"error": f"Fonte '{chave}' nao encontrado"}), 404
            context = (
                f"Fonte: {row[0]}\nModulo: {row[1]}\nFuncoes: {row[2]}\n"
                f"Pontos Entrada: {row[3]}\nTabelas Ref: {row[4]}\nLOC: {row[5]}"
            )

        prompt = f"Analise o seguinte artefato Protheus.\n{context}\n"
        if pergunta:
            prompt += f"\nContexto adicional do usuario: {pergunta}\n"
        prompt += (
            '\nResponda APENAS com JSON: {"humano": "descricao", "ia": {"processo": "...", "modulo": "...", '
            '"tipo_programa": "...", "complexidade": "alta|media|baixa"}, "tags": ["..."]}'
        )

        try:
            llm = _get_llm_provider()
        except Exception as e:
            return jsonify({"error": f"LLM nao disponivel: {str(e)[:200]}"}), 500

        result_text = _llm_chat_text(llm, [{"role": "user", "content": prompt}])
        result_text = result_text.strip()
        if result_text.startswith("```"):
            result_text = result_text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        try:
            parsed = json.loads(result_text)
        except (json.JSONDecodeError, TypeError):
            m = re.search(r'\{[\s\S]+\}', result_text)
            parsed = json.loads(m.group()) if m else {"humano": result_text[:300], "ia": {}, "tags": []}

        db.execute(
            "INSERT OR REPLACE INTO propositos (tipo, chave, proposito, tags) VALUES (?, ?, ?, ?)",
            (tipo, chave, json.dumps(parsed, ensure_ascii=False), json.dumps(parsed.get("tags", []))),
        )
        db.commit()
        return jsonify({"status": "ok", "chave": chave, "tipo": tipo, "proposito": parsed.get("humano", ""), **parsed})
    except Exception as e:
        logger.exception(f"Erro ao enriquecer {tipo}/{chave}: {e}")
        return jsonify({"error": str(e)[:300]}), 500
    finally:
        db.close()


# ========================================================================
# CATALOGAR PES — Auto-catalogo de PEs com LLM
# ========================================================================

@workspace_bp.route("/workspaces/<slug>/explorer/catalogar-pes", methods=["POST"])
@require_permission("devworkspace:analyze")
def explorer_catalogar_pes(slug):
    """Auto-cataloga PEs do cliente nao catalogados usando LLM."""
    db = _get_db(slug)
    try:
        if not _table_exists(db, "padrao_pes"):
            db.execute("""CREATE TABLE IF NOT EXISTS padrao_pes (
                nome TEXT PRIMARY KEY, modulo TEXT, rotina TEXT, onde_chamado TEXT,
                objetivo TEXT, params_entrada TEXT, params_saida TEXT, link_tdn TEXT)""")
            db.commit()

        all_client_pes = set()
        for row in db.execute("SELECT pontos_entrada FROM fontes WHERE pontos_entrada != '[]'").fetchall():
            for pe in _safe_json(row[0]):
                all_client_pes.add(pe.strip())

        already = {row[0].upper() for row in db.execute("SELECT nome FROM padrao_pes").fetchall()} if _table_exists(db, "padrao_pes") else set()
        uncataloged = [pe for pe in sorted(all_client_pes) if pe.upper() not in already]

        if not uncataloged:
            return jsonify({"status": "ok", "message": "Todos os PEs ja estao catalogados", "total": 0, "catalogados": 0})

        try:
            llm = _get_llm_provider()
        except Exception as e:
            return jsonify({"error": f"LLM nao disponivel: {str(e)[:200]}"}), 500

        BATCH_SIZE, total_cataloged, total_errors = 20, 0, 0
        for i in range(0, len(uncataloged), BATCH_SIZE):
            batch = uncataloged[i:i + BATCH_SIZE]
            pe_context_lines = []
            for pe in batch:
                fonte_row = db.execute("SELECT arquivo, modulo, tabelas_ref FROM fontes WHERE pontos_entrada LIKE ?", (f'%"{pe}"%',)).fetchone()
                ctx = f"- {pe}"
                if fonte_row:
                    ctx += f" (fonte: {fonte_row[0]}, modulo: {fonte_row[1]}, tabelas: {(fonte_row[2] or '')[:80]})"
                pe_context_lines.append(ctx)

            prompt = (
                "Voce e um especialista TOTVS Protheus. Para cada PE, identifique modulo, rotina, onde chamado, objetivo.\n"
                "Se NAO souber, escreva 'Desconhecido'.\n\nPEs:\n" + "\n".join(pe_context_lines) + "\n\n"
                'JSON array: [{"nome":"...","modulo":"...","rotina":"...","onde_chamado":"...","objetivo":"..."}]'
            )
            try:
                result_text = _llm_chat_text(llm, [{"role": "user", "content": prompt}])
                arr = None
                try:
                    arr = json.loads(result_text)
                except json.JSONDecodeError:
                    m = re.search(r'\[[\s\S]*\]', result_text)
                    if m:
                        arr = json.loads(m.group())
                if arr and isinstance(arr, list):
                    for item in arr:
                        nome = item.get("nome", "").strip()
                        objetivo = item.get("objetivo", "").strip()
                        if not nome or "desconhecido" in objetivo.lower():
                            continue
                        db.execute(
                            "INSERT OR REPLACE INTO padrao_pes (nome, modulo, rotina, onde_chamado, objetivo, params_entrada, params_saida, link_tdn) "
                            "VALUES (?, ?, ?, ?, ?, '', '', '')",
                            (nome, item.get("modulo", ""), item.get("rotina", ""), item.get("onde_chamado", ""), objetivo),
                        )
                        total_cataloged += 1
                    db.commit()
            except Exception:
                total_errors += 1

        return jsonify({"status": "ok", "total_uncataloged": len(uncataloged), "catalogados": total_cataloged, "errors": total_errors})
    except Exception as e:
        return jsonify({"error": str(e)[:300]}), 500
    finally:
        db.close()


# ========================================================================
# FUNCAO DETAIL + FUNCOES POR ARQUIVO
# ========================================================================

@workspace_bp.route("/workspaces/<slug>/explorer/funcao/<arquivo>/<funcao>", methods=["GET"])
@require_permission("devworkspace:view")
def explorer_funcao_detail(slug, arquivo, funcao):
    """Retorna detalhe de funcao com docs e codigo do chunk."""
    db = _get_db(slug)
    try:
        if not _table_exists(db, "funcao_docs"):
            return jsonify({"error": "Tabela funcao_docs nao encontrada"}), 404
        row = db.execute(
            "SELECT arquivo, funcao, tipo, assinatura, resumo, tabelas_ref, campos_ref, "
            "chama, chamada_por, retorno, fonte, updated_at "
            "FROM funcao_docs WHERE arquivo = ? AND funcao = ?", (arquivo, funcao),
        ).fetchone()
        if not row:
            return jsonify({"error": f"Funcao {funcao} nao encontrada em {arquivo}"}), 404
        codigo = ""
        try:
            chunk_row = db.execute("SELECT content FROM fonte_chunks WHERE arquivo = ? AND funcao = ?", (arquivo, funcao)).fetchone()
            if chunk_row:
                codigo = chunk_row[0]
        except Exception:
            pass
        return jsonify({
            "arquivo": row[0], "funcao": row[1], "tipo": row[2] or "",
            "assinatura": row[3] or "", "resumo": row[4] or "",
            "tabelas_ref": _safe_json(row[5]), "campos_ref": _safe_json(row[6]),
            "chama": _safe_json(row[7]), "chamada_por": _safe_json(row[8]),
            "retorno": row[9] or "", "fonte": row[10] or "auto",
            "updated_at": row[11] or "", "codigo": codigo,
        })
    except Exception as e:
        return jsonify({"error": str(e)[:300]}), 500
    finally:
        db.close()


@workspace_bp.route("/workspaces/<slug>/explorer/funcoes/<arquivo>", methods=["GET"])
@require_permission("devworkspace:view")
def explorer_funcoes_by_file(slug, arquivo):
    """Retorna todas as funcoes de um arquivo com suas docs."""
    db = _get_db(slug)
    try:
        if not _table_exists(db, "funcao_docs"):
            return jsonify({"arquivo": arquivo, "funcoes": []})
        rows = db.execute(
            "SELECT funcao, tipo, assinatura, resumo, tabelas_ref, campos_ref, chama, chamada_por, retorno, fonte, updated_at "
            "FROM funcao_docs WHERE arquivo = ? ORDER BY rowid", (arquivo,),
        ).fetchall()
        funcoes = [{
            "funcao": r[0], "tipo": r[1] or "", "assinatura": r[2] or "", "resumo": r[3] or "",
            "tabelas_ref": _safe_json(r[4]), "campos_ref": _safe_json(r[5]),
            "chama": _safe_json(r[6]), "chamada_por": _safe_json(r[7]),
            "retorno": r[8] or "", "fonte": r[9] or "auto", "updated_at": r[10] or "",
        } for r in rows]
        return jsonify({"arquivo": arquivo, "funcoes": funcoes})
    except Exception as e:
        return jsonify({"error": str(e)[:300]}), 500
    finally:
        db.close()


# ========================================================================
# ANALISE DE IMPACTO
# ========================================================================

@workspace_bp.route("/workspaces/<slug>/explorer/analise-impacto", methods=["POST"])
@require_permission("devworkspace:analyze")
def explorer_analise_impacto(slug):
    """Analisa impacto de alteracao em campo de tabela."""
    data = request.get_json()
    tabela = (data.get("tabela") or "").upper()
    campo = (data.get("campo") or "").upper()
    alteracao = data.get("alteracao", "obrigatorio")
    if not tabela or not campo:
        return jsonify({"error": "tabela e campo sao obrigatorios"}), 400

    db = _get_db(slug)
    try:
        campo_row = db.execute(
            "SELECT campo, tipo, tamanho, titulo, validacao, f3, vlduser "
            "FROM campos WHERE upper(tabela)=? AND upper(campo)=?", (tabela, campo),
        ).fetchone()
        if not campo_row:
            return jsonify({"error": f"Campo '{campo}' nao encontrado na tabela '{tabela}'"}), 404

        validacao_atual = campo_row[4] or ""
        campo_info = {
            "tipo": campo_row[1] or "", "tamanho": campo_row[2] or 0,
            "titulo": campo_row[3] or "", "validacao_atual": validacao_atual,
            "obrigatorio_atual": bool("vazio" in validacao_atual.lower() or "naovazio" in validacao_atual.lower().replace(" ", "")),
            "f3": campo_row[5] or "", "vlduser": campo_row[6] or "",
        }

        fontes_write, fontes_read = {}, {}
        for fr in db.execute(
            "SELECT arquivo, modulo, funcoes, write_tables, tabelas_ref, fields_ref, lines_of_code "
            "FROM fontes WHERE write_tables IS NOT NULL AND write_tables != '' AND write_tables != '[]'"
        ).fetchall():
            writes = [w.upper() for w in _safe_json(fr[3])]
            if tabela in writes:
                fontes_write[fr[0]] = {"arquivo": fr[0], "modulo": fr[1] or "", "funcoes": len(_safe_json(fr[2])),
                    "fields_ref": [f.upper() for f in _safe_json(fr[5])], "loc": fr[6] or 0}

        for fr in db.execute(
            "SELECT arquivo, modulo, funcoes, write_tables, tabelas_ref, fields_ref, lines_of_code "
            "FROM fontes WHERE tabelas_ref IS NOT NULL AND tabelas_ref != '' AND tabelas_ref != '[]'"
        ).fetchall():
            if fr[0] in fontes_write:
                continue
            refs = [t.upper() for t in _safe_json(fr[4])]
            if tabela in refs and tabela not in [w.upper() for w in _safe_json(fr[3])]:
                fontes_read[fr[0]] = {"arquivo": fr[0], "modulo": fr[1] or "", "funcoes": len(_safe_json(fr[2])),
                    "fields_ref": [f.upper() for f in _safe_json(fr[5])], "loc": fr[6] or 0}

        integration_fontes = set()
        if _table_exists(db, "fonte_chunks"):
            for arq in fontes_write:
                if db.execute("SELECT 1 FROM fonte_chunks WHERE arquivo=? AND lower(content) LIKE '%msexecauto%' LIMIT 1", (arq,)).fetchone():
                    integration_fontes.add(arq)
        for arq in fontes_write:
            if _INTEGRATION_PATTERNS.search(arq.replace(".prw", "").replace(".prx", "")):
                integration_fontes.add(arq)

        propositos_lookup = {}
        if _table_exists(db, "propositos"):
            propositos_lookup = {pr[0]: pr[1] or "" for pr in db.execute("SELECT chave, proposito FROM propositos").fetchall()}

        fontes_impactados = []
        for arq, finfo in fontes_write.items():
            ref_campo = campo in finfo["fields_ref"]
            eh_int = arq in integration_fontes
            if eh_int and (ref_campo or alteracao in ("obrigatorio", "novo_campo", "excluir_campo")):
                risco, motivo = "alto", f"Integracao que grava {tabela}" + (" e referencia " + campo if ref_campo else "")
            elif ref_campo:
                risco, motivo = "medio", f"Grava {tabela} e referencia {campo}"
            else:
                risco, motivo = "baixo", f"Grava {tabela} mas nao referencia {campo}"
            fontes_impactados.append({"arquivo": arq, "risco": risco, "motivo": motivo, "modo": "escrita",
                "referencia_campo": ref_campo, "eh_integracao": eh_int, "proposito": propositos_lookup.get(arq, ""),
                "funcoes": finfo["funcoes"], "loc": finfo["loc"]})

        for arq, finfo in fontes_read.items():
            ref_campo = campo in finfo["fields_ref"]
            fontes_impactados.append({"arquivo": arq, "risco": "info",
                "motivo": f"Le {tabela}" + (f" e referencia {campo}" if ref_campo else ""),
                "modo": "leitura", "referencia_campo": ref_campo, "eh_integracao": False,
                "proposito": propositos_lookup.get(arq, ""), "funcoes": finfo["funcoes"], "loc": finfo["loc"]})

        fontes_impactados.sort(key=lambda f: (_RISK_ORDER.get(f["risco"], 9), f["arquivo"]))

        gatilhos = [{"campo_origem": g[0] or "", "campo_destino": g[1] or "", "regra": g[2] or "",
            "condicao": g[3] or "", "tipo": g[4] or "", "sequencia": g[5] or ""}
            for g in db.execute("SELECT campo_origem, campo_destino, regra, condicao, tipo, sequencia FROM gatilhos WHERE upper(campo_origem)=? OR upper(campo_destino)=?", (campo, campo)).fetchall()]

        f_alto = sum(1 for f in fontes_impactados if f["risco"] == "alto")
        f_medio = sum(1 for f in fontes_impactados if f["risco"] == "medio")
        risco_geral = "alto" if f_alto > 0 else ("medio" if f_medio > 3 or len(fontes_write) > 10 else "baixo")

        return jsonify({
            "tabela": tabela, "campo": campo, "alteracao": alteracao,
            "alteracao_label": _ALTERACAO_LABELS.get(alteracao, alteracao),
            "campo_info": campo_info, "risco_geral": risco_geral,
            "resumo": f"{len(fontes_write)} fontes gravam {tabela}, {f_alto} integracoes em risco",
            "fontes_impactados": fontes_impactados, "gatilhos_relacionados": gatilhos,
            "estatisticas": {"total_fontes_escrita": len(fontes_write), "total_fontes_leitura": len(fontes_read),
                "fontes_risco_alto": f_alto, "fontes_risco_medio": f_medio, "gatilhos_campo": len(gatilhos)},
        })
    except Exception as e:
        logger.exception(f"Erro na analise de impacto: {e}")
        return jsonify({"error": str(e)[:300]}), 500
    finally:
        db.close()


# ========================================================================
# EXPORTAR — Markdown report para tabela/fonte
# ========================================================================

@workspace_bp.route("/workspaces/<slug>/explorer/exportar", methods=["POST"])
@require_permission("devworkspace:export")
def explorer_exportar(slug):
    """Gera documento markdown estruturado para tabela ou fonte."""
    data = request.get_json()
    tipo, chave = data.get("tipo"), data.get("chave")
    if tipo not in ("tabela", "fonte"):
        return jsonify({"error": "tipo deve ser 'tabela' ou 'fonte'"}), 400
    if not chave:
        return jsonify({"error": "chave e obrigatoria"}), 400

    db = _get_db(slug)
    try:
        if tipo == "tabela":
            codigo = chave.upper()
            row = db.execute("SELECT codigo, nome FROM tabelas WHERE upper(codigo)=?", (codigo,)).fetchone()
            if not row:
                return jsonify({"error": f"Tabela '{chave}' nao encontrada"}), 404
            dc = _load_diff_counts(db).get(codigo, {"adicionados": 0, "alterados": 0})
            campos = db.execute("SELECT campo, tipo, tamanho, titulo, custom FROM campos WHERE upper(tabela)=? ORDER BY campo", (codigo,)).fetchall()

            md = f"# {row[0]} — {row[1] or ''}\n\n## Resumo\n\n"
            md += f"Campos adicionados: {dc['adicionados']}, alterados: {dc['alterados']}, total: {len(campos)}\n\n"
            custom = [c for c in campos if c[4]]
            if custom:
                md += f"## Campos Custom ({len(custom)})\n\n| Campo | Tipo | Tam | Titulo |\n|---|---|---|---|\n"
                for c in custom:
                    md += f"| {c[0]} | {c[1] or ''} | {c[2] or ''} | {c[3] or ''} |\n"
            return jsonify({"markdown": md, "filename": f"{codigo}_report.md"})
        else:
            row = db.execute("SELECT arquivo, modulo, funcoes, pontos_entrada, tabelas_ref, write_tables, lines_of_code FROM fontes WHERE arquivo=?", (chave,)).fetchone()
            if not row:
                return jsonify({"error": f"Fonte '{chave}' nao encontrado"}), 404
            md = f"# {row[0]} — {row[1] or ''}\n\n## Info\n\nLOC: {row[6] or 0}\nFuncoes: {row[2]}\nPEs: {row[3]}\nTabelas: {row[4]}\n"
            return jsonify({"markdown": md, "filename": f"{chave.replace('.prw','')}_report.md"})
    except Exception as e:
        return jsonify({"error": str(e)[:300]}), 500
    finally:
        db.close()


# ========================================================================
# PADRAO CRUZAMENTO
# ========================================================================

@workspace_bp.route("/workspaces/<slug>/explorer/padrao-cruzamento/<tipo>/<chave>", methods=["GET"])
@require_permission("devworkspace:view")
def explorer_padrao_cruzamento(slug, tipo, chave):
    """Referencia cruzada com dados padrao Protheus."""
    if tipo not in ("tabela", "fonte"):
        return jsonify({"error": "tipo deve ser 'tabela' ou 'fonte'"}), 400
    db = _get_db(slug)
    try:
        if tipo == "tabela":
            codigo = chave.upper()
            nome_padrao, existe = "", False
            if _table_exists(db, "padrao_tabelas"):
                pt = db.execute("SELECT nome FROM padrao_tabelas WHERE upper(codigo)=?", (codigo,)).fetchone()
                if pt:
                    existe, nome_padrao = True, pt[0] or ""
            if not nome_padrao:
                tr = db.execute("SELECT nome FROM tabelas WHERE upper(codigo)=?", (codigo,)).fetchone()
                if tr:
                    nome_padrao = tr[0] or ""
            campos_padrao = db.execute("SELECT count(*) FROM padrao_campos WHERE upper(tabela)=?", (codigo,)).fetchone()[0] if _table_exists(db, "padrao_campos") else 0
            campos_cliente = db.execute("SELECT count(*) FROM campos WHERE upper(tabela)=?", (codigo,)).fetchone()[0]
            dc = _load_diff_counts(db).get(codigo, {"adicionados": 0, "alterados": 0})
            return jsonify({"tabela": codigo, "nome_padrao": nome_padrao, "existe_no_padrao": existe,
                "campos_padrao": campos_padrao, "campos_cliente": campos_cliente,
                "campos_adicionados": dc["adicionados"], "campos_alterados": dc["alterados"]})
        else:
            row = db.execute("SELECT arquivo, modulo, pontos_entrada, tabelas_ref, write_tables FROM fontes WHERE arquivo=?", (chave,)).fetchone()
            if not row:
                return jsonify({"error": f"Fonte '{chave}' nao encontrado"}), 404
            pes = _safe_json(row[2])
            pes_impl = []
            if _table_exists(db, "padrao_pes"):
                for pe in pes:
                    pr = db.execute("SELECT nome, objetivo, modulo, rotina FROM padrao_pes WHERE upper(nome)=?", (pe.upper(),)).fetchone()
                    if pr:
                        pes_impl.append({"nome": pr[0], "objetivo": pr[1] or "", "modulo": pr[2] or "", "rotina": pr[3] or ""})
                    else:
                        pes_impl.append({"nome": pe, "objetivo": "(nao catalogado)", "rotina": _pe_to_rotina(pe)})
            return jsonify({"arquivo": row[0], "pes_implementados": pes_impl,
                "rotinas_afetadas": [_pe_to_rotina(pe) for pe in pes if _pe_to_rotina(pe)]})
    except Exception as e:
        return jsonify({"error": str(e)[:300]}), 500
    finally:
        db.close()


# ========================================================================
# MENU DETAIL
# ========================================================================

@workspace_bp.route("/workspaces/<slug>/explorer/menu/<rotina>", methods=["GET"])
@require_permission("devworkspace:view")
def explorer_menu_detail(slug, rotina):
    """Detalhe de rotina/menu com fontes e tabelas."""
    db = _get_db(slug)
    try:
        rotina_upper = rotina.upper().replace("_MENU", "")
        client_menus, padrao_menus = {}, {}
        if _table_exists(db, "menus"):
            r = db.execute("SELECT nome, menu, modulo FROM menus WHERE upper(rotina)=?", (rotina_upper,)).fetchone()
            if r:
                client_menus = {"nome": r[0] or "", "menu": r[1] or "", "modulo": r[2] or ""}
        if _table_exists(db, "padrao_menus"):
            r = db.execute("SELECT nome, menu, modulo FROM padrao_menus WHERE upper(rotina)=?", (rotina_upper,)).fetchone()
            if r:
                padrao_menus = {"nome": r[0] or "", "menu": r[1] or "", "modulo": r[2] or ""}

        nome = padrao_menus.get("nome") or client_menus.get("nome") or ""
        modulo = _normalize_modulo_ext(padrao_menus.get("modulo") or client_menus.get("modulo") or "OUTROS")
        origem = "ambos" if (client_menus and padrao_menus.get("nome")) else ("custom" if client_menus else "padrao")

        fontes_rel = []
        for arq_row in db.execute("SELECT arquivo, funcoes, pontos_entrada, lines_of_code FROM fontes").fetchall():
            pes = _safe_json(arq_row[2])
            user_funcs = _safe_json(arq_row[1]) + pes
            if any(f.upper() == rotina_upper or _pe_to_rotina(f.upper()) == rotina_upper for f in user_funcs):
                fontes_rel.append({"arquivo": arq_row[0], "funcoes": len(user_funcs), "loc": arq_row[3] or 0, "pes": pes})

        return jsonify({"rotina": rotina_upper, "nome": nome, "modulo": modulo, "origem": origem,
            "menu_padrao": padrao_menus.get("menu", ""), "menu_cliente": client_menus.get("menu", ""),
            "fontes_relacionados": fontes_rel})
    except Exception as e:
        return jsonify({"error": str(e)[:300]}), 500
    finally:
        db.close()


# ========================================================================
# JOBS + SCHEDULES
# ========================================================================

@workspace_bp.route("/workspaces/<slug>/explorer/jobs", methods=["GET"])
@require_permission("devworkspace:view")
def explorer_jobs(slug):
    """Jobs agrupados por arquivo_ini."""
    db = _get_db(slug)
    try:
        if not _table_exists(db, "jobs"):
            return jsonify({"total": 0, "groups": []})
        rows = db.execute("SELECT arquivo_ini, sessao, rotina, refresh_rate, parametros FROM jobs ORDER BY arquivo_ini, sessao").fetchall()
        groups = {}
        for arquivo_ini, sessao, rotina, refresh_rate, parametros in rows:
            groups.setdefault(arquivo_ini, []).append({
                "sessao": sessao, "rotina": rotina, "refresh_rate": refresh_rate,
                "refresh_label": f"{refresh_rate}s" if refresh_rate else "N/A",
                "parametros": parametros if parametros != "N/A" else "",
            })
        return jsonify({"total": len(rows), "groups": [{"arquivo_ini": k, "sessions": v, "count": len(v)} for k, v in sorted(groups.items())]})
    except Exception as e:
        return jsonify({"error": str(e)[:300]}), 500
    finally:
        db.close()


@workspace_bp.route("/workspaces/<slug>/explorer/schedules", methods=["GET"])
@require_permission("devworkspace:view")
def explorer_schedules(slug):
    """Schedules agrupados por status."""
    db = _get_db(slug)
    try:
        if not _table_exists(db, "schedules"):
            return jsonify({"total": 0, "groups": []})
        rows = db.execute(
            "SELECT codigo, rotina, empresa_filial, environment, modulo, status, "
            "tipo_recorrencia, detalhe_recorrencia, execucoes_dia, intervalo, "
            "hora_inicio, data_criacao, ultima_execucao, ultima_hora FROM schedules ORDER BY status, rotina"
        ).fetchall()
        by_status = {}
        for r in rows:
            status = r[5]
            by_status.setdefault(status, []).append({
                "codigo": r[0], "rotina": r[1], "empresa_filial": r[2], "environment": r[3],
                "modulo": r[4], "status": status, "tipo_recorrencia": r[6],
                "execucoes_dia": r[8], "intervalo": r[9], "hora_inicio": r[10],
                "data_criacao": r[11], "ultima_execucao": r[12], "ultima_hora": r[13],
            })
        result = []
        for k in ["Ativo", "Inativo"]:
            if k in by_status:
                result.append({"status": k, "items": by_status.pop(k), "count": len(by_status.get(k, []))})
        for k, v in by_status.items():
            result.append({"status": k, "items": v, "count": len(v)})
        # Fix count after pop
        for g in result:
            g["count"] = len(g["items"])
        return jsonify({"total": len(rows), "groups": result})
    except Exception as e:
        return jsonify({"error": str(e)[:300]}), 500
    finally:
        db.close()


# ========================================================================
# GRAFO DE DEPENDENCIAS
# ========================================================================

@workspace_bp.route("/workspaces/<slug>/explorer/fonte/<arquivo>/grafo", methods=["GET"])
@require_permission("devworkspace:view")
def explorer_fonte_grafo(slug, arquivo):
    """Grafo de vinculos de um fonte."""
    db = _get_db(slug)
    try:
        if not db.execute("SELECT arquivo FROM fontes WHERE arquivo = ?", (arquivo,)).fetchone():
            return jsonify({"error": f"Fonte '{arquivo}' nao encontrado"}), 404
        try:
            from app.services.workspace.graph_traversal import traverse_graph
        except ImportError:
            return jsonify({"error": "graph_traversal nao disponivel"}), 500
        depth = request.args.get("depth", 2, type=int)
        ctx = traverse_graph(db, arquivo, "fonte", max_depth=min(depth, 3))
        return jsonify({
            "arquivo": arquivo,
            "nodes": ctx.get("nodes", []), "edges": ctx.get("edges", []),
            "by_type": {k: list(v) if isinstance(v, set) else v for k, v in ctx.get("by_type", {}).items()},
            "summary": ctx.get("summary", {}),
            "stats": {"nodes": len(ctx.get("nodes", [])), "edges": len(ctx.get("edges", []))},
        })
    except Exception as e:
        logger.exception(f"Erro ao gerar grafo: {e}")
        return jsonify({"error": str(e)[:300]}), 500
    finally:
        db.close()


# ========================================================================
# ANALISE TECNICA (GET cache + POST gerar com LLM)
# ========================================================================

@workspace_bp.route("/workspaces/<slug>/explorer/fonte/<arquivo>/analise-tecnica", methods=["GET"])
@require_permission("devworkspace:view")
def explorer_get_analise_tecnica(slug, arquivo):
    """Retorna analise tecnica cacheada."""
    db = _get_db(slug)
    try:
        if not _table_exists(db, "fonte_analise_tecnica"):
            return jsonify({"arquivo": arquivo, "analise_markdown": None, "analise_json": None, "processos_vinculados": []})
        row = db.execute("SELECT analise_markdown, analise_json, processos_vinculados, updated_at FROM fonte_analise_tecnica WHERE arquivo = ?", (arquivo,)).fetchone()
        if not row:
            return jsonify({"arquivo": arquivo, "analise_markdown": None, "analise_json": None, "processos_vinculados": []})
        return jsonify({"arquivo": arquivo, "analise_markdown": row[0],
            "analise_json": json.loads(row[1]) if row[1] else {},
            "processos_vinculados": json.loads(row[2]) if row[2] else [], "updated_at": row[3]})
    except Exception as e:
        return jsonify({"error": str(e)[:300]}), 500
    finally:
        db.close()


@workspace_bp.route("/workspaces/<slug>/explorer/fonte/<arquivo>/analise-tecnica", methods=["POST"])
@require_permission("devworkspace:analyze")
def explorer_gerar_analise_tecnica(slug, arquivo):
    """Gera analise tecnica com LLM."""
    db = _get_db(slug)
    force = request.args.get("force", "false").lower() == "true"
    try:
        if not force and _table_exists(db, "fonte_analise_tecnica"):
            cached = db.execute("SELECT analise_markdown, analise_json, processos_vinculados, updated_at FROM fonte_analise_tecnica WHERE arquivo = ?", (arquivo,)).fetchone()
            if cached and cached[0]:
                return jsonify({"arquivo": arquivo, "analise_markdown": cached[0],
                    "analise_json": json.loads(cached[1]) if cached[1] else {},
                    "processos_vinculados": json.loads(cached[2]) if cached[2] else [], "updated_at": cached[3]})

        fonte_row = db.execute("SELECT arquivo, modulo, lines_of_code FROM fontes WHERE arquivo = ?", (arquivo,)).fetchone()
        if not fonte_row:
            return jsonify({"error": f"Fonte '{arquivo}' nao encontrado"}), 404

        graph_text = ""
        try:
            from app.services.workspace.graph_traversal import traverse_graph, format_context_for_llm
            graph_text = format_context_for_llm(traverse_graph(db, arquivo, "fonte", max_depth=2))
        except Exception:
            pass

        func_rows = db.execute("SELECT funcao, tipo, resumo FROM funcao_docs WHERE arquivo = ?", (arquivo,)).fetchall() if _table_exists(db, "funcao_docs") else []
        func_sum = "\n".join(f"- {r[0]} ({r[1]}): {r[2]}" for r in func_rows if r[2]) or "(sem resumos)"

        try:
            llm = _get_llm_provider()
        except Exception as e:
            return jsonify({"error": f"LLM nao disponivel: {str(e)[:200]}"}), 500

        text = _llm_chat_text(llm, [{"role": "user", "content":
            f'Analise tecnicamente "{arquivo}" (Modulo: {fonte_row[1]}, LOC: {fonte_row[2]}).\n\n'
            f'{graph_text}\n\nFuncoes:\n{func_sum}\n\n'
            'Gere: 1) Markdown com ## Objetivo, ## Funcoes, ## Tabelas, ## Pontos de Atencao, ## Resumo\n'
            '2) ```json {"complexidade":"alta|media|baixa","tipo_programa":"..."}```'}])

        json_match = re.search(r"```json\s*([\s\S]*?)```", text)
        analise_json_str = "{}"
        if json_match:
            try:
                analise_json_str = json.dumps(json.loads(json_match.group(1).strip()), ensure_ascii=False)
            except json.JSONDecodeError:
                pass

        analise_md = text
        js = re.search(r"```json", analise_md)
        if js:
            analise_md = analise_md[:js.start()].strip()

        from datetime import datetime
        now = datetime.utcnow().isoformat()
        db.execute("""CREATE TABLE IF NOT EXISTS fonte_analise_tecnica (
            arquivo TEXT PRIMARY KEY, analise_markdown TEXT, analise_json TEXT,
            processos_vinculados TEXT, updated_at TEXT)""")
        db.execute("INSERT OR REPLACE INTO fonte_analise_tecnica VALUES (?, ?, ?, '[]', ?)",
            (arquivo, analise_md, analise_json_str, now))
        db.commit()
        return jsonify({"arquivo": arquivo, "analise_markdown": analise_md,
            "analise_json": json.loads(analise_json_str), "processos_vinculados": [], "updated_at": now})
    except Exception as e:
        logger.exception(f"Erro ao gerar analise tecnica: {e}")
        return jsonify({"error": str(e)[:300]}), 500
    finally:
        db.close()


# ========================================================================
# PROTHEUSDOC — Preview e injecao
# ========================================================================

@workspace_bp.route("/workspaces/<slug>/explorer/fonte/<arquivo>/protheusdoc/preview", methods=["GET"])
@require_permission("devworkspace:view")
def explorer_protheusdoc_preview(slug, arquivo):
    """Preview dos blocos ProtheusDoc."""
    db = _get_db(slug)
    try:
        from app.services.workspace.protheusdoc_injector import process_fonte, read_source
        fonte_row = db.execute("SELECT caminho FROM fontes WHERE arquivo = ?", (arquivo,)).fetchone()
        if not fonte_row or not fonte_row[0]:
            return jsonify({"error": f"Caminho do fonte '{arquivo}' nao encontrado"}), 404
        src_path = Path(fonte_row[0])
        if not src_path.exists():
            return jsonify({"error": f"Arquivo nao encontrado: {src_path}"}), 404
        _, encoding = read_source(src_path)
        func_resumos, func_details = {}, {}
        if _table_exists(db, "funcao_docs"):
            for r in db.execute("SELECT funcao, resumo, tipo, tabelas_ref FROM funcao_docs WHERE arquivo=?", (arquivo,)).fetchall():
                func_resumos[r[0]] = r[1] or ""
                func_details[r[0]] = {"tipo": r[2] or "Function", "tabelas_ref": _safe_json(r[3])}
        result = process_fonte(src_path, func_resumos, func_details, dry_run=True)
        result["encoding"] = encoding
        return jsonify(result)
    except ImportError:
        return jsonify({"error": "protheusdoc_injector nao disponivel"}), 500
    except Exception as e:
        return jsonify({"error": str(e)[:300]}), 500
    finally:
        db.close()


@workspace_bp.route("/workspaces/<slug>/explorer/fonte/<arquivo>/protheusdoc", methods=["POST"])
@require_permission("devworkspace:analyze")
def explorer_protheusdoc_inject(slug, arquivo):
    """Injeta blocos ProtheusDoc no fonte."""
    db = _get_db(slug)
    try:
        from app.services.workspace.protheusdoc_injector import process_fonte, read_source
        fonte_row = db.execute("SELECT caminho FROM fontes WHERE arquivo = ?", (arquivo,)).fetchone()
        if not fonte_row or not fonte_row[0]:
            return jsonify({"error": f"Caminho do fonte '{arquivo}' nao encontrado"}), 404
        src_path = Path(fonte_row[0])
        if not src_path.exists():
            return jsonify({"error": f"Arquivo nao encontrado: {src_path}"}), 404
        _, encoding = read_source(src_path)
        try:
            db.execute("ALTER TABLE fontes ADD COLUMN encoding TEXT")
        except Exception:
            pass
        db.execute("UPDATE fontes SET encoding=? WHERE arquivo=?", (encoding, arquivo))
        db.commit()
        func_resumos, func_details = {}, {}
        if _table_exists(db, "funcao_docs"):
            for r in db.execute("SELECT funcao, resumo, tipo, tabelas_ref FROM funcao_docs WHERE arquivo=?", (arquivo,)).fetchall():
                func_resumos[r[0]] = r[1] or ""
                func_details[r[0]] = {"tipo": r[2] or "Function", "tabelas_ref": _safe_json(r[3])}
        result = process_fonte(src_path, func_resumos, func_details, backup=True, dry_run=False)
        result["encoding"] = encoding
        return jsonify(result)
    except ImportError:
        return jsonify({"error": "protheusdoc_injector nao disponivel"}), 500
    except Exception as e:
        return jsonify({"error": str(e)[:300]}), 500
    finally:
        db.close()


# ========================================================================
# ENCODING — Deteccao e conversao
# ========================================================================

@workspace_bp.route("/workspaces/<slug>/explorer/fonte/<arquivo>/detect-encoding", methods=["POST"])
@require_permission("devworkspace:analyze")
def explorer_detect_encoding(slug, arquivo):
    """Detecta e salva encoding de um fonte."""
    db = _get_db(slug)
    try:
        from app.services.workspace.protheusdoc_injector import read_source
        fonte_row = db.execute("SELECT caminho FROM fontes WHERE arquivo = ?", (arquivo,)).fetchone()
        if not fonte_row or not fonte_row[0]:
            return jsonify({"error": "Caminho nao encontrado"}), 404
        src_path = Path(fonte_row[0])
        if not src_path.exists():
            return jsonify({"error": "Arquivo nao encontrado"}), 404
        _, encoding = read_source(src_path)
        try:
            db.execute("ALTER TABLE fontes ADD COLUMN encoding TEXT")
        except Exception:
            pass
        db.execute("UPDATE fontes SET encoding=? WHERE arquivo=?", (encoding, arquivo))
        db.commit()
        return jsonify({"arquivo": arquivo, "encoding": encoding})
    except ImportError:
        return jsonify({"error": "protheusdoc_injector nao disponivel"}), 500
    except Exception as e:
        return jsonify({"error": str(e)[:300]}), 500
    finally:
        db.close()


@workspace_bp.route("/workspaces/<slug>/explorer/fonte/<arquivo>/convert-cp1252", methods=["POST"])
@require_permission("devworkspace:edit")
def explorer_convert_to_cp1252(slug, arquivo):
    """Converte fonte para cp1252."""
    db = _get_db(slug)
    try:
        from app.services.workspace.protheusdoc_injector import convert_to_cp1252 as do_convert
        fonte_row = db.execute("SELECT caminho FROM fontes WHERE arquivo = ?", (arquivo,)).fetchone()
        if not fonte_row or not fonte_row[0]:
            return jsonify({"error": "Caminho nao encontrado"}), 404
        src_path = Path(fonte_row[0])
        if not src_path.exists():
            return jsonify({"error": "Arquivo nao encontrado"}), 404
        result = do_convert(src_path, backup=True)
        if result.get("converted"):
            try:
                db.execute("ALTER TABLE fontes ADD COLUMN encoding TEXT")
            except Exception:
                pass
            db.execute("UPDATE fontes SET encoding='cp1252' WHERE arquivo=?", (arquivo,))
            db.commit()
        return jsonify(result)
    except ImportError:
        return jsonify({"error": "protheusdoc_injector nao disponivel"}), 500
    except Exception as e:
        return jsonify({"error": str(e)[:300]}), 500
    finally:
        db.close()


@workspace_bp.route("/workspaces/<slug>/explorer/fontes/detect-encodings", methods=["POST"])
@require_permission("devworkspace:analyze")
def explorer_detect_all_encodings(slug):
    """Detecta encoding de TODOS os fontes."""
    db = _get_db(slug)
    try:
        from app.services.workspace.protheusdoc_injector import read_source
        try:
            db.execute("ALTER TABLE fontes ADD COLUMN encoding TEXT")
        except Exception:
            pass
        rows = db.execute("SELECT arquivo, caminho FROM fontes").fetchall()
        stats = {"total": len(rows), "cp1252": 0, "utf-8": 0, "other": 0, "not_found": 0}
        for r in rows:
            if not r[1] or not Path(r[1]).exists():
                stats["not_found"] += 1
                continue
            _, enc = read_source(Path(r[1]))
            db.execute("UPDATE fontes SET encoding=? WHERE arquivo=?", (enc, r[0]))
            stats["cp1252" if enc == "cp1252" else ("utf-8" if enc == "utf-8" else "other")] += 1
        db.commit()
        return jsonify(stats)
    except ImportError:
        return jsonify({"error": "protheusdoc_injector nao disponivel"}), 500
    except Exception as e:
        return jsonify({"error": str(e)[:300]}), 500
    finally:
        db.close()


@workspace_bp.route("/workspaces/<slug>/explorer/fontes/convert-all-cp1252", methods=["POST"])
@require_permission("devworkspace:edit")
def explorer_convert_all_cp1252(slug):
    """Converte TODOS os fontes nao-cp1252 para cp1252."""
    db = _get_db(slug)
    try:
        from app.services.workspace.protheusdoc_injector import read_source, convert_to_cp1252 as do_convert
        try:
            db.execute("ALTER TABLE fontes ADD COLUMN encoding TEXT")
        except Exception:
            pass
        rows = db.execute("SELECT arquivo, caminho FROM fontes").fetchall()
        results = {"total": len(rows), "already_cp1252": 0, "converted": 0, "failed": 0, "not_found": 0}
        for r in rows:
            if not r[1] or not Path(r[1]).exists():
                results["not_found"] += 1
                continue
            _, enc = read_source(Path(r[1]))
            if enc == "cp1252":
                results["already_cp1252"] += 1
                db.execute("UPDATE fontes SET encoding='cp1252' WHERE arquivo=?", (r[0],))
            else:
                res = do_convert(Path(r[1]), backup=True)
                if res.get("converted"):
                    results["converted"] += 1
                    db.execute("UPDATE fontes SET encoding='cp1252' WHERE arquivo=?", (r[0],))
                else:
                    results["failed"] += 1
        db.commit()
        return jsonify(results)
    except ImportError:
        return jsonify({"error": "protheusdoc_injector nao disponivel"}), 500
    except Exception as e:
        return jsonify({"error": str(e)[:300]}), 500
    finally:
        db.close()


@workspace_bp.route("/workspaces/<slug>/explorer/fontes/repair-encoding", methods=["POST"])
@require_permission("devworkspace:edit")
def explorer_repair_encoding(slug):
    """Repara fontes com encoding corrompido."""
    db = _get_db(slug)
    try:
        from app.services.workspace.protheusdoc_injector import repair_corrupted_encoding
        rows = db.execute("SELECT arquivo, caminho FROM fontes").fetchall()
        results = {"total": len(rows), "repaired": 0, "skipped": 0, "details": []}
        for r in rows:
            if not r[1] or not Path(r[1]).exists():
                continue
            if b'\xef\xbf\xbd' not in Path(r[1]).read_bytes():
                results["skipped"] += 1
                continue
            res = repair_corrupted_encoding(Path(r[1]), backup=True)
            if res.get("repaired"):
                results["repaired"] += 1
                results["details"].append({"arquivo": r[0], "chars_fixed": res.get("chars_fixed", 0)})
            else:
                results["skipped"] += 1
        return jsonify(results)
    except ImportError:
        return jsonify({"error": "protheusdoc_injector nao disponivel"}), 500
    except Exception as e:
        return jsonify({"error": str(e)[:300]}), 500
    finally:
        db.close()


# ========================================================================
# DOCUMENTO DO FONTE
# ========================================================================

@workspace_bp.route("/workspaces/<slug>/explorer/fonte/<arquivo>/documento", methods=["GET"])
@require_permission("devworkspace:view")
def explorer_fonte_documento(slug, arquivo):
    """Gera ou retorna documentacao de um fonte."""
    ws_path = _get_workspace_path(slug)
    knowledge_dir = ws_path / "knowledge" / "fontes"
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    md_path = knowledge_dir / f"{arquivo}.md"
    if md_path.exists():
        return jsonify({"arquivo": arquivo, "content": md_path.read_text(encoding="utf-8"), "cached": True})

    db = _get_db(slug)
    try:
        fonte_row = db.execute(
            "SELECT arquivo, modulo, funcoes, pontos_entrada, tabelas_ref, write_tables, lines_of_code "
            "FROM fontes WHERE arquivo = ?", (arquivo,),
        ).fetchone()
        if not fonte_row:
            return jsonify({"error": f"Fonte '{arquivo}' nao encontrado"}), 404

        context = f"Arquivo: {fonte_row[0]}\nModulo: {fonte_row[1]}\nFuncoes: {fonte_row[2]}\nPEs: {fonte_row[3]}\nTabelas: {fonte_row[4]}\nLOC: {fonte_row[6]}"

        try:
            llm = _get_llm_provider()
        except Exception as e:
            return jsonify({"error": f"LLM nao disponivel: {str(e)[:200]}"}), 500

        content = _llm_chat_text(llm, [{"role": "user", "content":
            f"Gere documentacao Markdown para o fonte Protheus:\n\n{context}\n\n"
            "Secoes: ## Overview, ## Funcoes, ## Tabelas, ## PEs, ## Observacoes. Seja conciso."}])
        md_path.write_text(content, encoding="utf-8")
        return jsonify({"arquivo": arquivo, "content": content, "cached": False})
    except Exception as e:
        return jsonify({"error": str(e)[:300]}), 500
    finally:
        db.close()


@workspace_bp.route("/workspaces/<slug>/explorer/fonte/<arquivo>/documento", methods=["DELETE"])
@require_permission("devworkspace:delete")
def explorer_fonte_documento_delete(slug, arquivo):
    """Remove documento cacheado."""
    ws_path = _get_workspace_path(slug)
    md_path = ws_path / "knowledge" / "fontes" / f"{arquivo}.md"
    if md_path.exists():
        md_path.unlink()
        return jsonify({"deleted": True})
    return jsonify({"deleted": False})
