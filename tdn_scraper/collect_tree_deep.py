#!/usr/bin/env python3
"""
Coleta arvore profunda do TDN navegando cada modulo individualmente.

Usa multithread para processar varios modulos em paralelo.
Cada thread abre seu proprio browser e navega o modulo.

Uso:
    python collect_tree_deep.py --input protheus12.json --output protheus12_full.json --workers 4
"""

import argparse
import json
import time
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from playwright.sync_api import sync_playwright

BASE_URL = "https://tdn.totvs.com"


def collect_page_links(url, max_depth=5):
    """Navega uma pagina TDN e coleta todos os links internos recursivamente.

    Usa requests + BeautifulSoup (mais rapido que Playwright para paginas individuais).
    """
    import requests
    from bs4 import BeautifulSoup

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    }

    visited = set()
    results = []

    def _crawl(page_url, title, depth, breadcrumb):
        if depth > max_depth:
            return
        if page_url in visited:
            return

        visited.add(page_url)
        time.sleep(0.3)  # rate limit

        try:
            resp = requests.get(page_url, headers=HEADERS, timeout=20, allow_redirects=True)
            if resp.status_code != 200:
                return
        except Exception:
            return

        soup = BeautifulSoup(resp.text, "html.parser")

        item = {
            "title": title,
            "url": page_url,
            "depth": depth,
            "breadcrumb": breadcrumb,
            "children": [],
        }

        # Coletar links filhos da arvore lateral
        pagetree = soup.find("div", {"class": "plugin_pagetree"})
        child_links = []

        if pagetree:
            for a in pagetree.find_all("a", href=True):
                href = a.get("href", "")
                link_title = a.get_text(strip=True)
                if not link_title or not href:
                    continue
                if not href.startswith("http"):
                    href = BASE_URL + href
                if href not in visited and "tdn.totvs.com" in href:
                    child_links.append((href, link_title))

        # Fallback: links no conteudo principal
        if not child_links:
            content = (
                soup.find("div", {"id": "main-content"})
                or soup.find("div", {"class": "wiki-content"})
            )
            if content:
                for a in content.find_all("a", href=True):
                    href = a.get("href", "")
                    link_title = a.get_text(strip=True)
                    if not link_title or not href or len(link_title) < 3:
                        continue
                    if not href.startswith("http"):
                        href = BASE_URL + href
                    if href not in visited and "tdn.totvs.com" in href:
                        child_links.append((href, link_title))

        # Crawl filhos
        for child_url, child_title in child_links:
            child_crumb = f"{breadcrumb} > {child_title}"
            child_item = _crawl(child_url, child_title, depth + 1, child_crumb)
            if child_item:
                item["children"].append(child_item)

        results.append(item)
        return item

    _crawl(url, os.path.basename(url).replace("+", " "), 0, "")
    return results


def process_module(module, worker_id):
    """Processa um modulo: navega e coleta sub-links."""
    title = module["title"]
    url = module["url"]
    print(f"[W{worker_id}] Iniciando: {title}")

    start = time.time()
    items = collect_page_links(url, max_depth=3)
    elapsed = time.time() - start

    # Contar total recursivo
    def count(tree):
        n = 0
        for item in tree:
            n += 1
            n += count(item.get("children", []))
        return n

    total = count(items)
    print(f"[W{worker_id}] {title}: {total} itens em {elapsed:.0f}s")

    return {
        "title": title,
        "url": url,
        "depth": 0,
        "children": items[0]["children"] if items else [],
    }


def main():
    parser = argparse.ArgumentParser(description="Coleta arvore TDN profunda com multithread")
    parser.add_argument("--input", required=True, help="JSON da arvore rasa (ex: protheus12.json)")
    parser.add_argument("--output", required=True, help="JSON de saida completo")
    parser.add_argument("--workers", type=int, default=4, help="Threads paralelas (default: 4)")
    parser.add_argument("--max-depth", type=int, default=3, help="Profundidade maxima por modulo (default: 3)")

    args = parser.parse_args()

    input_path = Path(__file__).parent / args.input
    output_path = Path(__file__).parent / args.output

    with open(input_path, "r", encoding="utf-8") as f:
        tree = json.load(f)

    # Extrair modulos (children do primeiro item)
    modules = []
    for item in tree:
        if item.get("children"):
            modules.extend(item["children"])
        elif "tdn.totvs.com" in item.get("url", ""):
            modules.append(item)

    # Filtrar modulos relevantes (ignorar itens sem URL TDN valida)
    modules = [m for m in modules if m.get("url") and "tdn.totvs.com" in m["url"]]

    print(f"Modulos a processar: {len(modules)}")
    print(f"Workers: {args.workers}")
    print("=" * 60)

    results = []
    start = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {}
        for i, module in enumerate(modules):
            future = executor.submit(process_module, module, i % args.workers)
            futures[future] = module

        for future in as_completed(futures):
            try:
                result = future.result()
                if result:
                    results.append(result)
            except Exception as e:
                module = futures[future]
                print(f"[ERRO] {module['title']}: {e}")

    elapsed = time.time() - start

    # Salvar
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # Contar total
    def count_all(items):
        n = 0
        for item in items:
            n += 1
            n += count_all(item.get("children", []))
        return n

    total = count_all(results)
    print(f"\n{'=' * 60}")
    print(f"Concluido em {elapsed:.0f}s")
    print(f"Modulos: {len(results)}")
    print(f"Total itens: {total}")
    print(f"Salvo em: {output_path}")


if __name__ == "__main__":
    main()
