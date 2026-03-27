#!/usr/bin/env python3
"""
Crawl + Ingest em passo unico para TDN TOTVS.

Visita cada pagina, extrai conteudo, chunka e grava direto no PostgreSQL.
Segue links filhos recursivamente ate max_depth.
Usa asyncio + aiohttp para alta performance.

Uso:
    python crawl_and_ingest.py --urls urls.txt --source protheus12 --workers 20 --max-depth 3

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
from urllib.parse import urljoin

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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}
BASE_URL = "https://tdn.totvs.com"
CHUNK_MAX_CHARS = 2500
CHUNK_OVERLAP = 200
CHUNK_MIN_CHARS = 80


# =================================================================
# BANCO DE DADOS (sync, protegido por lock)
# =================================================================

class DB:
    def __init__(self, host, port, dbname, user, password):
        self.conn = psycopg2.connect(
            host=host, port=port, dbname=dbname,
            user=user, password=password,
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
        self.conn.autocommit = False
        self._lock = asyncio.Lock()
        self._pages_done = 0
        self._chunks_done = 0
        self._errors = 0
        self._empty = 0

    def close(self):
        self.conn.close()

    async def ensure_page(self, source, title, url):
        """Registra pagina se nao existe, retorna (page_id, is_new)."""
        async with self._lock:
            cur = self.conn.cursor()
            cur.execute("SELECT id, status FROM tdn_pages WHERE page_url = %s", (url,))
            row = cur.fetchone()
            if row:
                return row["id"], row["status"] != "done"  # ja existe, is_new=False se done
            cur.execute("""
                INSERT INTO tdn_pages (source, page_title, page_url, status)
                VALUES (%s, %s, %s, 'pending') RETURNING id
            """, (source, title[:500], url))
            page_id = cur.fetchone()["id"]
            self.conn.commit()
            return page_id, True

    async def save_chunks(self, page_id, chunks, content):
        """Salva chunks e marca pagina como done."""
        async with self._lock:
            cur = self.conn.cursor()
            try:
                cur.execute("DELETE FROM tdn_chunks WHERE page_id = %s", (page_id,))
                for i, chunk in enumerate(chunks):
                    cur.execute("""
                        INSERT INTO tdn_chunks
                            (page_id, chunk_index, content, content_type, section_title,
                             tokens_approx, content_hash, metadata)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        page_id, i, chunk["content"], chunk["content_type"],
                        chunk.get("title", "")[:500],
                        len(chunk["content"]) // 4,
                        _hash(chunk["content"]),
                        json.dumps({"section": chunk.get("title", "")}),
                    ))
                cur.execute("""
                    UPDATE tdn_pages SET status='done', scraped_at=NOW(), updated_at=NOW(),
                        content_hash=%s, content_length=%s, chunks_count=%s
                    WHERE id = %s
                """, (_hash(content), len(content), len(chunks), page_id))
                self.conn.commit()
                self._pages_done += 1
                self._chunks_done += len(chunks)
            except Exception as e:
                self.conn.rollback()
                logger.error("DB erro page_id=%s: %s", page_id, e)

    async def mark_empty(self, page_id):
        async with self._lock:
            cur = self.conn.cursor()
            cur.execute("UPDATE tdn_pages SET status='empty', updated_at=NOW() WHERE id=%s", (page_id,))
            self.conn.commit()
            self._empty += 1

    async def mark_error(self, page_id, error):
        async with self._lock:
            cur = self.conn.cursor()
            cur.execute("UPDATE tdn_pages SET status='error', error_message=%s, updated_at=NOW() WHERE id=%s",
                        (str(error)[:500], page_id))
            self.conn.commit()
            self._errors += 1

    def stats(self):
        return f"pages={self._pages_done} chunks={self._chunks_done} empty={self._empty} err={self._errors}"


# =================================================================
# HTML PARSING + CHUNKING
# =================================================================

