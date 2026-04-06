"""Artifact Registry — collects typed artifacts from tool results.

Each artifact gets a short hash ID (#f1, #c1, #t1, etc.) that the LLM
can reference in its narrative. The frontend renders these as clickable
chips linked to structured data sections.

Prefixes:
  #t  → tabela
  #c  → campo
  #f  → fonte (PadR, SubStr, etc.)
  #p  → parametro
  #pe → ponto de entrada
  #g  → gatilho
  #i  → integracao
  #m  → msexecauto
  #pr → processo
"""
from typing import Any


# ── Artifact type definitions ────────────────────────────────────────────────

ARTIFACT_TYPES = {
    "tabela": {"prefix": "t", "icon": "pi pi-table"},
    "campo": {"prefix": "c", "icon": "pi pi-th-large"},
    "fonte": {"prefix": "f", "icon": "pi pi-file"},
    "parametro": {"prefix": "p", "icon": "pi pi-cog"},
    "pe": {"prefix": "pe", "icon": "pi pi-bolt"},
    "gatilho": {"prefix": "g", "icon": "pi pi-arrow-right"},
    "integracao": {"prefix": "i", "icon": "pi pi-globe"},
    "msexecauto": {"prefix": "m", "icon": "pi pi-exclamation-triangle"},
    "processo": {"prefix": "pr", "icon": "pi pi-sitemap"},
}


class ArtifactRegistry:
    """Collects and indexes artifacts from tool results."""

    def __init__(self):
        self._artifacts: dict[str, dict] = {}  # id → artifact
        self._counters: dict[str, int] = {}    # prefix → next number
        self._seen: set[str] = set()           # dedup keys

    def add(self, tipo: str, data: dict, dedup_key: str = "") -> str:
        """Add an artifact and return its hash ID.

        Args:
            tipo: One of ARTIFACT_TYPES keys
            data: Artifact data (varies by type)
            dedup_key: If provided, skip if already seen

        Returns:
            Hash ID like "#f1", "#c3", etc.
        """
        if dedup_key and dedup_key in self._seen:
            # Return existing ID
            for aid, a in self._artifacts.items():
                if a.get("_dedup") == dedup_key:
                    return aid
            return ""
        if dedup_key:
            self._seen.add(dedup_key)

        prefix = ARTIFACT_TYPES.get(tipo, {}).get("prefix", "x")
        icon = ARTIFACT_TYPES.get(tipo, {}).get("icon", "pi pi-circle")
        num = self._counters.get(prefix, 0) + 1
        self._counters[prefix] = num

        artifact_id = f"#{prefix}{num}"
        self._artifacts[artifact_id] = {
            "id": artifact_id,
            "tipo": tipo,
            "icon": icon,
            "_dedup": dedup_key,
            **data,
        }
        return artifact_id

    def get(self, artifact_id: str) -> dict | None:
        return self._artifacts.get(artifact_id)

    def all(self) -> list[dict]:
        """Return all artifacts sorted by type then ID."""
        return sorted(
            self._artifacts.values(),
            key=lambda a: (a["tipo"], a["id"]),
        )

    def by_type(self) -> dict[str, list[dict]]:
        """Return artifacts grouped by type."""
        groups: dict[str, list[dict]] = {}
        for a in self._artifacts.values():
            groups.setdefault(a["tipo"], []).append(a)
        return groups

    def count(self) -> int:
        return len(self._artifacts)

    def summary_for_llm(self) -> str:
        """Generate a concise artifact index for the LLM prompt.

        Lists all artifacts with their IDs so the LLM can reference them.
        """
        if not self._artifacts:
            return ""

        lines = ["ARTEFATOS IDENTIFICADOS (use #id para referenciar):"]
        by_type = self.by_type()

        type_labels = {
            "tabela": "Tabelas",
            "campo": "Campos",
            "fonte": "Fontes com problema",
            "parametro": "Parametros",
            "pe": "Pontos de Entrada",
            "gatilho": "Gatilhos",
            "integracao": "Integracoes",
            "msexecauto": "MsExecAuto (RISCO)",
            "processo": "Processos",
        }

        for tipo in ["msexecauto", "fonte", "campo", "tabela", "pe", "parametro", "gatilho", "integracao", "processo"]:
            items = by_type.get(tipo, [])
            if not items:
                continue
            label = type_labels.get(tipo, tipo)
            lines.append(f"\n{label} ({len(items)}):")
            for a in items[:30]:  # Limit to avoid token explosion
                preview = a.get("preview", a.get("arquivo", a.get("campo", a.get("nome", "?"))))
                lines.append(f"  {a['id']} → {preview}")
            if len(items) > 30:
                lines.append(f"  ... +{len(items)-30} mais")

        return "\n".join(lines)

    def to_sse_payload(self) -> list[dict]:
        """Return artifacts as SSE payload (without internal fields)."""
        result = []
        for a in self.all():
            clean = {k: v for k, v in a.items() if not k.startswith("_")}
            result.append(clean)
        return result


