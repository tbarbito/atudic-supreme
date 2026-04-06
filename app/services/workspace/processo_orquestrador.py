"""Orquestrador hierárquico de processos.

Coordena a decomposição, análise e cache de processos complexos.
Cada sub-processo é analisado independentemente com contexto focado.
Componentes compartilhados são analisados uma vez e referenciados.

Decomposição recursiva: após analisar um sub-processo, o LLM avalia
se ele contém sub-fluxos distintos e decide se vale quebrar mais.
"""
import asyncio
import hashlib
import json
import re
from app.services.workspace.workspace_db import Database
from app.services.workspace.processo_decomposer import (
    analisar_complexidade,
    decompor_processo,
    refinar_decomposicao,
    _get_fontes_escrita,
    _get_todas_fontes,
)


# ── Prompt para o LLM avaliar se deve decompor ──────────────────────────

AVALIAR_DECOMPOSICAO_PROMPT = """Você é um analista de processos Protheus.

Analise o resultado abaixo de um sub-processo e decida se ele deve ser quebrado em sub-processos menores.

PROCESSO: {nome}
TABELAS: {tabelas}
FONTES ({total_fontes}): {fontes_lista}

ANÁLISE ATUAL:
{analise}

REGRAS PARA DECIDIR:
- Se o processo tem fluxos DISTINTOS que acontecem em momentos diferentes (ex: criação vs aprovação vs integração) → DECOMPOR
- Se o processo tem diferentes ATORES (usuário, job, webservice, PE) fazendo coisas independentes → DECOMPOR
- Se é um fluxo linear simples (cadastro → validação → gravação) → NÃO DECOMPOR
- Se tem menos de 8 fontes → NÃO DECOMPOR (muito pequeno para quebrar)
- Cadastros de configuração/parametrização → sub-processo separado se relevante

Responda APENAS com JSON:
{{
  "deve_decompor": true/false,
  "razao": "explicação curta",
  "sub_fluxos": [
    {{
      "nome": "Nome do Sub-Fluxo",
      "descricao": "O que faz",
      "fontes": ["fonte1.prw", "fonte2.prw"],
      "tabelas": ["TAB1"]
    }}
  ]
}}

Se deve_decompor=false, sub_fluxos deve ser [].
Nos sub_fluxos, APENAS inclua fontes que existem na lista acima. NÃO invente fontes."""


# ── Prompt para gerar análise do nó pai ──────────────────────────────────

ANALISE_PAI_PROMPT = """Você é um analista de processos Protheus.

Gere uma análise-resumo do processo "{nome}" que é composto pelos seguintes sub-processos:

{sub_processos_resumo}

CONEXÕES ENTRE SUB-PROCESSOS:
{conexoes_texto}

{componentes_texto}

INSTRUÇÕES:
1. Gere um RESUMO EXECUTIVO (2-3 frases) do processo completo
2. Gere um diagrama Mermaid mostrando o FLUXO ENTRE os sub-processos (não detalhe internamente cada um)
3. Para cada sub-processo, escreva 2-3 linhas explicando seu papel no fluxo geral
4. Liste os pontos de atenção do processo como um todo

Responda APENAS com JSON:
{{
  "resumo_executivo": "Resumo do processo completo...",
  "resumo_1linha": "Uma frase curta descrevendo o processo",
  "mermaid": "flowchart TD\\n  ...",
  "descricao_subprocessos": [
    {{"nome": "Sub-Processo 1", "papel": "Explicação do papel no fluxo geral"}}
  ],
  "pontos_atencao": ["ponto 1", "ponto 2"],
  "tabelas_chave": ["TAB1", "TAB2"]
}}

REGRAS PARA O MERMAID:
- Use flowchart TD (top-down)
- Cada sub-processo é um nó retangular: SP1["Nome do Sub-Processo"]
- Conexões com label da tabela ponte: SP1 -->|"via TAB"| SP2
- Se houver componentes compartilhados, mostre como nós com borda tracejada
- Use cores: classDef subproc fill:#e3f2fd,stroke:#1565c0; classDef comp fill:#fff3e0,stroke:#e65100;
- Máximo 15 nós no diagrama"""


