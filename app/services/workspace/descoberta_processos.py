# -*- coding: utf-8 -*-
"""Pipeline de descoberta automatica de processos do cliente — SQL puro (passos 1-4)."""
import json
import logging
import re

from app.services.workspace.workspace_db import Database

logger = logging.getLogger(__name__)


def _safe_json(val):
    if not val:
        return []
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return []


# ──────────────────────────────────────────────────────────────
# PASSO 1 — Clustering de campos: 5 níveis SQL
# ──────────────────────────────────────────────────────────────

def passo1_clustering_campos(db) -> dict:
    """Detecta macro-processos via 5 niveis semanticos nos dados do cliente."""

    # Nível 1 — tabelas custom com >= 5 campos
    nivel1 = []
    rows = db.execute(
        "SELECT t.codigo, t.nome, COUNT(c.campo) as total_campos "
        "FROM tabelas t LEFT JOIN campos c ON c.tabela = t.codigo "
        "WHERE t.custom=1 GROUP BY t.codigo HAVING total_campos >= 5 "
        "ORDER BY total_campos DESC"
    ).fetchall()
    for r in rows:
        nivel1.append({"tabela": r[0], "nome": r[1], "total_campos": r[2]})

    # Nível 2 — cbox com 3+ estados (máquinas de estado)
    nivel2 = []
    rows = db.execute(
        "SELECT tabela, campo, titulo, cbox, "
        "  LENGTH(cbox) - LENGTH(REPLACE(cbox, ';', '')) + 1 as num_estados "
        "FROM campos "
        "WHERE custom=1 AND cbox IS NOT NULL AND LENGTH(TRIM(cbox)) > 3 "
        "  AND LENGTH(cbox) - LENGTH(REPLACE(cbox, ';', '')) >= 2 "
        "ORDER BY num_estados DESC LIMIT 50"
    ).fetchall()
    for r in rows:
        nivel2.append({
            "tabela": r[0], "campo": r[1], "titulo": r[2],
            "cbox": r[3], "num_estados": r[4],
        })

    # Nível 3 — títulos com keywords de processo
    nivel3_sql = """
        SELECT
            CASE
                WHEN LOWER(titulo) LIKE '%aprov%' OR LOWER(titulo) LIKE '%liber%' THEN 'WORKFLOW_APROVACAO'
                WHEN LOWER(titulo) LIKE '%bloq%' THEN 'CONTROLE_BLOQUEIO'
                WHEN LOWER(titulo) LIKE '%integr%' THEN 'INTEGRACAO'
                WHEN LOWER(titulo) LIKE '%envia%' OR LOWER(titulo) LIKE '%reenvi%' THEN 'ENVIO_INTEGRACAO'
                WHEN LOWER(titulo) LIKE '%status%' THEN 'STATUS_PROCESSO'
                WHEN LOWER(titulo) LIKE '%log de%' OR LOWER(titulo) LIKE '%histor%' THEN 'AUDITORIA_LOG'
                WHEN LOWER(titulo) LIKE '%taura%' THEN 'TAURA_WMS'
                WHEN LOWER(titulo) LIKE '%tms%' THEN 'TMS_TRANSPORTE'
                WHEN LOWER(titulo) LIKE '%frete%' OR LOWER(titulo) LIKE '%embarg%' THEN 'LOGISTICA'
                WHEN LOWER(titulo) LIKE '%fiscal%' OR LOWER(titulo) LIKE '%nf%' THEN 'FISCAL'
                WHEN LOWER(titulo) LIKE '%qualidade%' OR LOWER(titulo) LIKE '%inspecao%' THEN 'QUALIDADE'
                WHEN LOWER(titulo) LIKE '%salesforce%' OR LOWER(titulo) LIKE '%sf%' THEN 'SALESFORCE'
                WHEN LOWER(titulo) LIKE '%ecommerce%' OR LOWER(titulo) LIKE '%e-commerce%' THEN 'ECOMMERCE'
            END as processo,
            COUNT(*) as qtd_campos,
            GROUP_CONCAT(DISTINCT tabela) as tabelas
        FROM campos
        WHERE custom=1 AND titulo IS NOT NULL
        GROUP BY processo
        HAVING processo IS NOT NULL
        ORDER BY qtd_campos DESC
    """
    nivel3 = []
    for r in db.execute(nivel3_sql).fetchall():
        nivel3.append({
            "processo": r[0], "qtd_campos": r[1],
            "tabelas": (r[2] or "").split(","),
        })

    # Nível 4 — prefixo repetido em tabelas padrão (4+ campos com mesmo prefixo)
    nivel4 = []
    rows = db.execute(
        "SELECT tabela, SUBSTR(campo, 4, 3) as prefixo, COUNT(*) as qtd "
        "FROM campos WHERE custom=1 AND LENGTH(campo) >= 7 "
        "GROUP BY tabela, prefixo HAVING qtd >= 4 ORDER BY qtd DESC LIMIT 30"
    ).fetchall()
    for r in rows:
        nivel4.append({"tabela": r[0], "prefixo": r[1], "qtd_campos": r[2]})

    # Nível 5 — diff padrão vs cliente (tabelas muito modificadas)
    nivel5 = []
    rows = db.execute(
        "SELECT tabela, "
        "  SUM(CASE WHEN acao='adicionado' THEN 1 ELSE 0 END) as adicionados, "
        "  SUM(CASE WHEN acao='alterado' THEN 1 ELSE 0 END) as alterados, "
        "  COUNT(*) as total_diffs "
        "FROM diff WHERE tipo_sx='campo' "
        "GROUP BY tabela HAVING total_diffs >= 20 ORDER BY total_diffs DESC LIMIT 20"
    ).fetchall()
    for r in rows:
        nivel5.append({
            "tabela": r[0], "adicionados": r[1],
            "alterados": r[2], "total_diffs": r[3],
        })

    return {
        "nivel1_tabelas_custom": nivel1,
        "nivel2_cbox_estados": nivel2,
        "nivel3_titulos": nivel3,
        "nivel4_prefixos": nivel4,
        "nivel5_diff": nivel5,
    }


