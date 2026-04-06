# backend/services/code_specialist.py
"""Code Specialist — ADVPL/TLPP code analysis, diagnosis and generation.

This service is invoked by the Analista when the investigation
determines that code needs to be read, diagnosed, corrected, or created.

Uses structured knowledge from:
- knowledge/advpl/rules/     → 43 review rules (BP, PERF, SEC, MOD)
- knowledge/advpl/patterns/  → 6 generation templates (MVC, REST, PE, etc)
- knowledge/advpl/errors/    → 30 common errors with diagnosis
- ADVPL/Skills ADVPL/        → docs and code examples (fallback)
"""
import yaml
from pathlib import Path
from typing import Optional

ADVPL_DOCS_DIR = Path("ADVPL/Skills ADVPL/docs")
ADVPL_EXAMPLES_DIR = Path("ADVPL/Skills ADVPL/Exemplos")
KNOWLEDGE_ADVPL_DIR = Path("knowledge/advpl")

# ── Cached knowledge ─────────────────────────────────────────────────────────

_cached_rules: Optional[str] = None
_cached_patterns: Optional[dict] = None
_cached_errors: Optional[str] = None


def _load_knowledge_rules() -> str:
    """Load structured ADVPL rules from knowledge/advpl/rules/*.yaml.

    Returns formatted rules string for LLM prompt.
    Cached after first load.
    """
    global _cached_rules
    if _cached_rules is not None:
        return _cached_rules

    rules_dir = KNOWLEDGE_ADVPL_DIR / "rules"
    if not rules_dir.exists():
        _cached_rules = _load_advpl_rules_legacy()
        return _cached_rules

    sections = []
    for yaml_file in sorted(rules_dir.glob("*.yaml")):
        try:
            with open(yaml_file, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if not data or not data.get("rules"):
                continue

            name = data.get("name", yaml_file.stem)
            rules = data["rules"]
            lines = [f"### {name} ({len(rules)} regras)"]

            for rule in rules:
                severity = rule.get("severity", "medium").upper()
                lines.append(f"\n**[{rule['id']}] {rule.get('name','')}** ({severity})")
                lines.append(rule.get("description", ""))
                if rule.get("bad_pattern"):
                    lines.append(f"ERRADO:\n```advpl\n{rule['bad_pattern'].strip()}\n```")
                if rule.get("good_pattern"):
                    lines.append(f"CORRETO:\n```advpl\n{rule['good_pattern'].strip()}\n```")

            sections.append("\n".join(lines))
        except Exception:
            pass

    if sections:
        _cached_rules = "\n\n".join(sections)
    else:
        _cached_rules = _load_advpl_rules_legacy()

    return _cached_rules


def _load_knowledge_errors() -> str:
    """Load common errors from knowledge/advpl/errors/*.yaml."""
    global _cached_errors
    if _cached_errors is not None:
        return _cached_errors

    errors_file = KNOWLEDGE_ADVPL_DIR / "errors" / "common-errors.yaml"
    if not errors_file.exists():
        _cached_errors = ""
        return ""

    try:
        with open(errors_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not data or not data.get("rules"):
            _cached_errors = ""
            return ""

        lines = ["### Erros Comuns ADVPL (referencia para diagnostico)"]
        for err in data["rules"][:20]:  # Top 20 to fit in context
            lines.append(f"\n**[{err['id']}] {err.get('message', '')}**")
            lines.append(f"Causa: {err.get('cause', '')}")
            lines.append(f"Fix: {err.get('fix', '')[:200]}")

        _cached_errors = "\n".join(lines)
    except Exception:
        _cached_errors = ""

    return _cached_errors


def _load_knowledge_pattern(tipo: str) -> str:
    """Load a generation pattern from knowledge/advpl/patterns/*.yaml.

    Returns the template code for the requested pattern type.
    """
    global _cached_patterns
    if _cached_patterns is None:
        _cached_patterns = {}
        patterns_dir = KNOWLEDGE_ADVPL_DIR / "patterns"
        if patterns_dir.exists():
            for yaml_file in patterns_dir.glob("*.yaml"):
                try:
                    with open(yaml_file, encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                    if data and data.get("id"):
                        _cached_patterns[data["id"]] = data
                except Exception:
                    pass

    # Map tipo to pattern id
    tipo_map = {
        "pe": "ponto-entrada",
        "ponto_entrada": "ponto-entrada",
        "mvc": "mvc",
        "rest": "rest-api",
        "rest_api": "rest-api",
        "treport": "treport",
        "relatorio": "treport",
        "job": "jobs",
        "jobs": "jobs",
        "scheduler": "jobs",
        "browse": "fwformbrowse",
        "fwformbrowse": "fwformbrowse",
    }

    pattern_id = tipo_map.get(tipo.lower(), tipo.lower())
    pattern = _cached_patterns.get(pattern_id)

    if not pattern:
        return ""

    # Build template text from pattern
    parts = []
    parts.append(f"## Padrao: {pattern.get('name', tipo)}")
    parts.append(pattern.get("description", ""))

    # Include template if exists
    if pattern.get("template"):
        parts.append(f"\nTemplate completo:\n```advpl\n{pattern['template']}\n```")

    # Include sections
    for section in pattern.get("sections", []):
        parts.append(f"\n### {section.get('name', '')}")
        if section.get("description"):
            parts.append(section["description"])
        if section.get("code"):
            parts.append(f"```advpl\n{section['code']}\n```")

    return "\n".join(parts)[:4000]


def _load_advpl_rules_legacy() -> str:
    """Legacy: Load ADVPL rules from the skill file (fallback)."""
    skill_path = Path("ADVPL/Skills ADVPL/.claude/skills/advpl.md")
    if not skill_path.exists():
        return ""

    content = skill_path.read_text(encoding="utf-8")
    sections = []
    in_section = False
    current = []

    keywords = ["Boas práticas", "O que NÃO fazer", "Convenção de nomenclatura",
                 "Padrões por tipo", "Pontos de Entrada", "Código limpo"]
    for line in content.split("\n"):
        if any(kw in line for kw in keywords) and line.startswith("#"):
            if current:
                sections.append("\n".join(current))
            current = [line]
            in_section = True
            continue
        if line.startswith("## ") and in_section and not any(kw in line for kw in keywords):
            sections.append("\n".join(current))
            current = []
            in_section = False
        elif in_section:
            current.append(line)

    if current:
        sections.append("\n".join(current))

    return "\n\n".join(sections)


def _load_example(tipo: str) -> str:
    """Load a relevant code example for few-shot prompting."""
    # First try knowledge pattern template
    pattern = _load_knowledge_pattern(tipo)
    if pattern:
        return pattern[:3000]

    # Fallback to example files
    if not ADVPL_EXAMPLES_DIR.exists():
        return ""

    examples = {
        "pe": ["A300STRU.prw", "DAMDFE.prw"],
        "mvc": ["custom.mvc.customers.tlpp", "custom.mvc.quote.tlpp"],
        "tlpp": ["custom.mvc.monitors.tlpp"],
    }

    files = examples.get(tipo, list(examples.values())[0])
    for fname in files:
        fpath = ADVPL_EXAMPLES_DIR / fname
        if fpath.exists():
            content = fpath.read_text(encoding="utf-8", errors="replace")
            return content[:3000]

    return ""


SPECIALIST_PROMPTS = {
    "diagnosticar": """Voce e um debugger especialista em ADVPL/TLPP para TOTVS Protheus.

REGRAS ADVPL (use como checklist de problemas):
{advpl_rules}

ERROS COMUNS (consulte para diagnostico rapido):
{common_errors}

DOSSIE DO PROBLEMA:
Rotina: {rotina}
Fonte: {arquivo}
Funcao: {funcao}
Problema reportado: {problema}

CODIGO:
{codigo}

CONTEXTO ADICIONAL:
{contexto}

INSTRUCOES:
1. Leia o codigo linha por linha
2. Verifique contra as REGRAS ADVPL acima — qual regra foi violada?
3. Consulte ERROS COMUNS — este problema corresponde a algum catalogado?
4. Identifique a causa raiz do problema
5. Explique o fluxo que leva ao erro
6. Proponha a correcao EXATA com codigo

Responda com:
## Diagnostico
[causa raiz + qual regra foi violada (ex: BP-001, PERF-003)]

## Fluxo do Problema
[passo a passo]

## Correcao Proposta
```advpl
[codigo corrigido seguindo as regras]
```

## Regras Violadas
[lista das regras BP/PERF/SEC que o codigo viola]""",

    "gerar": """Voce e um desenvolvedor senior ADVPL/TLPP para TOTVS Protheus.

REGRAS ADVPL (siga TODAS):
{advpl_rules}

PADRAO DE REFERENCIA (template para o tipo solicitado):
{pattern_template}

ESPECIFICACAO:
Tipo: {tipo}
Nome: {nome}
Objetivo: {spec}

CONTEXTO:
{contexto}

PEs DISPONIVEIS (parametros reais do fonte padrao):
{pes_info}

EXEMPLO DE REFERENCIA:
{exemplo}

INSTRUCOES:
1. Siga o PADRAO DE REFERENCIA como base estrutural
2. Gere codigo ADVPL completo e funcional
3. Siga TODAS as regras (GetArea/RestArea, notacao hungara, Local no topo)
4. Use os parametros REAIS do PE (PARAMIXB conforme documentado)
5. Inclua Begin Sequence/Recover para operacoes criticas
6. Inclua comentarios explicativos
7. Use xFilial() em todas as buscas de registro

Responda com o codigo completo dentro de ```advpl ... ```""",

    "ajustar": """Voce e um desenvolvedor senior ADVPL/TLPP para TOTVS Protheus.

REGRAS ADVPL (use como checklist):
{advpl_rules}

CODIGO ATUAL:
{codigo}

DIAGNOSTICO:
{diagnostico}

AJUSTE NECESSARIO:
{ajuste}

INSTRUCOES:
1. Aplique o ajuste mantendo o estilo existente do codigo
2. Nao altere partes que nao precisam mudar
3. Verifique se o ajuste introduz violacao de alguma regra
4. Siga boas praticas ADVPL
5. Explique cada alteracao feita

Responda com:
## Alteracoes
[lista de mudancas + regras que o ajuste resolve]

## Codigo Ajustado
```advpl
[codigo completo com ajuste]
```""",

    "review": """Voce e um code reviewer especialista em ADVPL/TLPP para TOTVS Protheus.

REGRAS DE REVIEW (verifique CADA UMA):
{advpl_rules}

CODIGO PARA REVIEW:
{codigo}

CONTEXTO:
{contexto}

INSTRUCOES:
Analise o codigo contra CADA regra e reporte:
1. Regras VIOLADAS com severidade (critical/high/medium/low)
2. Para cada violacao: linha aproximada, o que esta errado, como corrigir
3. Regras ATENDIDAS (confirmacao positiva)
4. Sugestoes de melhoria (nao violacoes, mas oportunidades)
5. Score geral (0-100)

Responda com:
## Violacoes Encontradas
[lista com ID da regra, severidade, descricao, linha, fix]

## Pontos Positivos
[o que esta bem feito]

## Sugestoes de Melhoria
[oportunidades opcionais]

## Score: XX/100
[justificativa]""",
}


def _build_specialist_prompt(modo: str, dossie: dict) -> str:
    """Build the specialist prompt with structured ADVPL knowledge.

    Uses knowledge/advpl/ rules, patterns, and errors instead of
    just the skill file. Falls back to legacy if knowledge not available.
    """
    template = SPECIALIST_PROMPTS.get(modo, SPECIALIST_PROMPTS["diagnosticar"])

    # Load structured knowledge
    advpl_rules = _load_knowledge_rules()
    common_errors = _load_knowledge_errors() if modo == "diagnosticar" else ""
    tipo = dossie.get("tipo", "pe")
    pattern_template = _load_knowledge_pattern(tipo) if modo == "gerar" else ""

    # Fill template with dossiê fields
    fields = {
        "advpl_rules": advpl_rules[:6000],
        "common_errors": common_errors[:2000],
        "pattern_template": pattern_template[:4000],
        "rotina": dossie.get("rotina", ""),
        "arquivo": dossie.get("arquivo", ""),
        "funcao": dossie.get("funcao", ""),
        "problema": dossie.get("problema", ""),
        "codigo": dossie.get("codigo", "")[:6000],
        "contexto": dossie.get("contexto", "")[:2000],
        "tipo": tipo,
        "nome": dossie.get("nome", ""),
        "spec": dossie.get("spec", ""),
        "pes_info": dossie.get("pes_info", ""),
        "exemplo": _load_example(tipo)[:2000],
        "diagnostico": dossie.get("diagnostico", ""),
        "ajuste": dossie.get("ajuste", ""),
    }

    return template.format(**fields)


def code_specialist(llm, modo: str, dossie: dict) -> dict:
    """Invoke the code specialist.

    Args:
        llm: LLMService instance
        modo: 'diagnosticar' | 'gerar' | 'ajustar' | 'review'
        dossie: Context dict with relevant fields per modo

    Returns:
        {resposta: str, codigo: str (if generated), regras_violadas: list}
    """
    prompt = _build_specialist_prompt(modo, dossie)

    response = llm._call(
        [{"role": "user", "content": prompt}],
        temperature=0.2,
        use_gen=False,  # Use stronger chat model
        timeout=90,
    )

    # Extract code blocks if present
    import re
    code_blocks = re.findall(r'```(?:advpl|tlpp)?\s*\n(.*?)```', response, re.DOTALL)
    codigo = code_blocks[0].strip() if code_blocks else ""

    # Extract violated rules (BP-001, PERF-003, etc.)
    regras = re.findall(r'\b(BP-\d{3}|PERF-\d{3}|SEC-\d{3}|MOD-\d{3})\b', response)

    return {
        "resposta": response,
        "codigo": codigo,
        "modo": modo,
        "regras_violadas": list(set(regras)),
    }
