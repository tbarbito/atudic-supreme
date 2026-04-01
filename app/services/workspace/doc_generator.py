from pathlib import Path
from typing import Optional

def save_doc(knowledge_dir: Path, slug: str, camada: str, content: str):
    dir_path = knowledge_dir / camada
    dir_path.mkdir(parents=True, exist_ok=True)
    file_path = dir_path / f"{slug}.md"
    file_path.write_text(content, encoding="utf-8")

def load_doc(knowledge_dir: Path, slug: str, camada: str) -> Optional[str]:
    file_path = knowledge_dir / camada / f"{slug}.md"
    if not file_path.exists():
        return None
    return file_path.read_text(encoding="utf-8")

def list_docs(knowledge_dir: Path, camada: str) -> list[dict]:
    dir_path = knowledge_dir / camada
    if not dir_path.exists():
        return []
    result = []
    for f in sorted(dir_path.glob("*.md")):
        result.append({
            "slug": f.stem,
            "filename": f.name,
            "size": f.stat().st_size,
        })
    return result