# ── Extractors: build artifacts from tool results ────────────────────────────

def extract_from_analise_aumento(result: dict, registry: ArtifactRegistry) -> None:
    """Extract artifacts from analise_aumento_campo result."""
    tabela = result.get("tabela", "")
    campo = result.get("campo", "")

    # Main table
    registry.add("tabela", {
        "codigo": tabela,
        "campo_analisado": campo,
        "tamanho_atual": result.get("tamanho_atual", 0),
        "novo_tamanho": result.get("novo_tamanho", 0),
        "grupo_sxg": result.get("grupo_sxg", ""),
        "total_campos_grupo": result.get("total_campos_grupo", 0),
        "preview": f"{tabela}.{campo} — de {result.get('tamanho_atual',0)} para {result.get('novo_tamanho',0)} posicoes",
    }, dedup_key=f"tabela:{tabela}")

    # Campos fora do grupo
    for c in result.get("campos_fora_grupo", []):
        registry.add("campo", {
            "tabela": c["tabela"],
            "campo": c["campo"],
            "titulo": c.get("titulo", ""),
            "tamanho": c.get("tamanho", 0),
            "risco": c.get("risco", ""),
            "grupo": c.get("grupo_atual", "NENHUM"),
            "problema": "Fora do grupo SXG — precisa ajuste manual",
            "preview": f"{c['tabela']}.{c['campo']} — {c.get('titulo','')} (tam={c.get('tamanho',0)})",
        }, dedup_key=f"campo:{c['tabela']}.{c['campo']}")

    # Campos suspeitos custom — limit to most relevant (tables starting with Z)
    for c in result.get("campos_suspeitos_custom", [])[:20]:
        registry.add("campo", {
            "tabela": c["tabela"],
            "campo": c["campo"],
            "titulo": c.get("titulo", ""),
            "tamanho": c.get("tamanho", 0),
            "risco": "Campo custom suspeito — pode referenciar o campo",
            "preview": f"{c['tabela']}.{c['campo']} — {c.get('titulo','')} (suspeito)",
        }, dedup_key=f"campo:{c['tabela']}.{c['campo']}")

    # Fontes com tamanho chumbado
    for f in result.get("padr_chumbado", []):
        registry.add("fonte", {
            "arquivo": f["arquivo"],
            "funcao": f.get("funcao", ""),
            "tipo_problema": f.get("tipo", "PadR"),
            "tamanho_chumbado": f.get("tamanho", 0),
            "confianca": f.get("confianca", "alta"),
            "trechos": f.get("trechos", []),
            "problema": f"Usa {f.get('tipo','PadR')}({f.get('tamanho',0)}) fixo — vai truncar",
            "solucao": f"Trocar por TamSX3(\"{campo}\")",
            "preview": f"{f['arquivo']}::{f.get('funcao','')} — {f.get('tipo','PadR')}({f.get('tamanho',0)}) [{f.get('confianca','')}]",
        }, dedup_key=f"fonte:{f['arquivo']}::{f.get('funcao','')}::{f.get('tipo','')}::{f.get('tamanho',0)}")

    # MsExecAuto
    for m in result.get("msexecauto", []):
        registry.add("msexecauto", {
            "arquivo": m["arquivo"],
            "rotina": m.get("rotina", ""),
            "risco": m.get("risco", ""),
            "preview": f"{m['arquivo']} — MsExecAuto({m.get('rotina','')}) pode enviar tamanho antigo",
        }, dedup_key=f"msexec:{m['arquivo']}")

    # Integracoes
    for i in result.get("integracoes", []):
        registry.add("integracao", {
            "arquivo": i["arquivo"],
            "modulo": i.get("modulo", ""),
            "preview": f"{i['arquivo']} ({i.get('modulo','')})",
        }, dedup_key=f"integ:{i['arquivo']}")

    # Indices risco
    for idx in result.get("indices_risco", []):
        registry.add("tabela", {
            "codigo": idx.get("tabela", ""),
            "tipo_info": "indice",
            "ordem": idx.get("ordem", ""),
            "chave": idx.get("chave", ""),
            "tamanho_estimado": idx.get("tamanho_estimado", 0),
            "risco": idx.get("risco", ""),
            "preview": f"Indice {idx.get('tabela','')}.{idx.get('ordem','')} — ~{idx.get('tamanho_estimado',0)} chars ({idx.get('risco','')})",
        }, dedup_key=f"idx:{idx.get('tabela','')}:{idx.get('ordem','')}")


