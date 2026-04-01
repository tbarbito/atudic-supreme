"""Orchestrates Base Padrão enrichment: ChromaDB + Web + LLM → markdown insertion."""
import json
import re
from datetime import date
from pathlib import Path
from app.services.workspace.web_search import search_and_fetch

PADRAO_DIR = Path("processoPadrao")

ENRICH_PROMPT = """Você é um especialista em TOTVS Protheus. O usuário está consultando o módulo "{modulo}".

REGRAS ABSOLUTAS:
- Responda APENAS com base nas fontes fornecidas abaixo (TDN, Web, Base Padrão).
- NÃO invente funcionalidades, parâmetros ou comportamentos que não estejam nas fontes.
- Se não encontrar informação suficiente nas fontes, diga EXPLICITAMENTE que não encontrou.
- Use `monospace` para nomes técnicos: campos, rotinas, tabelas, parâmetros MV_.

FORMATO DA RESPOSTA — CRÍTICO:
O documento já contém tabelas markdown existentes. Você DEVE copiar o formato EXATO.

Quando a resposta for DADOS TABULARES (campos, parâmetros MV_, pontos de entrada, índices, gatilhos):
- Gere APENAS as LINHAS NOVAS da tabela, SEM header e SEM separador (---|---).
- COPIE o número de colunas e o formato da tabela existente mostrada abaixo.
- Use `backticks` em nomes técnicos (campos, rotinas, parâmetros) — IGUAL ao documento existente.
- Exemplo correto: se tabela existente tem 3 colunas | Campo | Descrição | Observação |:
  | `A1_CGC` | CNPJ/CPF do Cliente | Documento fiscal |
  | `A1_INSCR` | Inscrição Estadual | Obrigatório para contribuintes |
- Exemplo ERRADO (não faça): | A1_CGC | CNPJ/CPF |  (faltou coluna e backtick)

Quando a resposta for TEXTO DESCRITIVO (explicações, fluxos, observações):
- Gere markdown normal (parágrafos, listas, etc.)

CAMPO "tipo_insercao":
- "tabela" = dados devem ser ADICIONADOS como linhas na tabela existente mais próxima
- "texto" = conteúdo deve ser inserido como bloco de texto

SEÇÃO ALVO:
- O campo "secao_sugerida" DEVE ser o título EXATO de uma das seções existentes.
- Se a pergunta é sobre uma ROTINA ESPECÍFICA, use a seção da rotina.
- Se é sobre parâmetros GLOBAIS, use "2. Parametrização Geral do Módulo".

SEÇÕES EXISTENTES NO DOCUMENTO (use o título EXATO):
{secoes_existentes}

CONTEÚDO ATUAL DA SEÇÃO ALVO (para referência de formato):
{conteudo_secao}

FONTES TDN:
{contexto_tdn}

FONTES WEB:
{contexto_web}

FONTES BASE PADRÃO:
{contexto_padrao}

PERGUNTA DO USUÁRIO:
{pergunta}

Responda APENAS no formato JSON válido:
{{"encontrou": true/false, "secao_sugerida": "título EXATO da seção", "tipo_insercao": "tabela ou texto", "resposta_md": "linhas da tabela OU texto markdown", "resumo": "descrição curta do que foi adicionado", "fontes": ["fonte1", "fonte2"]}}
"""


def _get_existing_sections(content: str) -> list[str]:
    """Extract h2 and h3 section titles from markdown content.

    Includes ### (rotina subsections) so the LLM can target specific rotinas.
    """
    h2 = re.findall(r'^## (.+)$', content, re.MULTILINE)
    h3 = re.findall(r'^### (.+)$', content, re.MULTILINE)
    return h2 + h3


def _extract_table_samples(content: str) -> str:
    """Extract samples of markdown tables from the document to show format to LLM.

    Returns a few table headers + first 2 rows as format examples.
    """
    lines = content.split("\n")
    samples = []
    i = 0
    while i < len(lines) and len(samples) < 3:
        line = lines[i].strip()
        # Find table header (| Header1 | Header2 |)
        if line.startswith("|") and line.endswith("|") and "---" not in line:
            # Check if next line is separator
            if i + 1 < len(lines) and "---" in lines[i + 1]:
                table_lines = [lines[i], lines[i + 1]]
                # Grab up to 2 data rows
                for j in range(i + 2, min(i + 4, len(lines))):
                    if lines[j].strip().startswith("|"):
                        table_lines.append(lines[j])
                    else:
                        break
                samples.append("\n".join(table_lines))
                i += len(table_lines)
                continue
        i += 1

    if not samples:
        return "Nenhuma tabela encontrada no documento."

    return "Exemplos de tabelas existentes no documento (COPIE o formato EXATO — mesmas colunas, backticks em nomes técnicos):\n\n" + "\n\n".join(samples)


