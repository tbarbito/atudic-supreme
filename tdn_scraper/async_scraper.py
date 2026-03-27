#!/usr/bin/env python3
"""
Scraper async de alta performance para TDN TOTVS.

Roda no Ubuntu com aiohttp (30+ coroutines simultaneas) e grava
direto no PostgreSQL da VM Windows via rede local.

Uso:
    # Coletar arvore com Playwright primeiro:
    python scraper_tdn_advpl.py  (gera JSON)

    # Depois rodar este scraper async:
    python async_scraper.py --source tdn_framework_v2.json --name framework --workers 30
    python async_scraper.py --source tdn_totvstec_rest.json --name totvstec --workers 30

    # Com DB remoto:
    python async_scraper.py --source arquivo.json --name fonte --db-host 192.168.122.41

Requer: pip install aiohttp beautifulsoup4 psycopg2-binary
"""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import re
import sys
import time
from datetime import datetime

import aiohttp
import psycopg2
import psycopg2.extras
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Configuracao
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}
CHUNK_MAX_CHARS = 2500
CHUNK_OVERLAP = 200
CHUNK_MIN_CHARS = 80
REQUEST_TIMEOUT = 30


# =================================================================
# BANCO DE DADOS
# =================================================================

class DBWriter:
    """Gerencia conexao com PostgreSQL e escrita de chunks."""

    def __init__(self, host, port, dbname, user, password):
        self.conn = psycopg2.connect(
            host=host, port=port, dbname=dbname,
            user=user, password=password,
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
        self.conn.autocommit = False
        self._lock = asyncio.Lock()

    def close(self):
        self.conn.close()

    def register_pages(self, source, pages):
        """Registra paginas no PG (sync, roda uma vez)."""
        cur = self.conn.cursor()
        inserted = 0
        existing = 0

        for page in pages:
            cur.execute("SELECT id FROM tdn_pages WHERE page_url = %s", (page["url"],))
            if cur.fetchone():
                existing += 1
                continue
            cur.execute("""
                INSERT INTO tdn_pages (source, page_title, page_url, breadcrumb, status)
                VALUES (%s, %s, %s, %s, 'pending')
            """, (source, page["title"], page["url"], page.get("breadcrumb", "")))
            inserted += 1

        self.conn.commit()
        logger.info("Paginas registradas: %d novas, %d existentes", inserted, existing)
        return inserted, existing

    def get_pending_pages(self, source):
        """Retorna paginas pendentes."""
        cur = self.conn.cursor()
        cur.execute("""
            SELECT id, source, page_title, page_url, breadcrumb
            FROM tdn_pages WHERE status = 'pending' AND source = %s
            ORDER BY id
        """, (source,))
        return cur.fetchall()

    async def save_page_chunks(self, page_id, chunks, content, title):
        """Salva chunks de uma pagina (thread-safe via lock)."""
        async with self._lock:
            self._save_page_chunks_sync(page_id, chunks, content, title)

    def _save_page_chunks_sync(self, page_id, chunks, content, title):
        """Operacao sync de escrita no PG."""
        cur = self.conn.cursor()
        try:
            # Remover chunks antigos
            cur.execute("DELETE FROM tdn_chunks WHERE page_id = %s", (page_id,))

            for i, chunk in enumerate(chunks):
                content_hash = _hash(chunk["content"])
                cur.execute("""
                    INSERT INTO tdn_chunks
                        (page_id, chunk_index, content, content_type, section_title,
                         tokens_approx, content_hash, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    page_id, i, chunk["content"], chunk["content_type"],
                    chunk.get("title", ""),
                    len(chunk["content"]) // 4,
                    content_hash,
                    json.dumps({"source_section": chunk.get("title", "")}),
                ))

            # Atualizar pagina
            cur.execute("""
                UPDATE tdn_pages
                SET status = 'done', scraped_at = NOW(), updated_at = NOW(),
                    content_hash = %s, content_length = %s, chunks_count = %s
                WHERE id = %s
            """, (_hash(content), len(content), len(chunks), page_id))

            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            raise e

    async def mark_empty(self, page_id, reason=""):
        """Marca pagina como vazia."""
        async with self._lock:
            cur = self.conn.cursor()
            cur.execute("""
                UPDATE tdn_pages
                SET status = 'empty', error_message = %s, updated_at = NOW()
                WHERE id = %s
            """, (reason[:500], page_id))
            self.conn.commit()

    async def mark_error(self, page_id, error):
        """Marca pagina com erro."""
        async with self._lock:
            cur = self.conn.cursor()
            cur.execute("""
                UPDATE tdn_pages
                SET status = 'error', error_message = %s, updated_at = NOW()
                WHERE id = %s
            """, (str(error)[:500], page_id))
            self.conn.commit()


# =================================================================
# HTML → MARKDOWN → CHUNKS
# =================================================================

def _hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def html_to_markdown(element):
    """Converte HTML para Markdown simplificado."""
    lines = []
    for child in element.children:
        if isinstance(child, str):
            text = child.strip()
            if text:
                lines.append(text)
            continue

        tag_name = getattr(child, "name", None)
        if not tag_name:
            continue

        text = child.get_text(separator=" ", strip=True)
        if not text:
            continue

        if tag_name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag_name[1])
            prefix = "#" * min(level + 1, 4)
            lines.append(f"\n{prefix} {text}\n")
        elif tag_name == "pre" or (tag_name == "div" and "code" in (child.get("class") or [])):
            code = child.get_text(strip=False)
            lang = _detect_lang(code)
            lines.append(f"\n```{lang}\n{code.strip()}\n```\n")
        elif tag_name == "code":
            lines.append(f"`{text}`")
        elif tag_name == "table":
            lines.append(_table_to_md(child))
        elif tag_name in ("ul", "ol"):
            for li in child.find_all("li", recursive=False):
                li_text = li.get_text(separator=" ", strip=True)
                if li_text:
                    lines.append(f"- {li_text}")
        elif tag_name == "p":
            lines.append(text)
        elif tag_name in ("strong", "b"):
            lines.append(f"**{text}**")
        elif tag_name in ("div", "section", "article"):
            inner = html_to_markdown(child)
            if inner.strip():
                lines.append(inner)

    return "\n".join(lines)


def _detect_lang(code):
    c = code.lower()
    if any(k in c for k in ["function ", "local ", "user function", "beginsql"]):
        return "advpl"
    elif any(k in c for k in ["select ", "from ", "where ", "create table"]):
        return "sql"
    return ""


def _table_to_md(table):
    rows = []
    for tr in table.find_all("tr"):
        cells = [td.get_text(separator=" ", strip=True).replace("|", "\\|")
                 for td in tr.find_all(["td", "th"])]
        if cells:
            rows.append(cells)
    if not rows:
        return ""
    max_cols = max(len(r) for r in rows)
    for r in rows:
        while len(r) < max_cols:
            r.append("")
    lines = ["| " + " | ".join(rows[0]) + " |",
             "| " + " | ".join(["---"] * max_cols) + " |"]
    for row in rows[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n" + "\n".join(lines) + "\n"


def chunk_content(content, page_title=""):
    """Divide conteudo em chunks semanticos."""
    sections = _split_sections(content, page_title)
    chunks = []
    for section in sections:
        chunks.extend(_split_large(section))
    for chunk in chunks:
        chunk["content_type"] = _classify(chunk["content"])
    return chunks


def _split_sections(content, default_title):
    sections = []
    current_title = default_title
    current_lines = []

    for line in content.split("\n"):
        m = re.match(r"^(#{1,4})\s+(.+)$", line)
        if m:
            if current_lines:
                text = "\n".join(current_lines).strip()
                if len(text) >= CHUNK_MIN_CHARS:
                    sections.append({"title": current_title, "content": text})
            current_title = m.group(2).strip()
            current_lines = [line]
        else:
            current_lines.append(line)

    if current_lines:
        text = "\n".join(current_lines).strip()
        if len(text) >= CHUNK_MIN_CHARS:
            sections.append({"title": current_title, "content": text})

    if not sections:
        sections = [{"title": default_title, "content": content.strip()}]
    return sections


def _split_large(section):
    text = section["content"]
    if len(text) <= CHUNK_MAX_CHARS:
        return [section]

    chunks = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_MAX_CHARS, len(text))
        if end < len(text):
            bp = text.rfind("\n\n", start + CHUNK_MAX_CHARS // 2, end)
            if bp > start:
                end = bp
            else:
                cb = text.rfind("\n```\n", start + CHUNK_MAX_CHARS // 2, end)
                if cb > start:
                    end = cb + 4
        chunk_text = text[start:end].strip()
        if chunk_text and len(chunk_text) >= CHUNK_MIN_CHARS:
            part = len(chunks) + 1
            chunks.append({
                "title": f"{section['title']} (parte {part})",
                "content": chunk_text,
            })
        start = max(start + 1, end - CHUNK_OVERLAP)
    return chunks


def _classify(text):
    code_blocks = len(re.findall(r"```\w*\n", text))
    table_markers = text.count("| --- |")
    text_lines = len([l for l in text.split("\n")
                      if l.strip() and not l.startswith("|") and not l.startswith("```")])
    if code_blocks > 0 and code_blocks * 10 > text_lines:
        return "code"
    elif table_markers > 0 and table_markers * 5 > text_lines:
        return "table"
    return "text"


# =================================================================
# EXTRAI PAGINAS DO JSON
# =================================================================

def extract_pages(tree_data, breadcrumb=""):
    """Extrai paginas folha da arvore JSON."""
    pages = []
    nodes = tree_data if isinstance(tree_data, list) else [tree_data]
    for node in nodes:
        title = node.get("title", "").strip()
        url = node.get("url", "")
        children = node.get("children", [])
        crumb = f"{breadcrumb} > {title}" if breadcrumb else title

        if children:
            pages.extend(extract_pages(children, crumb))
        elif url and "tdn.totvs.com" in url:
            pages.append({"title": title, "url": url, "breadcrumb": crumb})
    return pages


# =================================================================
# SCRAPER ASYNC
# =================================================================

async def fetch_and_process(session, db, page, semaphore, stats):
    """Faz scraping de uma pagina e salva chunks."""
    async with semaphore:
        page_id = page["id"]
        url = page["page_url"]
        title = page["page_title"]

        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as resp:
                if resp.status != 200:
                    await db.mark_empty(page_id, f"HTTP {resp.status}")
                    stats["empty"] += 1
                    return
                html = await resp.text()
        except Exception as e:
            await db.mark_error(page_id, str(e))
            stats["errors"] += 1
            return

        # Parse HTML
        soup = BeautifulSoup(html, "html.parser")
        content_div = (
            soup.find("div", {"id": "main-content"})
            or soup.find("div", {"class": "wiki-content"})
            or soup.find("div", {"id": "content"})
            or soup.find("article")
        )

        if not content_div:
            await db.mark_empty(page_id, "Sem content div")
            stats["empty"] += 1
            return

        # Limpar
        for tag in content_div.find_all(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        for tag in content_div.find_all("div", {"class": re.compile(
                r"breadcrumb|sidebar|navigation|comment|page-metadata")}):
            tag.decompose()

        text = html_to_markdown(content_div).strip()
        if len(text) < CHUNK_MIN_CHARS:
            await db.mark_empty(page_id, "Conteudo muito curto")
            stats["empty"] += 1
            return

        # Chunkar e salvar
        chunks = chunk_content(text, page_title=title)
        if not chunks:
            await db.mark_empty(page_id, "Nenhum chunk gerado")
            stats["empty"] += 1
            return

        await db.save_page_chunks(page_id, chunks, text, title)
        stats["scraped"] += 1
        stats["chunks"] += len(chunks)

        # Rate limit suave (0.3s entre requests por coroutine)
        await asyncio.sleep(0.3)


async def run_scraper(args):
    """Pipeline principal async."""
    # Conectar ao PG
    db = DBWriter(
        host=args.db_host, port=args.db_port,
        dbname=args.db_name, user=args.db_user, password=args.db_password,
    )

    # Ler arvore JSON
    json_path = os.path.join(os.path.dirname(__file__), args.source)
    if not os.path.isfile(json_path):
        logger.error("Arquivo nao encontrado: %s", json_path)
        return

    with open(json_path, "r", encoding="utf-8") as f:
        tree = json.load(f)

    pages = extract_pages(tree)
    logger.info("Paginas na arvore: %d", len(pages))

    # Registrar paginas
    new, existing = db.register_pages(args.name, pages)

    # Buscar pendentes
    pending = db.get_pending_pages(args.name)
    total = len(pending)
    logger.info("Pendentes: %d", total)

    if not pending:
        logger.info("Nada a processar!")
        db.close()
        return

    stats = {"scraped": 0, "chunks": 0, "errors": 0, "empty": 0}
    semaphore = asyncio.Semaphore(args.workers)
    started = time.time()

    # Criar sessao HTTP e processar
    connector = aiohttp.TCPConnector(limit=args.workers, limit_per_host=args.workers)
    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        tasks = [fetch_and_process(session, db, page, semaphore, stats) for page in pending]

        # Processar com progresso
        done = 0
        for coro in asyncio.as_completed(tasks):
            await coro
            done += 1
            if done % 50 == 0 or done == total:
                elapsed = time.time() - started
                rate = done / elapsed if elapsed > 0 else 0
                remaining = (total - done) / rate if rate > 0 else 0
                logger.info(
                    "[%d/%d] %.1f pag/s | scraped=%d chunks=%d empty=%d err=%d | ETA %.0fs",
                    done, total, rate, stats["scraped"], stats["chunks"],
                    stats["empty"], stats["errors"], remaining,
                )

    elapsed = time.time() - started
    db.close()

    logger.info("=" * 60)
    logger.info("CONCLUIDO em %.1fs (%.1f pag/s)", elapsed, total / elapsed if elapsed else 0)
    logger.info("  Scraped: %d paginas, %d chunks", stats["scraped"], stats["chunks"])
    logger.info("  Empty: %d, Errors: %d", stats["empty"], stats["errors"])
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Scraper async TDN — alta performance")
    parser.add_argument("--source", required=True, help="Arquivo JSON da arvore (ex: tdn_framework_v2.json)")
    parser.add_argument("--name", required=True, help="Nome da fonte (ex: framework, protheus12)")
    parser.add_argument("--workers", type=int, default=30, help="Coroutines simultaneas (default: 30)")
    parser.add_argument("--db-host", default="192.168.122.41", help="Host do PostgreSQL")
    parser.add_argument("--db-port", type=int, default=5432, help="Porta do PostgreSQL")
    parser.add_argument("--db-name", default="atudir", help="Nome do banco")
    parser.add_argument("--db-user", default="atudir", help="Usuario do banco")
    parser.add_argument("--db-password", default="atudir", help="Senha do banco")

    args = parser.parse_args()
    asyncio.run(run_scraper(args))


if __name__ == "__main__":
    main()
