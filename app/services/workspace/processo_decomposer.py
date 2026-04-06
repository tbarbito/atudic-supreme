"""Decomposer de processos — divide processos grandes em sub-processos.

Usa regras de corte baseadas em complexidade e detecta componentes
compartilhados (ex: aprovação por alçada usada em N processos).

Inclui passo de refinamento via LLM para validar conexões e classificação
de componentes (ex: distinguir aprovação por alçada de tolerância de valor).
"""
import asyncio
import json
import re
from app.services.workspace.workspace_db import Database

# Limites para decidir quando decompor
MAX_FONTES_SEM_DECOMPOR = 25
MAX_TABELAS_ESCRITA_SEM_DECOMPOR = 5

# Tabelas que indicam componente transversal
TABELAS_TRANSVERSAIS = {
    "SCR": "Aprovação por Alçada",
    "SAL": "Grupos de Aprovação",
    "ZAD": "Grade de Aprovação",
    "ZA0": "Configuração de Alçada",
}

# Prefixos de fontes que indicam integração
PREFIXOS_INTEGRACAO = ("WSR", "INTEG", "API", "REST", "EDI", "MGFWSC")


def _get_fontes_escrita(db: Database, tabelas: list[str]) -> dict[str, list[str]]:
    """Retorna fontes agrupadas por tabela de escrita."""
    fontes_por_tabela = {}
    for tab in tabelas:
        rows = db.execute(
            "SELECT arquivo FROM fontes WHERE write_tables LIKE ?",
            (f'%"{tab.upper()}"%',),
        ).fetchall()
        fontes_por_tabela[tab.upper()] = [r[0] for r in rows]
    return fontes_por_tabela


def _get_todas_fontes(db: Database, tabelas: list[str]) -> set[str]:
    """Retorna set de todas as fontes que escrevem ou leem qualquer das tabelas."""
    all_fontes = set()
    for tab in tabelas:
        rows = db.execute(
            "SELECT arquivo FROM fontes WHERE write_tables LIKE ? OR tabelas_ref LIKE ?",
            (f'%"{tab.upper()}"%', f'%"{tab.upper()}"%'),
        ).fetchall()
        all_fontes.update(r[0] for r in rows)
    return all_fontes


def analisar_complexidade(db: Database, tabelas: list[str]) -> dict:
    """Analisa se um processo precisa ser decomposto e por quê.

    Returns:
        {
            deve_decompor: bool,
            total_fontes: int,
            tabelas_escrita: list[str],
            razoes: list[str],
            transversais: list[str],
            fontes_integracao: list[str],
            jobs: list[str],
        }
    """
    fontes = _get_todas_fontes(db, tabelas)
    fontes_escrita = _get_fontes_escrita(db, tabelas)
    tabelas_com_escrita = [t for t, f in fontes_escrita.items() if len(f) > 0]

    razoes = []
    if len(fontes) > MAX_FONTES_SEM_DECOMPOR:
        razoes.append(f"{len(fontes)} fontes (limite: {MAX_FONTES_SEM_DECOMPOR})")
    if len(tabelas_com_escrita) > MAX_TABELAS_ESCRITA_SEM_DECOMPOR:
        razoes.append(f"{len(tabelas_com_escrita)} tabelas com escrita (limite: {MAX_TABELAS_ESCRITA_SEM_DECOMPOR})")

    # Detectar tabelas transversais
    transversais = [t for t in tabelas if t.upper() in TABELAS_TRANSVERSAIS]
    if transversais:
        razoes.append(f"Tabelas transversais: {', '.join(transversais)}")

    # Detectar integrações
    fontes_integ = [f for f in fontes if any(f.upper().startswith(p) for p in PREFIXOS_INTEGRACAO)]
    if len(fontes_integ) >= 3:
        razoes.append(f"{len(fontes_integ)} fontes de integração")

    # Detectar jobs
    jobs = []
    for f in fontes:
        job_row = db.execute(
            "SELECT rotina FROM jobs WHERE upper(rotina) = upper(?)",
            (f.replace(".prw", "").replace(".PRW", ""),),
        ).fetchone()
        if job_row:
            jobs.append(job_row[0])
    if jobs:
        razoes.append(f"Jobs: {', '.join(jobs[:5])}")

    return {
        "deve_decompor": len(razoes) > 0,
        "total_fontes": len(fontes),
        "tabelas_escrita": tabelas_com_escrita,
        "razoes": razoes,
        "transversais": transversais,
        "fontes_integracao": fontes_integ,
        "jobs": jobs,
    }