def _get_section_content(content: str, section_title: str) -> str:
    """Extract the content of a specific section for context."""
    lines = content.split("\n")
    target_norm = _normalize(section_title)
    in_section = False
    section_lines = []

    for line in lines:
        if line.startswith("## ") or (line.startswith("### ") and not line.startswith("#### ")):
            title = line.lstrip("#").strip()
            if _normalize(title) == target_norm:
                in_section = True
                continue
            elif in_section:
                break
        if in_section:
            section_lines.append(line)

    return "\n".join(section_lines[:100])  # Limit to 100 lines for context


async def enrich(slug: str, pergunta: str, vs, llm) -> dict:
    """Search sources and generate enrichment preview.

    Args:
        slug: module filename stem (e.g. SIGACOM_Fluxo_Compras)
        pergunta: user question
        vs: VectorStore instance (initialized)
        llm: LLMService instance

    Returns:
        dict with keys: encontrou, secao_sugerida, tipo_insercao, resposta_md, resumo, fontes
    """
    md_path = PADRAO_DIR / f"{slug}.md"
    if not md_path.exists():
        return {"encontrou": False, "secao_sugerida": "", "tipo_insercao": "texto", "resposta_md": "", "resumo": "", "fontes": []}

    content = md_path.read_text(encoding="utf-8")
    secoes = _get_existing_sections(content)

    # 1. ChromaDB: TDN collection
    tdn_results = vs.search("tdn", pergunta, n_results=5)
    contexto_tdn = "\n\n".join([r["content"] for r in tdn_results]) if tdn_results else "Nenhum resultado no TDN."

    # 2. ChromaDB: padrao collection (other modules)
    padrao_results = vs.search("padrao", pergunta, n_results=3)
    contexto_padrao = "\n\n".join([r["content"] for r in padrao_results]) if padrao_results else "Nenhum resultado na base padrão."

    # 3. Web search (best-effort)
    web_results = await search_and_fetch(pergunta + " TOTVS Protheus")
    contexto_web = "\n\n".join([f"URL: {r['url']}\n{r['content']}" for r in web_results]) if web_results else "Nenhum resultado web."

    # 4. LLM call
    modulo = slug.split("_")[0] if "_" in slug else slug

    # Extract table samples from the document for format reference
    table_samples = _extract_table_samples(content)

    prompt = ENRICH_PROMPT.format(
        modulo=modulo,
        secoes_existentes="\n".join(f"- {s}" for s in secoes) if secoes else "Nenhuma seção encontrada.",
        conteudo_secao=table_samples,
        contexto_tdn=contexto_tdn[:8000],
        contexto_web=contexto_web[:5000],
        contexto_padrao=contexto_padrao[:5000],
        pergunta=pergunta,
    )

    raw = llm._call(
        [{"role": "user", "content": prompt}],
        temperature=0.2,
        use_gen=True,
    )

    # Parse JSON response
    try:
        clean = re.sub(r'^```json\s*', '', raw.strip())
        clean = re.sub(r'\s*```$', '', clean)
        result = json.loads(clean)
    except json.JSONDecodeError:
        result = {
            "encontrou": False,
            "secao_sugerida": "",
            "tipo_insercao": "texto",
            "resposta_md": raw,
            "resumo": "",
            "fontes": [],
        }

    # Ensure required fields
    result.setdefault("tipo_insercao", "texto")
    result.setdefault("resumo", "")

    # Add web URLs to fontes
    for wr in web_results:
        if wr["url"] not in result.get("fontes", []):
            result.setdefault("fontes", []).append(wr["url"])

    return result


def _normalize(text: str) -> str:
    """Normalize text for fuzzy section matching: lowercase, strip numbers, punctuation."""
    text = re.sub(r'^\d+[\.\)]\s*', '', text)  # strip leading "7. " or "7) "
    text = re.sub(r'[^\w\s]', '', text.lower()).strip()
    return text


def _find_best_section(lines: list[str], target: str) -> int | None:
    """Find the best matching h2 or h3 section for the target title.

    Uses 3 strategies:
    1. Exact match (after normalization)
    2. Target is contained in section title (e.g. "Parâmetros" matches "7. Principais Parâmetros (MV_)")
    3. Section title is contained in target

    Returns the line index of the NEXT section header (insertion point) or len(lines) for last section.
    """
    target_norm = _normalize(target)
    section_indices = []  # list of (line_idx, normalized_title, raw_title, level)

    for i, line in enumerate(lines):
        if line.startswith("### ") and not line.startswith("#### "):
            title = line[4:].strip()
            section_indices.append((i, _normalize(title), title, 3))
        elif line.startswith("## "):
            title = line[3:].strip()
            section_indices.append((i, _normalize(title), title, 2))

    if not section_indices:
        return None

    # Strategy 1: Exact match
    for idx, (line_i, norm_title, _, level) in enumerate(section_indices):
        if norm_title == target_norm:
            next_section = section_indices[idx + 1][0] if idx + 1 < len(section_indices) else len(lines)
            return next_section

    # Strategy 2: Target contained in section title (e.g. "parametros" in "principais parametros mv")
    for idx, (line_i, norm_title, _, level) in enumerate(section_indices):
        if target_norm in norm_title:
            next_section = section_indices[idx + 1][0] if idx + 1 < len(section_indices) else len(lines)
            return next_section

    # Strategy 3: Section title keywords contained in target
    for idx, (line_i, norm_title, _, level) in enumerate(section_indices):
        # Check if the main keyword of the section is in the target
        keywords = [w for w in norm_title.split() if len(w) > 3]
        if keywords and any(kw in target_norm for kw in keywords):
            next_section = section_indices[idx + 1][0] if idx + 1 < len(section_indices) else len(lines)
            return next_section

    return None