def extract_from_analise_impacto(result: dict, registry: ArtifactRegistry) -> None:
    """Extract artifacts from analise_impacto result."""
    tabela = result.get("tabela", "")

    # Fontes de escrita
    for f in result.get("fontes_escrita", []):
        registry.add("fonte", {
            "arquivo": f["arquivo"],
            "modulo": f.get("modulo", ""),
            "loc": f.get("loc", 0),
            "write_tables": f.get("write_tables", []),
            "problema": "Grava na tabela",
            "preview": f"{f['arquivo']} ({f.get('modulo','')}, {f.get('loc',0)} LOC)",
        }, dedup_key=f"fonte_escrita:{f['arquivo']}")

    # MsExecAuto
    for m in result.get("msexecauto_fontes", []):
        registry.add("msexecauto", {
            "arquivo": m["arquivo"],
            "rotina": m.get("rotina_chamada", ""),
            "risco": m.get("risco", ""),
            "preview": f"{m['arquivo']} — MsExecAuto({m.get('rotina_chamada','')}) RISCO campo nao tratado",
        }, dedup_key=f"msexec:{m['arquivo']}")

    # Integracoes
    for i in result.get("integracoes", []):
        registry.add("integracao", {
            "arquivo": i["arquivo"],
            "modulo": i.get("modulo", ""),
            "preview": f"{i['arquivo']} ({i.get('modulo','')})",
        }, dedup_key=f"integ:{i['arquivo']}")

    # Gatilhos
    for g in result.get("gatilhos", []):
        registry.add("gatilho", {
            "campo_origem": g.get("campo_origem", ""),
            "campo_destino": g.get("campo_destino", ""),
            "regra": g.get("regra", ""),
            "tipo": g.get("tipo", ""),
            "condicao": g.get("condicao", ""),
            "custom": g.get("custom", 0),
            "preview": f"{g.get('campo_origem','')} → {g.get('campo_destino','')} ({g.get('tipo','')})",
        }, dedup_key=f"gat:{g.get('campo_origem','')}:{g.get('sequencia','')}")

    # Campo info
    ci = result.get("campo_info", {})
    if ci:
        registry.add("campo", {
            "tabela": tabela,
            "campo": ci.get("campo", ""),
            "tipo": ci.get("tipo", ""),
            "tamanho": ci.get("tamanho", 0),
            "titulo": ci.get("titulo", ""),
            "obrigatorio": ci.get("obrigatorio", 0),
            "vlduser": ci.get("vlduser", ""),
            "preview": f"{tabela}.{ci.get('campo','')} ({ci.get('tipo','')}/{ci.get('tamanho','')}) — {ci.get('titulo','')}",
        }, dedup_key=f"campo:{tabela}.{ci.get('campo','')}")


