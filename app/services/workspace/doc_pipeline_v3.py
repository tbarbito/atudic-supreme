"""
doc_pipeline_v3.py — 4-stage document generation with dual-model strategy.

Stage 1: CODE-ONLY  — Sections 1,2,5,6,7,16 (zero LLM tokens)
Stage 2: CHEAP LLM  — Sections 3,4(data),9,10,11,15 (gen_model)
Stage 3: CHEAP LLM  — Section 15 fonte analysis (gen_model)
Stage 4: STRONG LLM — Sections 8,17,18,19,4(flows) (chat_model)

Cost: ~$0.16/module vs ~$3-5/module if everything goes to strong model.
"""
import json
import re
from pathlib import Path
from app.services.workspace.workspace_db import Database
from app.services.workspace.knowledge import KnowledgeService


class DocPipelineV3:
    def __init__(self, db: Database, llm, padrao_dir: Path = None):
        self.db = db
        self.llm = llm
        self.ks = KnowledgeService(db)
        self.padrao_dir = padrao_dir or Path("processoPadrao")
        mapa_path = Path("templates/processos/mapa-modulos.json")
        self._mapa = json.loads(mapa_path.read_text(encoding="utf-8")) if mapa_path.exists() else {}

    async def generate_module_doc(self, modulo: str, cliente: str = "",
                                    on_progress=None) -> dict:
        """Generate complete 19-section doc for a module.

        Args:
            modulo: module name (e.g. 'compras', 'fiscal')
            cliente: client name
            on_progress: optional callback(stage, message) for progress reporting

        Returns {"humano": markdown, "ia": markdown_with_yaml}
        """
        import asyncio

        def _log(stage, msg):
            if on_progress:
                on_progress(stage, msg)

        # Stage 1: Code-only sections (zero tokens)
        _log(1, "Gerando seções por código (sem IA)...")
        stage1 = self._stage1_code_only(modulo, cliente)
        _log(1, "Stage 1 completo")

        # Stage 2 + Stage 3: Run in PARALLEL (both use cheap gen_model)
        _log(2, "Iniciando Stage 2 (catálogo) + Stage 3 (fontes) em paralelo...")
        stage2_task = asyncio.create_task(self._stage2_cheap_catalog(modulo, stage1))
        stage3_task = asyncio.create_task(self._stage3_cheap_fontes(modulo))

        stage2, stage3 = await asyncio.gather(stage2_task, stage3_task)
        _log(3, "Stage 2 + 3 completos")

        # Stage 4: Strong LLM — needs results from stages 1-3
        _log(4, "Iniciando Stage 4 (síntese com IA forte)...")
        stage4 = await self._stage4_strong_synthesis(modulo, stage1, stage2, stage3)
        _log(4, "Stage 4 completo")

        # Assemble final document
        _log(5, "Montando documento final...")
        return self._assemble(modulo, cliente, stage1, stage2, stage3, stage4)

    # ── Stage 1: Code-only (zero tokens) ─────────────────────────────────────

    def _stage1_code_only(self, modulo: str, cliente: str = "") -> dict:
        """Generate sections that need NO LLM — pure SQL queries."""
        result = {}

        # Section 1: Resumo quantitativo
        result["sec1"] = self._gen_sec1_resumo(modulo, cliente)

        # Section 2: Parametros alterados
        result["sec2"] = self._gen_sec2_parametros(modulo)

        # Section 5: Contabilizacao (if applicable)
        result["sec5"] = ""  # Placeholder — requires manual data

        # Section 6: Tipos e classificacoes
        result["sec6"] = self._gen_sec6_tipos(modulo)

        # Section 7: Tabelas consolidado
        result["sec7"] = self._gen_sec7_tabelas(modulo)

        # Section 16: Mapa de vinculos
        result["sec16"] = self._gen_sec16_vinculos(modulo)

        return result

    def _gen_sec1_resumo(self, modulo: str, cliente: str) -> str:
        """Section 1: Quantitative summary — pure SQL."""
        tables = self._get_module_tables(modulo)
        if not tables:
            return "## 1. Objetivo do Módulo no Cliente\n\nNenhuma tabela encontrada para este módulo.\n"

        placeholders = ",".join(["?"] * len(tables))

        total_campos = self.db.execute(
            f"SELECT COUNT(*) FROM campos WHERE tabela IN ({placeholders})", tuple(tables)).fetchone()[0]
        custom_campos = self.db.execute(
            f"SELECT COUNT(*) FROM campos WHERE tabela IN ({placeholders}) AND custom = 1", tuple(tables)).fetchone()[0]
        total_indices = self.db.execute(
            f"SELECT COUNT(*) FROM indices WHERE tabela IN ({placeholders})", tuple(tables)).fetchone()[0]
        custom_indices = self.db.execute(
            f"SELECT COUNT(*) FROM indices WHERE tabela IN ({placeholders}) AND custom = 1", tuple(tables)).fetchone()[0]

        # Gatilhos — batch query with OR conditions
        prefixes = [tab[1:] for tab in tables]  # SA1 -> A1
        if prefixes:
            like_conditions = " OR ".join(["campo_origem LIKE ?"] * len(prefixes))
            like_params = tuple(f"{p}_%" for p in prefixes)
            total_gatilhos = self.db.execute(
                f"SELECT COUNT(*) FROM gatilhos WHERE {like_conditions}", like_params).fetchone()[0]
            custom_gatilhos = self.db.execute(
                f"SELECT COUNT(*) FROM gatilhos WHERE ({like_conditions}) AND custom = 1", like_params).fetchone()[0]
        else:
            total_gatilhos = 0
            custom_gatilhos = 0

        total_fontes = self.db.execute(
            "SELECT COUNT(*) FROM fontes WHERE modulo = ?", (modulo,)).fetchone()[0]

        # PEs
        total_pes = 0
        rows = self.db.execute("SELECT pontos_entrada FROM fontes WHERE modulo = ?", (modulo,)).fetchall()
        for r in rows:
            pes = json.loads(r[0]) if r[0] else []
            total_pes += len(pes)

        # Vinculos
        total_vinculos = self.db.execute(
            "SELECT COUNT(*) FROM vinculos WHERE modulo = ?", (modulo,)).fetchone()[0]

        # Custom tables (Z*, Q*)
        custom_tables = [t for t in tables if t[0] in "ZQ"]

        # Parametros custom
        param_custom = self.db.execute(
            "SELECT COUNT(*) FROM parametros WHERE custom = 1").fetchone()[0]

        lines = [
            f"## 1. Objetivo do Módulo no Cliente\n",
            f"**Módulo:** {modulo.upper()}",
            f"**Cliente:** {cliente}" if cliente else "",
            "",
            "### Resumo Quantitativo\n",
            "| Item | Padrão | Custom | Total |",
            "|------|--------|--------|-------|",
            f"| Campos | {total_campos - custom_campos:,} | {custom_campos:,} | {total_campos:,} |",
            f"| Índices | {total_indices - custom_indices:,} | {custom_indices:,} | {total_indices:,} |",
            f"| Gatilhos | {total_gatilhos - custom_gatilhos:,} | {custom_gatilhos:,} | {total_gatilhos:,} |",
            f"| Fontes custom | — | {total_fontes:,} | {total_fontes:,} |",
            f"| Pontos de Entrada | — | {total_pes:,} | {total_pes:,} |",
            f"| Parâmetros custom | — | {param_custom:,} | {param_custom:,} |",
            f"| Vínculos | — | {total_vinculos:,} | {total_vinculos:,} |",
        ]

        if custom_tables:
            lines.extend([
                "",
                "### Tabelas Custom (novas)\n",
                "| Tabela | Nome | Campos | Finalidade |",
                "|--------|------|--------|------------|",
            ])
            for t in custom_tables:
                nome = self.db.execute(
                    "SELECT nome FROM tabelas WHERE codigo = ?", (t,)).fetchone()
                n_campos = self.db.execute(
                    "SELECT COUNT(*) FROM campos WHERE tabela = ?", (t,)).fetchone()[0]
                lines.append(f"| `{t}` | {nome[0] if nome else ''} | {n_campos} | A verificar |")

        return "\n".join(lines) + "\n"

    def _gen_sec2_parametros(self, modulo: str) -> str:
        """Section 2: Custom parameters — pure SQL."""
        # NOTE: parametros table has no modulo column — returns all custom params for the client
        rows = self.db.execute(
            "SELECT variavel, tipo, descricao, conteudo FROM parametros WHERE custom = 1 ORDER BY variavel"
        ).fetchall()

        if not rows:
            return ""

        lines = [
            "## 2. Parametrização do Cliente\n",
            "| Parâmetro | Tipo | Descrição | Valor Cliente |",
            "|-----------|------|-----------|---------------|",
        ]
        for r in rows[:40]:
            var = r[0].strip()
            tipo = r[1] or ""
            desc = (r[2] or "")[:60]
            val = (r[3] or "")[:30]
            lines.append(f"| `{var}` | {tipo} | {desc} | `{val}` |")

        if len(rows) > 40:
            lines.append(f"\n> ... e mais {len(rows) - 40} parâmetros custom.")

        return "\n".join(lines) + "\n"

    def _gen_sec6_tipos(self, modulo: str) -> str:
        """Section 6: Custom SX5 tables and CBox values."""
        tables = self._get_module_tables(modulo)
        if not tables:
            return ""

        placeholders = ",".join(["?"] * len(tables))

        # CBox custom
        cbox_rows = self.db.execute(
            f"SELECT tabela, campo, titulo, cbox FROM campos WHERE tabela IN ({placeholders}) AND cbox != '' AND custom = 1 LIMIT 20",
            tuple(tables)).fetchall()

        if not cbox_rows:
            return ""

        lines = [
            "## 6. Tipos e Classificações Custom\n",
            "### CBox Customizados\n",
            "| Campo | Título | Valores |",
            "|-------|--------|---------|",
        ]
        for r in cbox_rows:
            lines.append(f"| `{r[0]}.{r[1]}` | {r[2]} | {r[3][:60]} |")

        return "\n".join(lines) + "\n"

    def _gen_sec7_tabelas(self, modulo: str) -> str:
        """Section 7: Module tables summary."""
        tables = self._get_module_tables(modulo)
        if not tables:
            return ""

        lines = [
            "## 7. Tabelas do Módulo\n",
            "| Tabela | Nome | Campos Custom | Índices Custom | Gatilhos Custom |",
            "|--------|------|---------------|----------------|-----------------|",
        ]

        # Pre-fetch all counts in batch
        placeholders = ",".join(["?"] * len(tables))
        params = tuple(tables)

        # Campos custom per table
        cc_rows = self.db.execute(
            f"SELECT tabela, COUNT(*) FROM campos WHERE tabela IN ({placeholders}) AND custom = 1 GROUP BY tabela",
            params).fetchall()
        cc_map = dict(cc_rows)

        # Indices custom per table
        ci_rows = self.db.execute(
            f"SELECT tabela, COUNT(*) FROM indices WHERE tabela IN ({placeholders}) AND custom = 1 GROUP BY tabela",
            params).fetchall()
        ci_map = dict(ci_rows)

        # Gatilhos custom per table prefix
        prefixes = [tab[1:] for tab in tables]
        like_conditions = " OR ".join(["campo_origem LIKE ?"] * len(prefixes))
        like_params = tuple(f"{p}_%" for p in prefixes)
        cg_rows = self.db.execute(
            f"SELECT SUBSTR(campo_origem, 1, 2), COUNT(*) FROM gatilhos WHERE ({like_conditions}) AND custom = 1 GROUP BY SUBSTR(campo_origem, 1, 2)",
            like_params).fetchall()
        cg_map = dict(cg_rows)

        # Table names
        nome_rows = self.db.execute(
            f"SELECT codigo, nome FROM tabelas WHERE codigo IN ({placeholders})",
            params).fetchall()
        nome_map = dict(nome_rows)

        for t in sorted(tables):
            cc = cc_map.get(t, 0)
            ci = ci_map.get(t, 0)
            prefix = t[1:]
            cg = cg_map.get(prefix, 0)
            nome = nome_map.get(t, "")

            if cc > 0 or ci > 0 or cg > 0 or t[0] in "ZQ":
                lines.append(f"| `{t}` | {nome} | {cc} | {ci} | {cg} |")

        return "\n".join(lines) + "\n"

    def _gen_sec16_vinculos(self, modulo: str) -> str:
        """Section 16: Vinculos map — pure SQL."""
        lines = ["## 16. Mapa de Vínculos\n"]

        # Campo → Funcao
        cv = self.db.execute(
            "SELECT origem, destino, contexto FROM vinculos WHERE tipo = 'campo_valida_funcao' AND modulo = ?",
            (modulo,)).fetchall()
        if cv:
            lines.extend([
                "### Campos → Funções (validação chama U_xxx)\n",
                "| Campo | Função | Tipo |",
                "|-------|--------|------|",
            ])
            for r in cv[:20]:
                lines.append(f"| `{r[0]}` | `U_{r[1]}()` | {r[2]} |")

        # Gatilho → Funcao
        gv = self.db.execute(
            "SELECT origem, destino FROM vinculos WHERE tipo = 'gatilho_executa_funcao' AND modulo = ?",
            (modulo,)).fetchall()
        if gv:
            lines.extend([
                "\n### Gatilhos → Funções\n",
                "| Gatilho | Função |",
                "|---------|--------|",
            ])
            for r in gv[:20]:
                lines.append(f"| `{r[0]}` | `U_{r[1]}()` |")

        # PE → Rotina
        pv = self.db.execute(
            "SELECT origem, destino, contexto FROM vinculos WHERE tipo = 'pe_afeta_rotina' AND modulo = ?",
            (modulo,)).fetchall()
        if pv:
            lines.extend([
                "\n### PEs → Rotinas\n",
                "| PE | Rotina | Fonte |",
                "|----|--------|-------|",
            ])
            for r in pv[:30]:
                lines.append(f"| `{r[0]}` | `{r[1]}` | {r[2]} |")

        # Fonte → Fonte
        fv = self.db.execute(
            "SELECT origem, destino FROM vinculos WHERE tipo = 'fonte_chama_funcao' AND modulo = ?",
            (modulo,)).fetchall()
        if fv:
            lines.extend([
                "\n### Fonte → Função (call graph)\n",
                "| Fonte | Chama |",
                "|-------|-------|",
            ])
            for r in fv[:30]:
                lines.append(f"| `{r[0]}` | `U_{r[1]}()` |")

        return "\n".join(lines) + "\n"

    # ── Stage 2: Cheap LLM — catalog ─────────────────────────────────────────

    async def _stage2_cheap_catalog(self, modulo: str, stage1: dict) -> dict:
        """Sections 3, 4 (data only), 9, 10, 11 — use gen_model (cheap)."""
        import asyncio

        # Build context from knowledge service
        context = self.ks.build_context_for_module(modulo)

        prompt = """Você é o Agente Catalogador. Organize os dados fornecidos nas seções abaixo.
REGRA: Documente APENAS o que existe nos dados. NÃO invente. NÃO analise. NÃO sugira.
Use monospace (backticks) para nomes técnicos. Tabelas markdown para dados tabulares.

Gere as seguintes seções em markdown:

## 3. Cadastros — Campos Customizados
Para cada tabela que tem campos custom, listar:
- Campos custom em tabela markdown: Campo | Título | Tipo | Tam | Obrig | F3 | VLDUSER
- Índices custom: Ordem | Chave | Descrição
- Gatilhos custom: Origem | Destino | Regra | Condição

## 4. Rotinas Customizadas
Para cada rotina que tem PEs ou fontes custom:
- Listar PEs com: PE | Fonte | Momento (baseado no nome do PE)
- Listar fontes que afetam esta rotina
- Listar campos custom das tabelas desta rotina
(NÃO gere fluxo Mermaid aqui — será gerado depois)

## 9. Integrações com Outros Módulos
Tabela: Módulo | Integração | Tabela Ponte | Direção
(baseado nos vínculos modulo_integra_modulo + integrações custom detectadas nos fontes)

## 10. Controles Especiais Custom
Se houver lógica especial detectada (aprovações, validações complexas, integrações externas)

## 11. Consultas e Relatórios Custom
Se houver fontes que parecem ser relatórios ou consultas

Retorne APENAS o markdown com as seções acima. Nada mais."""

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Módulo: {modulo}\n\n{self._truncate(context, 25000)}"},
        ]

        raw = await asyncio.to_thread(self.llm._call, messages, 0.2, True)
        return {"catalog_md": raw.strip()}

    # ── Stage 3: Cheap LLM — fonte analysis ──────────────────────────────────

    async def _stage3_cheap_fontes(self, modulo: str) -> dict:
        """Section 15: Analyze each fonte — use gen_model (cheap)."""
        import asyncio

        # Get fonte chunks for this module
        chunks = self.db.execute(
            "SELECT arquivo, funcao, content FROM fonte_chunks WHERE modulo = ? ORDER BY arquivo, funcao",
            (modulo,)).fetchall()

        if not chunks:
            return {"fontes_md": "## 15. Fontes Custom Detalhados\n\nNenhum fonte custom encontrado.\n"}

        # Group by arquivo
        fontes_grouped = {}
        for arquivo, funcao, content in chunks:
            if arquivo not in fontes_grouped:
                fontes_grouped[arquivo] = []
            fontes_grouped[arquivo].append({"funcao": funcao, "content": content[:2000]})

        # Get metadata for each fonte
        fonte_meta = {}
        for arquivo in fontes_grouped:
            row = self.db.execute(
                "SELECT funcoes, user_funcs, pontos_entrada, tabelas_ref, write_tables, calls_u, lines_of_code FROM fontes WHERE arquivo = ?",
                (arquivo,)).fetchone()
            if row:
                fonte_meta[arquivo] = {
                    "funcoes": json.loads(row[0]) if row[0] else [],
                    "user_funcs": json.loads(row[1]) if row[1] else [],
                    "pes": json.loads(row[2]) if row[2] else [],
                    "tabelas_ref": json.loads(row[3]) if row[3] else [],
                    "write_tables": json.loads(row[4]) if row[4] else [],
                    "calls_u": json.loads(row[5]) if row[5] else [],
                    "loc": row[6] or 0,
                }

        # Process in batches of 10 fontes to control context size
        all_results = []
        fonte_list = list(fontes_grouped.items())

        for batch_start in range(0, len(fonte_list), 10):
            batch = fonte_list[batch_start:batch_start + 10]

            context_parts = []
            for arquivo, funcs in batch:
                meta = fonte_meta.get(arquivo, {})
                context_parts.append(f"### {arquivo}")
                context_parts.append(f"LOC: {meta.get('loc', 0)}")
                context_parts.append(f"Funções: {', '.join(meta.get('funcoes', []))}")
                context_parts.append(f"PEs: {', '.join(meta.get('pes', []))}")
                context_parts.append(f"Tabelas lidas: {', '.join(meta.get('tabelas_ref', []))}")
                context_parts.append(f"Tabelas escritas: {', '.join(meta.get('write_tables', []))}")
                context_parts.append(f"Chama: {', '.join('U_' + c for c in meta.get('calls_u', []))}")
                context_parts.append("")
                for func in funcs[:5]:  # Max 5 functions per file
                    context_parts.append(f"#### Função: {func['funcao']}")
                    context_parts.append(f"```advpl\n{func['content'][:1500]}\n```\n")

            batch_context = "\n".join(context_parts)

            prompt = """Você é o Agente Analista de Fontes. Documente cada fonte customizado.
REGRA: Documente APENAS o que existe no código. NÃO invente. Seja técnico e preciso.

Para cada fonte, gere:
### 15.X [arquivo] — [breve descrição]
**LOC:** X | **Módulo:** X

#### Funções
| Função | Tipo | Descrição |
(User Function, Static Function, etc. + o que faz baseado no código)

#### Tabelas Acessadas
| Tabela | Modo | Campos Usados |
(Leitura ou Escrita, campos referenciados)

#### Chamadas
| Chama | Função | Contexto |
(outros fontes/funções chamadas)

Retorne APENAS markdown."""

            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"Fontes do módulo {modulo}:\n\n{self._truncate(batch_context, 20000)}"},
            ]

            raw = await asyncio.to_thread(self.llm._call, messages, 0.2, True)
            all_results.append(raw.strip())

        return {"fontes_md": "## 15. Fontes Custom Detalhados\n\n" + "\n\n".join(all_results)}

    # ── Stage 4: Strong LLM — synthesis ───────────────────────────────────────

    async def _stage4_strong_synthesis(self, modulo: str, stage1: dict, stage2: dict, stage3: dict) -> dict:
        """Sections 8, 17, 18, 19 + Mermaid flows for section 4.
        Uses chat_model (strong) for reasoning and diagram generation."""
        import asyncio

        # Build condensed context from previous stages
        context_parts = [
            "# Dados já catalogados\n",
            stage1.get("sec1", ""),
            stage1.get("sec7", ""),
            stage1.get("sec16", ""),
            "\n---\n",
            stage2.get("catalog_md", "")[:10000],
            "\n---\n",
            stage3.get("fontes_md", "")[:8000],
        ]

        # Add padrao context for comparison
        padrao_context = self._load_padrao_context(modulo)
        if padrao_context:
            context_parts.append(f"\n---\n## Base Padrão (referência)\n{padrao_context[:5000]}")

        context = "\n\n".join(context_parts)

        prompt = """Você é o Agente Sintetizador — analisa dados já catalogados e gera CONCLUSÕES.

REGRAS:
- Baseie-se EXCLUSIVAMENTE nos dados fornecidos. NÃO invente.
- Use Mermaid (flowchart TD) para TODOS os diagramas.
- Customizações em laranja: style NODE fill:#f47920,color:#fff
- Rotinas padrão em azul: style NODE fill:#00a1e0,color:#fff
- Conclusões em verde: style NODE fill:#28a745,color:#fff
- Rejeições em vermelho: style NODE fill:#dc3545,color:#fff
- Use subgraphs para agrupar etapas do processo.

Gere as seguintes seções:

## 8. Fluxo Geral do Módulo
Diagrama Mermaid (flowchart TD) mostrando o fluxo padrão + customizações integradas.
Use linhas tracejadas (-.->|nome|) para fluxos custom. Inclua subgraphs.

## 17. Grafo de Dependências
Diagrama Mermaid (graph LR) mostrando como os fontes custom se conectam entre si.
Subgraphs: Custom, PEs, Rotinas Padrão.

## 18. Comparativo Padrão × Cliente
Tabela markdown:
| Seção Padrão | Impacto | Detalhe |
Com indicadores: Alto (>10 customizações) | Médio (3-10) | Baixo (1-2)

## 19. Fluxo do Processo Customizado
Diagrama Mermaid COMPLETO (flowchart TD com subgraphs) do processo REAL do cliente.
Mostre cada etapa desde o início até o fim, com todas as customizações integradas.
Use subgraphs para agrupar por etapa (Solicitação, Cotação, Pedido, Entrada, etc).
Cada PE e fonte custom deve aparecer como nó em laranja conectado à rotina padrão.

## 4. Fluxos das Rotinas (complemento)
Para cada rotina que tem PEs ou fontes custom, gere um pequeno diagrama Mermaid
mostrando o fluxo da rotina com as customizações. Formato:
### 4.X Fluxo Custom — [ROTINA]
```mermaid
flowchart TD
...
```

Retorne APENAS markdown com as seções acima."""

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Módulo: {modulo}\n\n{self._truncate(context, 25000)}"},
        ]

        # Use chat_model (strong) — use_gen=False
        raw = await asyncio.to_thread(self.llm._call, messages, 0.3, False)
        return {"synthesis_md": raw.strip()}

    def _load_padrao_context(self, modulo: str) -> str:
        """Load relevant padrao markdown for comparison."""
        # Map module name to file
        module_map = {
            "compras": "SIGACOM_Fluxo_Compras.md",
            "faturamento": "SIGAFAT_Fluxo_Faturamento.md",
            "financeiro": "SIGAFIN_Fluxo_Financeiro.md",
            "estoque": "SIGAEST_Fluxo_Estoque_Custos.md",
            "fiscal": "SIGAFIS_Fluxo_Livros_Fiscais.md",
            "contabilidade": "SIGACTB_Fluxo_Contabilidade.md",
        }
        filename = module_map.get(modulo)
        if not filename:
            return ""
        filepath = self.padrao_dir / filename
        if not filepath.exists():
            return ""
        try:
            content = filepath.read_text(encoding="utf-8")
            # Extract sections 1, 4, 8 for comparison
            sections = []
            for section_start in ["## 1.", "## 4.", "## 8."]:
                idx = content.find(section_start)
                if idx >= 0:
                    end = content.find("\n## ", idx + len(section_start))
                    if end < 0:
                        end = idx + 2000
                    sections.append(content[idx:min(end, idx + 2000)])
            return "\n\n".join(sections)
        except Exception:
            return ""

    # ── Assemble final document ───────────────────────────────────────────────

    def _assemble(self, modulo: str, cliente: str, stage1: dict, stage2: dict, stage3: dict, stage4: dict) -> dict:
        """Combine all stages into final humano + ia documents."""
        synthesis = stage4.get("synthesis_md", "")

        # Extract section 8 and 17-19 from synthesis
        sec8 = self._extract_section(synthesis, "## 8.")
        sec17 = self._extract_section(synthesis, "## 17.")
        sec18 = self._extract_section(synthesis, "## 18.")
        sec19 = self._extract_section(synthesis, "## 19.")
        sec4_flows = self._extract_section(synthesis, "## 4.")

        # Build humano document
        humano_parts = [
            f"# {modulo.upper()} — Customizações {cliente}\n",
            stage1.get("sec1", ""),
            stage1.get("sec2", ""),
            stage2.get("catalog_md", ""),  # Contains sections 3, 4, 9, 10, 11
            sec4_flows,  # Mermaid flows for section 4
            stage1.get("sec5", ""),
            stage1.get("sec6", ""),
            stage1.get("sec7", ""),
            sec8,  # Fluxo geral
            "## 12. Obrigações Acessórias\n\n> Consultar Base Padrão para referência.\n",
            f"## 13. Referências\n\n| Fonte | Descrição |\n|-------|-----------|\n| Base Padrão {modulo.upper()} | Seções 1-14 do processo padrão |\n| SQLite | extrairpo.db — tabela vinculos |\n",
            "## 14. Enriquecimentos\n\n(seção reservada para informações adicionadas posteriormente)\n",
            stage3.get("fontes_md", ""),  # Section 15
            stage1.get("sec16", ""),  # Section 16
            sec17,  # Grafo dependencias
            sec18,  # Comparativo
            sec19,  # Fluxo customizado
        ]

        humano = "\n\n---\n\n".join([p for p in humano_parts if p.strip()])

        # Build ia document (same content + YAML frontmatter)
        tables = self._get_module_tables(modulo)
        custom_tables = [t for t in tables if t[0] in "ZQ"]

        # Count PEs
        total_pes = 0
        rows = self.db.execute("SELECT pontos_entrada FROM fontes WHERE modulo = ?", (modulo,)).fetchall()
        for r in rows:
            pes = json.loads(r[0]) if r[0] else []
            total_pes += len(pes)

        frontmatter = f"""---
tipo: cliente
cliente: "{cliente}"
modulo: {modulo}
nome: {modulo.capitalize()}
gerado_em: "{self._now()}"
tabelas_envolvidas: {json.dumps(sorted(tables))}
tabelas_custom: {json.dumps(sorted(custom_tables))}
total_fontes_custom: {self.db.execute("SELECT COUNT(*) FROM fontes WHERE modulo = ?", (modulo,)).fetchone()[0]}
total_pontos_entrada: {total_pes}
---
"""
        ia = frontmatter + "\n" + humano

        return {"humano": humano, "ia": ia}

    def _extract_section(self, text: str, header: str) -> str:
        """Extract a section from markdown by header prefix."""
        idx = text.find(header)
        if idx < 0:
            return ""
        end = text.find("\n## ", idx + len(header))
        if end < 0:
            return text[idx:]
        return text[idx:end]

    def _now(self) -> str:
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d")

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _truncate(text: str, max_chars: int) -> str:
        """Truncate text at a newline boundary to avoid cutting mid-word."""
        if len(text) <= max_chars:
            return text
        cut = text[:max_chars]
        last_nl = cut.rfind('\n')
        if last_nl > max_chars * 0.8:
            return cut[:last_nl]
        return cut

    def _get_module_tables(self, modulo: str) -> list[str]:
        """Get all tables for a module from mapa + fontes."""
        tables = set()

        # From mapa-modulos.json (cached in __init__)
        info = self._mapa.get(modulo, {})
        if info:
            for t in info.get("tabelas", []):
                tables.add(t.upper())

        # From fontes tabelas_ref
        rows = self.db.execute(
            "SELECT tabelas_ref, write_tables FROM fontes WHERE modulo = ?", (modulo,)).fetchall()
        for r in rows:
            for t in json.loads(r[0]) if r[0] else []:
                tables.add(t.upper())
            for t in json.loads(r[1]) if r[1] else []:
                tables.add(t.upper())

        # From vinculos
        for r in self.db.execute(
                "SELECT DISTINCT destino FROM vinculos WHERE tipo IN ('fonte_le_tabela','fonte_escreve_tabela') AND modulo = ?",
                (modulo,)).fetchall():
            tables.add(r[0].upper())

        return sorted(tables)