def detectar_componentes_compartilhados(grupos: list[dict]) -> list[dict]:
    """Detecta componentes usados por 2+ sub-processos.

    Args:
        grupos: lista de {"nome": str, "tabelas": list, "fontes": list}

    Returns:
        lista de componentes compartilhados:
        [{"nome", "tabelas": list, "fontes": list, "usado_por": list}]
    """
    # Contar frequência de cada fonte entre os grupos
    fonte_para_grupos = {}
    for g in grupos:
        for f in g["fontes"]:
            fonte_para_grupos.setdefault(f, []).append(g["nome"])

    # Fontes que aparecem em 2+ grupos
    fontes_compartilhadas = {f: gs for f, gs in fonte_para_grupos.items() if len(gs) >= 2}
    if not fontes_compartilhadas:
        return []

    # Agrupar por tabela transversal (SCR, SAL, etc.)
    componentes = {}
    for g in grupos:
        for tab in g.get("tabelas", []):
            tab_upper = tab.upper()
            if tab_upper in TABELAS_TRANSVERSAIS:
                key = TABELAS_TRANSVERSAIS[tab_upper]
                if key not in componentes:
                    componentes[key] = {
                        "nome": key,
                        "tabelas": set(),
                        "fontes": set(),
                        "usado_por": set(),
                    }
                componentes[key]["tabelas"].add(tab_upper)
                componentes[key]["usado_por"].add(g["nome"])
                for f in g["fontes"]:
                    if f in fontes_compartilhadas:
                        componentes[key]["fontes"].add(f)

    # Converter sets para lists, filtrar os que são usados por 2+
    result = []
    for comp in componentes.values():
        if len(comp["usado_por"]) >= 2:
            result.append({
                "nome": comp["nome"],
                "tabelas": sorted(comp["tabelas"]),
                "fontes": sorted(comp["fontes"]),
                "usado_por": sorted(comp["usado_por"]),
            })
    return result


