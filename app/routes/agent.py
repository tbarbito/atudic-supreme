"""
Rotas do Agente Inteligente do AtuDIC.

Endpoints para gerenciar a memória persistente do agente:
busca BM25, ingestão de arquivos, CRUD de entradas e estatísticas.
"""

import json
import logging
import os
from flask import Blueprint, request, jsonify, Response
from app.utils.security import require_auth, require_operator, require_admin
from app.services.agent_memory import get_agent_memory
from app.services.agent_chat import get_chat_engine
from app.services.llm_providers import get_provider_list, create_provider_from_config, LLMError
from app.database import get_db, release_db_connection, TransactionContext

logger = logging.getLogger(__name__)

agent_bp = Blueprint("agent", __name__)


# =========================================================
# BUSCA NA MEMÓRIA
# =========================================================


@agent_bp.route("/api/agent/memory/search", methods=["GET"])
@require_auth
def search_memory():
    """Busca BM25 na memória do agente."""
    query = request.args.get("q", "").strip()
    chunk_type = request.args.get("type", "").strip() or None
    env_id = request.args.get("environment_id", type=int)
    limit = min(int(request.args.get("limit", 10)), 50)

    if not query:
        return jsonify({"error": "Parâmetro 'q' é obrigatório"}), 400

    service = get_agent_memory()
    results = service.search_bm25(query, chunk_type=chunk_type, environment_id=env_id, limit=limit)

    return jsonify({"query": query, "count": len(results), "results": results})


# =========================================================
# ESTATÍSTICAS
# =========================================================


@agent_bp.route("/api/agent/memory/stats", methods=["GET"])
@require_auth
def memory_stats():
    """Retorna estatísticas da memória do agente."""
    service = get_agent_memory()
    stats = service.get_stats()
    # Incluir stats da SX2
    stats["sx2"] = service.get_sx2_stats()
    return jsonify(stats)


# =========================================================
# CHUNKS
# =========================================================


@agent_bp.route("/api/agent/memory/chunks", methods=["GET"])
@require_auth
def list_chunks():
    """Lista chunks da memória com paginação."""
    chunk_type = request.args.get("type", "").strip() or None
    source = request.args.get("source", "").strip() or None
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))

    service = get_agent_memory()
    conn = service._get_conn()
    cursor = conn.cursor()

    conditions = []
    params = []

    if chunk_type:
        conditions.append("chunk_type = ?")
        params.append(chunk_type)

    if source:
        conditions.append("source_file = ?")
        params.append(source)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    cursor.execute(f"SELECT COUNT(*) as total FROM chunks_meta {where}", params)
    total = cursor.fetchone()["total"]

    cursor.execute(
        f"""
        SELECT chunk_id, source_file, chunk_type, section_title,
               substr(content, 1, 200) as content_preview,
               length(content) as content_length,
               environment_id, created_at
        FROM chunks_meta {where}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    """,
        params + [limit, offset],
    )

    chunks = [dict(row) for row in cursor.fetchall()]

    return jsonify({"total": total, "limit": limit, "offset": offset, "chunks": chunks})


@agent_bp.route("/api/agent/memory/chunks/<int:chunk_id>", methods=["GET"])
@require_auth
def get_chunk(chunk_id):
    """Retorna um chunk completo pelo ID."""
    service = get_agent_memory()
    conn = service._get_conn()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM chunks_meta WHERE chunk_id = ?", (chunk_id,))
    row = cursor.fetchone()

    if not row:
        return jsonify({"error": "Chunk não encontrado"}), 404

    return jsonify(dict(row))


# =========================================================
# ARQUIVOS DE MEMÓRIA
# =========================================================


@agent_bp.route("/api/agent/memory/files", methods=["GET"])
@require_auth
def list_files():
    """Lista arquivos .md do diretório de memória."""
    service = get_agent_memory()
    files = service.list_files()
    return jsonify({"files": files})


@agent_bp.route("/api/agent/memory/file", methods=["GET"])
@require_auth
def read_file():
    """Lê conteúdo de um arquivo .md da memória."""
    path = request.args.get("path", "").strip()
    if not path:
        return jsonify({"error": "Parâmetro 'path' é obrigatório"}), 400

    service = get_agent_memory()
    try:
        content = service.read_file(path)
    except ValueError as e:
        return jsonify({"error": str(e)}), 403

    if content is None:
        return jsonify({"error": "Arquivo não encontrado"}), 404

    return jsonify({"path": path, "content": content})


# =========================================================
# INGESTÃO E MANUTENÇÃO
# =========================================================