async def _gerar_analise_pai(
    llm, nome: str, sub_resultados: list[dict],
    conexoes: list[dict], componentes: list[dict],
) -> dict:
    """Gera análise-resumo do nó pai a partir dos filhos já analisados."""
    # Montar resumo dos sub-processos
    sub_resumo_parts = []
    for i, sp in enumerate(sub_resultados, 1):
        resumo = sp.get("resumo_1linha", "")
        if not resumo:
            # Extrair primeiro parágrafo da análise
            md = sp.get("analise_markdown", "")
            lines = [l.strip() for l in md.split("\n") if l.strip() and not l.startswith("#")]
            resumo = lines[0][:200] if lines else "Sem resumo"
        tabelas = ", ".join(sp.get("tabelas", [])[:5])
        sub_resumo_parts.append(
            f"{i}. **{sp['nome']}** (tabelas: {tabelas})\n   Resumo: {resumo}"
        )

    # Montar texto de conexões
    conexoes_parts = []
    for c in conexoes:
        origem = c.get("origem", "?")
        destino = c.get("destino", "?")
        ponte = c.get("tabela_ponte", "")
        desc = c.get("descricao", "")
        conexoes_parts.append(f"- {origem} → {destino} via {ponte} ({desc})")

    # Montar texto de componentes
    comp_parts = []
    if componentes:
        comp_parts.append("COMPONENTES COMPARTILHADOS:")
        for c in componentes:
            usado = ", ".join(c.get("usado_por", []))
            comp_parts.append(f"- {c['nome']} ({c.get('tipo', '')}) — usado por: {usado}")

    prompt = ANALISE_PAI_PROMPT.format(
        nome=nome,
        sub_processos_resumo="\n".join(sub_resumo_parts) or "Nenhum sub-processo",
        conexoes_texto="\n".join(conexoes_parts) or "Nenhuma conexão mapeada",
        componentes_texto="\n".join(comp_parts) or "",
    )

    try:
        response = await asyncio.to_thread(
            llm._call,
            [{"role": "user", "content": prompt}],
            temperature=0.2,
            use_gen=True,
            timeout=45,
        )
        match = re.search(r'\{[\s\S]*\}', response)
        if match:
            return json.loads(match.group())
    except Exception:
        pass

    return {}


def _montar_markdown_pai(nome: str, analise_pai: dict, sub_resultados: list[dict], conexoes: list[dict]) -> str:
    """Monta o markdown formatado para o nó pai."""
    resumo = analise_pai.get("resumo_executivo", f"Processo {nome} composto por {len(sub_resultados)} etapas.")
    mermaid = analise_pai.get("mermaid", "")
    desc_subs = analise_pai.get("descricao_subprocessos", [])
    pontos = analise_pai.get("pontos_atencao", [])
    tabelas_chave = analise_pai.get("tabelas_chave", [])

    parts = [f"# Análise: {nome}\n", f"> {resumo}\n"]

    # Diagrama
    if mermaid:
        parts.append("## Diagrama de Fluxo\n")
        parts.append(f"```mermaid\n{mermaid}\n```\n")

    # Sub-processos
    parts.append("## Etapas do Processo\n")
    for i, sp in enumerate(sub_resultados, 1):
        sp_nome = sp["nome"]
        # Buscar descrição do LLM ou usar resumo
        papel = ""
        for d in desc_subs:
            if d.get("nome", "").lower() == sp_nome.lower():
                papel = d.get("papel", "")
                break
        if not papel:
            papel = sp.get("resumo_1linha", "")
        tabelas = ", ".join(sp.get("tabelas", [])[:5])
        parts.append(f"### {i}. {sp_nome}\n")
        parts.append(f"**Tabelas:** {tabelas}\n")
        if papel:
            parts.append(f"{papel}\n")

    # Conexões
    if conexoes:
        parts.append("## Conexões entre Etapas\n")
        parts.append("| Origem | Destino | Tabela Ponte | Descrição |")
        parts.append("|--------|---------|-------------|-----------|")
        for c in conexoes:
            parts.append(f"| {c.get('origem', '')} | {c.get('destino', '')} | {c.get('tabela_ponte', '')} | {c.get('descricao', '')} |")
        parts.append("")

    # Tabelas-chave
    if tabelas_chave:
        parts.append(f"## Tabelas Principais\n")
        parts.append(", ".join(f"`{t}`" for t in tabelas_chave) + "\n")

    # Pontos de atenção
    if pontos:
        parts.append("## Pontos de Atenção\n")
        for p in pontos:
            parts.append(f"- {p}")
        parts.append("")

    return "\n".join(parts)