def decompor_processo(db: Database, tabelas: list[str], nome: str = "") -> dict:
    """Decompõe um processo em sub-processos.

    Estratégia:
    1. Agrupa fontes por tabela principal de escrita
    2. Junta tabelas que compartilham >70% das fontes
    3. Detecta componentes compartilhados
    4. Identifica conexões entre sub-processos

    Returns:
        {
            "nome": str,
            "sub_processos": [{"nome", "tabelas", "fontes", "fontes_proprias", "tipo"}],
            "componentes": [{"nome", "tabelas", "fontes", "usado_por"}],
            "conexoes": [{"origem", "destino", "tabela_ponte", "fontes_ponte"}],
        }
    """
    fontes_por_tabela = _get_fontes_escrita(db, tabelas)

    # Agrupar tabelas semanticamente (tabelas escritas pelas mesmas fontes)
    grupos = []
    tabelas_processadas = set()

    for tab in tabelas:
        tab_upper = tab.upper()
        if tab_upper in tabelas_processadas or tab_upper in TABELAS_TRANSVERSAIS:
            continue
        tabelas_processadas.add(tab_upper)

        # Nome semântico baseado no dicionário
        row = db.execute(
            "SELECT nome FROM tabelas WHERE upper(codigo)=?", (tab_upper,)
        ).fetchone()
        nome_tabela = row[0] if row else tab_upper

        fontes = set(fontes_por_tabela.get(tab_upper, []))
        grupo_tabelas = [tab_upper]

        # Agrupar tabelas que compartilham >70% das fontes
        for other_tab in tabelas:
            other_upper = other_tab.upper()
            if (other_upper == tab_upper or other_upper in tabelas_processadas
                    or other_upper in TABELAS_TRANSVERSAIS):
                continue
            other_fontes = set(fontes_por_tabela.get(other_upper, []))
            if fontes and other_fontes:
                total = max(len(fontes), len(other_fontes))
                overlap = len(fontes & other_fontes) / total if total > 0 else 0
                if overlap > 0.7:
                    fontes |= other_fontes
                    grupo_tabelas.append(other_upper)
                    tabelas_processadas.add(other_upper)

        grupos.append({
            "nome": nome_tabela,
            "tabelas": grupo_tabelas,
            "fontes": sorted(fontes),
            "tipo": "sub_processo",
        })

    # Criar componentes para tabelas transversais (SCR, SAL, etc.)
    componentes = []
    for tab in tabelas:
        tab_upper = tab.upper()
        if tab_upper not in TABELAS_TRANSVERSAIS:
            continue
        nome_comp = TABELAS_TRANSVERSAIS[tab_upper]
        fontes_comp = set(fontes_por_tabela.get(tab_upper, []))

        # Detectar quais sub-processos também usam fontes desta tabela transversal
        usado_por = []
        for g in grupos:
            overlap = fontes_comp & set(g["fontes"])
            if overlap:
                usado_por.append(g["nome"])

        # Também incluir fontes que só escrevem na tabela transversal (sem overlap)
        todas_fontes_transversal = _get_todas_fontes(db, [tab_upper])
        fontes_comp |= todas_fontes_transversal

        if len(usado_por) >= 1:  # Pelo menos 1 sub-processo usa
            componentes.append({
                "nome": nome_comp,
                "tabelas": [tab_upper],
                "fontes": sorted(fontes_comp),
                "usado_por": sorted(usado_por),
            })

    # Adicionar componentes detectados por overlap de fontes entre grupos
    comp_overlap = detectar_componentes_compartilhados(grupos)
    # Evitar duplicatas por nome
    nomes_existentes = {c["nome"] for c in componentes}
    for c in comp_overlap:
        if c["nome"] not in nomes_existentes:
            componentes.append(c)

    # Remover fontes de componentes compartilhados dos sub-processos
    fontes_componentes = set()
    for comp in componentes:
        fontes_componentes.update(comp["fontes"])

    for g in grupos:
        g["fontes_proprias"] = [f for f in g["fontes"] if f not in fontes_componentes]

    # Detectar conexões direcionais reais:
    # Fonte que LÊ tabela de A e ESCREVE em tabela de B = fluxo A → B
    conexoes = []
    conexoes_vistas = set()
    for i, ga in enumerate(grupos):
        for j, gb in enumerate(grupos):
            if i == j:
                continue
            for tab_a in ga["tabelas"]:
                for tab_b in gb["tabelas"]:
                    # Fontes que leem de tab_a E escrevem em tab_b
                    pontes = db.execute(
                        "SELECT arquivo FROM fontes WHERE tabelas_ref LIKE ? AND write_tables LIKE ?",
                        (f'%"{tab_a}"%', f'%"{tab_b}"%'),
                    ).fetchall()
                    if pontes:
                        key = (ga["nome"], gb["nome"])
                        if key not in conexoes_vistas:
                            conexoes_vistas.add(key)
                            conexoes.append({
                                "origem": ga["nome"],
                                "destino": gb["nome"],
                                "tabela_ponte": f"{tab_a}->{tab_b}",
                                "fontes_ponte": sorted(r[0] for r in pontes)[:3],
                            })

    # Detectar quais sub-processos disparam aprovação:
    # Uma fonte "dispara aprovação" se ESCREVE na tabela do sub-processo E ESCREVE em SCR.
    # Isso exclui fontes que só leem a tabela (MGFCOM14 lê SC8 e escreve SCR, mas
    # não é parte do processo de cotação — é parte da aprovação do pedido gerado).
    for g in grupos:
        g["tem_aprovacao"] = False
        fontes_escrita = _get_fontes_escrita(db, g["tabelas"])
        fontes_que_escrevem_no_grupo = set()
        for tab, fs in fontes_escrita.items():
            fontes_que_escrevem_no_grupo.update(fs)
        # Dessas fontes que ESCREVEM no grupo, alguma também ESCREVE em SCR?
        # Exceção: se a fonte escreve em SCR mas também escreve em OUTRA tabela
        # de outro sub-processo, a aprovação é desse outro (não deste grupo).
        outras_tabelas_grupos = set()
        for og in grupos:
            if og["nome"] != g["nome"]:
                outras_tabelas_grupos.update(t.upper() for t in og["tabelas"])

        for fonte in fontes_que_escrevem_no_grupo:
            row = db.execute(
                "SELECT write_tables FROM fontes WHERE upper(arquivo)=?",
                (fonte.upper(),),
            ).fetchone()
            if not row or not row[0] or '"SCR"' not in row[0]:
                continue
            # Verifica: essa fonte escreve em SCR e em alguma outra tabela de outro grupo?
            # Se sim, a aprovação é provavelmente do outro grupo (ex: MGFCOM24 escreve SC8+SC7+SCR
            # → aprovação é do SC7, não do SC8)
            import json as _json
            try:
                fonte_writes = set(_json.loads(row[0]))
            except:
                fonte_writes = set()
            # Se escreve APENAS neste grupo + SCR → aprovação é deste grupo
            # Se escreve em outro grupo também → aprovação pode ser do outro
            escreve_outro = fonte_writes & outras_tabelas_grupos
            if not escreve_outro:
                g["tem_aprovacao"] = True
                break
            # Se escreve em outro mas ESTE grupo é a tabela principal (mais campos), considerar
            # Heurística simples: se escreve em mais tabelas deste grupo que de outros, é deste
            tabs_deste = fonte_writes & set(t.upper() for t in g["tabelas"])
            if len(tabs_deste) > len(escreve_outro):
                g["tem_aprovacao"] = True
                break

    # Ajustar componente de aprovação: só marcar usado_por quem realmente interage com SCR
    for comp in componentes:
        if any(t in ("SCR", "SAL", "ZAD") for t in comp["tabelas"]):
            usado = [g["nome"] for g in grupos if g.get("tem_aprovacao")]
            if usado:
                comp["usado_por"] = sorted(usado)

    # Filtrar conexões para manter apenas o fluxo principal:
    # A ordem dos sub-processos na lista reflete a ordem temporal do negócio.
    # Se A→B e B→A existem, manter apenas a que segue a ordem (A antes de B na lista).
    # Conexões "para trás" são feedbacks (atualização de status) — não fluxo principal.
    ordem_grupos = {g["nome"]: i for i, g in enumerate(grupos)}

    # Também: SF1 e SD1 são cabeçalho+itens — tratá-los como par
    conexoes_final = []
    seen = set()
    for conn in conexoes:
        key = (conn["origem"], conn["destino"])
        if key in seen:
            continue

        idx_orig = ordem_grupos.get(conn["origem"], 999)
        idx_dest = ordem_grupos.get(conn["destino"], 999)

        # Manter só fluxo "para frente" (origem antes de destino) OU par SF1↔SD1
        if idx_orig < idx_dest:
            seen.add(key)
            conexoes_final.append(conn)
        elif idx_orig == idx_dest:
            # Mesmo grupo — skip
            continue
        else:
            # Fluxo reverso — skip (é feedback/atualização de status)
            continue

    return {
        "nome": nome,
        "sub_processos": grupos,
        "componentes": componentes,
        "conexoes": conexoes_final,
    }


