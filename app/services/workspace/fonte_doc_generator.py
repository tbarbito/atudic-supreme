"""Generate per-fonte Markdown documentation.

Sections 1-7: pure SQL queries (zero LLM cost).
Section 8: LLM synthesis using sections 1-7 as context.
"""
import json
import sqlite3
from pathlib import Path


def _safe_json(val) -> list:
    if not val:
        return []
    if isinstance(val, list):
        return val
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return []


def _query_all(conn, sql, params=()):
    return conn.execute(sql, params).fetchall()


def _query_one(conn, sql, params=()):
    return conn.execute(sql, params).fetchone()


def _parse_resumo(text: str) -> str:
    """Extract human-readable text from resumo/proposito JSON fields."""
    if not text:
        return ""
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            # Try humano first, then ia.resumo
            if "humano" in parsed:
                return parsed["humano"]
            if "ia" in parsed:
                ia = parsed["ia"]
                if isinstance(ia, dict) and "resumo" in ia:
                    return ia["resumo"]
                if isinstance(ia, str):
                    return ia
            if "resumo" in parsed:
                return parsed["resumo"]
        return text
    except (json.JSONDecodeError, TypeError):
        return text


def _table_exists(conn, name):
    row = conn.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row and row[0] > 0


def _section_header(arquivo: str, meta: dict) -> str:
    lines = [f"# {arquivo}", ""]
    tags = []
    if meta.get("modulo"):
        tags.append(f"**Módulo:** {meta['modulo']}")
    if meta.get("source_type"):
        tags.append(f"**Tipo:** {meta['source_type']}")
    if meta.get("loc"):
        tags.append(f"**LOC:** {meta['loc']}")
    if meta.get("encoding"):
        tags.append(f"**Encoding:** {meta['encoding']}")
    lines.append(" | ".join(tags))
    lines.append("")
    if meta.get("proposito"):
        proposito_text = _parse_resumo(meta["proposito"])
        if proposito_text:
            lines.append(f"> {proposito_text}")
            lines.append("")
    return "\n".join(lines)


def _section_funcoes(conn, arquivo: str) -> str:
    if not _table_exists(conn, "funcao_docs"):
        return ""
    rows = _query_all(conn,
        "SELECT funcao, tipo, assinatura, retorno, resumo "
        "FROM funcao_docs WHERE arquivo=? ORDER BY funcao",
        (arquivo,))
    if not rows:
        return ""
    lines = ["## 1. Funções", "",
             "| Função | Tipo | Resumo |",
             "|--------|------|--------|"]
    for r in rows:
        funcao, tipo, assinatura, retorno, resumo = r
        resumo_text = _parse_resumo(resumo)
        resumo_text = resumo_text.replace("|", "\\|").replace("\n", " ")[:200]
        lines.append(f"| {funcao} | {tipo or ''} | {resumo_text} |")
    lines.append("")
    return "\n".join(lines)


def _section_tabelas(conn, arquivo: str) -> str:
    row = _query_one(conn,
        "SELECT tabelas_ref, write_tables, fields_ref FROM fontes WHERE arquivo=?",
        (arquivo,))
    if not row:
        return ""
    tabelas_ref = _safe_json(row[0])
    write_tables = _safe_json(row[1])
    fields_ref = _safe_json(row[2])

    # Group fields by table prefix
    fields_by_table = {}
    for f in fields_ref:
        for t in tabelas_ref + write_tables:
            if len(t) == 3 and f.startswith(t[1:3] + "_"):
                fields_by_table.setdefault(t, []).append(f)
                break

    lines = ["## 2. Tabelas e Campos", ""]

    if tabelas_ref:
        read_only = [t for t in tabelas_ref if t not in write_tables]
        if read_only:
            lines += ["### Leitura", "",
                      "| Tabela | Campos Referenciados |",
                      "|--------|---------------------|"]
            for t in sorted(read_only):
                campos = fields_by_table.get(t, [])
                if not campos:
                    continue
                lines.append(f"| {t} | {', '.join(sorted(campos))} |")
            lines.append("")

    if write_tables:
        lines += ["### Escrita", "",
                  "| Tabela | Campos Referenciados |",
                  "|--------|---------------------|"]
        for t in sorted(write_tables):
            campos = fields_by_table.get(t, [])
            if not campos:
                continue
            lines.append(f"| {t} | {', '.join(sorted(campos))} |")
        lines.append("")

    return "\n".join(lines)