def _find_last_table_row(lines: list[str], section_start: int, section_end: int) -> int | None:
    """Find the line index of the last row of a markdown table within a section.

    Returns the index of the last table row, or None if no table found.
    """
    last_table_row = None
    in_table = False
    for i in range(section_start, section_end):
        line = lines[i].strip()
        if line.startswith("|") and line.endswith("|"):
            in_table = True
            last_table_row = i
        elif in_table and not line.startswith("|"):
            # End of table — return last row
            break
    return last_table_row


def _append_enrichment_log(lines: list[str], today: str, resumo: str, secao: str, fontes_str: str):
    """Append an entry to the '14. Enriquecimentos' section."""
    enrich_idx = None
    for i, line in enumerate(lines):
        if line.startswith("## ") and "enriquecimento" in line.lower():
            enrich_idx = i
            break

    if enrich_idx is not None:
        log_entry = f"\n- **{today}** — {resumo} (Seção: {secao}) | Fontes: {fontes_str}"
        # Find end of section 14 or end of file
        insert_at = len(lines)
        for j in range(enrich_idx + 1, len(lines)):
            if lines[j].startswith("## "):
                insert_at = j
                break
        lines.insert(insert_at, log_entry)


def apply_enrichment(slug: str, resposta_md: str, secao_sugerida: str, fontes: list[str],
                     pergunta: str, tipo_insercao: str = "texto", resumo: str = "") -> str:
    """Insert enrichment into the module markdown file.

    If tipo_insercao == "tabela": appends rows to the last table in the target section.
    If tipo_insercao == "texto": inserts as a text block at end of section.
    Always logs the enrichment in section 14 (Enriquecimentos).

    Returns the updated content.
    """
    md_path = PADRAO_DIR / f"{slug}.md"
    if not md_path.exists():
        raise FileNotFoundError(f"File not found: {md_path}")

    content = md_path.read_text(encoding="utf-8")
    today = date.today().strftime("%d/%m/%Y")
    fontes_str = ", ".join(fontes) if fontes else "N/A"

    lines = content.split("\n")

    # Find the section boundaries
    section_start = None
    section_end = None
    target_norm = _normalize(secao_sugerida)

    for i, line in enumerate(lines):
        if line.startswith("## ") or (line.startswith("### ") and not line.startswith("#### ")):
            title = line.lstrip("#").strip()
            norm = _normalize(title)
            if section_start is not None and section_end is None:
                section_end = i
                break
            if norm == target_norm or target_norm in norm or any(
                kw in target_norm for kw in norm.split() if len(kw) > 3
            ):
                section_start = i

    if section_start is not None and section_end is None:
        section_end = len(lines)

    if tipo_insercao == "tabela" and section_start is not None:
        # Find the last table in the section and append rows
        last_row = _find_last_table_row(lines, section_start, section_end)
        if last_row is not None:
            # Insert new table rows after the last existing row
            new_rows = [l for l in resposta_md.strip().split("\n") if l.strip().startswith("|")]
            for offset, row in enumerate(new_rows):
                lines.insert(last_row + 1 + offset, row)
        else:
            # No table found — insert as text block at end of section
            lines.insert(section_end, f"\n{resposta_md}\n")
    elif section_start is not None:
        # Text insertion — add at end of section
        lines.insert(section_end, f"\n{resposta_md}\n")
    else:
        # Section not found — use fallback
        insert_idx = _find_best_section(lines, secao_sugerida)
        if insert_idx is not None:
            lines.insert(insert_idx, f"\n{resposta_md}\n")
        else:
            # Last resort: before Referências
            ref_idx = None
            for i, line in enumerate(lines):
                if line.startswith("## ") and "referên" in line.lower():
                    ref_idx = i
                    break
            if ref_idx is not None:
                lines.insert(ref_idx, f"\n## {secao_sugerida}\n\n{resposta_md}\n")
            else:
                lines.append(f"\n## {secao_sugerida}\n\n{resposta_md}\n")

    # Log enrichment in section 14
    if not resumo:
        resumo = f"Pergunta: {pergunta[:80]}"
    _append_enrichment_log(lines, today, resumo, secao_sugerida, fontes_str)

    updated = "\n".join(lines)
    md_path.write_text(updated, encoding="utf-8")
    return updated
