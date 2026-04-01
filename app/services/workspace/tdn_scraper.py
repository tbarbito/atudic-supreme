"""TDN Scraper — fetches PE details from TDN pages using Playwright.

Used on-demand (not bulk scraping). Two main functions:
- fetch_pe_page(url): opens a TDN page and extracts text content
- search_and_fetch_pe(pe_name): searches Google for the PE, finds TDN link, fetches it
"""

import re
import time
from pathlib import Path


def _extract_text_from_page(page) -> str:
    """Extract main content text from a TDN/Confluence page."""
    # Try different content selectors (TDN uses Confluence)
    for selector in [
        "#main-content",
        ".wiki-content",
        "#content .view",
        "article",
        ".confluence-information-macro",
        "#content",
    ]:
        el = page.query_selector(selector)
        if el:
            text = el.inner_text()
            if len(text) > 100:
                return text.strip()

    # Fallback: get all visible text
    return page.inner_text("body")[:10000]


def fetch_pe_page(url: str, timeout: int = 30) -> dict:
    """Fetch a TDN page and extract its text content.

    Returns: {"url": str, "content": str, "title": str, "success": bool}
    """
    from playwright.sync_api import sync_playwright

    result = {"url": url, "content": "", "title": "", "success": False}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 900},
            )
            page = context.new_page()

            page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
            time.sleep(2)  # Wait for JS rendering

            result["title"] = page.title() or ""
            result["content"] = _extract_text_from_page(page)
            result["success"] = len(result["content"]) > 50

            browser.close()
    except Exception as e:
        result["error"] = str(e)

    return result


def search_pe_on_web(pe_name: str) -> str | None:
    """Search Google for a Protheus PE and return the best TDN link.

    Returns the URL or None if not found.
    """
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            )
            page = context.new_page()

            # Search Google
            query = f"TOTVS Protheus ponto de entrada {pe_name} site:tdn.totvs.com OR site:centraldeatendimento.totvs.com"
            page.goto(f"https://www.google.com/search?q={query}", wait_until="networkidle", timeout=15000)
            time.sleep(2)

            # Find first TDN/Central link
            links = page.query_selector_all("a[href]")
            for link in links:
                href = link.get_attribute("href") or ""
                if "tdn.totvs.com" in href or "centraldeatendimento.totvs.com" in href:
                    # Clean Google redirect URL
                    if "/url?q=" in href:
                        href = href.split("/url?q=")[1].split("&")[0]
                    browser.close()
                    return href

            browser.close()
    except Exception:
        pass

    return None


def search_and_fetch_pe(pe_name: str) -> dict:
    """Full pipeline: search for PE on web → fetch the page → extract content.

    Returns: {"url": str, "content": str, "title": str, "success": bool}
    """
    # Step 1: Search for the PE
    url = search_pe_on_web(pe_name)
    if not url:
        return {"url": "", "content": "", "title": "", "success": False, "error": "PE not found on web"}

    # Step 2: Fetch the page
    result = fetch_pe_page(url)
    result["search_url"] = url
    return result