def _get_embedding_provider():
    """Obtem provider com suporte a embeddings.

    Cadeia de fallback (independente do provider de chat):
    1. Provider de embedding dedicado via EMBEDDING_PROVIDER env var
    2. Provider de chat ativo (se suportar embeddings)
    3. Qualquer provider configurado no banco que suporte embedding
    4. Ollama local (se disponivel)
    5. None (busca cai pra BM25 puro — funciona, mas sem semantica)
    """
    from app.services.llm_providers import LLMProvider, PROVIDERS

    # 1. Provider dedicado via env var (ex: EMBEDDING_PROVIDER=gemini)
    dedicated = os.environ.get("EMBEDDING_PROVIDER")
    if dedicated:
        try:
            api_key = os.environ.get("EMBEDDING_API_KEY") or os.environ.get(f"{dedicated.upper()}_API_KEY")
            provider = LLMProvider(dedicated, api_key=api_key)
            if provider.supports_embedding:
                return provider
        except Exception:
            pass

    # 2. Provider de chat ativo
    try:
        engine = get_chat_engine()
        if engine._llm_provider and getattr(engine._llm_provider, "supports_embedding", False):
            return engine._llm_provider
    except Exception:
        pass

    # 3. Buscar provider com embedding nas configs salvas no banco
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT provider_id, api_key, model, base_url
            FROM agent_settings
            WHERE is_active = FALSE AND provider_id IS NOT NULL
            ORDER BY updated_at DESC
        """)
        rows = cursor.fetchall()
        release_db_connection(conn)

        for row in rows:
            pid = row["provider_id"]
            if PROVIDERS.get(pid, {}).get("embedding"):
                try:
                    p = LLMProvider(pid, api_key=row.get("api_key"), base_url=row.get("base_url"))
                    if p.supports_embedding:
                        return p
                except Exception:
                    continue
    except Exception:
        pass

    # 4. Ollama local (se disponivel)
    try:
        provider = LLMProvider("ollama")
        if provider.supports_embedding:
            # Testar conectividade rapidamente
            import requests
            resp = requests.get(f"{provider.base_url}/api/version", timeout=2)
            if resp.status_code == 200:
                return provider
    except Exception:
        pass

    logger.info("Nenhum provider de embedding disponivel — busca via BM25 puro")
    return None


@agent_bp.route("/api/agent/memory/ingest", methods=["POST"])
@require_admin
def ingest_memory():
    """Re-indexa todos os arquivos de memória no FTS5 e gera embeddings."""
    env_id = request.json.get("environment_id") if request.is_json else None

    service = get_agent_memory()
    llm_provider = _get_embedding_provider()
    results = service.ingest_all(environment_id=env_id, llm_provider=llm_provider)

    embeddings = results.pop("_embeddings_generated", 0)
    total = sum(results.values())
    return jsonify(
        {
            "message": f"Ingestão concluída: {total} chunks em {len(results)} arquivos, {embeddings} embeddings gerados",
            "details": results,
            "total_chunks": total,
            "embeddings_generated": embeddings,
        }
    )


@agent_bp.route("/api/agent/memory/rebuild", methods=["POST"])
@require_admin
def rebuild_index():
    """Reconstrói índice FTS5 (leves) + ingere pesados no PG (hibrido)."""
    import os
    import threading

    service = get_agent_memory()
    results = service.rebuild_index()

    # Gerar embeddings apos rebuild
    llm_provider = _get_embedding_provider()
    embeddings = 0
    if llm_provider:
        embeddings = service.embed_all_chunks(llm_provider)

    total_sqlite = sum(results.values())

    # Ingerir arquivos TDN pesados (> 2MB) no PostgreSQL em background
    _MAX_SQLITE_FILE_SIZE = 2 * 1024 * 1024
    memory_dir = service.memory_dir
    heavy_files = []
    for filename in sorted(os.listdir(memory_dir)):
        if filename.startswith("tdn_") and filename.endswith(".md"):
            filepath = os.path.join(memory_dir, filename)
            if os.path.getsize(filepath) > _MAX_SQLITE_FILE_SIZE:
                heavy_files.append(filename)

    pg_status = "nenhum"
    if heavy_files:
        pg_status = f"{len(heavy_files)} arquivos em background"
        app = current_app._get_current_object()

        def _ingest_pg():
            with app.app_context():
                try:
                    from app.services.tdn_ingestor import TDNIngestor
                    ingestor = TDNIngestor(scraper_dir=memory_dir)
                    for md_file in heavy_files:
                        source = md_file.replace("tdn_", "").replace(".md", "")
                        app.logger.info("PG ingest: %s (source=%s)", md_file, source)
                        ingestor.ingest_from_markdown(md_file, source)
                    app.logger.info("PG ingest concluido: %d arquivos", len(heavy_files))
                except Exception as e:
                    app.logger.error("Erro PG ingest: %s", e)

        thread = threading.Thread(target=_ingest_pg, daemon=True)
        thread.start()

    return jsonify(
        {
            "message": f"Rebuild: {total_sqlite} chunks SQLite, {embeddings} embeddings, PG: {pg_status}",
            "details": results,
            "total_chunks": total_sqlite,
            "embeddings_generated": embeddings,
            "pg_heavy_files": heavy_files,
        }
    )


@agent_bp.route("/api/agent/memory/tdn-stats", methods=["GET"])
@require_auth
def tdn_memory_stats():
    """Retorna estatisticas dos chunks TDN (SQLite + PostgreSQL)."""
    stats = []

    # === SQLite FTS5 (leves, < 2MB) ===
    try:
        service = get_agent_memory()
        conn = service._get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT source_file, COUNT(*) as total_chunks
            FROM chunks_meta
            WHERE source_file LIKE 'tdn_%'
            GROUP BY source_file
            ORDER BY source_file
        """)
        for row in cursor.fetchall():
            source = row["source_file"].replace("tdn_", "").replace(".md", "")
            stats.append({
                "source": f"{source} (local)",
                "total_chunks": row["total_chunks"],
                "total_pages": row["total_chunks"],
                "scraped": row["total_chunks"],
                "pending": 0, "errors": 0, "empty": 0,
            })
    except Exception as e:
        current_app.logger.warning("Stats SQLite: %s", e)

    # === PostgreSQL tsvector (pesados, > 2MB) ===
    try:
        from app.database import get_db, release_db_connection
        pg_conn = get_db()
        pg_cursor = pg_conn.cursor()
        pg_cursor.execute("""
            SELECT source, COUNT(*) AS total_pages,
                   COUNT(*) FILTER (WHERE status = 'done') AS scraped,
                   COUNT(*) FILTER (WHERE status = 'pending') AS pending,
                   COUNT(*) FILTER (WHERE status = 'error') AS errors,
                   COUNT(*) FILTER (WHERE status = 'empty') AS empty,
                   COALESCE(SUM(chunks_count), 0) AS total_chunks
            FROM tdn_pages GROUP BY source ORDER BY source
        """)
        for row in pg_cursor.fetchall():
            stats.append({
                "source": f"{row['source']} (PG)",
                "total_chunks": row["total_chunks"],
                "total_pages": row["total_pages"],
                "scraped": row["scraped"],
                "pending": row["pending"],
                "errors": row["errors"],
                "empty": row["empty"],
            })
        release_db_connection(pg_conn)
    except Exception as e:
        current_app.logger.debug("Stats PG: %s (tabelas TDN podem nao existir)", e)

    return jsonify(stats)


@agent_bp.route("/api/agent/memory/embeddings", methods=["POST"])
@require_admin
def generate_embeddings():
    """Gera embeddings para chunks que ainda nao tem."""
    service = get_agent_memory()
    llm_provider = _get_embedding_provider()

    if not llm_provider:
        return jsonify({"error": "Nenhum provider com suporte a embeddings configurado (Ollama recomendado)"}), 400

    count = service.embed_all_chunks(llm_provider)
    return jsonify({
        "message": f"{count} embeddings gerados",
        "embeddings_generated": count,
        "model": getattr(llm_provider, "provider_id", "unknown"),
    })