async def avaliar_decomposicao_llm(
    llm, nome: str, tabelas: list[str], fontes: list[str], analise: str,
) -> dict:
    """Pergunta ao LLM se um sub-processo deve ser decomposto mais."""
    prompt = AVALIAR_DECOMPOSICAO_PROMPT.format(
        nome=nome,
        tabelas=", ".join(tabelas),
        total_fontes=len(fontes),
        fontes_lista=", ".join(fontes[:50]),  # Limitar para não estourar contexto
        analise=analise[:4000],  # Primeiros 4K chars da análise
    )

    try:
        response = await asyncio.to_thread(
            llm._call,
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            use_gen=True,  # Usar modelo mais barato para decisão
            timeout=30,
        )
        # Parse JSON
        match = re.search(r'\{[\s\S]*\}', response)
        if match:
            result = json.loads(match.group())
            # Validar fontes: só manter as que realmente existem
            fontes_set = set(f.lower() for f in fontes)
            for sf in result.get("sub_fluxos", []):
                sf["fontes"] = [f for f in sf.get("fontes", []) if f.lower() in fontes_set]
            return result
    except Exception:
        pass

    return {"deve_decompor": False, "razao": "erro na avaliação", "sub_fluxos": []}


# ── Cache ────────────────────────────────────────────────────────────────

def calcular_hash_inputs(db: Database, tabelas: list[str]) -> str:
    """Calcula hash dos inputs de um processo para cache."""
    parts = []
    for tab in sorted(t.upper() for t in tabelas):
        fontes = db.execute(
            "SELECT arquivo, lines_of_code FROM fontes WHERE write_tables LIKE ? ORDER BY arquivo",
            (f'%"{tab}"%',),
        ).fetchall()
        for f in fontes:
            parts.append(f"{f[0]}:{f[1]}")
        campos = db.execute(
            "SELECT COUNT(*) FROM campos WHERE upper(tabela)=? AND custom=1",
            (tab,),
        ).fetchone()[0]
        parts.append(f"sx3:{tab}:{campos}")
        gats = db.execute(
            "SELECT COUNT(*) FROM gatilhos WHERE tabela=? AND custom=1", (tab,)
        ).fetchone()[0]
        parts.append(f"sx7:{tab}:{gats}")

    return hashlib.md5("|".join(parts).encode()).hexdigest()[:16]


def verificar_cache(db: Database, analise_hash: str, nome: str) -> dict | None:
    """Verifica se existe análise cacheada com o mesmo hash."""
    row = db.execute(
        "SELECT id, analise_markdown, analise_json, resumo_1linha, resumo_paragrafo "
        "FROM processos_detectados WHERE analise_hash=? AND nome=?",
        (analise_hash, nome),
    ).fetchone()
    if row and row[1] and len(row[1]) > 200:  # Análise real, não só header de erro
        return {
            "id": row[0],
            "analise_markdown": row[1],
            "analise_json": row[2],
            "resumo_1linha": row[3],
            "resumo_paragrafo": row[4],
            "from_cache": True,
        }
    return None


