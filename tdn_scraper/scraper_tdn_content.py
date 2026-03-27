#!/usr/bin/env python3
"""
Scraper de conteudo real das paginas TDN TOTVS.

Os scrapers anteriores coletaram a ARVORE de links (indices).
Este scraper navega cada pagina e extrai o CONTEUDO real (texto, tabelas, codigo).

O resultado e salvo em memory/ como .md para ingestao automatica pelo agente.

Uso:
    python3 scraper_tdn_content.py --source tdn_tlpp_v2.json --output memory/tdn_tlpp_content.md --max-pages 200
    python3 scraper_tdn_content.py --source tdn_totvstec_rest.json --output memory/tdn_advpl_content.md --max-pages 500
    python3 scraper_tdn_content.py --source tdn_framework_v2.json --output memory/tdn_framework_content.md --max-pages 300

Requer: pip install requests beautifulsoup4
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Instale as dependencias: pip install requests beautifulsoup4")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Headers para simular browser
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}

# Delay entre requests para nao sobrecarregar o TDN
REQUEST_DELAY = 1.5  # segundos


def extract_urls_from_tree(nodes, results=None):
    """Extrai todas as URLs folha de uma arvore JSON."""
    if results is None:
        results = []
    for node in (nodes if isinstance(nodes, list) else [nodes]):
        title = node.get("title", "")
        url = node.get("url", "")
        children = node.get("children", [])

        if not children and url and "tdn.totvs.com" in url:
            results.append({"title": title, "url": url})

        if children:
            extract_urls_from_tree(children, results)
    return results


def fetch_page_content(url, timeout=30):
    """Faz request para uma pagina TDN e extrai o conteudo principal."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Conteudo principal do Confluence (TDN usa Confluence)
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
        for tag in content_div.find_all("div", {"class": re.compile(r"breadcrumb|sidebar|navigation|comment")}):
            tag.decompose()

        # Converter para texto limpo com formatacao basica
        text = _html_to_markdown(content_div)
        text = text.strip()

        # Filtrar paginas com pouco conteudo
        if len(text) < 50:
            return None

        return text

    except requests.RequestException as e:
        logger.warning("Erro ao acessar %s: %s", url, e)
        return None
    except Exception as e:
        logger.warning("Erro ao processar %s: %s", url, e)
        return None


def _html_to_markdown(element):
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
            prefix = "#" * min(level + 1, 4)  # Offset para ficar como subsecao
            lines.append(f"\n{prefix} {text}\n")
        elif tag_name == "pre" or (tag_name == "div" and "code" in (child.get("class") or [])):
            code = child.get_text(strip=False)
            # Detectar linguagem
            lang = ""
            if any(kw in code.lower() for kw in ["function ", "local ", "return ", "user function"]):
                lang = "advpl"
            elif any(kw in code.lower() for kw in ["select ", "from ", "where ", "insert "]):
                lang = "sql"
            lines.append(f"\n```{lang}\n{code.strip()}\n```\n")
        elif tag_name == "code":
            lines.append(f"`{text}`")
        elif tag_name == "table":
            lines.append(_table_to_markdown(child))
        elif tag_name in ("ul", "ol"):
            for li in child.find_all("li", recursive=False):
                li_text = li.get_text(separator=" ", strip=True)
                if li_text:
                    lines.append(f"- {li_text}")
        elif tag_name == "p":
            lines.append(text)
        elif tag_name == "strong" or tag_name == "b":
            lines.append(f"**{text}**")
        elif tag_name in ("div", "section", "article"):
            # Recursivo para divs
            inner = _html_to_markdown(child)
            if inner.strip():
                lines.append(inner)

    return "\n".join(lines)


def _table_to_markdown(table_element):
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

    # Normalizar largura
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


def scrape_and_save(source_json, output_path, max_pages=200, min_content_len=100):
    """Scrape principal: le arvore JSON, busca conteudo real, salva como MD."""
    logger.info("Carregando arvore de %s...", source_json)

    with open(source_json, "r", encoding="utf-8") as f:
        tree = json.load(f)

    pages = extract_urls_from_tree(tree)
    logger.info("Total de paginas folha: %d (processando ate %d)", len(pages), max_pages)

    # Limitar
    pages = pages[:max_pages]

    results = []
    errors = 0

    for i, page in enumerate(pages):
        title = page["title"]
        url = page["url"]

        logger.info("[%d/%d] %s", i + 1, len(pages), title)

        content = fetch_page_content(url)
        if content and len(content) >= min_content_len:
            results.append({
                "title": title,
                "url": url,
                "content": content,
            })
        else:
            errors += 1

        # Rate limiting
        time.sleep(REQUEST_DELAY)

    # Salvar como MD
    logger.info("Salvando %d paginas em %s...", len(results), output_path)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# Base de Conhecimento TDN — Conteudo Real\n\n")
        f.write(f"> Fonte: {source_json}\n")
        f.write(f"> Coletado em: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"> Paginas processadas: {len(pages)}\n")
        f.write(f"> Paginas com conteudo: {len(results)}\n")
        f.write(f"> Paginas sem conteudo ou erro: {errors}\n\n")
        f.write("---\n\n")

        for item in results:
            f.write(f"## {item['title']}\n")
            f.write(f"> URL: {item['url']}\n\n")
            f.write(item["content"])
            f.write("\n\n---\n\n")

    size_kb = os.path.getsize(output_path) // 1024
    logger.info(
        "Concluido: %d paginas salvas (%d KB). Erros: %d",
        len(results), size_kb, errors,
    )
    return len(results)


def main():
    parser = argparse.ArgumentParser(description="Scraper de conteudo real do TDN TOTVS")
    parser.add_argument("--source", required=True, help="JSON da arvore (ex: tdn_tlpp_v2.json)")
    parser.add_argument("--output", required=True, help="Arquivo .md de saida (ex: memory/tdn_tlpp_content.md)")
    parser.add_argument("--max-pages", type=int, default=200, help="Maximo de paginas a processar (default: 200)")
    parser.add_argument("--min-content", type=int, default=100, help="Conteudo minimo em chars (default: 100)")

    args = parser.parse_args()

    if not os.path.isfile(args.source):
        logger.error("Arquivo fonte nao encontrado: %s", args.source)
        sys.exit(1)

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)

    scrape_and_save(
        source_json=args.source,
        output_path=args.output,
        max_pages=args.max_pages,
        min_content_len=args.min_content,
    )


if __name__ == "__main__":
    main()
