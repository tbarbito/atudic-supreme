"""Ingestion helpers for standard process docs (processopadrao/) and TDN docs."""
from pathlib import Path
from typing import Optional

PADRAO_DIR = Path("processopadrao")
TDN_DIR = PADRAO_DIR / "TDN"


def list_padrao_docs() -> list[dict]:
    """List all .md files in processopadrao/ (non-recursive).

    Returns list of dicts with keys: arquivo, modulo, path, size.
    The module is inferred from the filename prefix (e.g. SIGAFAT -> sigafat).
    """
    result = []
    if not PADRAO_DIR.exists():
        return result
    for md_file in sorted(PADRAO_DIR.glob("*.md")):
        name = md_file.name
        # Extract prefix before the first underscore (or the full stem when no underscore)
        stem = md_file.stem
        modulo = stem.split("_")[0].lower() if "_" in stem else stem.lower()
        result.append({
            "arquivo": name,
            "modulo": modulo,
            "path": str(md_file),
            "size": md_file.stat().st_size,
        })
    return result


def list_tdn_docs() -> list[dict]:
    """List all .md files in processopadrao/TDN/.

    Returns list of dicts with keys: arquivo, path, size.
    """
    result = []
    if not TDN_DIR.exists():
        return result
    for md_file in sorted(TDN_DIR.glob("*.md")):
        result.append({
            "arquivo": md_file.name,
            "path": str(md_file),
            "size": md_file.stat().st_size,
        })
    return result


def chunk_markdown(content: str, max_chars: int = 2000) -> list[str]:
    """Split markdown content into chunks.

    Primary split is on '## ' section headers.  Sections that exceed
    max_chars are sub-chunked by paragraph (blank-line boundaries).
    """
    # Split on level-2 headers, preserving the header line in each section.
    raw_sections: list[str] = []
    current: list[str] = []
    for line in content.splitlines(keepends=True):
        if line.startswith("## ") and current:
            raw_sections.append("".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        raw_sections.append("".join(current))

    chunks: list[str] = []
    for section in raw_sections:
        if len(section) <= max_chars:
            text = section.strip()
            if text:
                chunks.append(text)
        else:
            # Sub-chunk by paragraphs (blank-line boundaries)
            paragraphs = [p.strip() for p in section.split("\n\n") if p.strip()]
            current_chunk: list[str] = []
            current_len = 0
            for para in paragraphs:
                if current_len + len(para) + 2 > max_chars and current_chunk:
                    chunks.append("\n\n".join(current_chunk))
                    current_chunk = [para]
                    current_len = len(para)
                else:
                    current_chunk.append(para)
                    current_len += len(para) + 2
            if current_chunk:
                chunks.append("\n\n".join(current_chunk))

    return chunks


def ingest_padrao(vs) -> dict:
    """Reset the 'padrao' collection and ingest all processopadrao/*.md files.

    Each chunk is stored with metadata: modulo, arquivo, tipo='processo_padrao'.
    Returns dict with keys: docs, chunks.
    """
    vs.reset_collection("padrao")
    docs_list = list_padrao_docs()
    total_chunks = 0

    for doc in docs_list:
        content = Path(doc["path"]).read_text(encoding="utf-8")
        parts = chunk_markdown(content, max_chars=2000)
        chunks = []
        for idx, part in enumerate(parts):
            chunk_id = f"padrao_{doc['modulo']}_{doc['arquivo']}_{idx}"
            chunks.append({
                "id": chunk_id,
                "content": part,
                "modulo": doc["modulo"],
                "arquivo": doc["arquivo"],
                "tipo": "processo_padrao",
            })
        if chunks:
            vs.add_source_chunks("padrao", chunks)
            total_chunks += len(chunks)

    return {"docs": len(docs_list), "chunks": total_chunks}


def ingest_tdn(vs) -> dict:
    """Reset the 'tdn' collection and ingest all processopadrao/TDN/*.md files.

    Each chunk is stored with metadata: arquivo, tipo='tdn'.
    Returns dict with keys: docs, chunks.
    """
    vs.reset_collection("tdn")
    docs_list = list_tdn_docs()
    total_chunks = 0

    for doc in docs_list:
        content = Path(doc["path"]).read_text(encoding="utf-8")
        parts = chunk_markdown(content, max_chars=3000)
        chunks = []
        for idx, part in enumerate(parts):
            chunk_id = f"tdn_{doc['arquivo']}_{idx}"
            chunks.append({
                "id": chunk_id,
                "content": part,
                "arquivo": doc["arquivo"],
                "tipo": "tdn",
            })
        if chunks:
            vs.add_source_chunks("tdn", chunks)
            total_chunks += len(chunks)

    return {"docs": len(docs_list), "chunks": total_chunks}
