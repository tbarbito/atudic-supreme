"""Padrão Cross-Reference — automatic comparison of client vs standard Protheus.

When a routine is identified, automatically injects steps to query padrao.db
and compares client customizations against standard behavior.
"""
import re
from typing import Optional
from app.services.workspace import padrao_tools as pt


def auto_crossref_steps(
    classification: dict,
    resolved_context: str,
) -> list[dict]:
    """Generate automatic cross-reference steps for the investigation plan.

    Detects routines from classification and resolved context, then creates
    padrao.db query steps.

    Returns list of plan steps to append.
    """
    steps = []
    rotinas = set()

    # Extract routines from classification
    tabelas = classification.get("tabelas", [])

    # Extract routine names from resolved context
    # Patterns: MATA410, FINA040, CTBA500, etc.
    rotina_pattern = re.compile(r'\b((?:MATA|FINA|CTBA|MATF|MATR|TMKA|GPEA|CNTA|ATFA|PONA)\d{3}[A-Z]?)\b', re.IGNORECASE)
    for match in rotina_pattern.finditer(resolved_context):
        rotinas.add(match.group(1).upper())

    # Also look for "rotina XXXX" or "XXXX.prw" patterns
    for match in re.finditer(r'rotina[:\s]+(\w+)', resolved_context, re.IGNORECASE):
        name = match.group(1).upper()
        if len(name) >= 6 and name[:4].isalpha():
            rotinas.add(name)

    for match in re.finditer(r'(\w+)\.pr[wx]', resolved_context, re.IGNORECASE):
        name = match.group(1).upper()
        if len(name) >= 6:
            rotinas.add(name)

    # Generate steps for each routine found
    for rotina in sorted(rotinas)[:3]:  # max 3 routines
        steps.append({
            "tool": "fonte_padrao",
            "args": {"arquivo": rotina},
            "reason": f"Verificar estrutura padrão de {rotina}",
        })
        steps.append({
            "tool": "pes_disponiveis",
            "args": {"rotina": rotina},
            "reason": f"PEs disponíveis no padrão de {rotina}",
        })

    return steps


def build_crossref_summary(
    client_pes: list[str],
    padrao_pes: list[dict],
    rotina: str = "",
) -> str:
    """Build a comparison summary between client PEs and standard PEs.

    Args:
        client_pes: PE names implemented by the client
        padrao_pes: PEs available in standard (from pes_disponiveis)
        rotina: Routine name for context

    Returns:
        Formatted markdown comparison.
    """
    if not padrao_pes:
        return ""

    client_set = set(pe.upper() for pe in client_pes)
    padrao_names = set(pe.get("nome_pe", "").upper() for pe in padrao_pes)

    implementados = client_set & padrao_names
    nao_implementados = padrao_names - client_set
    extras = client_set - padrao_names  # PEs the client has that aren't in standard

    lines = [f"## Comparação com Padrão{f' ({rotina})' if rotina else ''}"]
    lines.append(f"- PEs disponíveis no padrão: {len(padrao_names)}")
    lines.append(f"- PEs implementados pelo cliente: {len(implementados)}")

    if implementados:
        lines.append(f"- Implementados: {', '.join(sorted(implementados)[:10])}")

    if nao_implementados:
        lines.append(f"- **NÃO implementados** (oportunidades): {', '.join(sorted(nao_implementados)[:10])}")
        # Add context for the most interesting unimplemented PEs
        for pe_data in padrao_pes:
            if pe_data.get("nome_pe", "").upper() in nao_implementados:
                comment = pe_data.get("comentario", "")
                op = pe_data.get("operacao", "")
                ret = pe_data.get("tipo_retorno", "")
                if comment or op:
                    desc = comment[:60] if comment else op
                    lines.append(f"  - {pe_data['nome_pe']}: {desc} (retorno: {ret})")

    if extras:
        lines.append(f"- PEs extras do cliente (não no padrão): {', '.join(sorted(extras)[:5])}")

    return "\n".join(lines)


def quick_crossref(tabelas: list[str], rotinas: list[str] = None) -> Optional[str]:
    """Quick cross-reference lookup without LLM calls.

    Queries padrao.db directly for routine metadata and PEs.
    Returns formatted summary or None if padrao.db not available.
    """
    if not rotinas:
        return None

    sections = []
    for rotina in rotinas[:2]:
        try:
            fonte = pt.tool_fonte_padrao(rotina)
            if not fonte.get("encontrado"):
                continue

            pes = pt.tool_pes_disponiveis(rotina)

            lines = [f"**{rotina} no padrão**: {fonte.get('lines_of_code', 0)} LOC, {len(fonte.get('funcoes', []))} funções"]
            if pes:
                lines.append(f"  {len(pes)} PE(s) disponíveis:")
                for pe in pes[:8]:
                    op = pe.get("operacao", "")
                    ret = pe.get("tipo_retorno", "nil")
                    comment = pe.get("comentario", "")[:40]
                    desc = comment if comment else op
                    lines.append(f"  - {pe['nome_pe']}: {desc} → {ret}")
            sections.append("\n".join(lines))
        except Exception:
            continue

    if sections:
        return "## Referência Padrão\n" + "\n\n".join(sections)
    return None
