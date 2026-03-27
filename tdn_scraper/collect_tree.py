#!/usr/bin/env python3
"""
Coleta arvore de links de uma pagina TDN usando Playwright.

Uso:
    python collect_tree.py --url "https://tdn.totvs.com/display/public/PROT/Protheus++12" --output protheus12.json
"""

import argparse
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

BASE_URL = "https://tdn.totvs.com"


def expand_tree_node(page, node):
    """Expande um no da arvore clicando no icone."""
    try:
        expand_icon = node.query_selector(".plugin_pagetree_childtoggle_container .aui-icon")
        if not expand_icon:
            return
        # Verificar se o icone esta visivel antes de clicar
        if not expand_icon.is_visible():
            return
        parent_container = node.query_selector(".plugin_pagetree_children_container")
        if parent_container:
            style = parent_container.get_attribute("style") or ""
            if "display: none" in style or not parent_container.inner_html().strip():
                expand_icon.click(timeout=5000)
                time.sleep(1.0)
        else:
            expand_icon.click(timeout=5000)
            time.sleep(1.0)
    except Exception:
        pass  # Nao conseguiu expandir — seguir em frente


def collect_tree_recursive(page, container, depth=0, max_depth=8):
    """Coleta recursivamente os itens da arvore."""
    if depth > max_depth:
        return []

    items = []
    child_nodes = container.query_selector_all(":scope > li.plugin_pagetree_children_list_item")
    if not child_nodes:
        child_nodes = container.query_selector_all(":scope > li")

    for node in child_nodes:
        link = node.query_selector(":scope > div a.plugin_pagetree_childrenlink_content, :scope > div span a")
        if not link:
            link = node.query_selector("a")
        if not link:
            continue

        title = link.inner_text().strip()
        href = link.get_attribute("href") or ""
        if not title:
            continue
        if href and not href.startswith("http"):
            href = BASE_URL + href

        item = {"title": title, "url": href, "depth": depth, "children": []}
        prefix = "  " * depth
        print(f"{prefix}[{depth}] {title}")

        expand_tree_node(page, node)

        children_container = node.query_selector(":scope > .plugin_pagetree_children_container > ul")
        if not children_container:
            children_container = node.query_selector(":scope > ul")

        if children_container:
            item["children"] = collect_tree_recursive(page, children_container, depth + 1, max_depth)

        items.append(item)

    return items


def collect_content_links(page):
    """Fallback: coleta links da area de conteudo principal."""
    items = []
    content_area = page.query_selector("#main-content, .wiki-content, #content")
    if not content_area:
        return items

    links = content_area.query_selector_all("a[href*='/display/']")
    seen = set()
    for link in links:
        title = link.inner_text().strip()
        href = link.get_attribute("href") or ""
        if title and href and title not in seen:
            seen.add(title)
            if not href.startswith("http"):
                href = BASE_URL + href
            items.append({"title": title, "url": href, "depth": 0, "children": []})
            print(f"  {title}")

    return items


def count_items(items):
    """Conta total de itens recursivamente."""
    total = 0
    for item in items:
        total += 1
        if item.get("children"):
            total += count_items(item["children"])
    return total


def main():
    parser = argparse.ArgumentParser(description="Coleta arvore TDN via Playwright")
    parser.add_argument("--url", required=True, help="URL da pagina raiz do TDN")
    parser.add_argument("--output", required=True, help="Arquivo JSON de saida")
    parser.add_argument("--max-depth", type=int, default=8, help="Profundidade maxima (default: 8)")

    args = parser.parse_args()
    output_path = Path(__file__).parent / args.output

    print(f"Coletando arvore de: {args.url}")
    print(f"Saida: {output_path}")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0",
            viewport={"width": 1920, "height": 1080},
        )
        page = context.new_page()

        print(f"Acessando {args.url}...")
        page.goto(args.url, wait_until="networkidle", timeout=30000)
        time.sleep(3)

        all_items = []

        # Estrategia 1: Arvore lateral (pagetree)
        print("\nBuscando arvore lateral...")
        tree_container = page.query_selector(".plugin_pagetree_children_container ul, #page-tree ul")
        if tree_container:
            print("Arvore encontrada!")
            all_items = collect_tree_recursive(page, tree_container, max_depth=args.max_depth)

        # Estrategia 2: Links do conteudo
        if not all_items:
            print("\nFallback: coletando links do conteudo...")
            all_items = collect_content_links(page)

        # Estrategia 3: Todos os links internos
        if not all_items:
            print("\nFallback: todos os links internos...")
            all_links = page.query_selector_all("a[href]")
            seen = set()
            for link in all_links:
                href = link.get_attribute("href") or ""
                title = link.inner_text().strip()
                if "/display/" in href and title and title not in seen:
                    seen.add(title)
                    if not href.startswith("http"):
                        href = BASE_URL + href
                    all_items.append({"title": title, "url": href, "depth": 0, "children": []})

        browser.close()

    if not all_items:
        print("\nNenhum item coletado!")
        return

    total = count_items(all_items)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)

    print(f"\nConcluido! {total} itens salvos em {output_path}")


if __name__ == "__main__":
    main()
