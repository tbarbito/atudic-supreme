#!/usr/bin/env python3
"""
Robô de scraping da TDN TOTVS - Página AdvPL
Navega na árvore de submenus do Confluence e coleta a estrutura completa.
Gera um arquivo .md estruturado.
"""

import json
import time
import re
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout


BASE_URL = "https://tdn.totvs.com"
START_URL = f"{BASE_URL}/display/tec/AdvPL"
OUTPUT_MD = Path(__file__).parent / "tdn_knowledge_base.md"
OUTPUT_JSON = Path(__file__).parent / "advpl_tdn_tree.json"


def wait_and_retry(page, selector, timeout=10000, retries=2):
    """Tenta localizar um elemento com retries."""
    for i in range(retries):
        try:
            page.wait_for_selector(selector, timeout=timeout)
            return True
        except PWTimeout:
            if i < retries - 1:
                page.reload()
                time.sleep(2)
    return False


def expand_tree_node(page, node):
    """Expande um nó da árvore clicando no ícone de expansão."""
    try:
        # Confluence usa .plugin_pagetree_children_container ou similar
        expand_icon = node.query_selector(".plugin_pagetree_childtoggle_container .aui-icon")
        if expand_icon:
            # Verifica se já está expandido
            parent_container = node.query_selector(".plugin_pagetree_children_container")
            if parent_container:
                style = parent_container.get_attribute("style") or ""
                if "display: none" in style or not parent_container.inner_html().strip():
                    expand_icon.click()
                    time.sleep(1.5)
            else:
                expand_icon.click()
                time.sleep(1.5)
    except Exception as e:
        print(f"  [warn] Erro ao expandir nó: {e}")


def collect_tree_recursive(page, container, depth=0):
    """Coleta recursivamente os itens da árvore de páginas."""
    items = []

    # Busca links de páginas filhas neste nível
    child_nodes = container.query_selector_all(":scope > li.plugin_pagetree_children_list_item")

    if not child_nodes:
        # Tenta seletor alternativo
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

        item = {
            "title": title,
            "url": href,
            "depth": depth,
            "children": []
        }

        print(f"{'  ' * depth}📄 {title}")

        # Tenta expandir para ver filhos
        expand_tree_node(page, node)

        # Busca container de filhos
        children_container = node.query_selector(":scope > .plugin_pagetree_children_container > ul")
        if not children_container:
            children_container = node.query_selector(":scope > ul")

        if children_container:
            item["children"] = collect_tree_recursive(page, children_container, depth + 1)

        items.append(item)

    return items


def collect_page_content_links(page):
    """Coleta links da área de conteúdo principal da página (alternativa)."""
    items = []
    content_area = page.query_selector("#main-content, .wiki-content, #content")
    if not content_area:
        return items

    links = content_area.query_selector_all("a[href*='/display/tec/']")
    for link in links:
        title = link.inner_text().strip()
        href = link.get_attribute("href") or ""
        if title and href:
            if not href.startswith("http"):
                href = BASE_URL + href
            items.append({"title": title, "url": href, "depth": 0, "children": []})
            print(f"  📄 {title}")

    return items


def tree_to_markdown(items, depth=0):
    """Converte a árvore em Markdown estruturado."""
    lines = []
    for item in items:
        indent = "  " * depth
        title = item["title"]
        url = item["url"]

        if depth == 0:
            lines.append(f"\n### {title}")
            if url:
                lines.append(f"🔗 {url}")
        elif depth == 1:
            lines.append(f"\n{indent}#### {title}")
            if url:
                lines.append(f"{indent}🔗 {url}")
        else:
            if url:
                lines.append(f"{indent}- [{title}]({url})")
            else:
                lines.append(f"{indent}- {title}")

        if item.get("children"):
            lines.extend(tree_to_markdown(item["children"], depth + 1).split("\n"))

    return "\n".join(lines)


def main():
    print("=" * 60)
    print("🤖 TDN Scraper - Coletando árvore AdvPL")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = context.new_page()

        print(f"\n🌐 Acessando {START_URL}...")
        page.goto(START_URL, wait_until="networkidle", timeout=30000)
        time.sleep(3)

        # Salva screenshot para debug
        page.screenshot(path=str(Path(__file__).parent / "debug_page.png"), full_page=True)
        print("📸 Screenshot salvo em debug_page.png")

        # Salva HTML para análise
        html_content = page.content()
        debug_html = Path(__file__).parent / "debug_page.html"
        debug_html.write_text(html_content, encoding="utf-8")
        print(f"📋 HTML salvo em debug_page.html ({len(html_content)} bytes)")

        all_items = []

        # Estratégia 1: Árvore lateral do Confluence (pagetree)
        print("\n🔍 Estratégia 1: Buscando árvore lateral (pagetree)...")
        tree_container = page.query_selector(".plugin_pagetree_children_container ul, #page-tree ul, .acs-side-bar ul")
        if tree_container:
            print("✅ Árvore lateral encontrada!")
            all_items = collect_tree_recursive(page, tree_container)
        else:
            print("⚠️  Árvore lateral não encontrada")

        # Estratégia 2: Links na área de conteúdo
        if not all_items:
            print("\n🔍 Estratégia 2: Coletando links do conteúdo principal...")
            all_items = collect_page_content_links(page)

        # Estratégia 3: Todos os links internos da página
        if not all_items:
            print("\n🔍 Estratégia 3: Coletando todos os links internos...")
            all_links = page.query_selector_all("a[href]")
            seen = set()
            for link in all_links:
                href = link.get_attribute("href") or ""
                title = link.inner_text().strip()
                if "/display/tec/" in href and title and title not in seen:
                    seen.add(title)
                    if not href.startswith("http"):
                        href = BASE_URL + href
                    all_items.append({"title": title, "url": href, "depth": 0, "children": []})
                    print(f"  📄 {title}")

        browser.close()

    if not all_items:
        print("\n❌ Nenhum item coletado. Verifique debug_page.png e debug_page.html")
        return

    # Gera JSON
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)
    print(f"\n💾 JSON salvo em {OUTPUT_JSON}")

    # Gera Markdown
    md_content = f"""# Base de Conhecimento AdvPL — TDN TOTVS

> Fonte: {START_URL}
> Coletado em: {time.strftime('%Y-%m-%d %H:%M:%S')}
> Total de itens: {sum(1 for _ in flatten_items(all_items))}

## Índice de Conteúdo

{tree_to_markdown(all_items)}

---
*Gerado automaticamente pelo TDN Scraper*
"""

    OUTPUT_MD.write_text(md_content, encoding="utf-8")
    print(f"📝 Markdown salvo em {OUTPUT_MD}")
    print(f"\n✅ Concluído! {len(all_items)} itens de nível superior coletados.")


def flatten_items(items):
    """Itera recursivamente por todos os itens."""
    for item in items:
        yield item
        if item.get("children"):
            yield from flatten_items(item["children"])


if __name__ == "__main__":
    main()