# ──────────────────────────────────────────────────────────────
# PASSO 2 — Mapa de gatilhos e cadeias
# ──────────────────────────────────────────────────────────────

def passo2_gatilhos(db) -> dict:
    """Extrai super-triggers, funcoes U_ e tabelas consultadas."""

    # Super-triggers: campos que disparam 3+ gatilhos custom
    super_triggers = {}
    rows = db.execute(
        "SELECT campo_origem, COUNT(*) as qtd, "
        "  GROUP_CONCAT(DISTINCT regra) as regras "
        "FROM gatilhos WHERE custom=1 OR proprietario!='S' "
        "GROUP BY campo_origem HAVING qtd >= 3 ORDER BY qtd DESC LIMIT 20"
    ).fetchall()
    for r in rows:
        regras_raw = r[2] or ""
        funcoes = re.findall(r'U_\w+', regras_raw)
        super_triggers[r[0]] = {
            "qtd_destinos": r[1],
            "funcoes": list(set(funcoes)),
        }

    # Funções U_ chamadas em gatilhos (todas, ordenadas por frequência)
    funcoes_counter: dict[str, int] = {}
    rows = db.execute(
        "SELECT regra FROM gatilhos WHERE regra IS NOT NULL AND regra != ''"
    ).fetchall()
    for r in rows:
        for f in re.findall(r'U_\w+', r[0]):
            funcoes_counter[f] = funcoes_counter.get(f, 0) + 1
    funcoes_sorted = sorted(funcoes_counter.items(), key=lambda x: -x[1])

    # Alias consultados via seek nos gatilhos (tabelas dependentes)
    aliases = {}
    rows = db.execute(
        "SELECT alias, COUNT(*) as qtd FROM gatilhos "
        "WHERE alias IS NOT NULL AND alias != '' "
        "GROUP BY alias ORDER BY qtd DESC LIMIT 20"
    ).fetchall()
    for r in rows:
        aliases[r[0]] = r[1]

    # Total gatilhos custom
    total = db.execute(
        "SELECT COUNT(*) FROM gatilhos WHERE custom=1"
    ).fetchone()[0]

    return {
        "total_gatilhos_custom": total,
        "super_triggers": super_triggers,
        "funcoes_chamadas": [f for f, _ in funcoes_sorted[:20]],
        "aliases_consultados": aliases,
    }