def extract_from_quem_grava(result: list, args: dict, registry: ArtifactRegistry) -> None:
    """Extract artifacts from quem_grava result."""
    if not isinstance(result, list):
        return
    for r in result:
        registry.add("fonte", {
            "arquivo": r.get("arquivo", ""),
            "funcao": r.get("funcao", ""),
            "condicao": r.get("condicao", ""),
            "origem_campo": r.get("origem_campo", ""),
            "problema": "Ponto de escrita" + (f" [condicional: {r.get('condicao','')[:50]}]" if r.get("condicao") else ""),
            "preview": f"{r.get('arquivo','')}::{r.get('funcao','')}()" + (f" [cond]" if r.get("condicao") else ""),
        }, dedup_key=f"escrita:{r.get('arquivo','')}::{r.get('funcao','')}")


def extract_from_pes(result: list, registry: ArtifactRegistry) -> None:
    """Extract artifacts from buscar_pes or pes_disponiveis."""
    if not isinstance(result, list):
        return
    for pe in result:
        nome = pe.get("nome", pe.get("nome_pe", ""))
        registry.add("pe", {
            "nome": nome,
            "objetivo": pe.get("objetivo", ""),
            "operacao": pe.get("operacao", ""),
            "parametros": pe.get("parametros", ""),
            "tipo_retorno": pe.get("tipo_retorno", ""),
            "rotina": pe.get("rotina", pe.get("arquivo", "")),
            "preview": f"{nome} ({pe.get('operacao', pe.get('objetivo',''))[:50]})",
        }, dedup_key=f"pe:{nome}")


def extract_from_parametros(result: list, registry: ArtifactRegistry) -> None:
    """Extract artifacts from ver_parametro."""
    if not isinstance(result, list):
        return
    for p in result:
        var = p.get("variavel", "")
        registry.add("parametro", {
            "variavel": var,
            "conteudo": p.get("conteudo", ""),
            "descricao": p.get("descricao", ""),
            "valor_padrao": p.get("valor_padrao", ""),
            "preview": f"{var} = {p.get('conteudo','?')} — {p.get('descricao','')[:50]}",
        }, dedup_key=f"param:{var}")


# ── Main extractor dispatcher ────────────────────────────────────────────────

_EXTRACTORS = {
    "analise_aumento_campo": lambda r, a, reg: extract_from_analise_aumento(r, reg),
    "analise_impacto": lambda r, a, reg: extract_from_analise_impacto(r, reg),
    "quem_grava": lambda r, a, reg: extract_from_quem_grava(r, a, reg),
    "buscar_pes_cliente": lambda r, a, reg: extract_from_pes(r, reg),
    "pes_disponiveis": lambda r, a, reg: extract_from_pes(r, reg),
    "ver_parametro": lambda r, a, reg: extract_from_parametros(r, reg),
}

# Tools that should NOT extract artifacts when a more specific tool already ran
# e.g. when analise_aumento_campo ran, pes_disponiveis artifacts are noise
_SKIP_WHEN_PRESENT = {
    "analise_aumento_campo": {"pes_disponiveis", "buscar_pes_cliente", "fonte_padrao"},
}


def extract_artifacts(tool_name: str, args: dict, raw_result: Any, registry: ArtifactRegistry) -> None:
    """Extract artifacts from a tool result into the registry."""
    # Check if this tool should be skipped because a more specific tool already ran
    for primary_tool, skip_set in _SKIP_WHEN_PRESENT.items():
        if tool_name in skip_set and any(
            a.get("_dedup", "").startswith(f"tabela:") or a.get("tipo_problema")
            for a in registry._artifacts.values()
        ):
            return  # Skip — primary tool already populated the registry

    extractor = _EXTRACTORS.get(tool_name)
    if extractor:
        try:
            extractor(raw_result, args, registry)
        except Exception as e:
            print(f"[artifact_registry] extraction error for {tool_name}: {e}")
