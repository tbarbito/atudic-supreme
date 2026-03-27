"""
Rotas para gestao da base de conhecimento TDN (TOTVS Developer Network).

Endpoints:
  GET  /api/tdn/stats          — Estatisticas da base
  GET  /api/tdn/sources        — Fontes JSON disponiveis para ingestao
  POST /api/tdn/ingest         — Iniciar ingestao de uma fonte (background, multithread)
  POST /api/tdn/ingest-md      — Ingerir a partir de .md existente (background)
  GET  /api/tdn/search         — Busca full-text nos chunks (tsvector portugues)
  GET  /api/tdn/pages          — Listar paginas com filtros
  GET  /api/tdn/runs           — Historico de runs de scraping
"""

import os
import threading

from flask import Blueprint, request, jsonify, current_app

from app.utils.security import require_auth

tdn_bp = Blueprint("tdn", __name__)


def _get_ingestor():
    from app.services.tdn_ingestor import TDNIngestor
    return TDNIngestor()


# =================================================================
# ESTATISTICAS
# =================================================================

@tdn_bp.route("/api/tdn/stats", methods=["GET"])
@require_auth
def tdn_stats():
    """Retorna estatisticas da base TDN por fonte."""
    try:
        ingestor = _get_ingestor()
        stats = ingestor.get_stats()
        return jsonify([dict(s) for s in stats])
    except Exception as e:
        current_app.logger.error("Erro ao buscar stats TDN: %s", e)
        return jsonify({"error": str(e)}), 500


# =================================================================
# FONTES DISPONIVEIS
# =================================================================

@tdn_bp.route("/api/tdn/sources", methods=["GET"])
@require_auth
def tdn_sources():
    """Lista arquivos JSON disponiveis para ingestao."""
    ingestor = _get_ingestor()
    scraper_dir = ingestor.scraper_dir

    sources = []
    for f in sorted(os.listdir(scraper_dir)):
        if f.endswith(".json"):
            path = os.path.join(scraper_dir, f)
            size_kb = os.path.getsize(path) // 1024
            sources.append({"filename": f, "size_kb": size_kb})

    md_files = []
    for f in sorted(os.listdir(scraper_dir)):
        if f.endswith(".md"):
            path = os.path.join(scraper_dir, f)
            size_kb = os.path.getsize(path) // 1024
            md_files.append({"filename": f, "size_kb": size_kb})

    return jsonify({"json_sources": sources, "md_sources": md_files})


# =================================================================
# INGESTAO (JSON → scrape → chunk → persist)
# =================================================================

@tdn_bp.route("/api/tdn/ingest", methods=["POST"])
@require_auth
def tdn_ingest():
    """Inicia ingestao de uma fonte JSON em background.

    Body JSON:
        json_file: nome do arquivo JSON (ex: "tdn_framework_v2.json")
        source: identificador (ex: "framework")
        max_pages: limite de paginas (opcional, default: todas)
        scrape: se faz scraping real ou apenas registra (default: true)
        workers: threads paralelas para scraping (1-6, default: 1)
    """
    data = request.get_json(silent=True) or {}
    json_file = data.get("json_file")
    source = data.get("source")

    if not json_file or not source:
        return jsonify({"error": "json_file e source sao obrigatorios"}), 400

    max_pages = data.get("max_pages")
    scrape = data.get("scrape", True)
    workers = data.get("workers", 1)

    app = current_app._get_current_object()

    def _run():
        with app.app_context():
            try:
                ingestor = _get_ingestor()
                stats = ingestor.ingest_from_json(
                    json_filename=json_file,
                    source=source,
                    max_pages=max_pages,
                    scrape=scrape,
                    workers=workers,
                )
                app.logger.info("Ingestao TDN concluida: %s", stats)
            except Exception as e:
                app.logger.error("Erro na ingestao TDN: %s", e)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return jsonify({
        "success": True,
        "message": f"Ingestao iniciada em background para {json_file} (source={source}, workers={workers})",
    }), 202


# =================================================================
# INGESTAO A PARTIR DE MD EXISTENTE
# =================================================================

