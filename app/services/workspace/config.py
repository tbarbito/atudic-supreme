import json
from pathlib import Path
from pydantic import BaseModel, field_validator
from typing import Optional

class ClientConfig(BaseModel):
    cliente: str
    paths: dict  # csv_dicionario, fontes_custom, fontes_padrao

    @field_validator("cliente")
    @classmethod
    def cliente_not_empty(cls, v):
        if not v.strip():
            raise ValueError("cliente must not be empty")
        return v.strip()

class AppConfig(BaseModel):
    active_client: str = ""
    llm: dict = {}  # provider, model, api_key
    clients: dict = {}  # {slug: ClientConfig}

    # Backwards compat: also accept old format
    cliente: str = ""
    paths: dict = {}

def _slugify(name: str) -> str:
    return name.strip().lower().replace(" ", "-").replace("/", "-").replace("\\", "-")

def save_config(config, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(config, AppConfig):
        data = config.model_dump()
    else:
        data = config
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def load_config(path: Path) -> Optional[AppConfig]:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    # Migrate old format
    if "clients" not in data and "cliente" in data and data["cliente"] and data["cliente"] != "(pendente)":
        slug = _slugify(data["cliente"])
        data = {
            "active_client": slug,
            "llm": data.get("llm", {}),
            "clients": {
                slug: {"cliente": data["cliente"], "paths": data.get("paths", {})}
            }
        }
    return AppConfig(**data)

def get_client_workspace(base: Path, slug: str) -> Path:
    return base / "clients" / slug

def list_clients(config: AppConfig) -> list[dict]:
    result = []
    for slug, client_data in config.clients.items():
        if isinstance(client_data, dict):
            result.append({"slug": slug, "nome": client_data.get("cliente", slug)})
        else:
            result.append({"slug": slug, "nome": client_data.cliente})
    return result