def _section_grafo(conn, arquivo: str) -> str:
    if not _table_exists(conn, "funcao_docs"):
        return ""
    rows = _query_all(conn,
        "SELECT funcao, chama, chamada_por FROM funcao_docs WHERE arquivo=?",
        (arquivo,))
    if not rows:
        return ""

    all_chama = {}
    all_chamada_por = {}
    for funcao, chama_json, chamada_json in rows:
        for c in _safe_json(chama_json):
            all_chama[c] = funcao
        for c in _safe_json(chamada_json):
            all_chamada_por[c] = funcao

    chama_resolved = []
    for called, caller in all_chama.items():
        dest_row = _query_one(conn,
            "SELECT arquivo FROM funcao_docs WHERE funcao=? LIMIT 1",
            (called,))
        dest = dest_row[0] if dest_row else "?"
        chama_resolved.append((caller, called, dest))

    chamada_resolved = []
    for caller, target in all_chamada_por.items():
        src_row = _query_one(conn,
            "SELECT arquivo FROM funcao_docs WHERE funcao=? LIMIT 1",
            (caller,))
        src = src_row[0] if src_row else "?"
        chamada_resolved.append((caller, src, target))

    lines = ["## 3. Grafo de Chamadas", ""]

    if chama_resolved:
        lines += ["### Este fonte chama:", ""]
        for caller, called, dest in sorted(chama_resolved):
            lines.append(f"- `{caller}` → `U_{called}` ({dest})")
        lines.append("")

    if chamada_resolved:
        lines += ["### Chamado por:", ""]
        for caller, src, target in sorted(chamada_resolved):
            lines.append(f"- `{caller}` ({src}) → `{target}`")
        lines.append("")

    if not chama_resolved and not chamada_resolved:
        lines += ["Nenhuma chamada externa detectada.", ""]

    return "\n".join(lines)


def _section_pes(conn, arquivo: str) -> str:
    row = _query_one(conn, "SELECT pontos_entrada FROM fontes WHERE arquivo=?", (arquivo,))
    pes = _safe_json(row[0]) if row else []
    if not pes:
        return ""

    lines = ["## 4. Pontos de Entrada", "",
             "| PE | Rotina Afetada |",
             "|----|---------------|"]

    for pe in pes:
        vrow = None
        if _table_exists(conn, "vinculos"):
            vrow = _query_one(conn,
                "SELECT destino FROM vinculos WHERE tipo='pe_afeta_rotina' AND origem=? LIMIT 1",
                (pe,))
        rotina = vrow[0] if vrow else "—"
        lines.append(f"| {pe} | {rotina} |")

    lines.append("")
    return "\n".join(lines)


def _section_menus(conn, arquivo: str) -> str:
    row = _query_one(conn, "SELECT funcoes FROM fontes WHERE arquivo=?", (arquivo,))
    funcoes = _safe_json(row[0]) if row else []
    if not funcoes:
        return ""

    menu_hits = []
    for func in funcoes:
        if _table_exists(conn, "mpmenu"):
            try:
                mrows = _query_all(conn,
                    "SELECT menu, rotina, descricao FROM mpmenu WHERE rotina LIKE ? LIMIT 5",
                    (f"%{func}%",))
                for m in mrows:
                    menu_hits.append({"menu": m[0] or "", "rotina": m[1] or "", "descricao": m[2] or ""})
            except Exception:
                pass

        if _table_exists(conn, "vinculos"):
            try:
                vrows = _query_all(conn,
                    "SELECT origem, destino FROM vinculos WHERE tipo='menu_chama_rotina' AND destino LIKE ?",
                    (f"%{func}%",))
                for v in vrows:
                    menu_hits.append({"menu": v[0], "rotina": v[1], "descricao": ""})
            except Exception:
                pass

    if not menu_hits:
        return ""

    seen = set()
    unique = []
    for h in menu_hits:
        key = h["rotina"]
        if key not in seen:
            seen.add(key)
            unique.append(h)

    lines = ["## 5. Menus", "",
             "| Menu | Rotina | Descrição |",
             "|------|--------|-----------|"]
    for h in unique:
        lines.append(f"| {h['menu']} | {h['rotina']} | {h['descricao'][:80]} |")
    lines.append("")
    return "\n".join(lines)