def _hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def extract_content(html):
    """Extrai conteudo principal e links filhos de uma pagina TDN."""
    soup = BeautifulSoup(html, "html.parser")

    # Links filhos (pagetree + conteudo)
    child_links = []
    seen_urls = set()

    # Arvore lateral
    pagetree = soup.find("div", {"class": "plugin_pagetree"})
    if pagetree:
        for a in pagetree.find_all("a", href=True):
            href = a.get("href", "")
            title = a.get_text(strip=True)
            if title and href:
                if not href.startswith("http"):
                    href = BASE_URL + href
                if "tdn.totvs.com" in href and href not in seen_urls:
                    seen_urls.add(href)
                    child_links.append((href, title))

    # Links no conteudo principal
    content_div = (
        soup.find("div", {"id": "main-content"})
        or soup.find("div", {"class": "wiki-content"})
        or soup.find("div", {"id": "content"})
        or soup.find("article")
    )

    if content_div:
        for a in content_div.find_all("a", href=True):
            href = a.get("href", "")
            title = a.get_text(strip=True)
            if title and href and len(title) >= 3:
                if not href.startswith("http"):
                    href = BASE_URL + href
                if "tdn.totvs.com" in href and href not in seen_urls:
                    seen_urls.add(href)
                    child_links.append((href, title))

    # Extrair texto do conteudo
    text = ""
    if content_div:
        for tag in content_div.find_all(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        for tag in content_div.find_all("div", {"class": re.compile(
                r"breadcrumb|sidebar|navigation|comment|page-metadata")}):
            tag.decompose()
        text = _html_to_md(content_div).strip()

    return text, child_links


def _html_to_md(el):
    lines = []
    for child in el.children:
        if isinstance(child, str):
            t = child.strip()
            if t:
                lines.append(t)
            continue
        tag = getattr(child, "name", None)
        if not tag:
            continue
        t = child.get_text(separator=" ", strip=True)
        if not t:
            continue
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            lines.append(f"\n{'#' * min(int(tag[1]) + 1, 4)} {t}\n")
        elif tag == "pre" or (tag == "div" and "code" in (child.get("class") or [])):
            code = child.get_text(strip=False)
            lang = "advpl" if any(k in code.lower() for k in ["function ", "local ", "user function"]) else \
                   "sql" if any(k in code.lower() for k in ["select ", "from ", "where "]) else ""
            lines.append(f"\n```{lang}\n{code.strip()}\n```\n")
        elif tag == "code":
            lines.append(f"`{t}`")
        elif tag == "table":
            lines.append(_table_md(child))
        elif tag in ("ul", "ol"):
            for li in child.find_all("li", recursive=False):
                lt = li.get_text(separator=" ", strip=True)
                if lt:
                    lines.append(f"- {lt}")
        elif tag == "p":
            lines.append(t)
        elif tag in ("div", "section", "article"):
            inner = _html_to_md(child)
            if inner.strip():
                lines.append(inner)
    return "\n".join(lines)


def _table_md(table):
    rows = []
    for tr in table.find_all("tr"):
        cells = [td.get_text(separator=" ", strip=True).replace("|", "\\|") for td in tr.find_all(["td", "th"])]
        if cells:
            rows.append(cells)
    if not rows:
        return ""
    mc = max(len(r) for r in rows)
    for r in rows:
        while len(r) < mc:
            r.append("")
    lines = ["| " + " | ".join(rows[0]) + " |", "| " + " | ".join(["---"] * mc) + " |"]
    for row in rows[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n" + "\n".join(lines) + "\n"


def chunk_content(content, title=""):
    sections = []
    cur_title = title
    cur_lines = []
    for line in content.split("\n"):
        m = re.match(r"^(#{1,4})\s+(.+)$", line)
        if m:
            if cur_lines:
                t = "\n".join(cur_lines).strip()
                if len(t) >= CHUNK_MIN_CHARS:
                    sections.append({"title": cur_title, "content": t})
            cur_title = m.group(2).strip()
            cur_lines = [line]
        else:
            cur_lines.append(line)
    if cur_lines:
        t = "\n".join(cur_lines).strip()
        if len(t) >= CHUNK_MIN_CHARS:
            sections.append({"title": cur_title, "content": t})
    if not sections and len(content.strip()) >= CHUNK_MIN_CHARS:
        sections = [{"title": title, "content": content.strip()}]

    # Split large sections
    chunks = []
    for sec in sections:
        text = sec["content"]
        if len(text) <= CHUNK_MAX_CHARS:
            chunks.append(sec)
        else:
            start = 0
            part = 0
            while start < len(text):
                end = min(start + CHUNK_MAX_CHARS, len(text))
                if end < len(text):
                    bp = text.rfind("\n\n", start + CHUNK_MAX_CHARS // 2, end)
                    if bp > start:
                        end = bp
                chunk_text = text[start:end].strip()
                if chunk_text and len(chunk_text) >= CHUNK_MIN_CHARS:
                    part += 1
                    chunks.append({"title": f"{sec['title']} (parte {part})", "content": chunk_text})
                start = max(start + 1, end - CHUNK_OVERLAP)

    # Classify
    for c in chunks:
        txt = c["content"]
        code_blocks = len(re.findall(r"```\w*\n", txt))
        table_markers = txt.count("| --- |")
        text_lines = len([l for l in txt.split("\n") if l.strip() and not l.startswith("|") and not l.startswith("```")])
        if code_blocks > 0 and code_blocks * 10 > text_lines:
            c["content_type"] = "code"
        elif table_markers > 0 and table_markers * 5 > text_lines:
            c["content_type"] = "table"
        else:
            c["content_type"] = "text"
    return chunks


# =================================================================
# CRAWLER ASYNC
# =================================================================

async def crawl_page(session, db, url, title, source, depth, max_depth, visited, semaphore, queue):
    """Visita uma pagina, extrai conteudo, grava no PG, enfileira filhos."""
    if url in visited or depth > max_depth:
        return
    visited.add(url)

    async with semaphore:
        # Registrar pagina
        page_id, is_new = await db.ensure_page(source, title, url)
        if not is_new:
            return  # ja processada

        # Fetch
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=25)) as resp:
                if resp.status != 200:
                    await db.mark_empty(page_id)
                    return
                html = await resp.text()
        except Exception as e:
            await db.mark_error(page_id, str(e))
            return

        # Parse
        text, child_links = extract_content(html)

        # Ingest
        if text and len(text) >= CHUNK_MIN_CHARS:
            chunks = chunk_content(text, title=title)
            if chunks:
                await db.save_chunks(page_id, chunks, text)
            else:
                await db.mark_empty(page_id)
        else:
            await db.mark_empty(page_id)

        # Enfileirar filhos
        for child_url, child_title in child_links:
            if child_url not in visited:
                await queue.put((child_url, child_title, depth + 1))

        # Rate limit suave
        await asyncio.sleep(0.2)


async def worker(session, db, source, max_depth, visited, semaphore, queue, worker_id):
    """Worker que consome da fila e processa paginas."""
    while True:
        try:
            url, title, depth = await asyncio.wait_for(queue.get(), timeout=30)
        except asyncio.TimeoutError:
            break  # Fila vazia por 30s, encerrar worker

        await crawl_page(session, db, url, title, source, depth, max_depth, visited, semaphore, queue)
        queue.task_done()


async def run(args):
    # Conectar PG
    db = DB(
        host=args.db_host, port=args.db_port,
        dbname=args.db_name, user=args.db_user, password=args.db_password,
    )
    logger.info("Conectado ao PG %s:%s/%s", args.db_host, args.db_port, args.db_name)

    # URLs raiz
    root_urls = []
    for url in args.urls:
        url = url.strip()
        if url and url.startswith("http"):
            root_urls.append(url)

    logger.info("URLs raiz: %d", len(root_urls))
    logger.info("Workers: %d, Max depth: %d", args.workers, args.max_depth)
    logger.info("=" * 60)

    visited = set()
    queue = asyncio.Queue()
    semaphore = asyncio.Semaphore(args.workers)
    started = time.time()

    # Enfileirar URLs raiz
    for url in root_urls:
        name = url.split("/")[-1].replace("+", " ").replace("%20", " ")
        await queue.put((url, name, 0))

    # Criar sessao HTTP
    connector = aiohttp.TCPConnector(limit=args.workers + 5, limit_per_host=args.workers)
    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        # Lancar workers
        workers = [
            asyncio.create_task(worker(session, db, args.source, args.max_depth, visited, semaphore, queue, i))
            for i in range(args.workers)
        ]

        # Monitorar progresso
        while not all(w.done() for w in workers):
            await asyncio.sleep(10)
            elapsed = time.time() - started
            rate = len(visited) / elapsed if elapsed > 0 else 0
            logger.info(
                "[%.0fs] visited=%d qsize=%d %s (%.1f pag/s)",
                elapsed, len(visited), queue.qsize(), db.stats(), rate,
            )

        # Esperar workers finalizarem
        await asyncio.gather(*workers, return_exceptions=True)

    elapsed = time.time() - started
    db.close()

    logger.info("=" * 60)
    logger.info("CONCLUIDO em %.0fs", elapsed)
    logger.info("  Visitadas: %d paginas", len(visited))
    logger.info("  %s", db.stats())
    logger.info("  Rate: %.1f pag/s", len(visited) / elapsed if elapsed else 0)
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Crawl + Ingest TDN em passo unico")
    parser.add_argument("--urls", nargs="+", required=True, help="URLs raiz para crawlear")
    parser.add_argument("--source", required=True, help="Nome da fonte (ex: protheus12)")
    parser.add_argument("--workers", type=int, default=20, help="Coroutines simultaneas (default: 20)")
    parser.add_argument("--max-depth", type=int, default=3, help="Profundidade maxima de crawl (default: 3)")
    parser.add_argument("--db-host", default="192.168.122.41")
    parser.add_argument("--db-port", type=int, default=5432)
    parser.add_argument("--db-name", default="atudir")
    parser.add_argument("--db-user", default="atudir")
    parser.add_argument("--db-password", default="atudir")

    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
