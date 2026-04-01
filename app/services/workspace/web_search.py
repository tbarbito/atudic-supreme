"""Web search service for enrichment — searches TDN and centraldeatendimento.totvs.com."""
import re
import httpx

SEARCH_DOMAINS = [
    "centraldeatendimento.totvs.com",
    "tdn.totvs.com",
]

TIMEOUT = 10.0
MAX_RESULTS = 3


async def search_web(query: str) -> list[dict]:
    """Search the web for TOTVS/Protheus content.

    Uses Google search with site: restriction. Returns list of
    {url, title, snippet} dicts. Best-effort — returns empty on failure.
    """
    site_filter = " OR ".join(f"site:{d}" for d in SEARCH_DOMAINS)
    search_query = f"{query} {site_filter}"
    search_url = "https://www.google.com/search"
    params = {"q": search_query, "num": MAX_RESULTS, "hl": "pt-BR"}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    results = []
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(search_url, params=params, headers=headers)
            if resp.status_code != 200:
                return results

            # Extract URLs from Google results (simple regex on href)
            html = resp.text
            urls = re.findall(r'href="(https?://(?:centraldeatendimento\.totvs|tdn\.totvs)[^"&]+)"', html)
            seen = set()
            for url in urls:
                clean = url.split("&")[0]
                if clean not in seen and len(seen) < MAX_RESULTS:
                    seen.add(clean)
                    results.append({"url": clean, "title": "", "content": ""})
    except Exception:
        return results

    return results


async def fetch_page_text(url: str) -> str:
    """Fetch a URL and extract text content. Returns empty string on failure."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            if resp.status_code != 200:
                return ""
            html = resp.text
            # Strip HTML tags, keep text
            text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
            # Limit to 5000 chars to avoid token explosion
            return text[:5000]
    except Exception:
        return ""


async def search_and_fetch(query: str) -> list[dict]:
    """Search web and fetch content from top results.

    Returns list of {url, content} dicts.
    """
    results = await search_web(query)
    enriched = []
    for r in results:
        content = await fetch_page_text(r["url"])
        if content:
            enriched.append({"url": r["url"], "content": content})
    return enriched