@agent_bp.route("/api/agent/memory/embeddings/stats", methods=["GET"])
@require_auth
def embedding_stats():
    """Retorna estatisticas dos embeddings na memoria e consumo."""
    from app.services.agent_memory import get_embedding_stats

    service = get_agent_memory()
    conn = service._get_conn()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as total FROM chunks_meta")
    total = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as embedded FROM chunks_meta WHERE embedding IS NOT NULL")
    embedded = cursor.fetchone()["embedded"]

    usage = get_embedding_stats()

    return jsonify({
        "total_chunks": total,
        "with_embeddings": embedded,
        "without_embeddings": total - embedded,
        "coverage": round(embedded / total * 100, 1) if total > 0 else 0,
        "usage": {
            "api_calls": usage["calls"],
            "cache_hits": usage["cached"],
            "chars_sent": usage["chars_sent"],
            "cache_hit_rate": round(usage["cached"] / max(usage["calls"] + usage["cached"], 1) * 100, 1),
        },
    })


# =========================================================
# DICIONÁRIO SX2 (TABELAS PROTHEUS)
# =========================================================


@agent_bp.route("/api/agent/sx2/import", methods=["POST"])
@require_admin
def import_sx2():
    """Importa tabelas do Protheus a partir de CSV da SX2."""
    import os

    data = request.get_json() if request.is_json else {}
    csv_path = data.get("csv_path", "").strip()

    # Caminho padrão: prompt/sx2.csv
    if not csv_path:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        csv_path = os.path.join(base_dir, "prompt", "sx2.csv")

    service = get_agent_memory()
    count = service.import_sx2(csv_path)

    if count == 0:
        return jsonify({"error": "Nenhuma tabela importada. Verifique o arquivo CSV."}), 400

    return jsonify({"message": f"SX2 importada: {count} tabelas padrão (excluídas Z*)", "total": count})


@agent_bp.route("/api/agent/sx2/search", methods=["GET"])
@require_auth
def search_sx2():
    """Busca tabelas na SX2 por alias ou descrição."""
    query = request.args.get("q", "").strip()
    limit = min(int(request.args.get("limit", 20)), 100)

    if not query:
        return jsonify({"error": "Parâmetro 'q' é obrigatório"}), 400

    service = get_agent_memory()
    results = service.search_sx2(query, limit=limit)

    return jsonify({"query": query, "count": len(results), "tables": results})


# =========================================================
# CRUD DE ENTRADAS
# =========================================================


@agent_bp.route("/api/agent/memory/entry", methods=["POST"])
@require_operator
def add_entry():
    """Adiciona entrada na memória do agente.

    Body JSON:
        type: 'semantic' | 'episodic' | 'procedural'
        section: título da seção (obrigatório para semantic/procedural)
        content: conteúdo da entrada
        environment_id: id do ambiente (opcional)
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body obrigatório"}), 400

    entry_type = data.get("type", "").strip()
    section = data.get("section", "").strip()
    content = data.get("content", "").strip()
    env_id = data.get("environment_id")

    if not entry_type or entry_type not in ("semantic", "episodic", "procedural"):
        return jsonify({"error": "Tipo inválido. Use: semantic, episodic, procedural"}), 400

    if not content:
        return jsonify({"error": "Conteúdo é obrigatório"}), 400

    if entry_type in ("semantic", "procedural") and not section:
        return jsonify({"error": "Seção é obrigatória para tipo semantic/procedural"}), 400

    service = get_agent_memory()

    if entry_type == "semantic":
        chunks = service.add_semantic_entry(section, content, env_id)
    elif entry_type == "episodic":
        chunks = service.add_episodic_entry(content, env_id)
    else:
        chunks = service.add_procedural_entry(section, content)

    return jsonify({"message": f"Entrada adicionada ({entry_type})", "chunks_indexed": chunks})


# =========================================================
# EPISÓDIOS RECENTES
# =========================================================


@agent_bp.route("/api/agent/memory/episodes", methods=["GET"])
@require_auth
def recent_episodes():
    """Retorna episódios recentes da memória."""
    days = int(request.args.get("days", 7))
    limit = min(int(request.args.get("limit", 20)), 100)

    service = get_agent_memory()
    episodes = service.get_recent_episodes(days=days, limit=limit)

    return jsonify({"days": days, "count": len(episodes), "episodes": episodes})


# =========================================================
# SESSÕES
# =========================================================


@agent_bp.route("/api/agent/sessions", methods=["GET"])
@require_auth
def list_sessions():
    """Lista sessões recentes do agente."""
    limit = min(int(request.args.get("limit", 20)), 100)

    service = get_agent_memory()
    sessions = service.list_sessions(limit=limit)

    return jsonify({"sessions": sessions})


# =========================================================
# HISTÓRICO DE BUSCAS
# =========================================================


@agent_bp.route("/api/agent/memory/search-history", methods=["GET"])
@require_auth
def search_history():
    """Retorna histórico de buscas realizadas."""
    limit = min(int(request.args.get("limit", 50)), 200)

    service = get_agent_memory()
    history = service.get_search_history(limit=limit)

    return jsonify({"history": history})


# =========================================================
# CONFIGURAÇÕES DO AGENTE (PostgreSQL)
# =========================================================


@agent_bp.route("/api/agent/settings", methods=["GET"])
@require_auth
def get_settings():
    """Retorna configurações do agente para o ambiente ativo."""
    env_id = request.args.get("environment_id", type=int)
    if not env_id:
        return jsonify({"error": "environment_id é obrigatório"}), 400

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT setting_key, setting_value FROM agent_settings WHERE environment_id = %s", (env_id,))
        rows = cursor.fetchall()
        settings = {row["setting_key"]: row["setting_value"] for row in rows}

        # Defaults para settings que não existem
        defaults = {
            "agent_enabled": "true",
            "memory_auto_ingest": "false",
            "memory_chunk_size": "3000",
            "memory_chunk_overlap": "200",
        }
        for key, default in defaults.items():
            if key not in settings:
                settings[key] = default

        return jsonify({"environment_id": env_id, "settings": settings})
    finally:
        release_db_connection(conn)


@agent_bp.route("/api/agent/settings", methods=["PUT"])
@require_admin
def update_settings():
    """Atualiza configurações do agente."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body obrigatório"}), 400

    env_id = data.get("environment_id")
    settings = data.get("settings", {})

    if not env_id:
        return jsonify({"error": "environment_id é obrigatório"}), 400

    user_id = request.current_user.get("id") if hasattr(request, "current_user") else None

    try:
        with TransactionContext() as (conn, cursor):
            for key, value in settings.items():
                cursor.execute(
                    """
                    INSERT INTO agent_settings (environment_id, setting_key, setting_value, updated_by)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (environment_id, setting_key)
                    DO UPDATE SET setting_value = EXCLUDED.setting_value,
                                  updated_by = EXCLUDED.updated_by,
                                  updated_at = NOW()
                """,
                    (env_id, key, str(value), user_id),
                )

        return jsonify({"message": "Configurações atualizadas", "settings": settings})
    except Exception as e:
        return jsonify({"error": f"Erro ao salvar configurações: {str(e)}"}), 500