# ── Refinamento via LLM ─────────────────────────────────────────────────

REFINAR_PROMPT = """Você é um especialista em processos de negócio TOTVS Protheus.

Analise a decomposição abaixo de um processo e REFINE:

PROCESSO: {nome}

SUB-PROCESSOS:
{sub_processos_texto}

COMPONENTES COMPARTILHADOS:
{componentes_texto}

CONEXÕES (fluxo):
{conexoes_texto}

EVIDÊNCIAS (operações de escrita que ligam sub-processos a componentes):
{evidencias_texto}

REFINE A DECOMPOSIÇÃO:
1. As conexões representam o fluxo TEMPORAL correto do negócio? (ex: solicitação ANTES de cotação ANTES de pedido)
2. Cada componente compartilhado está corretamente classificado? (ex: aprovação por alçada vs tolerância de valor vs controle de estoque são coisas DIFERENTES)
3. Algum sub-processo está ligado a um componente quando não deveria?

IMPORTANTE no Protheus:
- Aprovação por Alçada (SCR) = usuário aprova/rejeita documento (SC1, SC7, SE2). É workflow.
- Tolerância de valor = bloqueio automático por divergência (NF vs Pedido). NÃO é aprovação por alçada.
- Seleção de fornecedor vencedor em cotação NÃO é aprovação por alçada.

Responda JSON:
{{
  "conexoes_remover": ["origem -> destino que não faz sentido"],
  "conexoes_adicionar": [{{"origem": "...", "destino": "...", "motivo": "..."}}],
  "componentes_ajustar": [
    {{"nome": "nome do componente", "usado_por_correto": ["sub1", "sub2"], "motivo": "..."}}
  ],
  "observacoes": ["notas sobre o processo"]
}}"""


