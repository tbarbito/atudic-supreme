"""
doc_pipeline.py — ExtraiRPO v2 document generation pipeline.

Stages:
  1. collect()      — Extract raw data from SQLite (no LLM)
  2. search_padrao()— Find relevant standard-process docs in ChromaDB
  3. generate()     — 1 LLM call → {"humano": "...", "ia": "..."}
  4. save()         — Write markdown files + index chunks in ChromaDB
"""

import json
import re
import uuid
from pathlib import Path

# ── Module-level prompt constant ──────────────────────────────────────────────

DOC_GENERATION_PROMPT = """Você é um documentador técnico especialista em TOTVS Protheus.

REGRAS ABSOLUTAS:
- Documente APENAS o que existe nos dados fornecidos. NÃO invente, NÃO sugira melhorias, NÃO analise riscos, NÃO faça recomendações.
- NÃO gere seções vazias. Se não há dados para uma seção, omita-a ou escreva "Nenhum registro encontrado."
- Seja preciso e técnico. Copie expressões ADVPL literalmente, depois explique em português.

Gere DOIS documentos retornados como JSON válido (sem markdown externo):

1. "humano" — Documento Markdown técnico com EXATAMENTE estas seções (na ordem):

   # <título do processo>

   ## Visão Geral
   Resumo de 2-3 linhas do processo baseado nas tabelas, campos e fontes fornecidos.

   ## Tabelas Envolvidas
   Tabela markdown: Código | Nome | Total Campos | Custom

   ## Campos Customizados
   Para CADA campo custom, uma subseção ### com:
   - **Campo / Título / Tipo / Tamanho**
   - **Descrição:** texto
   - **Validação:** `expressão` — explicação em português do que faz
   - **Inicializador:** `expressão` — explicação em português do valor padrão

   ## Campos Obrigatórios
   Tabela markdown: Tabela | Campo | Título | Tipo | Tamanho

   ## Gatilhos
   Para CADA gatilho uma subseção com:
   - Origem → Destino (Tipo)
   - **Regra:** `expressão ADVPL`
   - **Explicação:** o que este gatilho faz em português

   ## Índices
   Tabela markdown: Tabela | Índice | Chave | Descrição

   ## Relacionamentos
   Tabela markdown: Origem | Destino | Expressão Origem | Expressão Destino | Custom

   ## Parâmetros MV_
   Tabela markdown: Variável | Tipo | Valor Atual | Descrição | Custom

   ## Fontes Customizados
   Para cada fonte encontrado, escreva 2-3 linhas explicando:
   - O que o programa faz em relação à tabela principal
   - Quando é executado (PE de inclusão? alteração? exclusão? job? menu?)
   Se houver header do fonte (Autor, Objetivo), inclua.

   ## Campos Customizados Críticos
   Se houver seção "Campos Customizados Mais Referenciados no Ambiente" nos dados,
   identifique os 5-10 campos mais importantes e explique:
   - Para que serve o campo no contexto do negócio do cliente
   - Por que é crítico (quantos fontes usam, se tem gatilho)
   - Impacto de alterar este campo (quais processos seriam afetados)

   ## Fluxo do Processo
   Passo a passo numerado de como o processo funciona neste cliente, baseado APENAS nos dados acima.
   Inclua também um diagrama Mermaid (flowchart TD) mostrando o fluxo entre tabelas.
   Use os nomes das tabelas como nós. Indique aprovações/validações com nós diamond {{}}.
   Aplique cores: style para início fill:#00a1e0,color:#fff; conclusão fill:#28a745,color:#fff; rejeição/erro fill:#dc3545,color:#fff.
   Exemplo de formato:
   ```mermaid
   flowchart TD
       A[Pedido SC7] --> B{{Aprovação?}}
       B -->|Sim| C[Documento SF1]
       B -->|Não| D[Retorna]
       style A fill:#00a1e0,color:#fff
       style C fill:#28a745,color:#fff
       style D fill:#dc3545,color:#fff
   ```

   ## Comparação com Padrão
   Se houver contexto de processo padrão: descreva as diferenças e customizações identificadas.
   Se não houver: escreva "Contexto de processo padrão não disponível."

   ## Resumo Executivo
   Escreva um resumo em linguagem simples (não técnica) de 5-10 linhas explicando:
   - O que este processo faz no dia-a-dia da operação
   - Quais customizações principais foram feitas neste cliente
   - Qual o impacto para o usuário final
   Use linguagem que um gerente ou analista de negócios entenderia.

2. "ia" — Documento Markdown com frontmatter YAML seguido do mesmo conteúdo técnico:
   ```yaml
   ---
   processo: <slug>
   modulo: <modulo>
   tabelas: [lista de códigos]
   campos_custom: [{campo, tabela, titulo, finalidade}]
   gatilhos: [{campo_origem, campo_destino, regra}]
   fontes_custom: [lista de arquivos]
   pontos_entrada: [{nome, fonte}]
   parametros: [{variavel, valor}]
   relacionamentos: [{tabela_origem, tabela_destino}]
   ---
   ```
   Seguido do mesmo conteúdo markdown do documento humano.

Retorne APENAS JSON válido no formato: {"humano": "...", "ia": "..."}
Não envolva a resposta em blocos markdown. Escape corretamente as aspas dentro das strings JSON."""