# ──────────────────────────────────────────────────────────────
# PASSO 3 — Fontes de escrita + tabelas satélite
# ──────────────────────────────────────────────────────────────

def passo3_fontes_satelite(db) -> dict:
    """Agrupa fontes por tabela que escrevem e identifica satelites."""

    # Cluster por tabela: todos os fontes que a escrevem
    clusters: dict[str, dict] = {}
    rows = db.execute(
        "SELECT arquivo, write_tables, tabelas_ref, lines_of_code FROM fontes "
        "WHERE write_tables IS NOT NULL AND write_tables != '[]'"
    ).fetchall()

    satelite_counter: dict[str, set] = {}  # tabela_satelite -> set of arquivos

    for arquivo, write_raw, ref_raw, loc in rows:
        write_tabs = _safe_json(write_raw)
        ref_tabs = _safe_json(ref_raw)

        for tab in write_tabs:
            tab_upper = tab.upper()
            if tab_upper not in clusters:
                clusters[tab_upper] = {"tabela": tab_upper, "fontes": [], "total_fontes": 0}
            clusters[tab_upper]["fontes"].append(arquivo)
            clusters[tab_upper]["total_fontes"] += 1

            # Satélites: outras tabelas escritas pelo mesmo arquivo
            for other in write_tabs:
                other_upper = other.upper()
                if other_upper != tab_upper:
                    satelite_counter.setdefault(other_upper, set()).add(arquivo)

    # Satélites com 2+ fontes em comum
    satelites = []
    for tab, arquivos in sorted(satelite_counter.items(), key=lambda x: -len(x[1])):
        if len(arquivos) >= 2:
            trow = db.execute(
                "SELECT nome, custom FROM tabelas WHERE upper(codigo)=?", (tab,)
            ).fetchone()
            satelites.append({
                "tabela": tab,
                "nome": trow[0] if trow else "",
                "custom": trow[1] if trow else 0,
                "total_fontes_compartilhados": len(arquivos),
                "arquivos": sorted(arquivos)[:5],
            })

    # Top clusters (tabelas com mais fontes de escrita)
    clusters_list = sorted(clusters.values(), key=lambda x: -x["total_fontes"])

    return {
        "clusters_tabela": clusters_list[:30],
        "satelites": satelites[:20],
    }


# ──────────────────────────────────────────────────────────────
# PASSO 4 — Jobs, schedules e criticidade
# ──────────────────────────────────────────────────────────────

def passo4_jobs(db) -> dict:
    """Cruza fontes com jobs/schedules e classifica criticidade."""

    def _criticidade(refresh_rate, instancias):
        if refresh_rate is not None and refresh_rate < 60:
            return "critico"
        if refresh_rate is not None and refresh_rate < 300:
            return "alto"
        if instancias and instancias > 3:
            return "alto"
        if refresh_rate is not None and refresh_rate < 1800:
            return "medio"
        return "baixo"

    jobs_rows = db.execute(
        "SELECT MIN(arquivo_ini), MIN(sessao), rotina, MIN(refresh_rate) as refresh_rate, COUNT(*) as instancias "
        "FROM jobs GROUP BY rotina ORDER BY instancias DESC, refresh_rate ASC"
    ).fetchall()

    jobs_criticos = []
    for r in jobs_rows:
        crit = _criticidade(r[3], r[4])
        jobs_criticos.append({
            "arquivo": r[0],
            "rotina": r[2],
            "refresh_rate": r[3],
            "instancias": r[4],
            "criticidade": crit,
        })

    schedules_rows = db.execute(
        "SELECT rotina, execucoes_dia, status, tipo_recorrencia "
        "FROM schedules WHERE status != 'inativo' "
        "ORDER BY execucoes_dia DESC LIMIT 30"
    ).fetchall()

    schedules = []
    for r in schedules_rows:
        schedules.append({
            "rotina": r[0],
            "execucoes_dia": r[1],
            "status": r[2],
            "tipo_recorrencia": r[3],
        })

    return {
        "jobs_criticos": jobs_criticos,
        "schedules_ativos": schedules,
    }