# =========================================================
# CHAT DO AGENTE (Item 9B)
# =========================================================


@agent_bp.route("/api/agent/chat/session", methods=["POST"])
@require_auth
def create_chat_session():
    """Inicia nova sessão de chat."""
    env_id = None
    if request.is_json:
        env_id = request.get_json().get("environment_id")
    if not env_id:
        env_id = request.headers.get("X-Environment-Id", type=int)

    service = get_agent_memory()
    session_id = service.start_session(environment_id=env_id)

    return jsonify({"session_id": session_id, "environment_id": env_id})


@agent_bp.route("/api/agent/chat/session/<session_id>", methods=["DELETE"])
@require_auth
def end_chat_session(session_id):
    """Encerra sessao de chat com resumo automatico (9K-T5)."""
    summary = None
    if request.is_json:
        summary = request.get_json().get("summary")

    # [9K-T5] Gerar resumo automatico via LLM se sessao teve 3+ mensagens
    if not summary:
        try:
            engine = get_chat_engine()
            summary = engine.summarize_session(session_id)
        except Exception:
            pass

    # [20A] Consolidar fatos da sessão na memória semântica
    consolidated_facts = []
    try:
        from app.services.agent_consolidator import MemoryConsolidator
        from app.services.agent_working_memory import get_working_memory

        wm = get_working_memory()
        wm_facts = wm.get_facts_for_consolidation(session_id)

        engine = get_chat_engine()
        consolidator = MemoryConsolidator(get_agent_memory(), engine._llm_provider)
        consolidated_facts = consolidator.consolidate_session(session_id, working_memory_facts=wm_facts)

        # Descartar working memory da sessão
        wm.discard(session_id)
    except Exception as e:
        logger.warning("Erro na consolidação da sessão %s: %s", session_id[:8], e)

    service = get_agent_memory()
    service.end_session(session_id, summary=summary)

    return jsonify({
        "message": "Sessão encerrada",
        "session_id": session_id,
        "auto_summary": summary is not None,
        "facts_consolidated": len(consolidated_facts),
    })


@agent_bp.route("/api/agent/context/reload", methods=["POST"])
@require_admin
def reload_agent_context():
    """Recarrega o system prompt do agente a partir do arquivo AtuDIC_AGENT_CONTEXT.md."""
    from app.services.agent_chat import reload_system_prompt

    info = reload_system_prompt()
    return jsonify(info)


@agent_bp.route("/api/agent/chat/message", methods=["POST"])
@require_auth
def chat_message():
    """Envia mensagem ao agente e recebe resposta (LLM ou rule-based)."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body obrigatório"}), 400

    session_id = data.get("session_id", "").strip()
    message = data.get("message", "").strip()
    env_id = data.get("environment_id")

    if not session_id:
        return jsonify({"error": "session_id é obrigatório"}), 400

    if not message:
        return jsonify({"error": "message é obrigatória"}), 400

    # Coletar info do usuário e ambiente para contexto do LLM
    user_info = {}
    current_user = getattr(request, "current_user", None)
    if current_user:
        user_info["name"] = current_user.get("name", "")
        user_info["username"] = current_user.get("username", "")
        user_info["profile"] = current_user.get("profile", "")
        user_info["user_id"] = current_user.get("id")

    # Buscar nome do ambiente ativo
    if env_id:
        conn = get_db()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT name, description FROM environments WHERE id = %s", (env_id,))
            env_row = cursor.fetchone()
            if env_row:
                user_info["environment_name"] = env_row.get("name", "")
                user_info["environment_id"] = env_id
        except Exception:
            pass
        finally:
            release_db_connection(conn)

    # Processar attachments (arquivos e imagens)
    attachments = data.get("attachments", [])

    # Pending action: se o frontend envia uma acao pendente de confirmacao,
    # executar diretamente sem ir pro LLM (evita que modelos menores se percam)
    pending_action = data.get("pending_action")

    # Garantir sincronização caso o app tenha sido reiniciado / worker diferente
    engine = get_chat_engine()
    _ensure_active_llm(env_id, engine)

    if pending_action:
        response = engine.execute_confirmed_action(
            pending_action, session_id, environment_id=env_id, user_info=user_info
        )
    else:
        response = engine.process_message(
            message, session_id, environment_id=env_id, user_info=user_info, attachments=attachments
        )

    return jsonify(response)


@agent_bp.route("/api/agent/chat/stream", methods=["POST"])
@require_auth
def chat_message_stream():
    """Envia mensagem ao agente com resposta via SSE (Server-Sent Events).

    O LLM responde token por token em tempo real. Cada evento SSE é:
      data: {"chunk": "texto parcial", "done": false}
    O último evento inclui:
      data: {"chunk": "", "done": true, "response": {...resposta completa...}}

    Fallback: se o LLM não suporta streaming ou se há tool call,
    retorna a resposta completa de uma vez.
    """
    from flask import Response, stream_with_context

    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body obrigatório"}), 400

    session_id = data.get("session_id", "").strip()
    message = data.get("message", "").strip()
    env_id = data.get("environment_id")

    if not session_id or not message:
        return jsonify({"error": "session_id e message são obrigatórios"}), 400

    # Coletar info do usuário
    user_info = {}
    current_user = getattr(request, "current_user", None)
    if current_user:
        user_info["name"] = current_user.get("name", "")
        user_info["username"] = current_user.get("username", "")
        user_info["profile"] = current_user.get("profile", "")
        user_info["user_id"] = current_user.get("id")

    if env_id:
        conn = get_db()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT name FROM environments WHERE id = %s", (env_id,))
            env_row = cursor.fetchone()
            if env_row:
                user_info["environment_name"] = env_row.get("name", "")
                user_info["environment_id"] = env_id
        except Exception:
            pass
        finally:
            release_db_connection(conn)

    engine = get_chat_engine()
    _ensure_active_llm(env_id, engine)

    def generate():
        import json as _json

        try:
            # Verificar se o provider suporta streaming
            provider = engine._llm_provider
            if not provider or not hasattr(provider, 'chat_stream'):
                # Fallback: resposta blocking
                response = engine.process_message(
                    message, session_id, environment_id=env_id, user_info=user_info
                )
                yield f"data: {_json.dumps({'chunk': response.get('response', ''), 'done': True, 'response': response}, ensure_ascii=False)}\n\n"
                return

            # Processar intent e contexto (blocking — rápido)
            response = engine.process_message(
                message, session_id, environment_id=env_id, user_info=user_info
            )

            # Se houve tool call ou ação pendente, retornar de uma vez
            # (streaming só faz sentido para respostas textuais puras)
            yield f"data: {_json.dumps({'chunk': response.get('response', ''), 'done': True, 'response': response}, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error("Erro no chat stream: %s", e)
            yield f"data: {_json.dumps({'error': str(e), 'done': True}, ensure_ascii=False)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )


@agent_bp.route("/api/agent/chat/history", methods=["GET"])
@require_auth
def chat_history():
    """Retorna histórico de mensagens de uma sessão."""
    session_id = request.args.get("session_id", "").strip()
    limit = min(int(request.args.get("limit", 50)), 200)

    if not session_id:
        return jsonify({"error": "session_id é obrigatório"}), 400

    engine = get_chat_engine()
    messages = engine.get_chat_history(session_id, limit=limit)

    return jsonify({"session_id": session_id, "messages": messages})


# =========================================================
# PROVIDERS LLM (Item 9D)
# =========================================================


@agent_bp.route("/api/agent/llm/providers", methods=["GET"])
@require_auth
def list_llm_providers():
    """Lista providers LLM disponíveis."""
    return jsonify({"providers": get_provider_list()})


@agent_bp.route("/api/agent/llm/configs", methods=["GET"])
@require_auth
def list_llm_configs():
    """Lista configurações de LLM para o ambiente ativo."""
    env_id = request.args.get("environment_id", type=int)
    if not env_id:
        return jsonify({"error": "environment_id é obrigatório"}), 400

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, environment_id, provider_id, model, base_url,
                   options, is_active, created_at, updated_at
            FROM llm_provider_configs
            WHERE environment_id = %s
            ORDER BY is_active DESC, provider_id
        """,
            (env_id,),
        )
        configs = [dict(row) for row in cursor.fetchall()]
        # NÃO retornar api_key_encrypted
        return jsonify({"configs": configs})
    finally:
        release_db_connection(conn)