DOC_FONTE_PROMPT = """Você é um documentador técnico especialista em TOTVS Protheus / ADVPL.

REGRAS ABSOLUTAS:
- Documente APENAS o que existe no código-fonte fornecido. NÃO invente funcionalidades que não existem no código.
- NÃO sugira melhorias, NÃO analise riscos, NÃO faça recomendações.
- Seja preciso: copie trechos de código relevantes e explique em português.
- FOCO no programa, não nas tabelas.

Gere DOIS documentos retornados como JSON válido (sem markdown externo):

1. "humano" — Documento Markdown técnico com estas seções (omita as que não se aplicam):

   # <nome do programa>

   ## Identificação
   Tabela com: Programa, Autor, Data, Solicitante, Objetivo/Descrição (extraído do header do fonte).

   ## Resumo
   2-3 frases explicando O QUE este programa faz e QUANDO é executado (ponto de entrada? chamado por menu? gatilho? job?).

   ## Funções
   Para CADA função no programa:
   ### <NomeFunção>(parâmetros)
   - **Tipo:** User Function / Static Function
   - **O que faz:** explicação em português
   - **Parâmetros:** lista com tipo e finalidade
   - **Retorno:** o que retorna

   ## Chamadas Externas
   Lista de funções externas chamadas (U_XXXX, ExecAuto, etc) com explicação do que provavelmente fazem.

   ## Tabelas e Campos Utilizados
   Lista das tabelas acessadas e campos lidos/gravados pelo programa. Formato tabela markdown.
   NÃO listar todos os campos da tabela — apenas os que o programa REALMENTE usa.

   ## Fluxo de Execução
   Passo a passo numerado do que acontece quando o programa é executado, baseado na leitura do código.

   ## Resumo Executivo
   Escreva um resumo em linguagem simples (não técnica) de 5-10 linhas explicando:
   - Para que serve este programa em termos de negócio (ex: "Gera pedidos de exportação automaticamente a partir de orçamentos")
   - Quando ele é usado no dia-a-dia da operação
   - Qual o benefício para o usuário final
   Use linguagem que um gerente ou analista de negócios entenderia, sem termos técnicos ADVPL.

2. "ia" — Documento Markdown com frontmatter YAML:
   ```yaml
   ---
   tipo: fonte
   programa: <nome do arquivo>
   autor: <autor>
   funcoes: [lista de funções]
   tabelas_usadas: [lista]
   chamadas_externas: [lista de U_xxx]
   ponto_entrada: true/false
   ---
   ```
   Seguido do mesmo conteúdo markdown.

Retorne APENAS JSON válido no formato: {"humano": "...", "ia": "..."}
Não envolva a resposta em blocos markdown. Escape corretamente as aspas dentro das strings JSON."""


# ── Pipeline ───────────────────────────────────────────────────────────────────