# ── Persistência ─────────────────────────────────────────────────────────

def persistir_resultado_hierarquico(db: Database, resultado: dict, parent_id: int = None, nivel: int = 0) -> int:
    """Persiste processo, sub-processos (recursivo), componentes e conexões.

    Returns: ID do processo criado.
    """
    # Coletar todas as tabelas (incluindo sub-processos)
    todas_tabelas = list(set(
        t for sp in resultado.get("sub_processos", []) for t in sp.get("tabelas", [])
    ))
    if not todas_tabelas:
        todas_tabelas = resultado.get("tabelas", [])

    db.execute(
        """INSERT INTO processos_detectados
           (nome, tipo, descricao, tabelas, resumo_1linha, resumo_paragrafo,
            analise_markdown, analise_hash, nivel, parent_id, metodo)
           VALUES (?, 'workflow', ?, ?, ?, ?, ?, ?, ?, ?, 'hierarquico')""",
        (
            resultado["nome"],
            resultado.get("resumo_paragrafo", ""),
            json.dumps(todas_tabelas),
            resultado.get("resumo_1linha", ""),
            resultado.get("resumo_paragrafo", ""),
            resultado.get("analise_markdown", ""),
            resultado.get("analise_hash", ""),
            nivel,
            parent_id,
        ),
    )
    db.commit()
    proc_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Sub-processos
    filho_ids = {}
    for i, sp in enumerate(resultado.get("sub_processos", [])):
        # Se o sub-processo tem seus próprios sub-processos, persistir recursivamente
        if sp.get("sub_processos"):
            filho_id = persistir_resultado_hierarquico(db, sp, parent_id=proc_id, nivel=nivel + 1)
        else:
            db.execute(
                """INSERT INTO processos_detectados
                   (nome, tipo, descricao, tabelas, resumo_1linha,
                    analise_markdown, analise_hash, nivel, parent_id, metodo)
                   VALUES (?, 'workflow', ?, ?, ?, ?, ?, ?, ?, 'hierarquico')""",
                (
                    sp["nome"],
                    sp.get("resumo_paragrafo", ""),
                    json.dumps(sp.get("tabelas", [])),
                    sp.get("resumo_1linha", ""),
                    sp.get("analise_markdown", ""),
                    sp.get("analise_hash", ""),
                    nivel + 1,
                    proc_id,
                ),
            )
            db.commit()
            filho_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        filho_ids[sp["nome"]] = filho_id
        db.execute(
            "INSERT OR IGNORE INTO processo_hierarquia (processo_pai_id, processo_filho_id, ordem) VALUES (?,?,?)",
            (proc_id, filho_id, i + 1),
        )

    # Componentes compartilhados
    for comp in resultado.get("componentes", []):
        db.execute(
            """INSERT INTO processo_componentes
               (nome, tipo, descricao, tabelas, fontes, analise_markdown, analise_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                comp["nome"],
                comp.get("tipo", "generico"),
                comp.get("descricao", ""),
                json.dumps(comp.get("tabelas", [])),
                json.dumps(comp.get("fontes", [])),
                comp.get("analise_markdown", ""),
                comp.get("analise_hash", ""),
            ),
        )
        db.commit()
        comp_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        for proc_nome in comp.get("usado_por", []):
            pid = filho_ids.get(proc_nome, proc_id)
            db.execute(
                "INSERT OR IGNORE INTO processo_componente_uso (componente_id, processo_id) VALUES (?,?)",
                (comp_id, pid),
            )

    # Conexões
    for conn in resultado.get("conexoes", []):
        orig_id = filho_ids.get(conn["origem"], proc_id)
        dest_id = filho_ids.get(conn["destino"], proc_id)
        db.execute(
            """INSERT OR IGNORE INTO processo_conexoes
               (processo_origem_id, processo_destino_id, tabela_ponte, descricao)
               VALUES (?,?,?,?)""",
            (orig_id, dest_id, conn.get("tabela_ponte", ""), conn.get("descricao", "")),
        )

    db.commit()
    return proc_id


# ── Análise recursiva de um nó ───────────────────────────────────────────

async def _analisar_no(
    db: Database, llm, nome: str, tabelas: list[str], fontes: list[str],
    force: bool = False, nivel: int = 1, max_nivel: int = 4,
) -> dict:
    """Analisa um nó e decide recursivamente se deve decompor mais.

    Returns:
        {
            "nome": str,
            "tabelas": list,
            "fontes": list,
            "analise_markdown": str,
            "resumo_1linha": str,
            "sub_processos": list (vazio se folha),
            "analise_hash": str,
        }
    """
    from app.services.workspace.deep_analysis import run_deep_analysis

    # Cache check
    sp_hash = calcular_hash_inputs(db, tabelas)
    if not force:
        cached = verificar_cache(db, sp_hash, nome)
        if cached:
            return {
                "nome": nome,
                "tabelas": tabelas,
                "fontes": fontes,
                "analise_markdown": cached["analise_markdown"],
                "resumo_1linha": cached.get("resumo_1linha", ""),
                "sub_processos": [],
                "analise_hash": sp_hash,
            }

    # Analisar este nó
    result = await run_deep_analysis(
        db, llm, tabelas, nome, "",
        max_depth=1, skip_code_specialist=True,
    )

    analise_md = result.get("analysis_markdown", "")

    # Se markdown muito curto, tentar reconstruir a partir do JSON/raw
    if len(analise_md) < 200:
        raw = result.get("analysis_json", {})
        if isinstance(raw, dict):
            raw_text = raw.get("raw_response", "")
            if raw_text:
                # Tentar converter JSON raw em markdown formatado
                from app.services.workspace.deep_analysis import _try_parse_raw_analysis, _analysis_to_markdown
                parsed = _try_parse_raw_analysis(raw_text)
                if parsed and (parsed.get("passos") or parsed.get("resumo_executivo")):
                    analise_md = _analysis_to_markdown(parsed, nome, {})
                else:
                    # Usar raw direto (JSON é melhor que nada)
                    analise_md = f"# Análise: {nome}\n\n{raw_text[:10000]}"

    node = {
        "nome": nome,
        "tabelas": tabelas,
        "fontes": fontes,
        "analise_markdown": analise_md,
        "resumo_1linha": "",
        "sub_processos": [],
        "analise_hash": sp_hash,
    }

    # Decidir se deve decompor mais (só se tem fontes suficientes e não atingiu limite)
    if nivel < max_nivel and len(fontes) >= 8:
        avaliacao = await avaliar_decomposicao_llm(llm, nome, tabelas, fontes, analise_md)

        if avaliacao.get("deve_decompor") and avaliacao.get("sub_fluxos"):
            sub_fluxos = avaliacao["sub_fluxos"]
            # Validar: cada sub-fluxo precisa ter fontes
            sub_fluxos = [sf for sf in sub_fluxos if sf.get("fontes")]

            if len(sub_fluxos) >= 2:
                # Analisar cada sub-fluxo recursivamente
                for sf in sub_fluxos:
                    sf_tabelas = sf.get("tabelas", tabelas)  # Herdar tabelas se não especificado
                    sub_node = await _analisar_no(
                        db, llm,
                        nome=sf["nome"],
                        tabelas=sf_tabelas,
                        fontes=sf["fontes"],
                        force=force,
                        nivel=nivel + 1,
                        max_nivel=max_nivel,
                    )
                    node["sub_processos"].append(sub_node)

    return node


# ── Orquestrador principal ───────────────────────────────────────────────

async def orquestrar_analise(
    db: Database, llm, tabelas: list[str], nome: str,
    descricao: str = "", force: bool = False,
) -> dict:
    """Ponto de entrada principal — orquestra análise hierárquica completa.

    1. Calcula hash dos inputs
    2. Verifica cache (se não force)
    3. Decompõe em sub-processos (regras estruturais)
    4. Analisa cada sub-processo
    5. Para cada sub-processo, LLM decide se precisa decompor mais (recursivo)
    6. Analisa componentes compartilhados (uma vez)
    7. Monta resultado hierárquico
    8. Persiste tudo
    """
    from app.services.workspace.deep_analysis import run_deep_analysis

    # Cache check
    input_hash = calcular_hash_inputs(db, tabelas)
    if not force:
        cached = verificar_cache(db, input_hash, nome)
        if cached:
            return cached

    # Decomposição estrutural (regras)
    complexidade = analisar_complexidade(db, tabelas)
    if not complexidade["deve_decompor"]:
        # Processo simples — análise direta, mas ainda avalia decomposição via LLM
        fontes = list(_get_todas_fontes(db, tabelas))
        node = await _analisar_no(db, llm, nome, tabelas, fontes, force)
        node["componentes"] = []
        node["conexoes"] = []
        node["analise_hash"] = input_hash
        pai_id = persistir_resultado_hierarquico(db, node)
        node["id"] = pai_id
        return node

    decomposicao = decompor_processo(db, tabelas, nome)

    # Refinar via LLM: validar conexões e classificação de componentes
    decomposicao = await refinar_decomposicao(llm, db, decomposicao)

    # Analisar cada sub-processo (com possível decomposição recursiva)
    sub_resultados = []
    for sp in decomposicao["sub_processos"]:
        fontes = sp.get("fontes_proprias", sp.get("fontes", []))
        sub_node = await _analisar_no(
            db, llm,
            nome=sp["nome"],
            tabelas=sp["tabelas"],
            fontes=fontes,
            force=force,
            nivel=1,
        )
        sub_resultados.append(sub_node)

    # Analisar componentes compartilhados (uma vez, sem recursão)
    for comp in decomposicao["componentes"]:
        comp_fontes = comp.get("fontes", [])
        comp_node = await _analisar_no(
            db, llm,
            nome=comp["nome"],
            tabelas=comp["tabelas"],
            fontes=comp_fontes,
            force=force,
            nivel=1,
            max_nivel=2,  # Componentes compartilhados: máximo 1 nível de sub
        )
        comp["analise_markdown"] = comp_node.get("analise_markdown", "")
        comp["analise_hash"] = comp_node.get("analise_hash", "")
        # Se o componente foi decomposto, guardar os sub-fluxos
        if comp_node.get("sub_processos"):
            comp["sub_processos"] = comp_node["sub_processos"]

    # Gerar análise do nó pai (resumo + Mermaid do fluxo geral)
    analise_pai = await _gerar_analise_pai(
        llm, nome, sub_resultados,
        decomposicao["conexoes"], decomposicao["componentes"],
    )
    analise_md_pai = _montar_markdown_pai(
        nome, analise_pai, sub_resultados, decomposicao["conexoes"],
    )

    # Montar resultado
    resultado = {
        "nome": nome,
        "resumo_1linha": analise_pai.get("resumo_1linha", f"Processo {nome} — {len(sub_resultados)} etapas"),
        "resumo_paragrafo": analise_pai.get("resumo_executivo", descricao),
        "analise_markdown": analise_md_pai,
        "sub_processos": sub_resultados,
        "componentes": decomposicao["componentes"],
        "conexoes": decomposicao["conexoes"],
        "analise_hash": input_hash,
    }

    # Persistir
    pai_id = persistir_resultado_hierarquico(db, resultado)
    resultado["id"] = pai_id

    return resultado
