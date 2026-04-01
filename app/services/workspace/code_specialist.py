# backend/services/code_specialist.py
"""Code Specialist — ADVPL/TLPP code analysis, diagnosis and generation.

This service is invoked by the Analista when the investigation
determines that code needs to be read, diagnosed, corrected, or created.

It uses ADVPL knowledge from the skills docs and code examples.
"""
from pathlib import Path

ADVPL_DOCS_DIR = Path("ADVPL/Skills ADVPL/docs")
ADVPL_EXAMPLES_DIR = Path("ADVPL/Skills ADVPL/Exemplos")


def _load_advpl_rules() -> str:
    """Load core ADVPL rules from the skill file."""
    skill_path = Path("ADVPL/Skills ADVPL/.claude/skills/advpl.md")
    if not skill_path.exists():
        return ""

    content = skill_path.read_text(encoding="utf-8")

    # Extract key sections: boas práticas, o que não fazer, convenções
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
        # End section on next ## header that is NOT one of our keywords
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
    if not ADVPL_EXAMPLES_DIR.exists():
        return ""

    # Map tipo to example files
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
            return content[:3000]  # First 3K chars as example

    return ""


SPECIALIST_PROMPTS = {
    "diagnosticar": """Voce e um debugger especialista em ADVPL/TLPP para TOTVS Protheus.

REGRAS ADVPL:
{advpl_rules}

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
2. Identifique a causa raiz do problema
3. Explique o fluxo que leva ao erro
4. Proponha a correcao EXATA com codigo

Responda com:
## Diagnostico
[causa raiz]

## Fluxo do Problema
[passo a passo]

## Correcao Proposta
```advpl
[codigo corrigido]
```""",

    "gerar": """Voce e um desenvolvedor senior ADVPL/TLPP para TOTVS Protheus.

REGRAS ADVPL:
{advpl_rules}

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
1. Gere codigo ADVPL completo e funcional
2. Siga TODAS as boas praticas (GetArea/RestArea, notacao hungara, Local no topo)
3. Use os parametros REAIS do PE (PARAMIXB conforme documentado acima)
4. Inclua comentarios explicativos
5. Inclua tratamento de erro adequado

Responda com o codigo completo dentro de ```advpl ... ```""",

    "ajustar": """Voce e um desenvolvedor senior ADVPL/TLPP para TOTVS Protheus.

REGRAS ADVPL:
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
3. Siga boas praticas ADVPL
4. Explique cada alteracao feita

Responda com:
## Alteracoes
[lista de mudancas]

## Codigo Ajustado
```advpl
[codigo completo com ajuste]
```""",
}


def _build_specialist_prompt(modo: str, dossie: dict) -> str:
    """Build the specialist prompt with ADVPL rules and dossiê context."""
    template = SPECIALIST_PROMPTS.get(modo, SPECIALIST_PROMPTS["diagnosticar"])
    advpl_rules = _load_advpl_rules()

    # Fill template with dossiê fields (use empty string for missing keys)
    fields = {
        "advpl_rules": advpl_rules[:4000],
        "rotina": dossie.get("rotina", ""),
        "arquivo": dossie.get("arquivo", ""),
        "funcao": dossie.get("funcao", ""),
        "problema": dossie.get("problema", ""),
        "codigo": dossie.get("codigo", "")[:6000],
        "contexto": dossie.get("contexto", "")[:2000],
        "tipo": dossie.get("tipo", ""),
        "nome": dossie.get("nome", ""),
        "spec": dossie.get("spec", ""),
        "pes_info": dossie.get("pes_info", ""),
        "exemplo": _load_example(dossie.get("tipo", "pe"))[:2000],
        "diagnostico": dossie.get("diagnostico", ""),
        "ajuste": dossie.get("ajuste", ""),
    }

    return template.format(**fields)


def code_specialist(llm, modo: str, dossie: dict) -> dict:
    """Invoke the code specialist.

    Args:
        llm: LLMService instance
        modo: 'diagnosticar' | 'gerar' | 'ajustar'
        dossie: Context dict with relevant fields per modo

    Returns:
        {resposta: str, codigo: str (if generated)}
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

    return {
        "resposta": response,
        "codigo": codigo,
        "modo": modo,
    }