class DocPipeline:
    def __init__(self, db, vs, ks):
        self.db = db   # Database instance
        self.vs = vs   # VectorStore instance
        self.ks = ks   # KnowledgeService instance
        self._skills = {}  # Future: registered skills

    # ── Stage 1: Collect ──────────────────────────────────────────────────────

    def collect(self, tables: list[str], fontes: list[str] = None) -> dict:
        """Extract raw data from SQLite. No LLM call.

        Supports two modes:
        - tables given: full table-centric analysis (campos, gatilhos, indices, etc)
        - only fontes given: source-code-centric analysis (reads code, extracts metadata)

        Returns a dict with keys:
          tabelas, campos_custom, campos_obrigatorios, gatilhos, indices,
          relacionamentos, parametros, fontes, source_code, campos_com_logica,
          fonte_only (bool), fonte_headers (dict)
        """
        # If only fontes selected, resolve tables from the fontes' tabelas_ref
        fonte_only = not tables and bool(fontes)
        if fonte_only:
            tables = self._auto_detect_tables_from_fontes(fontes)

        tabelas_info = []
        all_campos_custom = []
        all_campos_obrigatorios = []
        all_gatilhos = []
        all_indices = []

        for codigo in tables:
            info = self.ks.get_table_info(codigo)
            if not info:
                continue

            tabelas_info.append({
                "codigo": info["codigo"],
                "nome": info["nome"],
                "total_campos": len(info["campos"]),
                "total_custom": len(info["campos_custom"]),
            })

            # Custom fields — keep all detail for LLM
            for c in info["campos_custom"]:
                all_campos_custom.append({
                    "tabela": codigo,
                    "campo": c["campo"],
                    "tipo": c["tipo"],
                    "tamanho": c["tamanho"],
                    "titulo": c["titulo"],
                    "descricao": c.get("descricao", ""),
                    "validacao": c.get("validacao", ""),
                    "inicializador": c.get("inicializador", ""),
                    "browse": c.get("browse", ""),
                    "obrigatorio": c.get("obrigatorio", False),
                })

            # Mandatory fields (standard + custom)
            for c in info["campos"]:
                if c.get("obrigatorio"):
                    all_campos_obrigatorios.append({
                        "tabela": codigo,
                        "campo": c["campo"],
                        "tipo": c["tipo"],
                        "tamanho": c["tamanho"],
                        "titulo": c.get("titulo", ""),
                    })

            # Triggers
            for g in info["gatilhos"]:
                all_gatilhos.append({
                    "tabela": codigo,
                    "campo_origem": g["campo_origem"],
                    "campo_destino": g["campo_destino"],
                    "regra": g.get("regra", ""),
                    "tipo": g.get("tipo", ""),
                    "custom": g.get("custom", False),
                })

            # Indices
            for i in info["indices"]:
                all_indices.append({
                    "tabela": codigo,
                    "indice": i["indice"],
                    "chave": i["chave"],
                    "descricao": i.get("descricao", ""),
                })

        # Cross-table relationships — only direct (where one side is in requested tables)
        all_rels = self.ks.get_relacionamentos_for_tables(tables)
        # Filter: keep only custom or directly relevant (limit to 30)
        relacionamentos = [r for r in all_rels if r.get("custom")]
        if len(relacionamentos) < 30:
            # Add standard ones up to limit
            standard = [r for r in all_rels if not r.get("custom")][:30 - len(relacionamentos)]
            relacionamentos.extend(standard)

        # Custom parameters from DB (MV_ params referenced by these tables)
        parametros = self._get_parametros_for_tables(tables)

        # Fields with complex validations/initializers (reference functions, ExecBlock, etc)
        campos_com_logica = []
        u_functions_found = set()  # Track U_ references to find matching sources
        for tabela in tables:
            rows = self.db.execute(
                """SELECT campo, titulo, validacao, inicializador FROM campos
                   WHERE tabela = ? AND (
                     validacao LIKE '%ExecBlock%' OR validacao LIKE '%ExistCpo%'
                     OR validacao LIKE '%Pertence%' OR validacao LIKE '%U_%'
                     OR inicializador LIKE '%Posicione%' OR inicializador LIKE '%ExecBlock%'
                     OR inicializador LIKE '%IIF(%' OR inicializador LIKE '%If(%'
                   )""", (tabela,)
            ).fetchall()
            for r in rows:
                campos_com_logica.append({
                    "tabela": tabela, "campo": r[0], "titulo": r[1],
                    "validacao": r[2] or "", "inicializador": r[3] or "",
                })
                # Extract U_ function references
                for text in [r[2] or "", r[3] or ""]:
                    for match in re.findall(r'U_(\w+)', text):
                        u_functions_found.add(match)

        # Also extract U_ from gatilhos
        for g in all_gatilhos:
            regra = g.get("regra", "")
            for match in re.findall(r'U_(\w+)', regra):
                u_functions_found.add(match)

        # Sources: explicit list or auto-detect via tabelas_ref + prefix + U_ references
        # For fonte-only: only resolve the requested fontes + their U_ deps (no table-based search)
        if fonte_only:
            fontes_list = self._resolve_fontes_recursive([], fontes, set(), max_depth=1)
        else:
            fontes_list = self._resolve_fontes_recursive(tables, fontes, u_functions_found, max_depth=2)

        # Source code — for fonte_only mode, read ALL selected fontes (full code, higher limit)
        if fonte_only:
            source_code = self._get_source_code_for_fontes(fontes, fontes_list)
            fonte_headers = self._extract_fonte_headers(source_code)
        else:
            source_code = self._get_source_code(fontes_list)
            fonte_headers = self._extract_fonte_headers(source_code)

        # Count how many fontes reference each custom field (importance metric)
        campos_relevancia = self._count_campo_references(tables, all_campos_custom) if not fonte_only else {}

        return {
            "tabelas": tabelas_info,
            "campos_custom": all_campos_custom,
            "campos_obrigatorios": all_campos_obrigatorios,
            "gatilhos": all_gatilhos,
            "indices": all_indices,
            "relacionamentos": relacionamentos,
            "parametros": parametros,
            "fontes": fontes_list,
            "source_code": source_code,
            "campos_com_logica": campos_com_logica,
            "fonte_only": fonte_only,
            "fonte_headers": fonte_headers,
            "campos_relevancia": campos_relevancia,
        }

    def _auto_detect_tables_from_fontes(self, fontes: list[str]) -> list[str]:
        """Given fonte names, return the tables they reference."""
        tables = set()
        for fonte_name in fontes:
            row = self.db.execute(
                "SELECT tabelas_ref FROM fontes WHERE UPPER(arquivo) = UPPER(?)", (fonte_name,)
            ).fetchone()
            if row and row[0]:
                for t in json.loads(row[0]):
                    tables.add(t)
        # For fonte-only mode, limit to 5 most relevant tables to avoid bloat
        if len(tables) > 5:
            return list(tables)[:5]
        return list(tables)

    def _get_source_code_for_fontes(self, requested_fontes: list[str],
                                     all_fontes: list[dict]) -> dict:
        """For fonte-only mode: read full code of requested fontes + top dependencies.
        Requested fontes get full code. Dependencies limited to 3."""
        result = {}
        requested_set = set(f.upper().rsplit(".", 1)[0] for f in requested_fontes)
        dep_count = 0
        MAX_DEPS = 3

        for f in all_fontes:
            arquivo_stem = f["arquivo"].upper().rsplit(".", 1)[0]
            is_requested = arquivo_stem in requested_set

            if not is_requested:
                if dep_count >= MAX_DEPS:
                    continue
                dep_count += 1

            caminho = self._get_fonte_path(f["arquivo"])
            if not caminho:
                continue
            try:
                code = self._read_file(caminho)
                limit = 6000 if is_requested else 1500
                result[f["arquivo"]] = code[:limit]
            except Exception:
                continue
        return result

    def _extract_fonte_headers(self, source_code: dict) -> dict:
        """Extract ADVPL file headers (Programa, Autor, Data, Descrição, etc)."""
        headers = {}
        for arquivo, code in source_code.items():
            header = {}
            # Standard Protheus header pattern
            for line in code.split("\n")[:30]:
                line = line.strip().lstrip("/*").lstrip("//").strip()
                for field in ["Programa", "Autor", "Data", "Descri", "Objetivo",
                              "Solicitante", "Uso", "Obs", "RITM", "Chamado"]:
                    if field.lower() in line.lower() and ":" in line:
                        key = line.split(":")[0].strip().rstrip(".")
                        val = ":".join(line.split(":")[1:]).strip()
                        if val:
                            header[key] = val
            if header:
                headers[arquivo] = header
        return headers

    def _count_campo_references(self, tables: list[str], campos_custom: list[dict]) -> dict:
        """Count how many fontes reference each custom field.

        Returns {campo: {count: N, fontes: [list], in_gatilhos: bool, titulo: str}}
        Reads each file once and checks all campos, for efficiency.
        """
        if not campos_custom:
            return {}

        campo_names = set()
        campo_info = {}
        for c in campos_custom:
            campo_names.add(c["campo"])
            campo_info[c["campo"]] = {"count": 0, "fontes": [], "titulo": c["titulo"], "in_gatilhos": False}

        # Read each fonte ONCE, check all campos
        all_fontes = self.db.execute("SELECT arquivo, caminho FROM fontes").fetchall()
        for arquivo, caminho in all_fontes:
            try:
                code = self._read_file(caminho)
                for campo in campo_names:
                    if campo in code:
                        campo_info[campo]["count"] += 1
                        if len(campo_info[campo]["fontes"]) < 5:
                            campo_info[campo]["fontes"].append(arquivo)
            except Exception:
                continue

        # Check gatilhos
        for campo in campo_names:
            count = self.db.execute(
                "SELECT COUNT(*) FROM gatilhos WHERE campo_origem = ? OR campo_destino = ?",
                (campo, campo)
            ).fetchone()[0]
            campo_info[campo]["in_gatilhos"] = count > 0

        # Return only campos with 2+ references (actually important)
        return {k: v for k, v in campo_info.items() if v["count"] >= 2}

    def _get_parametros_for_tables(self, tables: list[str]) -> list[dict]:
        """Find MV_ parameters referenced in validations/initializers of the given tables."""
        params_found = set()
        for tabela in tables:
            rows = self.db.execute(
                "SELECT validacao, inicializador FROM campos WHERE tabela = ?", (tabela,)
            ).fetchall()
            for row in rows:
                for text in [row[0] or "", row[1] or ""]:
                    for match in re.findall(r"MV_\w+", text):
                        params_found.add(match.strip())

        if not params_found:
            return []

        result = []
        for param in sorted(params_found):
            rows = self.db.execute(
                "SELECT variavel, tipo, descricao, conteudo, custom FROM parametros WHERE variavel LIKE ?",
                (f"%{param}%",),
            ).fetchall()
            for r in rows:
                result.append({
                    "variavel": r[0].strip(),
                    "tipo": r[1],
                    "descricao": r[2],
                    "conteudo": r[3],
                    "custom": bool(r[4]),
                })
        return result

    def _resolve_fontes(self, tables: list[str], fontes: list[str] = None,
                        u_functions: set = None) -> list[dict]:
        """Return fonte records. If fontes arg given, use those; otherwise auto-detect."""
        if fontes:
            # Case-insensitive search for explicitly requested fontes
            placeholders = " OR ".join(["UPPER(arquivo) = UPPER(?)"] * len(fontes))
            rows = self.db.execute(
                f"SELECT arquivo, tipo, funcoes, user_funcs, pontos_entrada, tabelas_ref "
                f"FROM fontes WHERE {placeholders}",
                tuple(fontes),
            ).fetchall()
        else:
            # Auto-detect: multiple strategies
            candidate_rows = self.db.execute(
                "SELECT arquivo, tipo, funcoes, user_funcs, pontos_entrada, tabelas_ref, write_tables FROM fontes"
            ).fetchall()
            table_set = set(tables)

            # Strategy 1: fontes that WRITE to the target tables
            # Excludes fontes that only READ from the table (reports, DANFE, etc)
            rows = []
            matched_files = set()
            for r in candidate_rows:
                write_tables = json.loads(r[6]) if len(r) > 6 and r[6] else []
                if table_set.intersection(write_tables):
                    rows.append(r)
                    matched_files.add(r[0])

            # Strategy 2: PE name prefix match (A0xx = SA1/MATA030, A1xx = SA1, C5xx = SC5, etc)
            # In Protheus, fonte names like A020DELE.prw = PE for rotina A020 (cadastro clientes)
            # The prefix mapping: SA1 -> A0/A1, SC5 -> C5, SE1 -> E1, SC7 -> C7, etc
            table_prefixes = set()
            for tab in tables:
                # SA1 -> A0, A1; SC5 -> C5; SE2 -> E2; SF2 -> F2
                code = tab[1:]  # A1, C5, E1, etc
                table_prefixes.add(code[:2].upper())
                # Also add A0 for SA1 (MATA030 PEs start with A0)
                if tab == "SA1":
                    table_prefixes.update(["A0", "A1"])
                elif tab == "SC5":
                    table_prefixes.update(["C5", "A4"])  # A410 = pedido vendas
                elif tab == "SC7":
                    table_prefixes.update(["C7", "A1"])  # A120 = pedido compras

            for r in candidate_rows:
                if r[0] in matched_files:
                    continue
                arquivo = r[0].upper()
                # Check if file starts with any table prefix
                for prefix in table_prefixes:
                    if arquivo.startswith(prefix):
                        rows.append(r)
                        matched_files.add(r[0])
                        break

            # Strategy 3: U_ function references found in validations/triggers
            # U_FUNCAO -> search by: 1) arquivo name (FUNCAO.prw), 2) funcoes/user_funcs columns
            if u_functions:
                u_funcs_upper = set(uf.upper() for uf in u_functions)
                for r in candidate_rows:
                    if r[0] in matched_files:
                        continue
                    # Check 1: arquivo name matches (MGFFATB3.PRW -> MGFFATB3)
                    arquivo_stem = r[0].upper().rsplit(".", 1)[0]
                    if arquivo_stem in u_funcs_upper:
                        rows.append(r)
                        matched_files.add(r[0])
                        continue
                    # Check 2: function exists inside the fonte
                    funcoes = json.loads(r[2]) if r[2] else []
                    user_funcs = json.loads(r[3]) if r[3] else []
                    pes = json.loads(r[4]) if r[4] else []
                    all_funcs = set(f.upper() for f in funcoes + user_funcs + pes)
                    if u_funcs_upper.intersection(all_funcs):
                        rows.append(r)
                        matched_files.add(r[0])

                # Track U_ functions NOT found in any fonte (missing from ingestion)
                found_funcs = set()
                for r in rows:
                    found_funcs.add(r[0].upper().rsplit(".", 1)[0])
                    for f in json.loads(r[2]) if r[2] else []:
                        found_funcs.add(f.upper())
                    for f in json.loads(r[3]) if r[3] else []:
                        found_funcs.add(f.upper())
                self._missing_u_functions = u_funcs_upper - found_funcs

        # Cap total fontes to avoid context explosion
        MAX_FONTES = 30
        if len(rows) > MAX_FONTES:
            # Prioritize: PEs first, then small focused fontes, then by name match
            def _score(r):
                pes = json.loads(r[4]) if r[4] else []
                tabs = json.loads(r[5]) if r[5] else []
                score = 0
                if pes:
                    score += 100  # PEs are most important
                if len(tabs) <= 3:
                    score += 50   # Focused fontes
                return -score  # negative for ascending sort
            rows = sorted(rows, key=_score)[:MAX_FONTES]

        result = []
        for r in rows:
            result.append({
                "arquivo": r[0],
                "tipo": r[1],
                "funcoes": json.loads(r[2]) if r[2] else [],
                "user_funcs": json.loads(r[3]) if r[3] else [],
                "pontos_entrada": json.loads(r[4]) if r[4] else [],
                "tabelas_ref": json.loads(r[5]) if r[5] else [],
            })
        return result

    def _resolve_fontes_recursive(self, tables: list[str], fontes: list[str] = None,
                                    u_functions: set = None, max_depth: int = 2) -> list[dict]:
        """Resolve fontes with recursive U_ function search.

        Depth 0: find fontes by table/prefix/U_ refs from campos/gatilhos
        Depth 1+: read found fontes, extract new U_ calls, find those fontes too
        """
        all_matched = {}  # arquivo -> row dict
        all_u_found = set(u_functions or set())
        u_searched = set()

        # Initial resolve
        initial = self._resolve_fontes(tables, fontes, all_u_found)
        for f in initial:
            all_matched[f["arquivo"]] = f

        # Recursive: scan found fontes for more U_ references
        for depth in range(max_depth):
            new_u = set()
            for arquivo, info in list(all_matched.items()):
                if arquivo in u_searched:
                    continue
                u_searched.add(arquivo)

                # Read source code and extract U_ calls
                caminho = self._get_fonte_path(arquivo)
                if not caminho:
                    continue
                try:
                    content = self._read_file(caminho)
                    for match in re.findall(r'U_(\w+)', content):
                        if match.upper() not in all_u_found and match.upper() not in {a.upper().rsplit(".", 1)[0] for a in all_matched}:
                            new_u.add(match)
                except Exception:
                    continue

            if not new_u:
                break

            all_u_found.update(new_u)
            # Find fontes for new U_ functions
            extra = self._resolve_fontes(tables, None, new_u)
            for f in extra:
                if f["arquivo"] not in all_matched:
                    all_matched[f["arquivo"]] = f

        return list(all_matched.values())

    def _get_fonte_path(self, arquivo: str) -> str:
        """Get file path for a fonte from SQLite (case-insensitive)."""
        row = self.db.execute("SELECT caminho FROM fontes WHERE UPPER(arquivo) = UPPER(?)", (arquivo,)).fetchone()
        return row[0] if row else None

    def _read_file(self, path: str) -> str:
        """Read a source file with encoding fallback."""
        from pathlib import Path
        p = Path(path)
        for enc in ["utf-8", "cp1252", "latin-1"]:
            try:
                return p.read_text(encoding=enc)
            except (UnicodeDecodeError, UnicodeError):
                continue
        return p.read_text(encoding="utf-8", errors="replace")

    def _get_source_code(self, fontes_list: list[dict]) -> dict:
        """Read source code for fontes with PEs or few tables (most relevant).
        Returns {arquivo: code}. Max 15 files, 2000 chars each."""
        # Prioritize: fontes with PEs first, then small focused ones
        prioritized = sorted(fontes_list, key=lambda f: (
            0 if f.get("pontos_entrada") else 1,
            len(f.get("tabelas_ref", [])),
        ))
        result = {}
        for f in prioritized[:15]:
            caminho = self._get_fonte_path(f["arquivo"])
            if not caminho:
                continue
            try:
                code = self._read_file(caminho)
                result[f["arquivo"]] = code[:2000]
            except Exception:
                continue
        return result

    # ── Stage 1b: Search padrão ───────────────────────────────────────────────

    def search_padrao(self, tables: list[str], modulo: str = "") -> str:
        """Search relevant standard process docs from ChromaDB collection 'padrao'."""
        if not self.vs:
            return ""
        try:
            query_parts = list(tables)
            if modulo:
                query_parts.append(modulo)
            query = " ".join(query_parts)
            results = self.vs.search("padrao", query, n_results=5)
            if not results:
                return ""
            parts = []
            for r in results:
                parts.append(r.get("content", ""))
            return "\n\n---\n\n".join(parts)
        except Exception:
            return ""

    # ── Stage 2: Generate ─────────────────────────────────────────────────────

    def generate(self, collected_data: dict, slug: str, padrao_context: str = "", llm=None) -> dict:
        """1 LLM call to generate documentation.

        Builds a human-readable context string, appends padrao_context (truncated),
        caps total context at 20 000 chars, then calls llm._call with use_gen=True.
        Returns dict with keys 'humano' and 'ia'.
        """
        if llm is None:
            raise ValueError("llm instance is required for generate()")

        context = self._build_context_text(collected_data, slug)

        # Append padrão context if available
        if padrao_context:
            padrao_snippet = padrao_context[:5000]
            context += f"\n\n## Contexto do Processo Padrão (referência)\n{padrao_snippet}"

        # Hard cap at 20 000 chars to avoid rate limits
        if len(context) > 20000:
            context = context[:20000] + "\n\n[contexto truncado]"

        is_fonte_only = collected_data.get("fonte_only", False)
        system_prompt = DOC_FONTE_PROMPT if is_fonte_only else DOC_GENERATION_PROMPT

        if is_fonte_only:
            user_msg = (
                f"Documente o programa customizado: **{slug}**\n\n"
                f"{context}"
            )
        else:
            user_msg = (
                f"Gere a documentação completa para o processo: **{slug}**\n\n"
                f"{context}"
            )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ]

        raw = llm._call(messages, temperature=0.3, use_gen=True)
        raw = raw.strip()

        # Strip ```json ... ``` wrapper if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            # Return a minimal fallback so the pipeline doesn't crash
            return {
                "humano": f"# {slug}\n\nErro ao parsear resposta do LLM: {exc}\n\nResposta bruta:\n{raw}",
                "ia": f"---\nprocesso: {slug}\n---\n\nErro ao parsear resposta do LLM.",
            }

    def _build_context_text(self, data: dict, slug: str) -> str:
        """Format collected_data as human-readable text for the LLM."""
        if data.get("fonte_only"):
            lines = [f"# Documentação de Programa Customizado: {slug}\n"]
            lines.append("MODO: Documentação focada em código-fonte (sem tabela principal selecionada).\n")
        else:
            lines = [f"# Dados Coletados para: {slug}\n"]

        # 0. Fonte headers (autor, objetivo, etc)
        if data.get("fonte_headers"):
            lines.append("## Informações dos Programas\n")
            for arquivo, header in data["fonte_headers"].items():
                lines.append(f"### {arquivo}")
                for k, v in header.items():
                    lines.append(f"- **{k}:** {v}")
                lines.append("")

        # 1. Tables
        if data.get("tabelas"):
            lines.append("## Tabelas Envolvidas\n")
            for t in data["tabelas"]:
                lines.append(
                    f"- **{t['codigo']}** — {t['nome']}  "
                    f"(total campos: {t['total_campos']}, custom: {t['total_custom']})"
                )
            lines.append("")

        # 2. Custom fields
        if data.get("campos_custom"):
            lines.append("## Campos Customizados\n")
            for c in data["campos_custom"]:
                lines.append(
                    f"### {c['tabela']}.{c['campo']} — {c['titulo']}\n"
                    f"- Tipo: {c['tipo']} | Tamanho: {c['tamanho']}\n"
                    f"- Descrição: {c['descricao']}\n"
                    f"- Obrigatório: {'Sim' if c.get('obrigatorio') else 'Não'}"
                )
                if c.get("validacao"):
                    lines.append(f"- Validação: `{c['validacao']}`")
                if c.get("inicializador"):
                    lines.append(f"- Inicializador: `{c['inicializador']}`")
                lines.append("")

        # 3. Mandatory fields
        if data.get("campos_obrigatorios"):
            lines.append("## Campos Obrigatórios\n")
            for c in data["campos_obrigatorios"]:
                lines.append(
                    f"- {c['tabela']}.{c['campo']} | {c['titulo']} | {c['tipo']} | tam:{c['tamanho']}"
                )
            lines.append("")

        # 4. Triggers
        if data.get("gatilhos"):
            lines.append("## Gatilhos (SX7)\n")
            for g in data["gatilhos"]:
                custom_tag = "[CUSTOM]" if g.get("custom") else "[Padrão]"
                lines.append(
                    f"- {custom_tag} {g['campo_origem']} → {g['campo_destino']} (tipo: {g.get('tipo', '')})"
                )
                if g.get("regra"):
                    lines.append(f"  Regra: `{g['regra']}`")
            lines.append("")

        # 5. Indices
        if data.get("indices"):
            lines.append("## Índices (SX3)\n")
            for i in data["indices"]:
                lines.append(
                    f"- {i['tabela']} | {i['indice']}: {i['chave']} — {i.get('descricao', '')}"
                )
            lines.append("")

        # 6. Relationships
        if data.get("relacionamentos"):
            lines.append("## Relacionamentos (SX9)\n")
            for r in data["relacionamentos"]:
                custom_tag = "[CUSTOM]" if r.get("custom") else "[Padrão]"
                lines.append(
                    f"- {custom_tag} {r['tabela_origem']} → {r['tabela_destino']} | "
                    f"{r.get('expr_origem', '')} = {r.get('expr_destino', '')}"
                )
            lines.append("")

        # 7. Parameters
        if data.get("parametros"):
            lines.append("## Parâmetros MV_\n")
            for p in data["parametros"]:
                custom_tag = "[CUSTOM]" if p.get("custom") else "[Padrão]"
                valor = (p.get("conteudo") or "").strip()
                lines.append(
                    f"- {custom_tag} **{p['variavel']}** ({p.get('tipo', '')}) — {p.get('descricao', '')}"
                )
                if valor:
                    lines.append(f"  Valor atual: `{valor}`")
            lines.append("")

        # 8. Custom sources
        custom_fontes = [f for f in (data.get("fontes") or []) if f.get("tipo") == "custom"]
        if custom_fontes:
            lines.append("## Fontes Customizados\n")
            for f in custom_fontes:
                lines.append(f"### {f['arquivo']} (tipo: {f['tipo']})")
                if f.get("funcoes"):
                    lines.append(f"  Funções: {', '.join(f['funcoes'])}")
                if f.get("user_funcs"):
                    lines.append(f"  User Functions: {', '.join(f['user_funcs'])}")
                if f.get("pontos_entrada"):
                    lines.append(f"  Pontos de Entrada: {', '.join(f['pontos_entrada'])}")
                if f.get("tabelas_ref"):
                    lines.append(f"  Tabelas referenciadas: {', '.join(f['tabelas_ref'])}")
                lines.append("")

        # 9. Fields with complex validations/initializers
        if data.get("campos_com_logica"):
            lines.append("## Campos com Validações/Inicializadores Complexos\n")
            for c in data["campos_com_logica"][:30]:  # limit to avoid bloat
                lines.append(f"### {c['tabela']}.{c['campo']} — {c['titulo']}")
                if c.get("validacao"):
                    lines.append(f"- Validação: `{c['validacao']}`")
                if c.get("inicializador"):
                    lines.append(f"- Inicializador: `{c['inicializador']}`")
                lines.append("")

        # 10. Missing U_ functions (referenced but source not found)
        missing = getattr(self, '_missing_u_functions', set())
        if missing:
            lines.append("## Funções U_ Referenciadas (fonte não encontrado na ingestão)\n")
            for uf in sorted(missing):
                lines.append(f"- U_{uf} — fonte {uf}.PRW não foi ingerido. Verificar pasta de customizados.")
            lines.append("")

        # 11. Campos custom mais referenciados (importância no ecossistema)
        if data.get("campos_relevancia"):
            lines.append("## Campos Customizados Mais Referenciados no Ambiente\n")
            lines.append("Campos ordenados por quantidade de fontes que os referenciam:\n")
            sorted_campos = sorted(data["campos_relevancia"].items(), key=lambda x: -x[1]["count"])
            for campo, info in sorted_campos[:15]:
                gatilho_tag = " [TEM GATILHO]" if info.get("in_gatilhos") else ""
                fontes_sample = ", ".join(info["fontes"][:3])
                lines.append(
                    f"- **{campo}** ({info['titulo']}) — referenciado em **{info['count']} fontes**{gatilho_tag}"
                )
                if fontes_sample:
                    lines.append(f"  Exemplos: {fontes_sample}")
            lines.append("")

        # 12. Fonte headers (autor, objetivo) dos fontes encontrados
        if data.get("fonte_headers"):
            lines.append("## Informações dos Programas Customizados\n")
            for arquivo, header in data["fonte_headers"].items():
                parts = [f"**{arquivo}**"]
                for k, v in header.items():
                    parts.append(f"{k}: {v}")
                lines.append("- " + " | ".join(parts))
            lines.append("")

        # 13. Source code of found fontes
        if data.get("source_code"):
            lines.append("## Código-Fonte dos Programas Customizados\n")
            for arquivo, code in data["source_code"].items():
                lines.append(f"### {arquivo}\n```advpl\n{code}\n```\n")

        return "\n".join(lines)

    # ── Stage 3: Save ─────────────────────────────────────────────────────────

    def save(self, knowledge_dir, slug: str, docs: dict, modulo: str = ""):
        """Save docs to markdown files.

        Writes:
          <knowledge_dir>/humano/<slug>.md
          <knowledge_dir>/ia/<slug>.md
        """
        from app.services.workspace.doc_generator import save_doc

        knowledge_dir = Path(knowledge_dir)

        humano_content = docs.get("humano", "")
        ia_content = docs.get("ia", "")

        save_doc(knowledge_dir, slug, "humano", humano_content)
        save_doc(knowledge_dir, slug, "ia", ia_content)

    def _chunk_doc(self, content: str, slug: str, modulo: str, camada: str) -> list[dict]:
        """Split markdown content by ## headings into indexable chunks."""
        if not content:
            return []

        sections = re.split(r"(?m)^##\s+", content)
        chunks = []
        for i, section in enumerate(sections):
            section = section.strip()
            if not section:
                continue
            chunk_id = f"{slug}_{camada}_{i}_{uuid.uuid4().hex[:8]}"
            chunks.append({
                "id": chunk_id,
                "content": section[:2000],  # cap chunk size
                "slug": slug,
                "modulo": modulo,
                "camada": camada,
                "section_index": i,
            })
        return chunks

    # ── Full pipeline ─────────────────────────────────────────────────────────

    def run(self, tables: list[str], fontes: list[str], slug: str, modulo: str,
            knowledge_dir, llm=None) -> dict:
        """Execute full pipeline: collect → search_padrao → generate → save.

        Returns summary dict with stats.
        """
        # Stage 1
        collected = self.collect(tables, fontes)

        # Stage 1b
        padrao_context = self.search_padrao(tables, modulo)

        # Stage 2
        docs = self.generate(collected, slug, padrao_context=padrao_context, llm=llm)

        # Stage 3
        self.save(knowledge_dir, slug, docs, modulo=modulo)

        return {
            "slug": slug,
            "modulo": modulo,
            "tabelas": [t["codigo"] for t in collected["tabelas"]],
            "campos_custom": len(collected["campos_custom"]),
            "campos_obrigatorios": len(collected["campos_obrigatorios"]),
            "gatilhos": len(collected["gatilhos"]),
            "indices": len(collected["indices"]),
            "relacionamentos": len(collected["relacionamentos"]),
            "parametros": len(collected["parametros"]),
            "fontes": len(collected["fontes"]),
            "padrao_context_chars": len(padrao_context),
            "humano_chars": len(docs.get("humano", "")),
            "ia_chars": len(docs.get("ia", "")),
        }

    # ── Skill registry ────────────────────────────────────────────────────────

    def register_skill(self, name: str, skill_fn):
        """Register a specialized skill for future use."""
        self._skills[name] = skill_fn