# ──────────────────────────────────────────────────────────────
# PASSO 5 — Classificação e nomeação via LLM (1 chamada)
# ──────────────────────────────────────────────────────────────

_PASSO5_PROMPT = """Você é um especialista em sistemas ERP Protheus.
Analise os dados estruturados abaixo extraídos do ambiente do cliente e identifique TODOS os macro-processos de negócio.

DADOS EXTRAÍDOS:
{dados}

INSTRUÇÕES:
- Detecte TODOS os processos distintos — incluindo os menores e mais específicos
- Cada tabela custom com nome descritivo provavelmente representa um processo próprio
- Cada prefixo de sistema externo (TAU, TMS, SFA etc.) é um processo de integração
- Cada máquina de estados (cbox com 3+ valores) é um workflow
- Cada cluster de keywords (STATUS, APROV, INTEGR etc.) é um processo
- Não agrupe processos diferentes num só — prefira granularidade maior
- Tipos válidos: workflow, integracao, pricing, fiscal, logistica, regulatorio, auditoria, qualidade, automacao, outro
- Score de 0 a 1 indicando confiança na detecção
- Retorne APENAS o JSON, sem explicações

FORMATO DE SAÍDA (JSON array):
[
  {{
    "nome": "Nome do Processo",
    "tipo": "workflow|integracao|pricing|fiscal|logistica|regulatorio|auditoria|qualidade|automacao|outro",
    "descricao": "Uma frase descrevendo o processo",
    "criticidade": "alta|media|baixa",
    "tabelas": ["SC5", "SZV"],
    "score": 0.85
  }}
]"""


def _passo5_llm(dados: dict, llm) -> list[dict]:
    """Chama LLM uma vez para nomear e classificar os processos detectados."""
    # Compact tabelas_custom: send nome+tabela only (saves tokens, keeps semantics)
    tabs_compact = [
        {"tabela": t["tabela"], "nome": t["nome"], "campos": t["total_campos"]}
        for t in dados["passo1"]["nivel1_tabelas_custom"][:80]
    ]
    dados_compacto = {
        "tabelas_custom": tabs_compact,
        "maquinas_estado": dados["passo1"]["nivel2_cbox_estados"][:30],
        "clusters_titulo": dados["passo1"]["nivel3_titulos"],
        "prefixos_sistemas": dados["passo1"]["nivel4_prefixos"][:25],
        "tabelas_modificadas": dados["passo1"]["nivel5_diff"][:15],
        "super_triggers": list(dados["passo2"]["super_triggers"].keys())[:15],
        "funcoes_u": dados["passo2"]["funcoes_chamadas"][:20],
        "satelites": [s["tabela"] for s in dados["passo3"]["satelites"][:15]],
        "jobs_criticos": [
            {"rotina": j["rotina"], "criticidade": j["criticidade"]}
            for j in dados["passo4"]["jobs_criticos"][:15]
        ],
    }
    prompt = _PASSO5_PROMPT.format(dados=json.dumps(dados_compacto, ensure_ascii=False, indent=2))

    logger.info("Passo 5: chamando LLM para classificacao de processos")
    result = llm.chat([{"role": "user", "content": prompt}], max_tokens=8000)

    # No Supreme, llm.chat() retorna dict {"content": "...", "model": "...", ...}
    text = result["content"] if isinstance(result, dict) else result
    text = text.strip()

    # Strip markdown code block if LLM wrapped the JSON
    md_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if md_match:
        text = md_match.group(1).strip()
    try:
        processos = json.loads(text)
        if not isinstance(processos, list):
            logger.warning("Passo 5: LLM retornou JSON valido mas nao e uma lista")
            return []
        logger.info("Passo 5: %d processos detectados via LLM", len(processos))
        return processos
    except (json.JSONDecodeError, TypeError) as exc:
        logger.error("Passo 5: falha ao parsear resposta da LLM: %s", exc)
        return []