async def refinar_decomposicao(llm, db: Database, decomposicao: dict) -> dict:
    """Usa LLM para refinar a decomposição: corrigir conexões e classificação de componentes."""

    # Montar texto dos sub-processos com evidências
    sp_lines = []
    evidencias_lines = []
    for sp in decomposicao["sub_processos"]:
        tabs = sp.get("tabelas", [])
        aprov = "SIM" if sp.get("tem_aprovacao") else "NAO"
        sp_lines.append(f"- {sp['nome']} (tabelas: {', '.join(tabs)}) — tem aprovação: {aprov}")

        # Buscar operações que escrevem em SCR para este sub-processo
        for fonte in sp.get("fontes", [])[:5]:
            ops = db.execute(
                "SELECT funcao, tipo, tabela, campos FROM operacoes_escrita WHERE upper(arquivo)=? AND tabela='SCR' LIMIT 3",
                (fonte.upper(),),
            ).fetchall()
            for o in ops:
                campos = json.loads(o[3]) if o[3] else []
                evidencias_lines.append(
                    f"  {fonte}::{o[0]}() {o[1]} SCR campos={campos[:5]}"
                )

    comp_lines = []
    for comp in decomposicao.get("componentes", []):
        comp_lines.append(
            f"- {comp['nome']} (tabelas: {', '.join(comp['tabelas'])}) — usado_por: {comp.get('usado_por', [])}"
        )

    conn_lines = []
    for c in decomposicao.get("conexoes", []):
        conn_lines.append(f"- {c['origem']} -> {c['destino']} via {c['tabela_ponte']}")

    prompt = REFINAR_PROMPT.format(
        nome=decomposicao.get("nome", ""),
        sub_processos_texto="\n".join(sp_lines) or "Nenhum",
        componentes_texto="\n".join(comp_lines) or "Nenhum",
        conexoes_texto="\n".join(conn_lines) or "Nenhum",
        evidencias_texto="\n".join(evidencias_lines) or "Nenhum",
    )

    try:
        response = await asyncio.to_thread(
            llm._call,
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            use_gen=True,
            timeout=30,
        )
        match = re.search(r'\{[\s\S]*\}', response)
        if match:
            refinamento = json.loads(match.group())
        else:
            return decomposicao
    except Exception:
        return decomposicao

    # Aplicar refinamentos
    # 1. Ajustar componentes
    for ajuste in refinamento.get("componentes_ajustar", []):
        for comp in decomposicao["componentes"]:
            if comp["nome"].lower() == ajuste.get("nome", "").lower():
                if "usado_por_correto" in ajuste:
                    comp["usado_por"] = ajuste["usado_por_correto"]

    # 2. Remover conexões
    nomes_remover = set()
    for r in refinamento.get("conexoes_remover", []):
        if "->" in r:
            parts = r.split("->")
            nomes_remover.add((parts[0].strip(), parts[1].strip()))

    if nomes_remover:
        decomposicao["conexoes"] = [
            c for c in decomposicao["conexoes"]
            if (c["origem"].strip(), c["destino"].strip()) not in nomes_remover
        ]

    # 3. Atualizar tem_aprovacao nos sub-processos baseado no refinamento
    for ajuste in refinamento.get("componentes_ajustar", []):
        if "alçada" in ajuste.get("nome", "").lower() or "aprovação" in ajuste.get("nome", "").lower():
            usados = set(ajuste.get("usado_por_correto", []))
            for sp in decomposicao["sub_processos"]:
                sp["tem_aprovacao"] = sp["nome"] in usados

    # Guardar observações do LLM
    decomposicao["refinamento_obs"] = refinamento.get("observacoes", [])

    return decomposicao