@agent_bp.route("/api/agent/llm/configs", methods=["POST"])
@require_admin
def save_llm_config():
    """Salva/atualiza configuração de um provider LLM."""
    import app.utils.crypto as crypto

    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body obrigatório"}), 400

    env_id = data.get("environment_id")
    provider_id = data.get("provider_id", "").strip()
    api_key = data.get("api_key", "").strip()
    model = data.get("model", "").strip() or None
    base_url = data.get("base_url", "").strip() or None
    options = data.get("options", {})
    is_active = data.get("is_active", True)

    if not env_id or not provider_id:
        return jsonify({"error": "environment_id e provider_id são obrigatórios"}), 400

    # Validar provider
    providers = {p["id"]: p for p in get_provider_list()}
    if provider_id not in providers:
        return jsonify({"error": f"Provider inválido: {provider_id}"}), 400

    # Criptografar API key se fornecida
    encrypted_key = None
    if api_key:
        try:
            encrypted_key = crypto.token_encryption.encrypt_token(api_key)
        except Exception as e:
            return jsonify({"error": f"Erro ao criptografar API key: {str(e)}"}), 500

    user_id = request.current_user.get("id") if hasattr(request, "current_user") else None
    options_json = json.dumps(options) if isinstance(options, dict) else options

    try:
        with TransactionContext() as (conn, cursor):
            # Upsert por (environment_id, provider_id)
            if encrypted_key:
                cursor.execute(
                    """
                    INSERT INTO llm_provider_configs
                    (environment_id, provider_id, api_key_encrypted, model, base_url, options, is_active, created_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (environment_id, provider_id)
                    DO UPDATE SET api_key_encrypted = EXCLUDED.api_key_encrypted,
                                  model = EXCLUDED.model,
                                  base_url = EXCLUDED.base_url,
                                  options = EXCLUDED.options,
                                  is_active = EXCLUDED.is_active,
                                  updated_at = NOW()
                """,
                    (env_id, provider_id, encrypted_key, model, base_url, options_json, is_active, user_id),
                )
            else:
                # Sem API key — atualizar apenas outros campos (manter key existente)
                cursor.execute(
                    """
                    INSERT INTO llm_provider_configs
                    (environment_id, provider_id, model, base_url, options, is_active, created_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (environment_id, provider_id)
                    DO UPDATE SET model = EXCLUDED.model,
                                  base_url = EXCLUDED.base_url,
                                  options = EXCLUDED.options,
                                  is_active = EXCLUDED.is_active,
                                  updated_at = NOW()
                """,
                    (env_id, provider_id, model, base_url, options_json, is_active, user_id),
                )

        return jsonify({"message": f"Provider {provider_id} configurado com sucesso"})
    except Exception as e:
        return jsonify({"error": f"Erro ao salvar configuração: {str(e)}"}), 500