# ──────────────────────────────────────────────────────────────
# ORQUESTRADOR PRINCIPAL
# ──────────────────────────────────────────────────────────────

def descobrir_processos(db, llm, force: bool = False) -> list[dict]:
    """
    Roda o pipeline completo de descoberta (passos 1-5) e salva em processos_detectados.
    Usa cache — nao recalcula se ja existem registros, a menos que force=True.
    """
    # Checar cache
    if not force:
        count = db.execute("SELECT COUNT(*) FROM processos_detectados").fetchone()[0]
        if count > 0:
            logger.info("Descoberta de processos: usando cache (%d registros)", count)
            rows = db.execute(
                "SELECT id, nome, tipo, descricao, criticidade, tabelas, score "
                "FROM processos_detectados ORDER BY score DESC"
            ).fetchall()
            return [
                {"id": r[0], "nome": r[1], "tipo": r[2], "descricao": r[3],
                 "criticidade": r[4], "tabelas": _safe_json(r[5]), "score": r[6]}
                for r in rows
            ]

    logger.info("Iniciando pipeline de descoberta de processos (force=%s)", force)

    # Rodar passos 1-4
    dados = {
        "passo1": passo1_clustering_campos(db),
        "passo2": passo2_gatilhos(db),
        "passo3": passo3_fontes_satelite(db),
        "passo4": passo4_jobs(db),
    }

    logger.info(
        "Passos 1-4 concluidos: %d tabelas custom, %d gatilhos custom, %d clusters, %d jobs",
        len(dados["passo1"]["nivel1_tabelas_custom"]),
        dados["passo2"]["total_gatilhos_custom"],
        len(dados["passo3"]["clusters_tabela"]),
        len(dados["passo4"]["jobs_criticos"]),
    )

    # Passo 5: LLM
    processos = _passo5_llm(dados, llm)

    if not processos:
        logger.warning("Nenhum processo detectado pelo pipeline")
        return []

    # Limpar resultados anteriores e salvar novos
    db.execute("DELETE FROM processos_detectados")
    for p in processos:
        tabelas_json = json.dumps(p.get("tabelas", []), ensure_ascii=False)
        evidencias_json = json.dumps({
            "nivel1": [t["tabela"] for t in dados["passo1"]["nivel1_tabelas_custom"][:5]],
            "nivel3": [g["processo"] for g in dados["passo1"]["nivel3_titulos"][:5]],
        }, ensure_ascii=False)
        db.execute(
            "INSERT INTO processos_detectados "
            "(nome, tipo, descricao, criticidade, tabelas, evidencias, score) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                p.get("nome", ""),
                p.get("tipo", "outro"),
                p.get("descricao", ""),
                p.get("criticidade", "media"),
                tabelas_json,
                evidencias_json,
                float(p.get("score", 0.5)),
            ),
        )
    db.commit()

    # Retornar os registros salvos (com IDs)
    rows = db.execute(
        "SELECT id, nome, tipo, descricao, criticidade, tabelas, score "
        "FROM processos_detectados ORDER BY score DESC"
    ).fetchall()

    logger.info("Pipeline de descoberta concluido: %d processos salvos", len(rows))

    return [
        {"id": r[0], "nome": r[1], "tipo": r[2], "descricao": r[3],
         "criticidade": r[4], "tabelas": _safe_json(r[5]), "score": r[6]}
        for r in rows
    ]
