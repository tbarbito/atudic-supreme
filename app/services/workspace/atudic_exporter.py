"""atudic_exporter.py — Converts Analista artefatos to AtuDic ingest format.

Supported output formats:
  - markdown  (default)  → AtuDic Markdown with ## headers and - key: value lines
  - json                 → AtuDic JSON envelope {"format": "atudic-ingest", ...}
"""
import json as _json
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_spec(raw: Any) -> dict:
    """Return spec as dict regardless of whether it is None, dict or JSON string."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return {}
        try:
            parsed = _json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except _json.JSONDecodeError:
            return {}
    return {}


def _prop(key: str, value: Any) -> str | None:
    """Return '- key: value' line or None when value should be skipped."""
    if value is None or value == "":
        return None
    return f"- {key}: {value}"


def _sort_key(artefato: dict) -> int:
    """Ordering: tabela=0, campo=1, indice=2, parametro/pergunta/combo=3, rest=4."""
    t = (artefato.get("tipo") or "").lower()
    order = {"tabela": 0, "campo": 1, "indice": 2, "parametro": 3, "sx6": 3,
             "pergunta": 3, "sx1": 3, "combo": 3, "sx5": 3}
    return order.get(t, 4)


# ---------------------------------------------------------------------------
# Markdown block builders
# ---------------------------------------------------------------------------

def _md_campo(artefato: dict, spec: dict) -> list[str]:
    nome = artefato.get("nome", "UNNAMED")
    acao = (artefato.get("acao") or "criar").lower()
    header = f"## Campo {nome}" if acao == "criar" else f"## Campo Diff {nome}"

    lines = [header]
    if acao == "criar":
        for key in ("tipo", "tabela", "tamanho", "decimal", "titulo", "descricao",
                    "validacao", "inicializador", "obrigatorio", "browse", "contexto"):
            # For criar, tabela can come from artefato itself or spec
            val = spec.get(key) if key != "tabela" else (spec.get("tabela") or artefato.get("tabela"))
            line = _prop(key, val)
            if line:
                lines.append(line)
        # Include any extra spec keys not already handled
        handled = {"tipo", "tabela", "tamanho", "decimal", "titulo", "descricao",
                   "validacao", "inicializador", "obrigatorio", "browse", "contexto"}
        for k, v in spec.items():
            if k not in handled:
                line = _prop(k, v)
                if line:
                    lines.append(line)
    else:
        # Diff: emit tabela from artefato if available, then spec contents
        tabela = spec.get("tabela") or artefato.get("tabela")
        if tabela:
            lines.append(f"- tabela: {tabela}")
        for k, v in spec.items():
            if k == "tabela":
                continue
            line = _prop(k, v)
            if line:
                lines.append(line)

    return lines


def _md_tabela(artefato: dict, spec: dict) -> list[str]:
    nome = artefato.get("nome", "UNNAMED")
    lines = [f"## Tabela {nome}"]

    nome_tab = spec.get("nome") or spec.get("descricao") or ""
    if nome_tab:
        lines.append(f"- nome: {nome_tab}")
    modo = spec.get("modo")
    if modo:
        lines.append(f"- modo: {modo}")

    campos = spec.get("campos")
    if campos:
        lines.append("- campos:")
        if isinstance(campos, dict):
            for campo_nome, campo_def in campos.items():
                lines.append(f"  - {campo_nome}: {campo_def}")
        elif isinstance(campos, list):
            for item in campos:
                lines.append(f"  - {item}")

    return lines


def _md_indice(artefato: dict, spec: dict) -> list[str]:
    nome = artefato.get("nome", "UNNAMED")
    lines = [f"## Índice {nome}"]

    tabela = spec.get("tabela") or artefato.get("tabela")
    if tabela:
        lines.append(f"- tabela: {tabela}")
    for key in ("ordem", "chave", "descricao", "unico"):
        line = _prop(key, spec.get(key))
        if line:
            lines.append(line)
    handled = {"tabela", "ordem", "chave", "descricao", "unico"}
    for k, v in spec.items():
        if k not in handled:
            line = _prop(k, v)
            if line:
                lines.append(line)

    return lines


def _md_parametro(artefato: dict, spec: dict) -> list[str]:
    nome = artefato.get("nome", "UNNAMED")
    acao = (artefato.get("acao") or "criar").lower()
    header = f"## Metadado SX6 {nome}" if acao == "criar" else f"## Metadado Diff SX6 {nome}"
    lines = [header]

    for key in ("X6_VAR", "X6_TIPO", "X6_DESCRIC", "X6_CONTEUD", "X6_CONT1", "X6_CONT2"):
        line = _prop(key, spec.get(key))
        if line:
            lines.append(line)
    handled = {"X6_VAR", "X6_TIPO", "X6_DESCRIC", "X6_CONTEUD", "X6_CONT1", "X6_CONT2"}
    for k, v in spec.items():
        if k not in handled:
            line = _prop(k, v)
            if line:
                lines.append(line)

    return lines


def _md_pergunta(artefato: dict, spec: dict) -> list[str]:
    nome = artefato.get("nome", "UNNAMED")
    lines = [f"## Metadado SX1 {nome}"]

    for key in ("X1_GRUPO", "X1_ORDEM", "X1_PERGUNT", "X1_TIPO", "X1_TAMANHO",
                "X1_GSC", "X1_VAR01"):
        line = _prop(key, spec.get(key))
        if line:
            lines.append(line)
    handled = {"X1_GRUPO", "X1_ORDEM", "X1_PERGUNT", "X1_TIPO", "X1_TAMANHO",
               "X1_GSC", "X1_VAR01"}
    for k, v in spec.items():
        if k not in handled:
            line = _prop(k, v)
            if line:
                lines.append(line)

    return lines


def _md_combo(artefato: dict, spec: dict) -> list[str]:
    nome = artefato.get("nome", "UNNAMED")
    lines = [f"## Metadado SX5 {nome}"]

    for key in ("X5_TABELA", "X5_CHAVE", "X5_DESCRI", "X5_DESCR2"):
        line = _prop(key, spec.get(key))
        if line:
            lines.append(line)
    handled = {"X5_TABELA", "X5_CHAVE", "X5_DESCRI", "X5_DESCR2"}
    for k, v in spec.items():
        if k not in handled:
            line = _prop(k, v)
            if line:
                lines.append(line)

    return lines


# ---------------------------------------------------------------------------
# JSON helpers — full AtuDic ingest format
# ---------------------------------------------------------------------------

# Map from human-readable spec keys → SX3 field names
_HUMAN_TO_SX3 = {
    "tipo": "X3_TIPO",
    "tamanho": "X3_TAMANHO",
    "decimal": "X3_DECIMAL",
    "titulo": "X3_TITULO",
    "titulospa": "X3_TITSPA",
    "titulo_spa": "X3_TITSPA",
    "tituloeng": "X3_TITENG",
    "titulo_eng": "X3_TITENG",
    "descricao": "X3_DESCRIC",
    "descricaospa": "X3_DESCSPA",
    "descricao_spa": "X3_DESCSPA",
    "descricaoeng": "X3_DESCENG",
    "descricao_eng": "X3_DESCENG",
    "picture": "X3_PICTURE",
    "validacao": "X3_VALID",
    "usado": "X3_USADO",
    "relacao": "X3_RELACAO",
    "f3": "X3_F3",
    "nivel": "X3_NIVEL",
    "browse": "X3_BROWSE",
    "visual": "X3_VISUAL",
    "contexto": "X3_CONTEXT",
    "context": "X3_CONTEXT",
    "obrigatorio": "X3_OBRIGAT",
    "inicializador": "X3_INIBRW",
    "when": "X3_WHEN",
    "propri": "X3_PROPRI",
    "propriedade": "X3_PROPRI",
    "cbox": "X3_CBOX",
    "grupo": "X3_GRPSXG",
    "folder": "X3_FOLDER",
    "pyme": "X3_PYME",
    "ordem": "X3_ORDEM",
}

# All SX3 fields with default values (matches ingest_sample_field.json structure)
_SX3_DEFAULTS: dict[str, Any] = {
    "X3_ARQUIVO": "",
    "X3_ORDEM": "01",
    "X3_CAMPO": "",
    "X3_TIPO": "C",
    "X3_TAMANHO": 10,
    "X3_DECIMAL": 0,
    "X3_TITULO": "",
    "X3_TITSPA": "",
    "X3_TITENG": "",
    "X3_DESCRIC": "",
    "X3_DESCSPA": "",
    "X3_DESCENG": "",
    "X3_PICTURE": "",
    "X3_VALID": "",
    "X3_USADO": "",
    "X3_RELACAO": "",
    "X3_F3": "",
    "X3_NIVEL": 1,
    "X3_RESERV": "",
    "X3_CHECK": "",
    "X3_TRIGGER": "",
    "X3_PROPRI": "U",
    "X3_BROWSE": "S",
    "X3_VISUAL": "A",
    "X3_CONTEXT": "R",
    "X3_OBRIGAT": "",
    "X3_VLDUSER": "",
    "X3_CBOX": "",
    "X3_CBOXSPA": "",
    "X3_CBOXENG": "",
    "X3_PICTVAR": "",
    "X3_WHEN": "",
    "X3_INIBRW": "",
    "X3_GRPSXG": "",
    "X3_FOLDER": "",
    "X3_PYME": "",
    "X3_CONDSQL": "",
    "X3_CHKSQL": "",
    "X3_IDXSRV": "",
    "X3_ORTOGRA": "",
    "X3_IDXFLD": "",
    "X3_TELA": "",
    "X3_PICBRV": "",
    "X3_AGRUP": "",
    "X3_POSLGT": "",
    "X3_MODAL": "",
    "D_E_L_E_T_": " ",
}


def _build_sx3(field_name: str, tabela: str, spec: dict) -> dict:
    """Build a complete SX3 dict from artefato spec."""
    sx3 = dict(_SX3_DEFAULTS)
    sx3["X3_ARQUIVO"] = tabela
    sx3["X3_CAMPO"] = field_name

    # Apply X3_* keys directly from spec if present
    for k, v in spec.items():
        if k.startswith("X3_") and k in sx3:
            sx3[k] = v

    # Map human-readable keys (override if not already set via X3_* above)
    for human_key, sx3_key in _HUMAN_TO_SX3.items():
        if human_key in spec and spec[human_key] is not None and spec[human_key] != "":
            sx3[sx3_key] = spec[human_key]

    return sx3


def _to_int(val: Any, default: int = 0) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _build_physical(sx3: dict) -> dict:
    """Build the physical DDL block from SX3 tipo/tamanho/decimal."""
    tipo = sx3.get("X3_TIPO", "C")
    tamanho = _to_int(sx3.get("X3_TAMANHO"), 10)
    decimal = _to_int(sx3.get("X3_DECIMAL"), 0)

    if tipo == "N":
        return {
            "data_type": "NUMERIC",
            "character_maximum_length": None,
            "numeric_precision": tamanho,
            "numeric_scale": decimal,
        }
    if tipo == "M":
        return {
            "data_type": "TEXT",
            "character_maximum_length": None,
            "numeric_precision": None,
            "numeric_scale": None,
        }
    if tipo == "L":
        return {
            "data_type": "CHAR",
            "character_maximum_length": 1,
            "numeric_precision": None,
            "numeric_scale": None,
        }
    # C, D, and anything else → VARCHAR
    return {
        "data_type": "VARCHAR",
        "character_maximum_length": tamanho,
        "numeric_precision": None,
        "numeric_scale": None,
    }


def _build_top_field(field_name: str, tabela: str, sx3: dict) -> dict:
    """Build the TOP physical field block."""
    tipo = sx3.get("X3_TIPO", "C")
    tamanho = sx3.get("X3_TAMANHO", 10)
    decimal = sx3.get("X3_DECIMAL", 0)
    # Protheus physical table name = alias + "010"
    phys_table = f"{tabela}010" if tabela else ""
    return {
        "FIELD_TABLE": phys_table,
        "FIELD_NAME": field_name,
        "FIELD_TYPE": tipo,
        "FIELD_PREC": str(tamanho),
        "FIELD_DEC": str(decimal),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def export_to_markdown(artefatos: list[dict]) -> str:
    """Convert a list of artefatos to AtuDic Markdown format."""
    if not artefatos:
        return ""

    sorted_arts = sorted(artefatos, key=_sort_key)
    blocks: list[str] = []

    for art in sorted_arts:
        try:
            tipo = (art.get("tipo") or "").lower()
            nome = art.get("nome") or "UNNAMED"
            spec = _parse_spec(art.get("spec_json"))
            spec_vazia = not spec

            # Types that become HTML comments (manual implementation required)
            if tipo in ("pe", "fonte", "gatilho"):
                blocks.append(f"<!-- ARTEFATO tipo:{tipo} nome:{nome} — requer implementação manual -->")
                continue

            # Build the block lines
            if tipo == "campo":
                lines = _md_campo(art, spec)
            elif tipo == "tabela":
                lines = _md_tabela(art, spec)
            elif tipo in ("indice", "índice", "index"):
                lines = _md_indice(art, spec)
            elif tipo in ("parametro", "sx6"):
                lines = _md_parametro(art, spec)
            elif tipo in ("pergunta", "sx1"):
                lines = _md_pergunta(art, spec)
            elif tipo in ("combo", "sx5"):
                lines = _md_combo(art, spec)
            else:
                blocks.append(f"<!-- ARTEFATO tipo:{tipo} nome:{nome} — tipo desconhecido, requer implementação manual -->")
                continue

            if spec_vazia:
                lines.append("<!-- spec incompleta, preencher manualmente -->")

            blocks.append("\n".join(lines))

        except Exception as exc:  # noqa: BLE001
            nome = art.get("nome", "?") if isinstance(art, dict) else "?"
            blocks.append(f"<!-- ERRO ao processar artefato nome:{nome} — {exc} -->")

    return "\n\n".join(blocks) + "\n"


_TYPE_MAP = {
    ("campo", "criar"): "field",
    ("campo", "alterar"): "field_diff",
    ("tabela", "criar"): "full_table",
    ("tabela", "alterar"): "full_table",
    ("parametro", "criar"): "metadata",
    ("sx6", "criar"): "metadata",
    ("parametro", "alterar"): "metadata_diff",
    ("sx6", "alterar"): "metadata_diff",
    ("pergunta", "criar"): "metadata",
    ("sx1", "criar"): "metadata",
    ("pergunta", "alterar"): "metadata",
    ("sx1", "alterar"): "metadata",
    ("combo", "criar"): "metadata",
    ("sx5", "criar"): "metadata",
    ("combo", "alterar"): "metadata",
    ("sx5", "alterar"): "metadata",
    ("indice", "criar"): "index",
    ("índice", "criar"): "index",
    ("index", "criar"): "index",
    ("indice", "alterar"): "index",
    ("índice", "alterar"): "index",
    ("index", "alterar"): "index",
}

_TABELA_META = {
    "parametro": "SX6", "sx6": "SX6",
    "pergunta": "SX1", "sx1": "SX1",
    "combo": "SX5", "sx5": "SX5",
}

_SKIP = {"pe", "fonte", "gatilho"}


def export_to_json(
    artefatos: list[dict],
    source_environment: str = "",
    source_driver: str = "mssql",
    company_code: str = "01",
    exported_by: str = "ExtraiRPO",
) -> str:
    """Convert a list of artefatos to AtuDic JSON ingest format.

    The output matches layoutAtuRPO/ingest_sample_field.json exactly:
      - Envelope: version, format, source_environment, source_driver, exported_at,
                  exported_by, company_code
      - field items: type, table_alias, field_name, physical, sx3, top_field
      - Other item types: type, tabela/name + spec passthrough
    """
    items: list[dict] = []

    for art in (artefatos or []):
        try:
            tipo = (art.get("tipo") or "").lower()
            acao = (art.get("acao") or "criar").lower()
            nome = art.get("nome") or "UNNAMED"

            if tipo in _SKIP:
                continue

            type_key = (tipo, acao)
            atudic_type = _TYPE_MAP.get(type_key)
            if atudic_type is None:
                continue

            spec = _parse_spec(art.get("spec_json"))
            tabela = (
                art.get("tabela")
                or spec.get("tabela")
                or spec.get("X3_ARQUIVO")
                or _TABELA_META.get(tipo)
                or ""
            )

            if tipo == "campo":
                # Full field format with physical + sx3 + top_field
                sx3 = _build_sx3(nome, tabela, spec)
                item = {
                    "type": atudic_type,
                    "table_alias": tabela,
                    "field_name": nome,
                    "physical": _build_physical(sx3),
                    "sx3": sx3,
                    "top_field": _build_top_field(nome, tabela, sx3),
                }
            else:
                # Other types: simpler passthrough structure
                item: dict = {"type": atudic_type, "name": nome}
                if tabela:
                    item["tabela"] = tabela
                if spec:
                    item["spec"] = spec

            items.append(item)

        except Exception:  # noqa: BLE001
            continue

    result = {
        "version": "1.0",
        "format": "atudic-ingest",
        "source_environment": source_environment,
        "source_driver": source_driver,
        "exported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "exported_by": exported_by,
        "company_code": company_code,
        "items": items,
    }
    return _json.dumps(result, ensure_ascii=False, indent=2)


def export(artefatos: list[dict], formato: str = "markdown", **meta) -> str:
    """Dispatcher: call export_to_markdown or export_to_json based on formato.

    Extra keyword args (source_environment, source_driver, company_code, exported_by)
    are forwarded to export_to_json when formato='json'.
    """
    fmt = (formato or "markdown").lower()
    if fmt == "json":
        return export_to_json(artefatos, **meta)
    return export_to_markdown(artefatos)
