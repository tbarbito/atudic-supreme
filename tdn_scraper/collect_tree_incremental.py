#!/usr/bin/env python3
"""
Coleta arvore profunda do TDN salvando incrementalmente.

Cada modulo concluido e salvo imediatamente no JSON de saida.
Se o processo morrer, os modulos ja coletados estao preservados.

Uso:
    python collect_tree_incremental.py --input protheus12.json --output protheus12_full.json --workers 6 --skip "Plano de Saúde"
"""

import argparse
import json
import os
import re
import time
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://tdn.totvs.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}

# Lock para salvar JSON de forma thread-safe
_save_lock = threading.Lock()


def collect_page_links(url, max_depth=3):
    """Crawl recursivo de uma pagina TDN."""
    visited = set()

    def _crawl(page_url, title, depth, breadcrumb):
        if depth > max_depth or page_url in visited:
            return None
        visited.add(page_url)
        time.sleep(0.3)

        try:
            resp = requests.get(page_url, headers=HEADERS, timeout=20, allow_redirects=True)
            if resp.status_code != 200:
                return None
        except Exception:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")
        item = {"title": title, "url": page_url, "depth": depth, "breadcrumb": breadcrumb, "children": []}

        # Links da arvore lateral
        child_links = []
        pagetree = soup.find("div", {"class": "plugin_pagetree"})
        if pagetree:
            for a in pagetree.find_all("a", href=True):
                href = a.get("href", "")
                lt = a.get_text(strip=True)
                if lt and href:
                    if not href.startswith("http"):
                        href = BASE_URL + href
                    if href not in visited and "tdn.totvs.com" in href:
                        child_links.append((href, lt))

        # Fallback: links no conteudo
        if not child_links:
            content = soup.find("div", {"id": "main-content"}) or soup.find("div", {"class": "wiki-content"})
            if content:
                for a in content.find_all("a", href=True):
                    href = a.get("href", "")
                    lt = a.get_text(strip=True)
                    if lt and href and len(lt) >= 3:
                        if not href.startswith("http"):
                            href = BASE_URL + href
                        if href not in visited and "tdn.totvs.com" in href:
                            child_links.append((href, lt))

        for child_url, child_title in child_links:
            child = _crawl(child_url, child_title, depth + 1, f"{breadcrumb} > {child_title}")
            if child:
                item["children"].append(child)

        return item

    result = _crawl(url, "", 0, "")
    return result


def save_results(output_path, results):
    """Salva resultados incrementalmente no JSON."""
    with _save_lock:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)


def count_items(item):
    """Conta itens recursivamente."""
    n = 1
    for child in item.get("children", []):
        n += count_items(child)
    return n


def process_module(module, output_path, results, worker_id, max_depth):
    """Processa um modulo e salva incrementalmente."""
    title = module["title"]
    url = module["url"]
    print(f"[W{worker_id}] Iniciando: {title}", flush=True)

    start = time.time()
    result = collect_page_links(url, max_depth=max_depth)
    elapsed = time.time() - start

    if result:
        result["title"] = title
        total = count_items(result)
        print(f"[W{worker_id}] {title}: {total} itens em {elapsed:.0f}s", flush=True)

        with _save_lock:
            results.append(result)
        save_results(output_path, results)
        return total
    else:
        print(f"[W{worker_id}] {title}: 0 itens", flush=True)
        return 0


def main():
    parser = argparse.ArgumentParser(description="Coleta arvore TDN incremental")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--max-depth", type=int, default=3)
    parser.add_argument("--skip", nargs="*", default=[], help="Modulos para pular (substring match)")

    args = parser.parse_args()
    input_path = Path(__file__).parent / args.input
    output_path = Path(__file__).parent / args.output

    with open(input_path, "r", encoding="utf-8") as f:
        tree = json.load(f)

    # Extrair modulos
    modules = []
    for item in tree:
        if item.get("children"):
            modules.extend(item["children"])
        elif "tdn.totvs.com" in item.get("url", ""):
            modules.append(item)

    modules = [m for m in modules if m.get("url") and "tdn.totvs.com" in m["url"]]

    # Aplicar skip
    if args.skip:
        original = len(modules)
        modules = [m for m in modules if not any(s.lower() in m["title"].lower() for s in args.skip)]
        print(f"Modulos: {len(modules)} (skipped {original - len(modules)})")

    # Carregar resultados ja existentes (resume)
    results = []
    done_urls = set()
    if output_path.exists():
        with open(output_path, "r", encoding="utf-8") as f:
            results = json.load(f)
        done_urls = {r["url"] for r in results}
        print(f"Resumindo: {len(results)} modulos ja coletados")

    # Filtrar modulos pendentes
    modules = [m for m in modules if m["url"] not in done_urls]

    print(f"Pendentes: {len(modules)}")
    print(f"Workers: {args.workers}")
    print("=" * 60, flush=True)

    if not modules:
        print("Nada a processar!")
        return

    start = time.time()
    total_items = 0

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {}
        for i, module in enumerate(modules):
            future = executor.submit(process_module, module, output_path, results, i % args.workers, args.max_depth)
            futures[future] = module

        for future in as_completed(futures):
            try:
                total_items += future.result() or 0
            except Exception as e:
                print(f"[ERRO] {futures[future]['title']}: {e}", flush=True)

    elapsed = time.time() - start
    grand_total = sum(count_items(r) for r in results)

    print(f"\n{'=' * 60}")
    print(f"Concluido em {elapsed:.0f}s")
    print(f"Modulos processados: {len(results)}")
    print(f"Total itens: {grand_total}")
    print(f"Salvo em: {output_path}", flush=True)


if __name__ == "__main__":
    main()