def extract_pe_info_from_content(content: str, pe_name: str) -> dict:
    """Extract structured PE info from raw page text using regex patterns.

    TDN pages use tab-separated tables for params and return values.
    Also captures PARAMIXB references in observation sections.
    """
    info = {
        "params_entrada": "",
        "params_saida": "",
        "objetivo": "",
        "onde_chamado": "",
    }

    lines = content.split("\n")
    params_list = []
    retorno_parts = []

    # ── Strategy 1: Tab-separated table rows (TDN Confluence format) ──
    # Pattern: "PARAMIXB\tArray\tDescription\tX" or "PARAMIXB[1]\tTipo\tDesc\tX"
    for line in lines:
        stripped = line.strip()
        if re.match(r'PARAMIXB', stripped, re.IGNORECASE):
            parts = stripped.split("\t")
            if len(parts) >= 3:
                nome = parts[0].strip()
                tipo = parts[1].strip()
                desc = parts[2].strip()
                params_list.append(f"{nome}: {tipo} — {desc}")

    # ── Strategy 2: Observation section with PARAMIXB[N] -> description ──
    paramixb_obs = re.findall(
        r'PARAMIXB\s*\[\s*(\d+)\s*\]\s*[-–>:]+\s*(.+?)(?:\n|$)',
        content, re.IGNORECASE
    )
    if paramixb_obs:
        for idx, desc in paramixb_obs:
            params_list.append(f"PARAMIXB[{idx}]: {desc.strip()}")

    # ── Strategy 3: Inline PARAMIXB mentions ──
    if not params_list:
        paramixb_inline = re.findall(
            r'PARAMIXB\s*(?:\[\s*(\d+)\s*\])?\s*[:\-–]\s*(.+?)(?:\n|$)',
            content, re.IGNORECASE
        )
        for idx, desc in paramixb_inline:
            label = f"PARAMIXB[{idx}]" if idx else "PARAMIXB"
            params_list.append(f"{label}: {desc.strip()}")

    if params_list:
        # Deduplicate while preserving order
        seen = set()
        unique = []
        for p in params_list:
            if p not in seen:
                seen.add(p)
                unique.append(p)
        info["params_entrada"] = "\n".join(unique)

    # ── Return value extraction ──
    # Strategy 1: Tab-separated return table
    # Find "Retorno:" section, then look for tab-separated data after it
    in_retorno = False
    for line in lines:
        stripped = line.strip()
        if re.match(r'Retorno\s*:', stripped, re.IGNORECASE):
            in_retorno = True
            continue
        if in_retorno and "\t" in stripped:
            parts = stripped.split("\t")
            if len(parts) >= 3:
                nome = parts[0].strip()
                tipo = parts[1].strip()
                desc = parts[2].strip()
                if nome and tipo and nome not in ("Nome", "Name"):
                    retorno_parts.append(f"{nome}: {tipo} — {desc}")
                    in_retorno = False  # Usually just one return row
        elif in_retorno and stripped and stripped not in ("Nome", "Tipo", "Descri", "Obrigat"):
            # Skip header words
            if len(stripped) > 3 and "\t" not in stripped and "Nome" not in stripped:
                in_retorno = False

    # Strategy 2: Inline retorno description
    if not retorno_parts:
        ret_match = re.search(
            r'(?:retorno|return)\s+(?:for|ser|é)\s+\.T\.\s*[,.]?\s*(.+?)(?:\.\s|\n)',
            content, re.IGNORECASE
        )
        if ret_match:
            retorno_parts.append(f"Lógico — .T. = {ret_match.group(1).strip()}")

    if retorno_parts:
        info["params_saida"] = "\n".join(retorno_parts)

    # ── Strategy 4: Return in old TDN format ──
    # Pattern: "lRet(logico)" followed by lines with .T./.F. descriptions
    if not retorno_parts:
        ret_old = re.search(
            r'Retorno\s*\n+\s*(\w+)\s*\(\s*(\w+)\s*\)\s*\n(.+?)(?:\nExemplo|\nPrograma|\n\n\n)',
            content, re.IGNORECASE | re.DOTALL
        )
        if ret_old:
            var_name = ret_old.group(1)
            var_type = ret_old.group(2)
            desc_lines = ret_old.group(3).strip()
            retorno_parts.append(f"{var_name}: {var_type} — {desc_lines}")
            info["params_saida"] = "\n".join(retorno_parts)

    # ── Strategy 5: PARAMIXB in code examples ──
    if not params_list:
        # Look for PARAMIXB[N] in example code with comments
        code_params = re.findall(
            r'PARAMIXB\s*\[\s*(\d+)\s*\]\s*.*?//\s*(.+?)(?:\n|$)',
            content, re.IGNORECASE
        )
        if code_params:
            seen_idx = set()
            for idx, comment in code_params:
                if idx not in seen_idx:
                    seen_idx.add(idx)
                    # Clean comment: remove code artifacts
                    clean = re.sub(r'\s*(\.And\.|\.Or\.|EndIf|Return|lRet\s*:=).*', '', comment, flags=re.IGNORECASE).strip()
                    if clean:
                        params_list.append(f"PARAMIXB[{idx}]: {clean}")
            if params_list:
                info["params_entrada"] = "\n".join(params_list)

    # ── Description/Objective extraction ──
    # Try multiple patterns (new and old TDN formats)
    desc_match = re.search(
        r'Descri[çc][ãa]o\s*:\s*\t?\s*(.+?)(?:\n\n|\nEventos|\nPrograma)',
        content, re.IGNORECASE | re.DOTALL
    )
    if desc_match:
        raw_desc = desc_match.group(1).strip()
        # Old format has "LOCALIZAÇÃO: ... EM QUE PONTO: ..."
        loc_match = re.search(r'EM QUE PONTO\s*:\s*(.+?)(?:\n\n|$)', raw_desc, re.IGNORECASE | re.DOTALL)
        if loc_match:
            info["onde_chamado"] = loc_match.group(1).strip()[:300]
            # Objective: clean LOCALIZAÇÃO prefix, extract function/routine info
            obj_part = re.sub(r'EM QUE PONTO\s*:.*', '', raw_desc, flags=re.IGNORECASE | re.DOTALL).strip()
            obj_part = re.sub(r'^LOCALIZA[ÇC][ÃA]O\s*:\s*', 'Localizado em ', obj_part, flags=re.IGNORECASE).strip()
            info["objetivo"] = obj_part[:300]
        else:
            info["objetivo"] = raw_desc[:300]

    # ── Where called — multiple patterns ──
    if not info["onde_chamado"]:
        # Try "Eventos:" (new format)
        eventos_match = re.search(
            r'Eventos\s*:\s*\t?\s*(.+?)(?:\n\n|\nPrograma)',
            content, re.IGNORECASE | re.DOTALL
        )
        if eventos_match:
            info["onde_chamado"] = eventos_match.group(1).strip()[:300]

    if not info["onde_chamado"]:
        # Try "EM QUE PONTO:" (old format) - search in full content
        ponto_match = re.search(
            r'EM QUE PONTO\s*:\s*(.+?)(?:\n\n|\nPrograma|\nSintaxe)',
            content, re.IGNORECASE | re.DOTALL
        )
        if ponto_match:
            info["onde_chamado"] = ponto_match.group(1).strip()[:300]

    return info