def _section_padrao(conn, arquivo: str) -> str:
    row = _query_one(conn,
        "SELECT tabelas_ref, write_tables, fields_ref FROM fontes WHERE arquivo=?",
        (arquivo,))
    if not row:
        return ""
    tabelas = list(set(_safe_json(row[0]) + _safe_json(row[1])))
    fields_ref = set(_safe_json(row[2]))
    if not tabelas:
        return ""

    lines = ["## 6. Interação com Padrão", ""]
    placeholders = ",".join("?" * len(tabelas))

    # Custom fields — only those actually referenced by this fonte
    custom_rows = []
    if _table_exists(conn, "campos") and _table_exists(conn, "padrao_campos"):
        try:
            all_custom = _query_all(conn,
                f"SELECT tabela, campo, tipo, tamanho, titulo FROM campos "
                f"WHERE tabela IN ({placeholders}) AND campo NOT IN "
                f"(SELECT campo FROM padrao_campos WHERE tabela=campos.tabela) "
                f"ORDER BY tabela, campo",
                tabelas)
            # Filter: only fields referenced by this fonte
            if fields_ref:
                custom_rows = [r for r in all_custom if r[1] in fields_ref]
            else:
                custom_rows = all_custom
        except Exception:
            pass

    if custom_rows:
        lines += ["### Campos Customizados nas Tabelas Referenciadas", "",
                  "| Tabela | Campo | Tipo | Tamanho | Título |",
                  "|--------|-------|------|---------|--------|"]
        for r in custom_rows[:50]:
            lines.append(f"| {r[0]} | {r[1]} | {r[2] or ''} | {r[3] or ''} | {r[4] or ''} |")
        lines.append("")

    if not custom_rows:
        lines += ["Nenhuma customização detectada nas tabelas referenciadas.", ""]

    return "\n".join(lines)


def _section_params(conn, arquivo: str) -> str:
    """Show SX6 parameters and SX1 groups per function, enriched with SX6 data."""
    if not _table_exists(conn, "funcao_docs"):
        return ""
    rows = _query_all(conn,
        "SELECT funcao, params FROM funcao_docs WHERE arquivo=? ORDER BY funcao",
        (arquivo,))
    if not rows:
        return ""

    has_sx6 = False
    has_sx1 = False
    sx6_lines = ["### Parâmetros SX6", "",
                 "| Função | Parâmetro | Valor Efetivo | Descrição |",
                 "|--------|-----------|--------------|-----------|"]
    sx1_lines = ["### Grupos de Perguntas SX1", "",
                 "| Função | Grupo |",
                 "|--------|-------|"]

    has_parametros = _table_exists(conn, "parametros")

    for funcao, params_json in rows:
        params = _safe_json(params_json) if isinstance(params_json, str) else params_json
        if not params or not isinstance(params, dict):
            continue

        # SX6
        for p in params.get("sx6", []):
            var = p.get("var", "")
            default_inline = p.get("default", "")
            desc_sx6 = ""
            val_sx6 = ""
            if has_parametros and var:
                prow = _query_one(conn,
                    "SELECT descricao, conteudo FROM parametros WHERE variavel=? LIMIT 1",
                    (var,))
                if prow:
                    desc_sx6 = (prow[0] or "")[:80].replace("|", "\\|")
                    val_sx6 = (prow[1] or "")[:40].replace("|", "\\|")
            # Valor efetivo: SX6 se tem, senão default inline
            valor_efetivo = val_sx6 if val_sx6 else default_inline
            # Origem
            if val_sx6:
                valor_efetivo = f"{val_sx6} *(SX6)*"
            elif default_inline:
                valor_efetivo = f"{default_inline} *(default código)*"
            else:
                valor_efetivo = "—"
            sx6_lines.append(f"| {funcao} | `{var}` | {valor_efetivo} | {desc_sx6} |")
            has_sx6 = True

        # SX1
        for grp in params.get("sx1", []):
            sx1_lines.append(f"| {funcao} | {grp} |")
            has_sx1 = True

    if not has_sx6 and not has_sx1:
        return ""

    lines = ["## Parâmetros", ""]
    if has_sx6:
        lines += sx6_lines + [""]
    if has_sx1:
        lines += sx1_lines + [""]

    return "\n".join(lines)


def _section_codigo(conn, arquivo: str) -> str:
    if not _table_exists(conn, "fonte_chunks"):
        return ""
    rows = _query_all(conn,
        "SELECT funcao, content FROM fonte_chunks WHERE arquivo=? ORDER BY id",
        (arquivo,))
    if not rows:
        return ""

    lines = ["## 7. Código — Resumo por Função", ""]
    seen = set()
    for funcao, content in rows:
        if funcao in seen or funcao == "_header":
            continue
        seen.add(funcao)
        preview = "\n".join((content or "").splitlines()[:30])
        lines += [f"### {funcao}", "", "```advpl", preview, "```", ""]

    return "\n".join(lines)