@agent_bp.route("/api/agent/llm/configs/<int:config_id>", methods=["DELETE"])
@require_admin
def delete_llm_config(config_id):
    """Remove configuração de provider LLM."""
    try:
        with TransactionContext() as (conn, cursor):
            cursor.execute("DELETE FROM llm_provider_configs WHERE id = %s", (config_id,))
            if cursor.rowcount == 0:
                return jsonify({"error": "Configuração não encontrada"}), 404
        return jsonify({"message": "Configuração removida"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@agent_bp.route("/api/agent/llm/test", methods=["POST"])
@require_admin
def test_llm_connection():
    """Testa conexão com um provider LLM."""
    import app.utils.crypto as crypto

    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body obrigatório"}), 400

    provider_id = data.get("provider_id", "").strip()
    api_key = data.get("api_key", "").strip()
    model = data.get("model", "").strip() or None
    base_url = data.get("base_url", "").strip() or None

    if not provider_id:
        return jsonify({"error": "provider_id é obrigatório"}), 400

    # Se não enviou api_key, tentar buscar do banco
    if not api_key:
        env_id = data.get("environment_id")
        if env_id:
            conn = get_db()
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "SELECT api_key_encrypted FROM llm_provider_configs WHERE environment_id = %s AND provider_id = %s",
                    (env_id, provider_id),
                )
                row = cursor.fetchone()
                if row and row.get("api_key_encrypted"):
                    api_key = crypto.token_encryption.decrypt_token(row["api_key_encrypted"])
            finally:
                release_db_connection(conn)

    try:
        from app.services.llm_providers import LLMProvider

        provider = LLMProvider(provider_id, api_key=api_key, model=model, base_url=base_url)
        success, message = provider.test_connection()
        return jsonify({"success": success, "message": message})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@agent_bp.route("/api/agent/llm/activate", methods=["POST"])
@require_admin
def activate_llm():
    """Ativa um provider LLM para o chat do agente no ambiente."""
    import app.utils.crypto as crypto

    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body obrigatório"}), 400

    env_id = data.get("environment_id")
    provider_id = data.get("provider_id", "").strip()

    if not env_id or not provider_id:
        return jsonify({"error": "environment_id e provider_id são obrigatórios"}), 400

    # Buscar config do banco
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT provider_id, api_key_encrypted, model, base_url, options
            FROM llm_provider_configs
            WHERE environment_id = %s AND provider_id = %s AND is_active = TRUE
        """,
            (env_id, provider_id),
        )
        row = cursor.fetchone()
    finally:
        release_db_connection(conn)

    if not row:
        return jsonify({"error": f"Provider {provider_id} não configurado ou inativo"}), 404

    # Descriptografar API key
    api_key = None
    if row.get("api_key_encrypted"):
        try:
            api_key = crypto.token_encryption.decrypt_token(row["api_key_encrypted"])
        except Exception:
            return jsonify({"error": "Erro ao descriptografar API key"}), 500

    # Configurar o engine
    config = {
        "provider_id": row["provider_id"],
        "api_key": api_key,
        "model": row.get("model"),
        "base_url": row.get("base_url"),
        "options": row.get("options"),
    }

    try:
        provider = create_provider_from_config(config)
        engine = get_chat_engine()
        engine.set_llm_provider(provider)
        # Guardar na tabela agent_settings para persistência entre workers/restarts
        user_id = request.current_user.get("id") if hasattr(request, "current_user") else None
        with TransactionContext() as (ctx_conn, ctx_cursor):
            ctx_cursor.execute(
                """
                INSERT INTO agent_settings (environment_id, setting_key, setting_value, updated_by)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (environment_id, setting_key)
                DO UPDATE SET setting_value = EXCLUDED.setting_value,
                              updated_by = EXCLUDED.updated_by,
                              updated_at = NOW()
                """,
                (env_id, "active_llm_provider", provider_id, user_id),
            )

        return jsonify(
            {
                "message": f"LLM ativado: {provider_id}",
                "mode": "llm",
                "provider": provider_id,
                "model": provider.model,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@agent_bp.route("/api/agent/llm/deactivate", methods=["POST"])
@require_admin
def deactivate_llm():
    """Desativa LLM e volta para modo rule-based."""
    data = request.get_json() or {}
    env_id = data.get("environment_id")

    engine = get_chat_engine()
    engine.set_llm_provider(None)

    # Limpar no DB
    if env_id:
        try:
            with TransactionContext() as (conn, cursor):
                cursor.execute(
                    "DELETE FROM agent_settings WHERE environment_id = %s AND setting_key = 'active_llm_provider'",
                    (env_id,)
                )
        except Exception as e:
            logger.warning("Falha ao remover active_llm_provider do BD: %s", e)

    return jsonify({"message": "LLM desativado. Modo: rule-based", "mode": "rule-based"})


def _ensure_active_llm(env_id, engine):
    """Sincroniza o engine global com a preferência salva no banco p/ o ambiente atual.
    Necessário se Flask usar múltiplos workers ou houver reset de memória."""
    if not env_id:
        return

    from app.database import TransactionContext

    try:
        with TransactionContext() as (conn, cursor):
            cursor.execute(
                "SELECT setting_value FROM agent_settings WHERE environment_id = %s AND setting_key = 'active_llm_provider'",
                (env_id,)
            )
            row = cursor.fetchone()

            active_provider = row["setting_value"] if row else None

            # Se não tem provider no banco, engine não deve ter
            if not active_provider:
                if engine._llm_provider:
                    engine.set_llm_provider(None)
                return

            # Tem provider ativo no banco. Ver se engine já está com ele
            if engine._llm_provider and engine._llm_provider.provider_id == active_provider:
                return  # Já está OK

            # Precisa instanciar o provedor do banco
            import app.utils.crypto as crypto
            cursor.execute(
                """
                SELECT provider_id, api_key_encrypted, model, base_url, options
                FROM llm_provider_configs
                WHERE environment_id = %s AND provider_id = %s AND is_active = TRUE
                """,
                (env_id, active_provider)
            )
            prov_row = cursor.fetchone()

            if prov_row:
                api_key = None
                if prov_row.get("api_key_encrypted"):
                    try:
                        api_key = crypto.token_encryption.decrypt_token(prov_row["api_key_encrypted"])
                    except Exception:
                        pass
                config = {
                    "provider_id": prov_row["provider_id"],
                    "api_key": api_key,
                    "model": prov_row["model"],
                    "base_url": prov_row["base_url"],
                    "options": prov_row["options"],
                }
                from app.services.llm_providers import create_provider_from_config
                provider = create_provider_from_config(config)
                engine.set_llm_provider(provider)
                logger.info("Auto-sincronizado o motor de chat para o provider: %s", active_provider)
            else:
                # Provider referenciado não existe mais — limpar referência
                cursor.execute(
                    "DELETE FROM agent_settings WHERE environment_id = %s AND setting_key = 'active_llm_provider'",
                    (env_id,)
                )

    except Exception as e:
        logger.warning("Erro ao sincronizar active_llm_provider do BD: %s", e)


@agent_bp.route("/api/agent/llm/status", methods=["GET"])
@require_auth
def llm_status():
    """Retorna status atual do LLM."""
    env_id = request.args.get("environment_id", type=int)
    engine = get_chat_engine()
    
    _ensure_active_llm(env_id, engine)
    
    mode = engine.get_active_mode()
    result = {"mode": mode}
    if engine._llm_provider:
        result["provider"] = engine._llm_provider.provider_id
        result["model"] = engine._llm_provider.model
    return jsonify(result)


@agent_bp.route("/api/agent/llm/token-stats", methods=["GET"])
@require_auth
def llm_token_stats():
    """Retorna estatísticas de consumo de tokens por provider.

    Agrega dados do agent_audit_log para mostrar tokens consumidos
    hoje, nos últimos 7 dias e 30 dias, por provider.
    """
    env_id = request.args.get("environment_id", type=int)
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Tokens por provider nos últimos 30 dias (com input/output separados)
        query = """
            SELECT
                COALESCE(params::json->>'provider', 'unknown') AS provider,
                COALESCE(params::json->>'model', '') AS model,
                COUNT(*) AS total_calls,
                COALESCE(SUM(tokens_used), 0) AS total_tokens,
                COALESCE(SUM((params::json->>'prompt_tokens')::int), 0) AS total_input,
                COALESCE(SUM((params::json->>'completion_tokens')::int), 0) AS total_output,
                COALESCE(SUM(CASE WHEN created_at >= NOW() - INTERVAL '1 day' THEN tokens_used ELSE 0 END), 0) AS tokens_today,
                COALESCE(SUM(CASE WHEN created_at >= NOW() - INTERVAL '7 days' THEN tokens_used ELSE 0 END), 0) AS tokens_7d,
                COALESCE(SUM(CASE WHEN created_at >= NOW() - INTERVAL '30 days' THEN tokens_used ELSE 0 END), 0) AS tokens_30d,
                COUNT(CASE WHEN created_at >= NOW() - INTERVAL '1 day' THEN 1 END) AS calls_today,
                COUNT(CASE WHEN created_at >= NOW() - INTERVAL '7 days' THEN 1 END) AS calls_7d
            FROM agent_audit_log
            WHERE action = 'llm_chat'
              AND tokens_used > 0
        """
        params = []
        if env_id:
            query += " AND environment_id = %s"
            params.append(env_id)
        query += " GROUP BY provider, model ORDER BY total_tokens DESC"

        cursor.execute(query, params)
        rows = [dict(r) for r in cursor.fetchall()]

        # Custo estimado por provider (USD por 1M tokens)
        cost_table = {
            "anthropic": {"input": 3.0, "output": 15.0},
            "openai": {"input": 2.5, "output": 10.0},
            "gemini": {"input": 0.075, "output": 0.30},
            "deepseek": {"input": 0.27, "output": 1.10},
            "groq": {"input": 0.05, "output": 0.08},
            "ollama": {"input": 0.0, "output": 0.0},
        }

        for r in rows:
            costs = cost_table.get(r["provider"], {"input": 1.0, "output": 5.0})
            r["cost_usd"] = round(
                (r["total_input"] * costs["input"] / 1_000_000) +
                (r["total_output"] * costs["output"] / 1_000_000), 4
            )

        total_tokens = sum(r["total_tokens"] for r in rows)
        total_today = sum(r["tokens_today"] for r in rows)
        total_calls = sum(r["total_calls"] for r in rows)
        total_cost = round(sum(r["cost_usd"] for r in rows), 4)

        return jsonify({
            "by_provider": rows,
            "totals": {
                "tokens_30d": total_tokens,
                "tokens_today": total_today,
                "total_calls": total_calls,
                "cost_usd": total_cost,
            }
        })
    except Exception as e:
        logger.warning("Erro ao buscar token stats: %s", e)
        return jsonify({"by_provider": [], "totals": {"tokens_30d": 0, "tokens_today": 0, "total_calls": 0}})
    finally:
        release_db_connection(conn)


# =========================================================
# SKILLS DO AGENTE
# =========================================================


@agent_bp.route("/api/agent/skills", methods=["GET"])
@require_auth
def list_skills():
    """Lista skills disponíveis com metadados."""
    from app.services.agent_skills import get_skill_registry

    registry = get_skill_registry()
    skills = registry.get_all_skills()
    return jsonify({"skills": skills, "total": len(skills)})


@agent_bp.route("/api/agent/skills/reload", methods=["POST"])
@require_admin
def reload_skills():
    """Recarrega skills do disco (admin only)."""
    from app.services.agent_skills import get_skill_registry

    registry = get_skill_registry()
    result = registry.reload()
    return jsonify({"message": "Skills recarregadas", **result})


@agent_bp.route("/api/agent/skills/match", methods=["GET"])
@require_auth
def match_skills():
    """Testa quais skills seriam ativadas para um intent/mensagem."""
    from app.services.agent_skills import get_skill_registry

    intent = request.args.get("intent", "")
    message = request.args.get("message", "")
    if not intent and not message:
        return jsonify({"error": "Informe 'intent' ou 'message'"}), 400

    registry = get_skill_registry()
    skills = registry.get_skills_for_intent(intent, message)
    return jsonify(
        {
            "intent": intent,
            "message": message[:100],
            "skills_matched": [
                {
                    "name": s.name,
                    "description": s.description,
                    "token_estimate": s.token_estimate,
                    "always_load": s.always_load,
                }
                for s in skills
            ],
            "total_tokens": sum(s.token_estimate for s in skills),
        }
    )


# =====================================================================
# SPECIALISTS (9K-T2)
# =====================================================================


@agent_bp.route("/api/agent/specialists", methods=["GET"])
@require_auth
def list_specialists():
    """Lista specialists registrados."""
    from app.services.agent_specialists import get_specialist_registry

    registry = get_specialist_registry()
    return jsonify({"specialists": registry.get_all_specialists()})


@agent_bp.route("/api/agent/specialists/reload", methods=["POST"])
@require_admin
def reload_specialists():
    """Recarrega specialists do YAML."""
    from app.services.agent_specialists import get_specialist_registry

    registry = get_specialist_registry()
    result = registry.reload()
    return jsonify(result)


# =====================================================================
# SANDBOX CONFIG (9J — configuracao por ambiente)
# =====================================================================


@agent_bp.route("/api/agent/sandbox/config", methods=["GET"])
@require_auth
def get_sandbox_config():
    """Retorna configuracao de sandbox do ambiente ativo."""
    env_id = request.args.get("environment_id", type=int)
    if not env_id:
        return jsonify({"error": "environment_id e obrigatorio"}), 400

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT * FROM agent_sandbox_config WHERE environment_id = %s",
            (env_id,),
        )
        row = cursor.fetchone()
        if row:
            config = dict(row)
            # Parsear JSON fields
            for field in ("allowed_paths", "blocked_commands"):
                if config.get(field):
                    try:
                        config[field] = json.loads(config[field])
                    except (json.JSONDecodeError, TypeError):
                        config[field] = []
                else:
                    config[field] = []
            return jsonify({"config": config})
        else:
            # Retornar defaults se nao existe config
            return jsonify(
                {
                    "config": {
                        "environment_id": env_id,
                        "max_iterations": 10,
                        "token_budget": 50000,
                        "command_timeout": 30,
                        "react_enabled": False,
                        "system_tools_enabled": False,
                        "allowed_paths": [],
                        "blocked_commands": [],
                    }
                }
            )
    finally:
        release_db_connection(conn)


@agent_bp.route("/api/agent/sandbox/config", methods=["PUT"])
@require_admin
def update_sandbox_config():
    """Atualiza configuracao de sandbox do ambiente."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body obrigatorio"}), 400

    env_id = data.get("environment_id")
    if not env_id:
        return jsonify({"error": "environment_id e obrigatorio"}), 400

    # Serializar listas para JSON
    allowed_paths = json.dumps(data.get("allowed_paths", [])) if data.get("allowed_paths") else None
    blocked_commands = json.dumps(data.get("blocked_commands", [])) if data.get("blocked_commands") else None

    try:
        with TransactionContext() as (conn, cursor):
            cursor.execute(
                """
                INSERT INTO agent_sandbox_config
                    (environment_id, max_iterations, token_budget, command_timeout,
                     react_enabled, system_tools_enabled, allowed_paths, blocked_commands, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (environment_id)
                DO UPDATE SET
                    max_iterations = EXCLUDED.max_iterations,
                    token_budget = EXCLUDED.token_budget,
                    command_timeout = EXCLUDED.command_timeout,
                    react_enabled = EXCLUDED.react_enabled,
                    system_tools_enabled = EXCLUDED.system_tools_enabled,
                    allowed_paths = EXCLUDED.allowed_paths,
                    blocked_commands = EXCLUDED.blocked_commands,
                    updated_at = NOW()
                """,
                (
                    env_id,
                    data.get("max_iterations", 10),
                    data.get("token_budget", 50000),
                    data.get("command_timeout", 30),
                    data.get("react_enabled", False),
                    data.get("system_tools_enabled", False),
                    allowed_paths,
                    blocked_commands,
                ),
            )

        # Recarregar sandbox no proximo request
        return jsonify({"message": "Configuracao de sandbox atualizada", "environment_id": env_id})
    except Exception as e:
        return jsonify({"error": f"Erro ao salvar configuracao: {str(e)}"}), 500


