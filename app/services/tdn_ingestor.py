"""
Servico de ingestao de conteudo TDN (TOTVS Developer Network).

Responsavel por:
1. Ler arvores JSON ja coletadas pelos scrapers
2. Fazer scraping do conteudo real das paginas (com checkpoint/resume)
3. Dividir conteudo em chunks semanticos
4. Persistir no PostgreSQL (tdn_pages + tdn_chunks) com full-text search
5. Indexar no SQLite FTS5 do agente para busca hibrida

Uso:
    from app.services.tdn_ingestor import TDNIngestor
    ingestor = TDNIngestor()
    ingestor.ingest_from_json("tdn_scraper/tdn_framework_v2.json", source="framework")
"""

import hashlib
import json
import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from app.database import get_db, release_db_connection, TransactionContext

logger = logging.getLogger(__name__)

# Configuracao de scraping
REQUEST_DELAY = 1.5
REQUEST_TIMEOUT = 30
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}

# Configuracao de chunking
CHUNK_MAX_CHARS = 2500
CHUNK_OVERLAP = 200
CHUNK_MIN_CHARS = 80


class TDNIngestor:
    """Servico de ingestao de conteudo TDN para base de conhecimento."""

    def __init__(self, scraper_dir=None):
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.scraper_dir = scraper_dir or os.path.join(base, "tdn_scraper")

    # =================================================================
    # LEITURA DE ARVORE JSON
    # =================================================================

    def extract_pages_from_tree(self, tree_data, breadcrumb=""):
        """Extrai todas as paginas folha de uma arvore JSON com breadcrumb."""
        pages = []
        nodes = tree_data if isinstance(tree_data, list) else [tree_data]

        for node in nodes:
            title = node.get("title", "").strip()
            url = node.get("url", "")
            children = node.get("children", [])

            current_breadcrumb = f"{breadcrumb} > {title}" if breadcrumb else title

            if children:
                pages.extend(self.extract_pages_from_tree(children, current_breadcrumb))
            elif url and "tdn.totvs.com" in url:
                pages.append({
                    "title": title,
                    "url": url,
                    "breadcrumb": current_breadcrumb,
                })

        return pages

    # =================================================================
    # SCRAPING DE CONTEUDO
    # =================================================================

    def fetch_page_content(self, url):
        """Faz request para pagina TDN e extrai conteudo principal como markdown."""
        try:
            resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")

            content_div = (
                soup.find("div", {"id": "main-content"})
                or soup.find("div", {"class": "wiki-content"})
                or soup.find("div", {"id": "content"})
                or soup.find("article")
            )

            if not content_div:
                return None

            # Remover elementos irrelevantes
            for tag in content_div.find_all(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            for tag in content_div.find_all("div", {"class": re.compile(
                    r"breadcrumb|sidebar|navigation|comment|page-metadata")}):
                tag.decompose()

            text = self._html_to_markdown(content_div)
            text = text.strip()

            if len(text) < CHUNK_MIN_CHARS:
                return None

            return text

        except requests.RequestException as e:
            logger.warning("Erro ao acessar %s: %s", url, e)
            return None
        except Exception as e:
            logger.warning("Erro ao processar %s: %s", url, e)
            return None

    def _html_to_markdown(self, element):
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
                lang = self._detect_code_language(code)
                lines.append(f"\n```{lang}\n{code.strip()}\n```\n")
            elif tag_name == "code":
                lines.append(f"`{text}`")
            elif tag_name == "table":
                lines.append(self._table_to_markdown(child))
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
                inner = self._html_to_markdown(child)
                if inner.strip():
                    lines.append(inner)

        return "\n".join(lines)

    def _detect_code_language(self, code):
        """Detecta linguagem de um bloco de codigo."""
        code_lower = code.lower()
        if any(kw in code_lower for kw in ["function ", "local ", "user function", "beginsql"]):
            return "advpl"
        elif any(kw in code_lower for kw in ["select ", "from ", "where ", "insert ", "create table"]):
            return "sql"
        elif any(kw in code_lower for kw in ["def ", "import ", "class ", "self."]):
            return "python"
        elif any(kw in code_lower for kw in ["{", "var ", "const ", "function("]):
            return "javascript"
        return ""

    def _table_to_markdown(self, table_element):
        """Converte tabela HTML para Markdown."""
        rows = []
        for tr in table_element.find_all("tr"):
            cells = []
            for td in tr.find_all(["td", "th"]):
                cells.append(td.get_text(separator=" ", strip=True).replace("|", "\\|"))
            if cells:
                rows.append(cells)

        if not rows:
            return ""

        max_cols = max(len(r) for r in rows)
        for r in rows:
            while len(r) < max_cols:
                r.append("")

        lines = []
        lines.append("| " + " | ".join(rows[0]) + " |")
        lines.append("| " + " | ".join(["---"] * max_cols) + " |")
        for row in rows[1:]:
            lines.append("| " + " | ".join(row) + " |")

        return "\n" + "\n".join(lines) + "\n"

    # =================================================================
    # CHUNKING SEMANTICO
    # =================================================================

    def chunk_content(self, content, page_title=""):
        """Divide conteudo em chunks semanticos respeitando estrutura.

        Regras:
        - Blocos de codigo nunca sao cortados
        - Tabelas ficam inteiras em um chunk
        - Secoes (headings) sao separadores naturais
        - Chunks grandes sao subdivididos com overlap
        """
        sections = self._split_by_sections(content, page_title)
        chunks = []

        for section in sections:
            section_chunks = self._split_large_section(section)
            chunks.extend(section_chunks)

        # Classificar tipo de conteudo
        for chunk in chunks:
            chunk["content_type"] = self._classify_content(chunk["content"])

        return chunks

    def _split_by_sections(self, content, default_title=""):
        """Divide conteudo por headings markdown."""
        sections = []
        current_title = default_title
        current_lines = []

        for line in content.split("\n"):
            heading_match = re.match(r"^(#{1,4})\s+(.+)$", line)
            if heading_match:
                # Salvar secao anterior
                if current_lines:
                    text = "\n".join(current_lines).strip()
                    if len(text) >= CHUNK_MIN_CHARS:
                        sections.append({
                            "title": current_title,
                            "content": text,
                        })
                current_title = heading_match.group(2).strip()
                current_lines = [line]
            else:
                current_lines.append(line)

        # Ultima secao
        if current_lines:
            text = "\n".join(current_lines).strip()
            if len(text) >= CHUNK_MIN_CHARS:
                sections.append({
                    "title": current_title,
                    "content": text,
                })

        # Se nao encontrou secoes, retorna conteudo inteiro
        if not sections:
            sections = [{"title": default_title, "content": content.strip()}]

        return sections

    def _split_large_section(self, section):
        """Subdivide secao grande em chunks menores com overlap."""
        text = section["content"]
        if len(text) <= CHUNK_MAX_CHARS:
            return [section]

        chunks = []
        start = 0
        while start < len(text):
            end = min(start + CHUNK_MAX_CHARS, len(text))

            if end < len(text):
                # Tentar quebrar em linha vazia
                break_pos = text.rfind("\n\n", start + CHUNK_MAX_CHARS // 2, end)
                if break_pos > start:
                    end = break_pos
                else:
                    # Tentar quebrar em fim de bloco de codigo
                    code_break = text.rfind("\n```\n", start + CHUNK_MAX_CHARS // 2, end)
                    if code_break > start:
                        end = code_break + 4  # incluir o ```

            chunk_text = text[start:end].strip()
            if chunk_text and len(chunk_text) >= CHUNK_MIN_CHARS:
                part = len(chunks) + 1
                chunks.append({
                    "title": f"{section['title']} (parte {part})" if len(text) > CHUNK_MAX_CHARS else section["title"],
                    "content": chunk_text,
                })

            start = max(start + 1, end - CHUNK_OVERLAP)

        return chunks

    def _classify_content(self, text):
        """Classifica tipo predominante do conteudo."""
        code_blocks = len(re.findall(r"```\w*\n", text))
        table_markers = text.count("| --- |")
        text_lines = len([l for l in text.split("\n") if l.strip() and not l.startswith("|") and not l.startswith("```")])

        if code_blocks > 0 and code_blocks * 10 > text_lines:
            return "code"
        elif table_markers > 0 and table_markers * 5 > text_lines:
            return "table"
        return "text"

    def _hash_content(self, text):
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    def _approx_tokens(self, text):
        """Estimativa grosseira de tokens (~4 chars por token em portugues)."""
        return len(text) // 4

    # =================================================================
    # REGISTRO DE PAGINAS NO POSTGRESQL
    # =================================================================

    def register_pages(self, source, pages):
        """Registra paginas na tabela tdn_pages (ignora duplicatas por URL).

        Returns:
            tuple: (inseridas, ja_existentes)
        """
        inserted = 0
        existing = 0

        with TransactionContext() as (conn, cursor):
            for page in pages:
                cursor.execute(
                    "SELECT id FROM tdn_pages WHERE page_url = %s",
                    (page["url"],)
                )
                if cursor.fetchone():
                    existing += 1
                    continue

                cursor.execute("""
                    INSERT INTO tdn_pages (source, page_title, page_url, breadcrumb, status)
                    VALUES (%s, %s, %s, %s, 'pending')
                """, (source, page["title"], page["url"], page.get("breadcrumb", "")))
                inserted += 1

        logger.info("Paginas registradas: %d novas, %d ja existentes", inserted, existing)
        return inserted, existing

    def get_pending_pages(self, source=None, limit=100):
        """Retorna paginas pendentes de scraping."""
        conn = get_db()
        try:
            cursor = conn.cursor()
            if source:
                cursor.execute("""
                    SELECT id, source, page_title, page_url, breadcrumb
                    FROM tdn_pages WHERE status = 'pending' AND source = %s
                    ORDER BY id LIMIT %s
                """, (source, limit))
            else:
                cursor.execute("""
                    SELECT id, source, page_title, page_url, breadcrumb
                    FROM tdn_pages WHERE status = 'pending'
                    ORDER BY id LIMIT %s
                """, (limit,))
            return cursor.fetchall()
        finally:
            release_db_connection(conn)

    # =================================================================
    # INGESTAO COMPLETA: SCRAPE + CHUNK + PERSIST
    # =================================================================

    def scrape_and_ingest_page(self, page_row):
        """Faz scraping de uma pagina e ingere os chunks.

        Args:
            page_row: dict com id, page_url, page_title, breadcrumb

        Returns:
            int: numero de chunks inseridos (0 se erro)
        """
        page_id = page_row["id"]
        url = page_row["page_url"]
        title = page_row["page_title"]

        content = self.fetch_page_content(url)

        if not content:
            self._update_page_status(page_id, "empty", error_message="Sem conteudo extraivel")
            return 0

        content_hash = self._hash_content(content)

        # Chunking
        chunks = self.chunk_content(content, page_title=title)

        if not chunks:
            self._update_page_status(page_id, "empty", error_message="Nenhum chunk gerado")
            return 0

        # Persistir chunks
        inserted = self._persist_chunks(page_id, chunks)

        # Atualizar pagina
        self._update_page_status(
            page_id, "done",
            content_hash=content_hash,
            content_length=len(content),
            chunks_count=inserted
        )

        return inserted

    def _persist_chunks(self, page_id, chunks):
        """Persiste chunks no PostgreSQL."""
        inserted = 0

        with TransactionContext() as (conn, cursor):
            # Remover chunks antigos desta pagina (re-ingestao)
            cursor.execute("DELETE FROM tdn_chunks WHERE page_id = %s", (page_id,))

            for i, chunk in enumerate(chunks):
                content_hash = self._hash_content(chunk["content"])
                cursor.execute("""
                    INSERT INTO tdn_chunks
                        (page_id, chunk_index, content, content_type, section_title,
                         tokens_approx, content_hash, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    page_id, i, chunk["content"], chunk["content_type"],
                    chunk.get("title", ""),
                    self._approx_tokens(chunk["content"]),
                    content_hash,
                    json.dumps({"source_section": chunk.get("title", "")}),
                ))
                inserted += 1

        return inserted

    def _update_page_status(self, page_id, status, **kwargs):
        """Atualiza status de uma pagina."""
        with TransactionContext() as (conn, cursor):
            sets = ["status = %s", "updated_at = NOW()"]
            params = [status]

            if status == "done":
                sets.append("scraped_at = NOW()")

            for key in ("content_hash", "content_length", "chunks_count", "error_message"):
                if key in kwargs:
                    sets.append(f"{key} = %s")
                    params.append(kwargs[key])

            params.append(page_id)
            cursor.execute(f"UPDATE tdn_pages SET {', '.join(sets)} WHERE id = %s", params)

    # =================================================================
    # PIPELINE COMPLETO
    # =================================================================

    def ingest_from_json(self, json_filename, source, max_pages=None,
                         scrape=True, workers=1):
        """Pipeline completo: JSON → registrar paginas → scrape → chunk → persist.

        Args:
            json_filename: nome do arquivo JSON na pasta tdn_scraper/
            source: identificador da fonte (ex: 'framework', 'advpl', 'tlpp', 'rest')
            max_pages: limite de paginas a processar (None = todas)
            scrape: se True, faz scraping do conteudo; se False, apenas registra paginas
            workers: numero de threads paralelas (default: 1, max: 6)

        Returns:
            dict com estatisticas
        """
        json_path = os.path.join(self.scraper_dir, json_filename)
        if not os.path.isfile(json_path):
            raise FileNotFoundError(f"Arquivo nao encontrado: {json_path}")

        workers = max(1, min(workers, 6))  # limitar entre 1 e 6

        logger.info("=== Ingestao TDN: %s (source=%s, workers=%d) ===",
                     json_filename, source, workers)

        # 1. Ler arvore
        with open(json_path, "r", encoding="utf-8") as f:
            tree = json.load(f)

        pages = self.extract_pages_from_tree(tree)
        logger.info("Paginas folha encontradas: %d", len(pages))

        # 2. Registrar paginas no PG
        new_pages, existing = self.register_pages(source, pages)

        stats = {
            "source": source,
            "json_file": json_filename,
            "total_pages_in_tree": len(pages),
            "new_pages_registered": new_pages,
            "already_registered": existing,
            "pages_scraped": 0,
            "chunks_created": 0,
            "errors": 0,
            "workers": workers,
            "started_at": datetime.now().isoformat(),
        }

        if not scrape:
            logger.info("Modo registro apenas. %d paginas registradas.", new_pages)
            return stats

        # 3. Criar run de controle
        run_id = self._create_run(source, len(pages))

        # 4. Processar paginas pendentes
        pending = self.get_pending_pages(source=source, limit=max_pages or 9999)
        if max_pages:
            pending = pending[:max_pages]
        total = len(pending)

        if workers == 1:
            # Modo sequencial (original)
            self._scrape_sequential(pending, stats)
        else:
            # Modo paralelo com ThreadPoolExecutor
            self._scrape_parallel(pending, stats, workers)

        # 5. Finalizar run
        self._finish_run(run_id, stats)

        stats["finished_at"] = datetime.now().isoformat()
        logger.info(
            "=== Ingestao concluida: %d paginas, %d chunks, %d erros (workers=%d) ===",
            stats["pages_scraped"], stats["chunks_created"], stats["errors"], workers
        )
        return stats

    def _scrape_sequential(self, pending, stats):
        """Processa paginas sequencialmente (1 thread)."""
        total = len(pending)
        for i, page in enumerate(pending):
            logger.info("[%d/%d] %s", i + 1, total, page["page_title"])
            try:
                chunks_count = self.scrape_and_ingest_page(page)
                if chunks_count > 0:
                    stats["pages_scraped"] += 1
                    stats["chunks_created"] += chunks_count
                else:
                    stats["errors"] += 1
            except Exception as e:
                logger.error("Erro ao processar pagina %s: %s", page["page_url"], e)
                self._update_page_status(page["id"], "error", error_message=str(e)[:500])
                stats["errors"] += 1
            time.sleep(REQUEST_DELAY)

    def _scrape_parallel(self, pending, stats, workers):
        """Processa paginas em paralelo com ThreadPoolExecutor.

        Rate limiting distribuido: cada worker espera REQUEST_DELAY * workers
        entre requests, garantindo que o rate global nao exceda 1/REQUEST_DELAY req/s.
        """
        total = len(pending)
        stats_lock = threading.Lock()
        processed = [0]  # lista para mutabilidade em closure

        # Delay por worker para manter rate global
        worker_delay = REQUEST_DELAY * workers * 0.6  # 60% do teorico (overlap natural)

        def _process_page(page):
            try:
                chunks_count = self.scrape_and_ingest_page(page)
                with stats_lock:
                    processed[0] += 1
                    if chunks_count > 0:
                        stats["pages_scraped"] += 1
                        stats["chunks_created"] += chunks_count
                    else:
                        stats["errors"] += 1
                    if processed[0] % 50 == 0:
                        logger.info(
                            "[%d/%d] Progresso paralelo (workers=%d)",
                            processed[0], total, workers
                        )
            except Exception as e:
                logger.error("Erro ao processar %s: %s", page["page_url"], e)
                self._update_page_status(page["id"], "error", error_message=str(e)[:500])
                with stats_lock:
                    processed[0] += 1
                    stats["errors"] += 1
            time.sleep(worker_delay)

        logger.info("Iniciando scraping paralelo: %d paginas, %d workers", total, workers)

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_process_page, page): page for page in pending}
            for future in as_completed(futures):
                # Exceções já tratadas dentro de _process_page
                future.result()

    # =================================================================
    # INGESTAO A PARTIR DE MD JA EXISTENTES (sem scraping)
    # =================================================================

    def ingest_from_markdown(self, md_filename, source):
        """Ingere conteudo de um .md ja existente (knowledge base gerada anteriormente).

        Suporta dois formatos:
        1. Artigos com URL (scraper_tdn_content.py): ## Titulo\\n> URL: ...
        2. Indices de links (scraper_tdn_advpl.py): ### Titulo\\n[link](url)

        Returns:
            dict com estatisticas
        """
        md_path = os.path.join(self.scraper_dir, md_filename)
        if not os.path.isfile(md_path):
            raise FileNotFoundError(f"Arquivo nao encontrado: {md_path}")

        logger.info("=== Ingestao MD: %s (source=%s) ===", md_filename, source)

        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Detectar formato: se tem "> URL:" e muito conteudo entre secoes, e formato artigo
        has_url_markers = "> URL:" in content
        # Se tem poucos ## mas muitos ### e links, e formato indice
        h2_count = len(re.findall(r"\n## ", content))
        link_count = len(re.findall(r"\[.+?\]\(https?://tdn\.totvs\.com", content))

        if has_url_markers and h2_count > 3:
            return self._ingest_md_articles(content, source)
        else:
            return self._ingest_md_index(content, source, md_filename)

    def _ingest_md_articles(self, content, source):
        """Ingere .md no formato artigo (## Titulo + > URL: + conteudo)."""
        articles = re.split(r"\n## ", content)
        stats = {"source": source, "pages": 0, "chunks": 0, "errors": 0}

        for article in articles[1:]:
            lines = article.split("\n")
            title = lines[0].strip()

            url = ""
            url_match = re.search(r"> URL: (.+)", article)
            if url_match:
                url = url_match.group(1).strip()

            if not url:
                link_match = re.search(r"\[.+?\]\((https?://tdn\.totvs\.com[^\)]+)\)", article)
                if link_match:
                    url = link_match.group(1)

            if not url or not title:
                continue

            page_id = self._ensure_page(source, title, url)

            article_content = "\n".join(lines[1:]).strip()
            if len(article_content) < CHUNK_MIN_CHARS:
                continue

            chunks = self.chunk_content(article_content, page_title=title)
            if chunks:
                inserted = self._persist_chunks(page_id, chunks)
                self._update_page_status(
                    page_id, "done",
                    content_hash=self._hash_content(article_content),
                    content_length=len(article_content),
                    chunks_count=inserted
                )
                stats["pages"] += 1
                stats["chunks"] += inserted
            else:
                stats["errors"] += 1

        return stats

    def _ingest_md_index(self, content, source, filename):
        """Ingere .md no formato indice (### Secoes com links [titulo](url)).

        Agrupa o conteudo por secoes (###/####) e gera chunks com os links
        e textos de cada secao. Cada secao vira uma 'pagina' virtual.
        """
        stats = {"source": source, "pages": 0, "chunks": 0, "errors": 0}

        # Dividir por secoes (## ou ###)
        sections = re.split(r"\n(?=#{2,4}\s+)", content)

        for section in sections:
            if not section.strip():
                continue

            # Extrair titulo da secao
            heading_match = re.match(r"(#{2,4})\s+(.+)", section)
            if not heading_match:
                continue

            title = heading_match.group(2).strip()
            section_body = section[heading_match.end():].strip()

            if len(section_body) < CHUNK_MIN_CHARS:
                continue

            # Extrair primeira URL da secao como URL representativa
            url = ""
            # Link com emoji (🔗 https://...)
            emoji_link = re.search(r"🔗\s*(https?://\S+)", section_body)
            if emoji_link:
                url = emoji_link.group(1).strip()
            else:
                # Link markdown
                md_link = re.search(r"\[.+?\]\((https?://tdn\.totvs\.com[^\)]+)\)", section_body)
                if md_link:
                    url = md_link.group(1)

            if not url:
                # Gerar URL sintetica baseada no filename + titulo
                url = f"https://tdn.totvs.com/local/{source}/{self._hash_content(title)}"

            page_id = self._ensure_page(source, title, url)

            chunks = self.chunk_content(section_body, page_title=title)
            if chunks:
                inserted = self._persist_chunks(page_id, chunks)
                self._update_page_status(
                    page_id, "done",
                    content_hash=self._hash_content(section_body),
                    content_length=len(section_body),
                    chunks_count=inserted
                )
                stats["pages"] += 1
                stats["chunks"] += inserted

        return stats

    def _ensure_page(self, source, title, url):
        """Garante que uma pagina existe no PG, retorna page_id."""
        with TransactionContext() as (conn, cursor):
            cursor.execute("SELECT id FROM tdn_pages WHERE page_url = %s", (url,))
            row = cursor.fetchone()
            if row:
                return row["id"]
            cursor.execute("""
                INSERT INTO tdn_pages (source, page_title, page_url, status, scraped_at)
                VALUES (%s, %s, %s, 'done', NOW())
                RETURNING id
            """, (source, title, url))
            return cursor.fetchone()["id"]

        logger.info(
            "=== MD ingestao concluida: %d paginas, %d chunks, %d erros ===",
            stats["pages"], stats["chunks"], stats["errors"]
        )
        return stats

    # =================================================================
    # BUSCA (direto no PostgreSQL — fonte unica da verdade para TDN)
    # =================================================================

    def search(self, query, source=None, content_type=None, limit=10):
        """Busca full-text nos chunks TDN com fallback ILIKE.

        Estrategia:
        1. tsvector (full-text search portugues) — rapida e com ranking
        2. Se tsvector nao encontra nada, fallback com ILIKE nos termos principais

        Args:
            query: texto de busca
            source: filtrar por fonte
            content_type: filtrar por tipo (text, code, table)
            limit: maximo de resultados

        Returns:
            list[dict]: chunks encontrados com rank
        """
        if not query or not query.strip():
            return []

        conn = get_db()
        try:
            cursor = conn.cursor()

            # Filtros opcionais
            extra_conds = []
            extra_params = []
            if source:
                extra_conds.append("p.source = %s")
                extra_params.append(source)
            if content_type:
                extra_conds.append("c.content_type = %s")
                extra_params.append(content_type)

            extra_sql = (" AND " + " AND ".join(extra_conds)) if extra_conds else ""

            # Tentativa 1: tsvector full-text search
            params = [query, query] + extra_params + [limit]
            cursor.execute(f"""
                SELECT c.id, c.content, c.section_title, c.content_type,
                       c.tokens_approx, p.page_title, p.page_url, p.source,
                       ts_rank(c.tsv, plainto_tsquery('portuguese', %s)) AS rank
                FROM tdn_chunks c
                JOIN tdn_pages p ON c.page_id = p.id
                WHERE c.tsv @@ plainto_tsquery('portuguese', %s){extra_sql}
                ORDER BY rank DESC
                LIMIT %s
            """, params)

            results = cursor.fetchall()
            if results:
                return results

            # Fallback: ILIKE nos termos mais relevantes (palavras com 4+ chars)
            terms = [w for w in query.split() if len(w) >= 4][:5]
            if not terms:
                return []

            ilike_parts = " OR ".join(["c.content ILIKE %s"] * len(terms))
            ilike_params = [f"%{t}%" for t in terms]
            params = ilike_params + extra_params + [limit]

            cursor.execute(f"""
                SELECT c.id, c.content, c.section_title, c.content_type,
                       c.tokens_approx, p.page_title, p.page_url, p.source,
                       0.0 AS rank
                FROM tdn_chunks c
                JOIN tdn_pages p ON c.page_id = p.id
                WHERE ({ilike_parts}){extra_sql}
                LIMIT %s
            """, params)

            return cursor.fetchall()
        except Exception as e:
            logger.warning("Erro na busca TDN: %s", e)
            return []
        finally:
            release_db_connection(conn)

    def search_multi(self, queries, limit=10):
        """Busca TDN com multiplas queries, deduplica e ranqueia.

        Executa cada query, combina resultados removendo duplicatas,
        e retorna os top-N por rank.

        Args:
            queries: lista de strings de busca
            limit: maximo de resultados finais

        Returns:
            list[dict]: chunks unicos, ordenados por rank
        """
        seen_ids = set()
        all_results = []

        for q in queries:
            if not q or not q.strip():
                continue
            results = self.search(q, limit=limit)
            for r in results:
                rid = r.get("id")
                if rid and rid not in seen_ids:
                    seen_ids.add(rid)
                    all_results.append(r)

        # Ordenar por rank descendente
        all_results.sort(key=lambda r: r.get("rank", 0), reverse=True)
        return all_results[:limit]

    def search_by_title(self, query, limit=5):
        """Busca nos titulos das paginas e secoes (mais preciso para nomes de rotinas/modulos)."""
        if not query or not query.strip():
            return []

        conn = get_db()
        try:
            cursor = conn.cursor()
            terms = [w for w in query.split() if len(w) >= 3][:5]
            if not terms:
                return []

            conditions = " OR ".join(
                ["c.section_title ILIKE %s OR p.page_title ILIKE %s"] * len(terms)
            )
            params = []
            for t in terms:
                params.extend([f"%{t}%", f"%{t}%"])
            params.append(limit)

            cursor.execute(f"""
                SELECT c.id, c.content, c.section_title, c.content_type,
                       c.tokens_approx, p.page_title, p.page_url, p.source,
                       1.0 AS rank
                FROM tdn_chunks c
                JOIN tdn_pages p ON c.page_id = p.id
                WHERE {conditions}
                LIMIT %s
            """, params)

            return cursor.fetchall()
        except Exception as e:
            logger.warning("Erro busca titulo TDN: %s", e)
            return []
        finally:
            release_db_connection(conn)

    def get_stats(self):
        """Retorna estatisticas da base TDN."""
        conn = get_db()
        try:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    source,
                    COUNT(*) AS total_pages,
                    COUNT(*) FILTER (WHERE status = 'done') AS scraped,
                    COUNT(*) FILTER (WHERE status = 'pending') AS pending,
                    COUNT(*) FILTER (WHERE status = 'error') AS errors,
                    COUNT(*) FILTER (WHERE status = 'empty') AS empty,
                    SUM(chunks_count) AS total_chunks,
                    SUM(content_length) AS total_chars
                FROM tdn_pages
                GROUP BY source
                ORDER BY source
            """)
            return cursor.fetchall()
        finally:
            release_db_connection(conn)

    # =================================================================
    # CONTROLE DE RUNS
    # =================================================================

    def _create_run(self, source, total_pages):
        with TransactionContext() as (conn, cursor):
            cursor.execute("""
                INSERT INTO tdn_scrape_runs (source, total_pages, status)
                VALUES (%s, %s, 'running') RETURNING id
            """, (source, total_pages))
            return cursor.fetchone()["id"]

    def _finish_run(self, run_id, stats):
        with TransactionContext() as (conn, cursor):
            cursor.execute("""
                UPDATE tdn_scrape_runs
                SET scraped_pages = %s, chunked_pages = %s, errors = %s,
                    status = 'done', finished_at = NOW()
                WHERE id = %s
            """, (stats["pages_scraped"], stats["pages_scraped"], stats["errors"], run_id))