async def _section_sintese(sections_text: str, arquivo: str, llm_config: dict) -> str:
    try:
        from litellm import acompletion
    except ImportError:
        return "## 8. Síntese\n\n> LiteLLM não disponível.\n"

    import os
    provider = llm_config.get("provider", "anthropic")
    model_name = llm_config.get("model", "claude-sonnet-4-20250514")
    model = f"{provider}/{model_name}" if "/" not in model_name else model_name

    # Set API keys from config if not in env
    api_keys = llm_config.get("api_keys", {})
    if api_keys.get("anthropic") and not os.environ.get("ANTHROPIC_API_KEY"):
        os.environ["ANTHROPIC_API_KEY"] = api_keys["anthropic"]
    if api_keys.get("openai") and not os.environ.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = api_keys["openai"]

    prompt = f"""Você é um analista de sistemas Protheus. Com base na documentação técnica abaixo de um fonte ADVPL customizado, gere uma síntese concisa em português contendo:

1. **Propósito** — O que este programa faz (2-3 frases)
2. **Fluxo Principal** — Passo a passo do processo
3. **Parâmetros** — Para cada parâmetro SX6/SX1 listado na seção "Parâmetros", explique brevemente para que ele serve NO CONTEXTO deste fonte. Ex: "MV_RESTINC: controla se permite inclusão de pedidos nesta rotina"
4. **Riscos e Atenção** — Pontos críticos, tabelas de escrita, integrações sensíveis
5. **Recomendações** — Melhorias ou cuidados para manutenção

Fonte: {arquivo}

Documentação técnica:
{sections_text[:8000]}

Responda em Markdown, direto ao ponto, sem repetir os dados das tabelas."""

    try:
        response = await acompletion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
            temperature=0.3,
        )
        text = response.choices[0].message.content
    except Exception as e:
        text = f"Erro ao gerar síntese: {e}"

    return f"## 8. Síntese\n\n{text}\n"


async def generate_fonte_doc(
    arquivo: str,
    db_path: Path,
    knowledge_dir: Path,
    llm_config: dict,
) -> dict:
    """Generate complete fonte documentation.

    Returns: {"arquivo": str, "md_path": str, "sections": int}
    """
    conn = sqlite3.connect(str(db_path))
    try:
        row = _query_one(conn,
            "SELECT arquivo, modulo, lines_of_code, encoding FROM fontes WHERE arquivo=?",
            (arquivo,))
        if not row:
            return {"error": f"Fonte '{arquivo}' not found"}

        meta = {
            "modulo": row[1] or "",
            "source_type": "",
            "loc": row[2] or 0,
            "encoding": row[3] or "cp1252",
            "proposito": "",
        }

        # Get proposito
        if _table_exists(conn, "propositos"):
            try:
                prow = _query_one(conn, "SELECT proposito FROM propositos WHERE chave=?", (arquivo,))
                if prow:
                    meta["proposito"] = prow[0] or ""
            except Exception:
                pass

        # Build sections 1-7
        header = _section_header(arquivo, meta)
        sec1 = _section_funcoes(conn, arquivo)
        sec2 = _section_tabelas(conn, arquivo)
        sec3 = _section_grafo(conn, arquivo)
        sec4 = _section_pes(conn, arquivo)
        sec5 = _section_menus(conn, arquivo)
        sec6 = _section_padrao(conn, arquivo)
        sec_params = _section_params(conn, arquivo)
        sec7 = _section_codigo(conn, arquivo)

        sections_text = "\n".join([header, sec1, sec2, sec3, sec4, sec5, sec6, sec_params, sec7])

    finally:
        conn.close()

    # Section 8: AI synthesis
    sec8 = await _section_sintese(sections_text, arquivo, llm_config)

    full_doc = sections_text + "\n" + sec8

    # Save
    fontes_dir = knowledge_dir / "fontes"
    fontes_dir.mkdir(parents=True, exist_ok=True)
    md_path = fontes_dir / f"{arquivo}.md"
    md_path.write_text(full_doc, encoding="utf-8")

    section_count = sum(1 for s in [sec1, sec2, sec3, sec4, sec5, sec6, sec7, sec8] if s.strip())

    return {
        "arquivo": arquivo,
        "md_path": str(md_path),
        "sections": section_count,
        "size": len(full_doc),
    }