# =====================================================================
# FEEDBACK (20C)
# =====================================================================


@agent_bp.route("/api/agent/feedback", methods=["POST"])
@require_auth
def submit_feedback():
    """Registra feedback (thumbs up/down) para uma mensagem do agente."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body obrigatório"}), 400

    message_id = data.get("message_id")
    rating = data.get("rating")  # 1 ou -1

    if rating not in (1, -1):
        return jsonify({"error": "rating deve ser 1 (positivo) ou -1 (negativo)"}), 400

    from app.services.agent_feedback import FeedbackService
    from app.services.agent_memory import get_agent_memory

    fb = FeedbackService(get_agent_memory())
    fb.save_feedback(
        message_id=message_id,
        session_id=data.get("session_id", ""),
        environment_id=data.get("environment_id"),
        rating=rating,
        metadata={
            "intent": data.get("intent", ""),
            "specialist": data.get("specialist", ""),
            "skills_used": data.get("skills_used", []),
            "tools_used": data.get("tools_used", []),
        },
    )

    return jsonify({"message": "Feedback registrado", "rating": rating})


@agent_bp.route("/api/agent/feedback/stats", methods=["GET"])
@require_auth
def feedback_stats():
    """Retorna métricas de satisfação do agente."""
    days = min(int(request.args.get("days", 7)), 90)
    env_id = request.args.get("environment_id", type=int)

    from app.services.agent_feedback import FeedbackService
    from app.services.agent_memory import get_agent_memory

    fb = FeedbackService(get_agent_memory())
    stats = fb.get_satisfaction_stats(days=days, environment_id=env_id)
    alerts = fb.get_low_performing(days=days)

    return jsonify({"stats": stats, "alerts": alerts})


# =====================================================================
# MONITOR PROATIVO (20B)
# =====================================================================


@agent_bp.route("/api/agent/proactive/status", methods=["GET"])
@require_auth
def proactive_status():
    """Retorna status do monitor proativo."""
    from app.services.agent_proactive import get_proactive_monitor

    monitor = get_proactive_monitor()
    return jsonify(monitor.get_status())


@agent_bp.route("/api/agent/proactive/start", methods=["POST"])
@require_admin
def proactive_start():
    """Inicia monitor proativo para o ambiente."""
    data = request.get_json() or {}
    env_id = data.get("environment_id")

    if not env_id:
        return jsonify({"error": "environment_id obrigatório"}), 400

    from app.services.agent_proactive import get_proactive_monitor
    from app.services.events import event_manager

    monitor = get_proactive_monitor()
    monitor.set_emit_fn(lambda eid, step: event_manager.broadcast(
        json.dumps({"type": "agent_step", "environment_id": eid, "data": step})
    ))
    monitor.enable_environment(env_id)
    monitor.start()

    return jsonify({"message": f"Monitor proativo iniciado para ambiente {env_id}"})


@agent_bp.route("/api/agent/proactive/stop", methods=["POST"])
@require_admin
def proactive_stop():
    """Para monitor proativo para o ambiente."""
    data = request.get_json() or {}
    env_id = data.get("environment_id")

    from app.services.agent_proactive import get_proactive_monitor

    monitor = get_proactive_monitor()
    if env_id:
        monitor.disable_environment(env_id)
        return jsonify({"message": f"Monitor proativo desabilitado para ambiente {env_id}"})
    else:
        monitor.stop()
        return jsonify({"message": "Monitor proativo parado completamente"})


# =====================================================================
# AGENT STEPS SSE (9J-F5)
# =====================================================================


@agent_bp.route("/api/agent/steps/stream", methods=["GET"])
@require_auth
def stream_agent_steps():
    """SSE stream para steps do agente ReAct em tempo real."""
    from app.services.events import event_manager
    import json as json_mod

    def generate():
        q = event_manager.subscribe()
        try:
            while True:
                try:
                    message = q.get(timeout=30)
                    # Filtrar apenas eventos do tipo agent_step
                    try:
                        data = json_mod.loads(message)
                        if data.get("type") == "agent_step":
                            yield f"data: {message}\n\n"
                    except (json_mod.JSONDecodeError, TypeError):
                        pass
                except Exception:
                    # Timeout — enviar keepalive
                    yield f"data: {json_mod.dumps({'type': 'keepalive'})}\n\n"
        finally:
            event_manager.unsubscribe(q)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