@tdn_bp.route("/api/tdn/ingest-md", methods=["POST"])
@require_auth
def tdn_ingest_md():
    """Inicia ingestao a partir de .md existente em background.

    Body JSON:
        md_file: nome do arquivo .md (ex: "tdn_v2_knowledge_base.md")
        source: identificador (ex: "framework")
    """
    data = request.get_json(silent=True) or {}
    md_file = data.get("md_file")
    source = data.get("source")

    if not md_file or not source:
        return jsonify({"error": "md_file e source sao obrigatorios"}), 400

    app = current_app._get_current_object()

    def _run():
        with app.app_context():
            try:
                ingestor = _get_ingestor()
                stats = ingestor.ingest_from_markdown(md_file, source)
                app.logger.info("Ingestao MD TDN concluida: %s", stats)
            except Exception as e:
                app.logger.error("Erro na ingestao MD TDN: %s", e)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return jsonify({
        "success": True,
        "message": f"Ingestao MD iniciada em background para {md_file} (source={source})",
    }), 202


# =================================================================
# BUSCA
# =================================================================

@tdn_bp.route("/api/tdn/search", methods=["GET"])
@require_auth
def tdn_search():
    """Busca full-text nos chunks TDN.

    Query params:
        q: texto de busca (obrigatorio)
        source: filtrar por fonte (opcional)
        type: filtrar por tipo - text, code, table (opcional)
        limit: maximo de resultados (default: 10)
    """
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"error": "Parametro q e obrigatorio"}), 400

    source = request.args.get("source")
    content_type = request.args.get("type")
    limit = min(int(request.args.get("limit", 10)), 50)

    try:
        ingestor = _get_ingestor()
        results = ingestor.search(query, source=source, content_type=content_type, limit=limit)
        return jsonify([dict(r) for r in results])
    except Exception as e:
        current_app.logger.error("Erro na busca TDN: %s", e)
        return jsonify({"error": str(e)}), 500


# =================================================================
# PAGINAS
# =================================================================

@tdn_bp.route("/api/tdn/pages", methods=["GET"])
@require_auth
def tdn_pages():
    """Lista paginas TDN com filtros.

    Query params:
        source: filtrar por fonte
        status: filtrar por status (pending, done, error, empty)
        limit: maximo (default: 50)
        offset: paginacao (default: 0)
    """
    from app.database import get_db, release_db_connection

    source = request.args.get("source")
    status = request.args.get("status")
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))

    conn = get_db()
    try:
        cursor = conn.cursor()

        conditions = []
        params = []
        if source:
            conditions.append("source = %s")
            params.append(source)
        if status:
            conditions.append("status = %s")
            params.append(status)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.extend([limit, offset])

        cursor.execute(f"""
            SELECT id, source, page_title, page_url, status,
                   chunks_count, content_length, scraped_at, created_at
            FROM tdn_pages
            {where}
            ORDER BY id
            LIMIT %s OFFSET %s
        """, params)

        rows = cursor.fetchall()

        # Contar total
        cursor.execute(f"SELECT COUNT(*) as total FROM tdn_pages {where}",
                       params[:-2] if params[:-2] else [])
        total = cursor.fetchone()["total"]

        return jsonify({"pages": [dict(r) for r in rows], "total": total})
    except Exception as e:
        current_app.logger.error("Erro ao listar paginas TDN: %s", e)
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


# =================================================================
# HISTORICO DE RUNS
# =================================================================

@tdn_bp.route("/api/tdn/runs", methods=["GET"])
@require_auth
def tdn_runs():
    """Lista historico de runs de scraping."""
    from app.database import get_db, release_db_connection

    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, source, total_pages, scraped_pages, chunked_pages,
                   errors, status, started_at, finished_at
            FROM tdn_scrape_runs
            ORDER BY id DESC LIMIT 20
        """)
        return jsonify([dict(r) for r in cursor.fetchall()])
    except Exception as e:
        current_app.logger.error("Erro ao listar runs TDN: %s", e)
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)
