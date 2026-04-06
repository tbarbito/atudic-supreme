"""AnalistaPipeline — Clean orchestration of the Analista chat pipeline.

Replaces the 1100-line event_generator() closure in analista.py with a
structured, testable class. Maintains exact SSE event compatibility.

Flow: classify → resolve → plan → investigate → verify → stream → save
"""
import re
import json
import asyncio
import threading
import queue as _queue_mod
from typing import AsyncGenerator, Optional
from pathlib import Path

from app.services.workspace.analista_prompts import get_system_prompt
from app.services.workspace.context_window import ContextWindowManager


class AnalistaPipeline:
    """Orchestrates the full Analista chat pipeline."""

    def __init__(
        self,
        llm,
        db_factory,  # callable returning a new DB connection (_get_db)
        modo: str,
        conversa_id: int,
        hist_rows: list,
        artefatos_text: str,
    ):
        self.llm = llm
        self._get_db = db_factory
        self.modo = modo
        self.conversa_id = conversa_id
        self.hist_rows = hist_rows
        self.artefatos_text = artefatos_text

        # State accumulated during pipeline
        self.tabelas: list[str] = []
        self.modulos: list[str] = []
        self.campos_msg: list[str] = []
        self.campos_msg_original: list[str] = []
        self.tool_results_parts: list[str] = []
        self.usou_clarificacao = False
        self.usou_investigacao_dirigida = False
        self._clarificacao_blocos: list[dict] = []
        self.classification: dict = {}
        self.verified_draft = ""

        # Steering queue — set by router to allow user mid-flight corrections
        self._steering_queue = None  # type: Optional[asyncio.Queue]

        # Artifact registry — collects typed artifacts from tools
        from app.services.workspace.artifact_registry import ArtifactRegistry
        self.artifact_registry = ArtifactRegistry()

        # Cost tracker — per-conversation cost tracking
        from app.services.workspace.cost_tracker import CostTracker
        self.cost_tracker = CostTracker(conversa_id=conversa_id, modo=modo)

        # Session memory — persists discoveries between conversations
        from app.services.workspace.session_memory import SessionMemory
        try:
            from app.services.workspace.config import load_config, get_client_workspace
            config = load_config(Path("config.json"))
            client_dir = get_client_workspace(Path("workspace"), config.active_client)
            self.memory = SessionMemory(client_dir)
        except Exception:
            self.memory = None

    async def run(self, message: str) -> AsyncGenerator[dict, None]:
        """Full pipeline — yields SSE-compatible events.

        Events:
            {"event": "status", "data": {"step": "..."}}
            {"event": "token", "data": {"content": "..."}}
            {"event": "artefatos", "data": [...]}
            {"event": "done", "data": "{}"}
        """
        # ── Check follow-up from clarification ────────────────────────────
        followup_result = await self._check_followup(message)
        if followup_result is not None:
            async for event in followup_result:
                yield event
            return

        # ── Step 1: Classify ──────────────────────────────────────────────
        yield self._status("Classificando sua pergunta...")
        await self._classify(message)

        # ── Step 1b: Load relevant memories from previous sessions ──────
        if self.memory:
            memories = self.memory.load_relevant(message)
            if memories:
                self.tool_results_parts.insert(0, memories)

        # ── Step 2: Query Decomposer (padrao + client cross-reference) ──
        yield self._status("Investigando padrão e customizações...")
        await self._run_decomposer(message)

        # ── Step 2b: Resolve context (semantic + V1) ──────────────────────
        await self._resolve_semantic(message)
        if not self.usou_clarificacao:
            await self._resolve_v1(message)

        # Inject cached detected processes
        await self._inject_processes()

        # ── Step 2c: Sufficiency check (skip heavy investigation for simple questions) ──
        _context_sufficient = self._is_context_sufficient(message)
        if _context_sufficient:
            print(f"[AnalistaPipeline] Sufficiency check PASSED — skipping steps 3-5 for: {message[:80]}")
            yield self._status("Contexto suficiente, preparando resposta...")
        else:
            # ── Step 3: Ambiguity detection ───────────────────────────────────
            if not self.usou_clarificacao:
                yield self._status("Verificando ambiguidade...")
                await self._check_ambiguity(message)

            # ── Step 4: Directed investigation (nao_salva pattern) ────────────
            if not self.usou_clarificacao:
                async for event in self._directed_investigation(message):
                    yield event

            # ── Step 5: Plan + Investigate (always runs if we have tables) ─────
            if self.tabelas and not self.usou_clarificacao:
                async for event in self._plan_and_investigate(message):
                    yield event

        # ── Step 6: Build context + Verify ────────────────────────────────
        # Separate resumos from investigation data
        self._resumo_parts = [p for p in self.tool_results_parts if p.startswith("FUNCAO RELEVANTE") or p.startswith("FONTE RELEVANTE")]
        other_parts = [p for p in self.tool_results_parts if p not in self._resumo_parts]

        # Context = ONLY investigation data (no resumos - they go in dedicated section)
        tool_results_text = "\n".join(other_parts) or "Contexto carregado."
        context = tool_results_text[:20000]

        yield self._status("Analisando e preparando resposta...")

        if not self.usou_clarificacao:
            await self._verify(context, message)

        # ── Step 7: Build system prompt ───────────────────────────────────
        system = self._build_system_prompt(context, tool_results_text)
        messages = self._build_messages(system)

        # ── Step 8: Stream response ───────────────────────────────────────
        yield self._status("")

        full_response = ""
        if self.verified_draft and not self.usou_clarificacao and self.modo == "ajuste":
            # Stream pre-verified response — ONLY for ajuste mode
            # In melhoria/duvida, the main model with full system prompt
            # produces better responses than the cheap gen model draft
            async for event in self._stream_verified(self.verified_draft):
                yield event
                if event.get("event") == "token":
                    full_response += json.loads(event["data"]).get("content", "")
        else:
            # Stream from main LLM with rich system prompt
            async for event in self._stream_llm(messages):
                yield event
                if event.get("event") == "token":
                    full_response += json.loads(event["data"]).get("content", "")

        # ── Step 8b: Append technical detail lists (not LLM-generated) ────
        technical_appendix = self._build_technical_appendix()
        if technical_appendix:
            # Stream the appendix as additional tokens
            for chunk in [technical_appendix[i:i+200] for i in range(0, len(technical_appendix), 200)]:
                yield {"event": "token", "data": json.dumps({"content": chunk})}
                full_response += chunk

        # ── Step 9: Save + artifacts ──────────────────────────────────────
        artefatos_novos = self._parse_artifacts(full_response)
        chat_text = full_response
        if artefatos_novos and "###ARTEFATOS###" in full_response:
            chat_text = full_response.split("###ARTEFATOS###", 1)[0].strip()

        await self._save_response(chat_text, artefatos_novos)

        if artefatos_novos:
            yield {"event": "artefatos", "data": json.dumps(artefatos_novos)}

        # Send technical artifacts from tool investigation
        if self.artifact_registry.count() > 0:
            yield {
                "event": "technical_sections",
                "data": json.dumps(self.artifact_registry.to_sse_payload(), ensure_ascii=False),
            }

        # ── Step 10: Auto-save discoveries for future sessions ──────────
        if self.memory and self.artifact_registry.count() > 0:
            self._save_session_discoveries(message)

        # ── Step 11: Record cost tracking ────────────────────────────────
        try:
            summary = self.cost_tracker.get_summary()
            from app.services.workspace.cost_tracker import AggregateTracker
            agg = AggregateTracker()
            agg.record_conversation(summary)
        except Exception:
            pass

        yield {"event": "done", "data": "{}"}

    # ── Internal pipeline steps ───────────────────────────────────────────────

    def _save_session_discoveries(self, message: str):
        """Auto-save key discoveries from this conversation."""
        try:
            by_type = self.artifact_registry.by_type()

            # Build a summary of what was discovered
            parts = []
            for tipo, items in by_type.items():
                if items:
                    names = [i.get("preview", i.get("arquivo", i.get("nome", "?")))[:60] for i in items[:5]]
                    parts.append(f"{tipo}: {len(items)} ({', '.join(names)})")

            if not parts:
                return

            # Create topic from the question
            topic_words = message[:80].replace("?", "").strip()
            tags = list(self.tabelas[:5]) + list(self.campos_msg[:5])

            content = f"Pergunta: {message[:200]}\n\nDescoberto:\n" + "\n".join(f"- {p}" for p in parts)

            self.memory.save_discovery(
                topic=topic_words,
                content=content,
                tags=tags,
                source=f"conversa:{self.conversa_id}",
                conversa_id=self.conversa_id,
            )
        except Exception as e:
            print(f"[pipeline] memory save error: {e}")

        # Auto-extract learnable patterns
        try:
            from app.services.workspace.memory_extractor import MemoryExtractor
            from app.services.workspace.config import load_config, get_client_workspace
            config = load_config(Path("config.json"))
            client_dir = get_client_workspace(Path("workspace"), config.active_client)

            extractor = MemoryExtractor(client_dir)
            from app.services.workspace.investigation_planner import _detect_action_type
            action_type = _detect_action_type(message)

            tools_used = list(set(
                a.get("tipo_problema", a.get("tipo", ""))
                for a in self.artifact_registry.all()
            ))

            extracted = extractor.extract_from_investigation(
                message=message,
                modo=self.modo,
                action_type=action_type,
                tools_used=tools_used,
                artifacts_by_type=self.artifact_registry.by_type(),
                context_text=" ".join(self.tool_results_parts[:5]),
                conversa_id=self.conversa_id,
            )
            if extracted:
                print(f"[pipeline] extracted {len(extracted)} patterns from conversation")
        except Exception as e:
            print(f"[pipeline] memory extraction error: {e}")

    def _is_context_sufficient(self, message: str) -> bool:
        """Check if we have enough context to answer without full investigation.

        Returns True for simple 'duvida' questions where decomposer already
        provided sufficient context (e.g., "o que é o campo X?", "como funciona Y?").
        Conservative — better to investigate too much than too little.
        """
        # Only for understanding mode
        if self.modo != "duvida":
            return False

        # Must have some context from decomposer
        if not self.tool_results_parts:
            return False

        # Don't skip if clarification was used (ambiguity path)
        if self.usou_clarificacao:
            return False

        # ── FAST SUFFICIENT: trigger analysis already has everything ──
        # When decomposer did deep trigger analysis (step3c), skip investigation
        total_context = sum(len(p) for p in self.tool_results_parts)
        has_deep_analysis = any(
            "ANÁLISE DE IMPACTO: GATILHO" in p or "ANÁLISE DE IMPACTO: TORNAR" in p
            for p in self.tool_results_parts
        )
        if has_deep_analysis and total_context > 500:
            return True

        # Must have at least one table identified
        if not self.tabelas:
            return False

        # Don't skip for complex questions
        msg_lower = message.lower()
        complex_keywords = [
            "erro", "não grava", "nao grava", "obrigatório", "obrigatorio",
            "aumentar", "aumento", "criar", "alterar", "processo completo",
            "todos os", "listar todos", "impacto", "quem grava",
            "por que", "causa", "debug", "problema",
            "parametro", "mv_", "mgf_", "ti_", "sy_", "xg_", "tx_", "mf_", "pt_",
            "supergetmv", "getmv", "putmv", "getnewpar",
            "ponto de entrada", "pontos de entrada",
            "pe ", "implementou", "implementado", "customiz",
        ]
        if any(kw in msg_lower for kw in complex_keywords):
            return False

        # Context must have meaningful content (not just "Contexto carregado.")
        if total_context < 200:
            return False

        return True

    async def _classify(self, message: str):
        """Classify the message to extract entities."""
        try:
            self.classification = await asyncio.to_thread(self.llm.classify, message)
            self.tabelas = self.classification.get("tabelas", [])
            self.modulos = self.classification.get("modulos", [])
        except Exception as e:
            err_str = str(e).lower()
            if "overload" in err_str or "529" in err_str:
                for retry in range(3):
                    wait = 10 * (retry + 1)
                    await asyncio.sleep(wait)
                    try:
                        self.classification = await asyncio.to_thread(self.llm.classify, message)
                        self.tabelas = self.classification.get("tabelas", [])
                        self.modulos = self.classification.get("modulos", [])
                        break
                    except Exception:
                        if retry == 2:
                            self.tabelas = []
                            self.modulos = []
            else:
                self.tabelas = []
                self.modulos = []

            # Fallback: regex extraction
            if not self.tabelas:
                from app.services.workspace.analista_orchestrator import extract_entities_from_text
                ent = extract_entities_from_text(message)
                self.tabelas = ent.get("tabelas", [])
                self.modulos = ent.get("modulos", [])

        self.campos_msg = re.findall(r'\b([A-Z][A-Z0-9]{1,2}_\w+)\b', message.upper())
        self.campos_msg_original = list(self.campos_msg)

        # Infer table from field prefix when classify missed it
        # e.g. B1_COD -> SB1, C5_NUM -> SC5, E2_VALOR -> SE2
        if not self.tabelas and self.campos_msg:
            inferred = set()
            for campo in self.campos_msg:
                prefix = campo[:2]  # e.g. "B1", "C5", "E2"
                table = "S" + prefix  # e.g. "SB1", "SC5", "SE2"
                if re.match(r'^S[A-Z][A-Z0-9]$', table):
                    inferred.add(table)
            if inferred:
                self.tabelas = list(inferred)
                print(f"[pipeline] inferred tables from fields: {self.tabelas}")

    async def _run_decomposer(self, message: str):
        """Run the query decomposer pipeline (padrao + client cross-reference)."""
        try:
            from app.services.workspace.query_decomposer import decompose_and_investigate
            decomposer_result = await asyncio.wait_for(
                asyncio.to_thread(decompose_and_investigate, message, self.llm),
                timeout=30,
            )
            if decomposer_result and len(decomposer_result) > 50:
                # Insert at the beginning — this is the most important context
                self.tool_results_parts.insert(0, decomposer_result)
        except asyncio.TimeoutError:
            print(f"[pipeline] decomposer TIMEOUT (30s) for: {message[:80]}")
        except Exception as e:
            print(f"[pipeline] decomposer error: {e}")
            import traceback
            traceback.print_exc()

    async def _resolve_semantic(self, message: str):
        """V2: Semantic resolution via menus, propósitos, processos."""
        if self.campos_msg:
            return  # Skip semantic when user provided explicit fields

        try:
            from app.services.workspace.analista_tools import resolver_semantico
            sem_result = await asyncio.to_thread(resolver_semantico, message)
            if not sem_result.get("resolvido") or not sem_result.get("candidatos"):
                return

            candidatos = sem_result["candidatos"]
            top = candidatos[0]
            strong = [c for c in candidatos if c["confianca"] >= 0.6]
            top_conf = top["confianca"]

            if top_conf >= 0.8 and (len(strong) <= 2 or (len(strong) > 2 and strong[0]["confianca"] - strong[1]["confianca"] >= 0.15)):
                # Clear winner
                if not self.tabelas:
                    self.tabelas = [top["tabela"]]
                if top.get("rotinas"):
                    self.tool_results_parts.append(f"ROTINA IDENTIFICADA: {', '.join(top['rotinas'][:3])}")
                self.tool_results_parts.append(f"CONTEXTO: {top['descricao'][:150]}")

            elif len(strong) >= 2:
                # Multiple candidates — trigger clarification
                seen_tabs = set()
                opcoes = []
                for c in strong[:6]:
                    if c["tabela"] in seen_tabs:
                        continue
                    seen_tabs.add(c["tabela"])
                    rotinas_str = ", ".join(c.get("rotinas", [])[:2]) if c.get("rotinas") else ""
                    desc = c.get("descricao", "")[:100]
                    opcoes.append(f"- **{c['tabela']}** ({rotinas_str}): {desc}")

                if len(opcoes) >= 2:
                    clarification = "CANDIDATOS ENCONTRADOS NO AMBIENTE:\n" + "\n".join(opcoes)
                    clarification += "\n\nApresente essas opcoes ao usuario de forma clara e pergunte qual se aplica."
                    self.tool_results_parts.append(clarification)
                    if not self.tabelas:
                        self.tabelas = [c["tabela"] for c in strong[:3]]
                    self._clarificacao_blocos = [
                        {"nome": c.get("descricao", c["tabela"])[:100],
                         "campos": c.get("campos_relevantes", [])[:5],
                         "fontes": c.get("rotinas", [])[:5],
                         "tabela": c["tabela"],
                         "descricao": c.get("descricao", "")[:100]}
                        for c in strong[:6]
                        if c["tabela"] not in [x.get("tabela") for x in self._clarificacao_blocos]
                    ]
                    self.usou_clarificacao = True
                else:
                    if not self.tabelas:
                        self.tabelas = [top["tabela"]]
            else:
                # Weak — add as context
                for c in candidatos[:3]:
                    self.tool_results_parts.append(
                        f"CANDIDATO SEMANTICO: {c['tabela']} (confianca {c['confianca']}) — {c.get('descricao','')[:100]}"
                    )
                if top_conf >= 0.5 and not self.tabelas:
                    self.tabelas = [top["tabela"]]

        except Exception as e:
            print(f"[pipeline] semantic resolver error: {e}")

    async def _search_resumos(self, message: str):
        """Search resumo_auto + resumo LLM + propositos for relevant fontes.

        Uses synonym expansion to bridge business vocabulary → technical terms.
        """
        # Synonym map: business terms → technical terms in resumo_auto
        _SYNONYMS = {
            "bloquear": ["bloq", "bloqueia", "return .f"],
            "bloqueio": ["bloq", "bloqueia", "return .f"],
            "adiantamento": ["adiant", "e2_tipo", "PA", "titulo"],
            "fornecedor": ["fornec", "sa2", "se2", "pagar"],
            "financeiro": ["fina050", "fina", "se2", "pagar", "titulo"],
            "compras": ["compra", "mata121", "mata120", "sc7", "pedido"],
            "excluir": ["exclu", "delet", "exclus"],
            "exclusão": ["exclu", "delet", "exclus"],
            "incluir": ["inclu", "inclusão"],
            "alterar": ["alter", "alteração"],
            "aprovar": ["aprov", "aprovação", "alcada", "alçada"],
            "pedido": ["pedido", "sc7", "mata121", "mata120", "compra"],
            "produto": ["produto", "sb1", "b1_cod"],
            "cliente": ["cliente", "sa1", "receber"],
            "nota": ["nota", "sf1", "sd1", "entrada", "fiscal"],
            "título": ["titulo", "se1", "se2", "pagar", "receber"],
            "estoque": ["estoq", "sb1", "sb2", "saldo"],
        }

        try:
            db = self.db_factory()
            words = [w for w in message.lower().split() if len(w) > 3]
            if not words:
                db.close()
                return

            # Expand words with synonyms
            expanded = set(words)
            for w in words:
                for key, syns in _SYNONYMS.items():
                    if w.startswith(key[:4]) or key.startswith(w[:4]):
                        expanded.update(syns)
            search_terms = list(expanded)

            found_arquivos = set()

            # Strategy 1: Score-based search on resumo_auto
            # Generate multiple 2-word combos from expanded terms and find best matches
            scored = {}  # key -> (arquivo, funcao, resumo_auto, resumo, score)
            combos_tried = set()
            for w1 in search_terms:
                for w2 in search_terms:
                    if w1 == w2:
                        continue
                    combo_key = tuple(sorted([w1, w2]))
                    if combo_key in combos_tried:
                        continue
                    combos_tried.add(combo_key)
                    try:
                        rows = db.execute(
                            "SELECT arquivo, funcao, resumo_auto, resumo FROM funcao_docs "
                            "WHERE LOWER(resumo_auto) LIKE ? AND LOWER(resumo_auto) LIKE ? LIMIT 5",
                            (f"%{w1}%", f"%{w2}%")
                        ).fetchall()
                        for rr in rows:
                            key = f"{rr[0]}::{rr[1]}"
                            # Score: count how many search terms match
                            ra_lower = (rr[2] or "").lower()
                            score = sum(1 for t in search_terms if t.lower() in ra_lower)
                            if key not in scored or score > scored[key][4]:
                                scored[key] = (rr[0], rr[1], rr[2], rr[3], score)
                    except Exception:
                        pass

            # Sort by score, take top results and enrich with code evidence
            top = sorted(scored.values(), key=lambda x: -x[4])[:10]
            for rr in top:
                key = f"{rr[0]}::{rr[1]}"
                found_arquivos.add(key)
                resumo = rr[3] if rr[3] else rr[2]

                # Fetch key code lines (Help messages, Return .F., conditions)
                evidence = ""
                try:
                    chunk = db.execute(
                        "SELECT content FROM fonte_chunks WHERE arquivo=? AND funcao=?",
                        (rr[0], rr[1])
                    ).fetchone()
                    if chunk and chunk[0]:
                        code = chunk[0]
                        key_lines = []
                        for line in code.split("\n"):
                            ls = line.strip()
                            ll = ls.lower()
                            if any(k in ll for k in ["help(", "fwalert", "msgalert", "msgstop",
                                                      "return .f", "lret := .f", "_lret := .f",
                                                      "supergetmv", "funname()", "e2_tipo",
                                                      "e2_xstapro", "bloq", "exclu"]):
                                if len(ls) > 10:
                                    key_lines.append(ls[:160])
                        if key_lines:
                            evidence = "\n  CÓDIGO: " + " | ".join(key_lines[:6])
                except Exception:
                    pass

                self.tool_results_parts.insert(0,
                    f"FUNCAO RELEVANTE: {rr[0]}::{rr[1]} — {resumo}{evidence}"
                )

            # Strategy 2: Search proposito_auto + proposito
            try:
                for n in [3, 2]:
                    if n > len(search_terms):
                        continue
                    for combo in [search_terms[i:i+n] for i in range(min(len(search_terms)-n+1, 5))]:
                        conditions = " AND ".join(["LOWER(COALESCE(proposito_auto, proposito, '')) LIKE ?"] * len(combo))
                        params = tuple(f"%{w}%" for w in combo)
                        prop_rows = db.execute(
                            f"SELECT chave, substr(COALESCE(proposito, proposito_auto), 1, 800) FROM propositos WHERE {conditions} LIMIT 3",
                            params
                        ).fetchall()
                        for pr in prop_rows:
                            if pr[0] not in [k.split("::")[0] for k in found_arquivos]:
                                self.tool_results_parts.insert(0, f"FONTE RELEVANTE: {pr[0]}\n{pr[1]}")
            except Exception:
                pass

            # Strategy 3: LLM resumos (hand-crafted, highest quality)
            try:
                for n in [min(len(words), 3), 2]:
                    if n < 2:
                        break
                    conditions = " AND ".join(["LOWER(resumo) LIKE ?"] * n)
                    params = tuple(f"%{w}%" for w in words[:n])
                    rows = db.execute(
                        f"SELECT arquivo, funcao, resumo FROM funcao_docs WHERE resumo IS NOT NULL AND resumo != '' AND {conditions} LIMIT 5",
                        params
                    ).fetchall()
                    for rr in rows:
                        key = f"{rr[0]}::{rr[1]}"
                        if key not in found_arquivos:
                            found_arquivos.add(key)
                            self.tool_results_parts.insert(0, f"FUNCAO RELEVANTE (detalhado): {rr[0]}::{rr[1]} — {rr[2]}")
                    if rows:
                        break
            except Exception:
                pass

            db.close()
        except Exception as e:
            print(f"[pipeline] search_resumos error: {e}")

    async def _resolve_v1(self, message: str):
        """V1: Context resolution via tool_resolver_contexto."""
        if self.campos_msg:
            return

        try:
            from app.services.workspace.analista_tools import tool_resolver_contexto
            ctx = await asyncio.to_thread(tool_resolver_contexto, message)
            if not ctx.get("contexto_resolvido"):
                return

            # Cross-matched fields
            cross_campos = [c for c in ctx.get("campos_encontrados", []) if c.get("_cross")]
            if cross_campos:
                cross_tabelas = list(set(c["tabela"] for c in cross_campos))
                self.tabelas = cross_tabelas
                for c in cross_campos:
                    campo_upper = c["campo"].upper()
                    if campo_upper not in self.campos_msg:
                        self.campos_msg.insert(0, campo_upper)
            else:
                resolved_tabs = [t["codigo"] for t in ctx.get("tabelas_encontradas", []) if t.get("codigo")]
                if resolved_tabs:
                    self.tabelas = resolved_tabs[:4]
                else:
                    for t in ctx.get("tabelas_encontradas", []):
                        if t["codigo"] not in self.tabelas:
                            self.tabelas.append(t["codigo"])

            for c in ctx.get("campos_encontrados", []):
                campo_upper = c["campo"].upper()
                if campo_upper not in self.campos_msg:
                    self.campos_msg.append(campo_upper)

            # Context info for LLM
            if ctx.get("action_type"):
                self.tool_results_parts.append(f"TIPO DE PROBLEMA: {ctx['action_type']}")
            if ctx.get("context_type"):
                self.tool_results_parts.append(f"CONTEXTO: {ctx['context_type']}")
            if ctx.get("rotinas_encontradas"):
                rot_list = ", ".join(
                    f"{r['rotina']} ({r['nome']}" + (f" - {r['modulo']}" if r.get('modulo') else "") + ")"
                    for r in ctx["rotinas_encontradas"][:3]
                )
                self.tool_results_parts.append(f"ROTINA/MENU IDENTIFICADO: {rot_list}")
            if ctx.get("tabelas_encontradas"):
                tab_list = ", ".join(f"{t['codigo']} ({t['nome']})" for t in ctx["tabelas_encontradas"][:5])
                self.tool_results_parts.append(f"TABELAS RELACIONADAS: {tab_list}")
            if ctx.get("campos_encontrados"):
                cross = [c for c in ctx["campos_encontrados"] if c.get("_cross")]
                if cross:
                    campo_list = ", ".join(f"{c['campo']} ({c.get('titulo','')})" for c in cross[:3])
                    self.tool_results_parts.append(f"CAMPO IDENTIFICADO (alta confianca): {campo_list}")
                else:
                    campo_list = ", ".join(f"{c['campo']} ({c.get('titulo','')})" for c in ctx["campos_encontrados"][:5])
                    self.tool_results_parts.append(f"Campos possiveis: {campo_list}")

            extra = ctx.get("info_extra", {})
            if extra.get("pes_disponiveis"):
                pe_list = ", ".join(f"{p['nome']} ({p['objetivo'][:40]})" for p in extra["pes_disponiveis"][:5])
                self.tool_results_parts.append(f"PEs DISPONIVEIS na rotina: {pe_list}")
            if extra.get("pes_implementados"):
                impl_list = ", ".join(
                    f"{p['arquivo']} (PEs: {', '.join(p['pes'][:3])})" for p in extra["pes_implementados"][:3]
                )
                self.tool_results_parts.append(f"PEs IMPLEMENTADOS no cliente: {impl_list}")
            if extra.get("jobs"):
                job_list = ", ".join(f"{j['rotina']} ({j['arquivo']})" for j in extra["jobs"][:3])
                self.tool_results_parts.append(f"JOBS encontrados: {job_list}")
            if extra.get("gatilhos"):
                gat_list = ", ".join(
                    f"{g['origem']}→{g['destino']} ({g.get('regra','')[:30]})" for g in extra["gatilhos"][:3]
                )
                self.tool_results_parts.append(f"GATILHOS encontrados: {gat_list}")

        except Exception as e:
            print(f"[pipeline] V1 resolver error: {e}")

    async def _inject_processes(self):
        """Inject cached detected processes for identified tables."""
        if not self.tabelas:
            return
        try:
            from app.services.workspace.analista_tools import tool_processos_cliente
            proc_result = await asyncio.to_thread(tool_processos_cliente, self.tabelas)
            if proc_result.get("processos"):
                proc_lines = ["=== PROCESSOS DO CLIENTE NESTAS TABELAS ==="]
                for p in proc_result["processos"][:5]:
                    tabs_str = ", ".join(p["tabelas"][:4])
                    proc_lines.append(
                        f"- {p['nome']} ({p['tipo']}, {p['criticidade']}) "
                        f"[tabelas: {tabs_str}]: {p['descricao']}"
                    )
                self.tool_results_parts.insert(0, "\n".join(proc_lines))
        except Exception:
            pass

    async def _check_ambiguity(self, message: str):
        """Check if the question is ambiguous and needs clarification."""
        if not self.tabelas:
            return
        try:
            from app.services.workspace.clarificacao import avaliar_ambiguidade
            msg_lower = message.lower()
            amb_db = self._get_db()
            amb_keywords = re.findall(r'\b([a-zA-Z_]{3,})\b', msg_lower)
            amb_result = avaliar_ambiguidade(amb_db, self.tabelas, amb_keywords, self.campos_msg_original)
            amb_db.close()

            if amb_result["ambiguo"] and amb_result.get("sugestao_pergunta"):
                self.tool_results_parts.append(amb_result["sugestao_pergunta"])
                self.usou_clarificacao = True
                self._clarificacao_blocos = amb_result["blocos"]
        except Exception as e:
            print(f"[pipeline] ambiguity error: {e}")

    async def _directed_investigation(self, message: str) -> AsyncGenerator[dict, None]:
        """Detect 'field doesn't save' patterns and investigate directly."""
        NAO_SALVA_KEYWORDS = [
            "nao salva", "não salva", "nao grava", "não grava",
            "nao atualiza", "não atualiza", "nao persiste", "não persiste",
            "perde valor", "perde o valor", "nao altera", "não altera",
            "some o valor", "valor nao fica", "valor não fica",
        ]
        msg_lower = message.lower()
        if self.usou_clarificacao:
            return
        if not any(kw in msg_lower for kw in NAO_SALVA_KEYWORDS):
            return
        if not self.tabelas or not self.campos_msg:
            return

        # Prefer cross-matched campo (from resolver) over classify guess
        # campos_msg_original = fields user typed explicitly (XX_YYYY)
        # campos_msg = enriched by resolver (may include cross-matches)
        tab_alvo = self.tabelas[0]
        campo_alvo = ""
        if self.campos_msg:
            # If resolver added campos (more than original), prefer the first added one
            if len(self.campos_msg) > len(self.campos_msg_original) and self.campos_msg[0] not in self.campos_msg_original:
                campo_alvo = self.campos_msg[0]  # Cross-matched field (high confidence)
            else:
                campo_alvo = self.campos_msg[0]
        if not (campo_alvo or tab_alvo):
            return

        yield self._status(f"Investigação dirigida: {campo_alvo or tab_alvo}...")
        try:
            from app.services.workspace.analista_tools import investigar_problema
            inv_result = await asyncio.to_thread(investigar_problema, tab_alvo, campo_alvo, "nao_salva")
            if inv_result.get("contexto_llm"):
                self.tool_results_parts.append("=== INVESTIGACAO DIRIGIDA (campo especifico) ===")
                self.tool_results_parts.append(inv_result["contexto_llm"])
                self.usou_investigacao_dirigida = True
        except Exception as e:
            print(f"[pipeline] directed investigation error: {e}")

    async def _check_steering(self) -> Optional[str]:
        """Check if user sent a steering instruction via the /steer endpoint."""
        if not self._steering_queue:
            return None
        try:
            instruction = self._steering_queue.get_nowait()
            return instruction
        except Exception:
            return None

    async def _plan_and_investigate(self, message: str) -> AsyncGenerator[dict, None]:
        """Plan investigation and execute — the core reasoning loop."""
        yield self._status("Planejando investigação...")
        try:
            from app.services.workspace.investigation_loop import (
                run_investigation, run_planned_investigation, build_tool_descriptions,
            )
            from app.services.workspace.investigation_planner import create_investigation_plan

            # Build initial context
            initial_ctx_parts = [
                f"MODO: {self.modo}",
                f"PERGUNTA: {message}",
                f"TABELAS: {', '.join(self.tabelas)}",
            ]
            if self.campos_msg:
                initial_ctx_parts.append(f"CAMPOS EXPLICITOS: {', '.join(self.campos_msg)}")
            if self.modulos:
                initial_ctx_parts.append(f"MODULOS: {', '.join(self.modulos)}")
            if self.tool_results_parts:
                initial_ctx_parts.append("CONTEXTO INICIAL:")
                initial_ctx_parts.extend(self.tool_results_parts[:10])

            initial_context = "\n".join(initial_ctx_parts)

            # Try to create investigation plan
            classification_ctx = {
                "tabelas": self.tabelas, "modulos": self.modulos,
                "campos": self.campos_msg,
            }
            plan = await create_investigation_plan(
                self.llm, message, classification_ctx,
                initial_context, self.modo, build_tool_descriptions(),
            )

            investigation_context = ""
            if plan and plan.get("steps"):
                yield self._status(f"Plano: {plan.get('objective', '...')[:80]}")
                async for event in run_planned_investigation(
                    self.llm, plan, initial_context, self.modo,
                    artifact_registry=self.artifact_registry,
                ):
                    if event["type"] == "status":
                        yield self._status(event["step"])
                    elif event["type"] == "tool_result":
                        # Forward tool results to frontend for granular visibility
                        steering = await self._check_steering()
                        if steering:
                            self.tool_results_parts.append(f"## CORRECAO DO USUARIO\n{steering}")
                            yield self._status(f"Usuario corrigiu: {steering[:80]}...")
                        yield {
                            "event": "tool_result",
                            "data": json.dumps({
                                "tool": event.get("tool", ""),
                                "args": event.get("args", {}),
                                "summary": event.get("summary", ""),
                            }, ensure_ascii=False),
                        }
                    elif event["type"] == "complete":
                        investigation_context = event["context"]
            else:
                # Fallback: unplanned ReAct
                yield self._status("Investigando...")
                async for event in run_investigation(self.llm, initial_context, self.modo):
                    if event["type"] == "status":
                        yield self._status(event["step"])
                    elif event["type"] == "tool_result":
                        # Forward tool results to frontend for granular visibility
                        steering = await self._check_steering()
                        if steering:
                            self.tool_results_parts.append(f"## CORRECAO DO USUARIO\n{steering}")
                            yield self._status(f"Usuario corrigiu: {steering[:80]}...")
                        yield {
                            "event": "tool_result",
                            "data": json.dumps({
                                "tool": event.get("tool", ""),
                                "args": event.get("args", {}),
                                "summary": event.get("summary", ""),
                            }, ensure_ascii=False),
                        }
                    elif event["type"] == "complete":
                        investigation_context = event["context"]

            if investigation_context:
                self.tool_results_parts.append("=== INVESTIGACAO ITERATIVA ===")
                self.tool_results_parts.append(investigation_context)

        except Exception as e:
            print(f"[pipeline] investigation error: {e}")
            import traceback
            traceback.print_exc()

    async def _verify(self, context: str, message: str):
        """Verification + Reflection step."""
        try:
            from app.services.workspace.verification import verify_and_reflect, should_verify
            tool_count = sum(1 for p in self.tool_results_parts if p.startswith("===") or p.startswith("[") or p.startswith("**"))
            if should_verify(self.modo, tool_count, context=context):
                vr = await verify_and_reflect(self.llm, context, message, self.modo)
                if vr.get("verified_draft") and vr.get("confidence", 0) > 0.3:
                    self.verified_draft = vr["verified_draft"]
        except Exception:
            pass

    def _build_system_prompt(self, context: str, tool_results_text: str) -> str:
        """Build the mode-specific system prompt."""
        if self.usou_clarificacao:
            return f"""Voce e um assistente tecnico de TOTVS Protheus.
Foi detectada AMBIGUIDADE na pergunta do usuario — existem multiplos cenarios possiveis.

SUA UNICA TAREFA: apresentar as opcoes abaixo e perguntar qual se aplica.

REGRAS ABSOLUTAS:
- NAO faca analise tecnica
- NAO gere resumo executivo
- NAO investigue nenhum cenario
- NAO liste campos ou fontes
- APENAS apresente as opcoes e pergunte

{tool_results_text}"""

        # Build dedicated customizations section
        customizacoes = ""
        resumo_parts = getattr(self, '_resumo_parts', [])
        if resumo_parts:
            customizacoes = """
══════════════════════════════════════════════════════════════
CUSTOMIZAÇÕES JÁ IMPLEMENTADAS NO CLIENTE — LEIA COM ATENÇÃO:
Se alguma das funções abaixo JÁ FAZ o que o usuário pede,
DESCREVA O QUE JÁ EXISTE em vez de sugerir criar algo novo.
══════════════════════════════════════════════════════════════
""" + "\n\n".join(resumo_parts)

        # Inject artifact index so LLM can use #refs
        artifact_index = self.artifact_registry.summary_for_llm()
        if artifact_index:
            context = context + "\n\n" + artifact_index

        # Try modular composer first — focused prompt with only relevant rules
        try:
            from app.services.workspace.prompt_composer import compose_system_prompt
            return compose_system_prompt(
                modo=self.modo,
                context=context,
                artefatos_text=self.artefatos_text,
                tool_results_text=tool_results_text[:10000],
                customizacoes=customizacoes,
                has_artifacts=self.artifact_registry.count() > 0,
            )
        except Exception as e:
            print(f"[pipeline] prompt composer failed: {e}, using monolithic")

        # Fallback to monolithic prompts
        prompt_template = get_system_prompt(self.modo)

        if artifact_index:
            context += """

REGRA DE REFERENCIAMENTO:
Use #id (ex: #f1, #c3, #m1) para referenciar artefatos na sua resposta.
NAO reproduza listas completas de fontes, campos ou dados tecnicos — o frontend
vai exibir os dados estruturados automaticamente em secoes colapsaveis.
Foque na ANALISE: por que importa, qual o risco, o que o usuario deve fazer.
Exemplo BOM: "Os fontes #f1 a #f10 usam PadR(15) fixo e precisam ser corrigidos"
Exemplo RUIM: listar cada fonte com seu codigo linha por linha"""

        try:
            if self.modo == "melhoria":
                return prompt_template.format(
                    context=context,
                    artefatos=self.artefatos_text,
                    tool_results=tool_results_text[:10000],
                    customizacoes_existentes=customizacoes,
                )
            else:
                return prompt_template.format(
                    context=context,
                    tool_results=tool_results_text[:10000],
                    customizacoes_existentes=customizacoes,
                )
        except KeyError:
            # Fallback if template doesn't have all placeholders
            return prompt_template.format(
                context=context + "\n\n" + customizacoes,
                tool_results=tool_results_text[:10000],
                artefatos=self.artefatos_text,
                customizacoes_existentes=customizacoes,
            )

    # Context window manager — singleton shared across calls
    _ctx_manager = ContextWindowManager(max_tokens=120_000, reserve_output=8_000)

    def _build_messages(self, system: str) -> list[dict]:
        """Build the messages array for LLM using budget-based context management.

        Uses ContextWindowManager to maximize useful context instead of
        crude truncation.
        """
        # The last entry in hist_rows is the current user message
        if self.hist_rows:
            current_message = self.hist_rows[-1][1]
            prior_history = self.hist_rows[:-1]
        else:
            current_message = ""
            prior_history = []

        return self._ctx_manager.build_messages_from_rows(
            system_prompt=system,
            hist_rows=prior_history,
            current_message=current_message,
        )

        # ── Old logic (crude truncation) — kept as fallback ──
        # messages = [{"role": "system", "content": system}]
        # for r in self.hist_rows[-10:]:
        #     messages.append({"role": r[0], "content": r[1][:2000]})
        # return messages

    def _build_technical_appendix(self) -> str:
        """Build COMPLETE technical appendix — NOT LLM-generated.

        Uses the artifact_registry to render ALL technical data:
        - Campos fora do SXG (com tabela, tamanho, risco)
        - Fontes com tamanho chumbado (com trechos de codigo)
        - MsExecAuto (com rotina e risco)
        - Integracoes
        - Info geral (grupo SXG, totais)

        This data goes DIRECTLY to the frontend, bypassing the LLM.
        """
        if self.artifact_registry.count() == 0:
            return ""

        by_type = self.artifact_registry.by_type()
        parts = ["\n\n---\n\n# Dados Tecnicos Completos\n"]
        parts.append("*Dados extraidos automaticamente do ambiente do cliente — 100% precisos.*\n")

        # ── MsExecAuto (RISCO) ──
        msexec = by_type.get("msexecauto", [])
        if msexec:
            parts.append(f"\n## MsExecAuto — RISCO CRITICO ({len(msexec)})\n")
            parts.append("| # | Arquivo | Rotina | Risco |")
            parts.append("|---|---------|--------|-------|")
            for a in msexec:
                parts.append(f"| {a['id']} | {a.get('arquivo','')} | {a.get('rotina','')} | {a.get('risco','')[:80]} |")
            parts.append("")

        # ── Campos fora do SXG ──
        campos = by_type.get("campo", [])
        campos_fora = [c for c in campos if "Fora do grupo" in c.get("problema", "")]
        campos_suspeitos = [c for c in campos if "suspeito" in c.get("risco", "").lower()]
        if campos_fora:
            parts.append(f"\n## Campos FORA do Grupo SXG — Ajuste Manual ({len(campos_fora)})\n")
            parts.append("| # | Tabela.Campo | Titulo | Tamanho | Risco |")
            parts.append("|---|-------------|--------|---------|-------|")
            for c in campos_fora:
                parts.append(f"| {c['id']} | {c.get('tabela','')}.{c.get('campo','')} | {c.get('titulo','')} | {c.get('tamanho','')} | {c.get('risco','')} |")
            parts.append("")

        if campos_suspeitos:
            parts.append(f"\n## Campos Custom Suspeitos ({len(campos_suspeitos)})\n")
            parts.append("| # | Tabela.Campo | Titulo | Tamanho |")
            parts.append("|---|-------------|--------|---------|")
            for c in campos_suspeitos[:20]:
                parts.append(f"| {c['id']} | {c.get('tabela','')}.{c.get('campo','')} | {c.get('titulo','')} | {c.get('tamanho','')} |")
            parts.append("")

        # ── Fontes com tamanho chumbado ──
        fontes = by_type.get("fonte", [])
        fontes_chumbado = [f for f in fontes if f.get("tipo_problema")]
        if fontes_chumbado:
            # Group by tipo_problema
            by_tipo = {}
            for f in fontes_chumbado:
                key = f"{f['tipo_problema']}({f.get('tamanho_chumbado', '?')})"
                by_tipo.setdefault(key, []).append(f)

            total_unique = len(set(f["arquivo"] for f in fontes_chumbado))
            parts.append(f"\n## Fontes com Tamanho Chumbado ({len(fontes_chumbado)} ocorrencias em {total_unique} fontes)\n")
            parts.append("*Todos devem usar `TamSX3(\"CAMPO\")` em vez de numero fixo.*\n")

            for key in sorted(by_tipo.keys()):
                items = by_tipo[key]
                alta = [i for i in items if i.get("confianca") == "alta"]
                media = [i for i in items if i.get("confianca") == "media"]

                parts.append(f"\n### {key} — {len(items)} ocorrencia(s)\n")

                if alta:
                    parts.append(f"**Confianca ALTA** ({len(alta)} — referenciam o campo diretamente):\n")
                    for f in alta:
                        parts.append(f"- {f['id']} **{f['arquivo']}::{f.get('funcao','')}**")
                        for trecho in f.get("trechos", []):
                            parts.append(f"  ```\n  {trecho}\n  ```")
                    parts.append("")

                if media:
                    parts.append(f"**Confianca MEDIA** ({len(media)} — usam a tabela, podem estar relacionados):\n")
                    for f in media:
                        parts.append(f"- {f['id']} **{f['arquivo']}::{f.get('funcao','')}**")
                        for trecho in f.get("trechos", []):
                            parts.append(f"  ```\n  {trecho}\n  ```")
                    parts.append("")

        # ── Fontes de escrita (sem tipo_problema = vem do analise_impacto) ──
        fontes_escrita = [f for f in fontes if not f.get("tipo_problema") and f.get("problema") == "Grava na tabela"]
        if fontes_escrita:
            parts.append(f"\n## Fontes que Gravam na Tabela ({len(fontes_escrita)})\n")
            parts.append("| # | Arquivo | Modulo | LOC |")
            parts.append("|---|---------|--------|-----|")
            for f in fontes_escrita:
                parts.append(f"| {f['id']} | {f.get('arquivo','')} | {f.get('modulo','')} | {f.get('loc','')} |")
            parts.append("")

        # ── Integracoes ──
        integ = by_type.get("integracao", [])
        if integ:
            parts.append(f"\n## Integracoes/WebServices ({len(integ)})\n")
            parts.append("| # | Arquivo | Modulo |")
            parts.append("|---|---------|--------|")
            for i in integ:
                parts.append(f"| {i['id']} | {i.get('arquivo','')} | {i.get('modulo','')} |")
            parts.append("")

        # ── Gatilhos ──
        gats = by_type.get("gatilho", [])
        if gats:
            parts.append(f"\n## Gatilhos ({len(gats)})\n")
            parts.append("| # | Origem | Destino | Tipo | Regra |")
            parts.append("|---|--------|---------|------|-------|")
            for g in gats[:30]:
                parts.append(f"| {g['id']} | {g.get('campo_origem','')} | {g.get('campo_destino','')} | {g.get('tipo','')} | {g.get('regra','')[:50]} |")
            if len(gats) > 30:
                parts.append(f"\n*... +{len(gats)-30} gatilhos adicionais*")
            parts.append("")

        # ── PEs ──
        pes = by_type.get("pe", [])
        if pes:
            parts.append(f"\n## Pontos de Entrada ({len(pes)})\n")
            parts.append("| # | Nome | Operacao | Retorno |")
            parts.append("|---|------|----------|---------|")
            for p in pes[:30]:
                parts.append(f"| {p['id']} | {p.get('nome','')} | {p.get('operacao','')} | {p.get('tipo_retorno','')} |")
            if len(pes) > 30:
                parts.append(f"\n*... +{len(pes)-30} PEs adicionais*")
            parts.append("")

        # ── Parametros ──
        params = by_type.get("parametro", [])
        if params:
            parts.append(f"\n## Parametros ({len(params)})\n")
            parts.append("| # | Variavel | Valor | Descricao |")
            parts.append("|---|----------|-------|-----------|")
            for p in params:
                parts.append(f"| {p['id']} | {p.get('variavel','')} | {p.get('conteudo','')} | {p.get('descricao','')[:50]} |")
            parts.append("")

        return "\n".join(parts)

    async def _stream_verified(self, draft: str) -> AsyncGenerator[dict, None]:
        """Stream a pre-verified draft in small chunks."""
        chunk_size = 12
        for i in range(0, len(draft), chunk_size):
            chunk = draft[i:i+chunk_size]
            yield {"event": "token", "data": json.dumps({"content": chunk})}
            if i % 120 == 0:
                await asyncio.sleep(0.01)

    async def _stream_llm(self, messages: list[dict]) -> AsyncGenerator[dict, None]:
        """Stream response from LLM with retry logic."""
        for attempt in range(3):
            try:
                q = _queue_mod.Queue(maxsize=64)
                _stream_err = [None]

                def _produce(msgs=messages):
                    try:
                        for tok in self.llm.chat_stream(msgs):
                            q.put(tok)
                    except Exception as ex:
                        _stream_err[0] = ex
                    finally:
                        q.put(None)

                t = threading.Thread(target=_produce, daemon=True)
                t.start()

                while True:
                    token = await asyncio.to_thread(q.get)
                    if token is None:
                        break
                    yield {"event": "token", "data": json.dumps({"content": token})}

                t.join(timeout=5)
                if _stream_err[0]:
                    raise _stream_err[0]
                break

            except Exception as e:
                if ("rate_limit" in str(e).lower() or "429" in str(e) or "overload" in str(e).lower()) and attempt < 2:
                    wait = 30 * (attempt + 1)
                    yield {"event": "token", "data": json.dumps({"content": f"\n\n... aguardando {wait}s...\n\n"})}
                    await asyncio.sleep(wait)
                    continue
                yield {"event": "token", "data": json.dumps({"content": f"\n\nErro: {str(e)[:200]}"})}
                return

    def _parse_artifacts(self, response: str) -> list[dict]:
        """Extract artifacts from melhoria mode responses."""
        if self.modo != "melhoria" or "###ARTEFATOS###" not in response:
            return []
        try:
            parts = response.split("###ARTEFATOS###", 1)
            return json.loads(parts[1].strip())
        except (json.JSONDecodeError, IndexError):
            return []

    async def _save_response(self, chat_text: str, artefatos_novos: list[dict]):
        """Save assistant response and artifacts to database."""
        db = self._get_db()
        try:
            _tool_data = None
            if artefatos_novos:
                _tool_data = json.dumps(artefatos_novos)
            elif self.usou_clarificacao and self._clarificacao_blocos:
                _tool_data = json.dumps({"clarificacao_pendente": True, "blocos": [
                    {"nome": b["nome"], "campos": b["campos"], "fontes": b.get("fontes", [])[:5],
                     "tabela": b.get("tabela", ""), "descricao": b.get("descricao", "")[:100]}
                    for b in self._clarificacao_blocos if b.get("fontes")
                ]})

            db.execute(
                "INSERT INTO analista_mensagens (demanda_id, projeto_id, role, content, tool_data) VALUES (?, 0, 'assistant', ?, ?)",
                (self.conversa_id, chat_text, _tool_data),
            )
            for art in artefatos_novos:
                if isinstance(art, dict) and art.get("nome"):
                    _spec = art.get("spec")
                    if not _spec:
                        _spec = {k: v for k, v in art.items() if k not in {"tipo", "nome", "tabela", "acao"}}
                    _spec_str = json.dumps(_spec, ensure_ascii=False) if _spec else None
                    db.execute(
                        "INSERT INTO analista_artefatos (demanda_id, projeto_id, tipo, nome, tabela, acao, spec_json) VALUES (?, 0, ?, ?, ?, ?, ?)",
                        (self.conversa_id, art.get("tipo", ""), art.get("nome", ""),
                         art.get("tabela", ""), art.get("acao", "criar"), _spec_str),
                    )
            db.execute("UPDATE analista_demandas SET updated_at=datetime('now') WHERE id=?", (self.conversa_id,))
            db.commit()
        finally:
            db.close()

    async def _check_followup(self, message: str) -> Optional[AsyncGenerator]:
        """Check if this is a follow-up to a clarification question."""
        if len(self.hist_rows) < 2:
            return None

        try:
            db = self._get_db()
            last_msg = db.execute(
                "SELECT tool_data FROM analista_mensagens WHERE demanda_id=? AND role='assistant' ORDER BY id DESC LIMIT 1",
                (self.conversa_id,),
            ).fetchone()
            db.close()

            if not last_msg or not last_msg[0]:
                return None

            td = json.loads(last_msg[0])
            if not isinstance(td, dict) or not td.get("clarificacao_pendente"):
                return None

            blocos = td["blocos"]
            return self._handle_followup(message, blocos)

        except Exception:
            return None

    async def _handle_followup(self, message: str, blocos: list[dict]) -> AsyncGenerator[dict, None]:
        """Handle follow-up to a clarification — investigate the matched block."""
        yield self._status("Identificando opção escolhida...")
        msg_lower = message.lower()

        matched_block = None
        for i, bloco in enumerate(blocos):
            nome_lower = bloco["nome"].lower()
            if (str(i+1) in message
                or any(kw in msg_lower for kw in nome_lower.split()[:2] if len(kw) > 3)
                or any(c.lower() in msg_lower for c in bloco.get("campos", [])[:3])):
                matched_block = bloco
                break

        if not matched_block:
            # Couldn't match — let LLM handle it normally
            yield self._status("Não consegui identificar a opção, analisando...")
            return

        yield self._status(f"Investigando: {matched_block['nome']}...")

        tab = matched_block.get("tabela", "SC5")
        from app.services.workspace.investigation_loop import run_investigation

        followup_ctx_parts = [
            f"MODO: {self.modo}",
            f"PERGUNTA ORIGINAL: {self.hist_rows[0][1][:200] if self.hist_rows else message}",
            f"USUARIO ESCOLHEU: {message}",
            f"TABELA: {tab}",
            f"ROTINAS: {', '.join(matched_block.get('fontes', [])[:5])}",
            f"CAMPOS: {', '.join(matched_block.get('campos', [])[:5])}",
            f"DESCRICAO: {matched_block.get('descricao', '')}",
        ]
        followup_context = "\n".join(followup_ctx_parts)

        tool_results_parts_followup = []
        async for event in run_investigation(self.llm, followup_context, self.modo):
            if event["type"] == "status":
                yield self._status(event["step"])
            elif event["type"] == "complete":
                if event["context"]:
                    tool_results_parts_followup.append(event["context"])

        if tool_results_parts_followup:
            tool_results_text = "\n".join(tool_results_parts_followup)
            prompt_template = get_system_prompt(self.modo)
            if self.modo == "melhoria":
                system = prompt_template.format(
                    context=tool_results_text[:8000], artefatos=self.artefatos_text,
                    tool_results=tool_results_text[:6000],
                )
            else:
                system = prompt_template.format(
                    context=tool_results_text[:8000], tool_results=tool_results_text[:6000],
                )

            messages = [{"role": "system", "content": system}]
            for r in self.hist_rows[-10:]:
                messages.append({"role": r[0], "content": r[1][:2000]})

            yield self._status("")

            full_response = ""
            async for event in self._stream_llm(messages):
                yield event
                if event.get("event") == "token":
                    full_response += json.loads(event["data"]).get("content", "")

            # Save followup response
            db = self._get_db()
            try:
                db.execute(
                    "INSERT INTO analista_mensagens (demanda_id, projeto_id, role, content) VALUES (?, 0, 'assistant', ?)",
                    (self.conversa_id, full_response),
                )
                db.execute("UPDATE analista_demandas SET updated_at=datetime('now') WHERE id=?", (self.conversa_id,))
                db.commit()
            finally:
                db.close()

        yield {"event": "done", "data": "{}"}

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _status(step: str) -> dict:
        return {"event": "status", "data": json.dumps({"step": step})}
