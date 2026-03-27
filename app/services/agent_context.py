"""
Coleta de contexto e construção de user context do GolIAs.

Responsabilidades:
- Consultar fontes de dados relevantes por intent (memória, KB, alertas, pipelines)
- Construir texto de contexto para o system prompt
- Construir contexto do usuário logado
- Injetar snapshot do sistema (quando solicitado)
"""

import logging

from app.database import get_db, release_db_connection
from app.services.knowledge_base import find_matching_article, search_articles, get_recurring_errors

logger = logging.getLogger(__name__)


class ContextBuilder:
    """Coleta contexto relevante para a resposta do agente."""

    def __init__(self, memory, llm_provider=None):
        self.memory = memory
        self._llm_provider = llm_provider

    def set_llm_provider(self, provider):
        """Atualiza o provider LLM (para busca híbrida)."""
        self._llm_provider = provider
        # Se o provider de chat nao suporta embedding, tentar fallback
        if provider and not getattr(provider, "supports_embedding", False):
            self._embed_provider = self._get_embed_fallback()
        else:
            self._embed_provider = provider

    def _get_embed_fallback(self):
        """Tenta obter provider de embedding alternativo.

        Usa mesma cadeia de fallback do _get_embedding_provider() em agent.py
        mas sem acesso ao banco (para evitar dependencia circular).
        """
        import os
        from app.services.llm_providers import LLMProvider, PROVIDERS

        # 1. Provider dedicado via env var
        dedicated = os.environ.get("EMBEDDING_PROVIDER")
        if dedicated:
            try:
                api_key = os.environ.get("EMBEDDING_API_KEY") or os.environ.get(f"{dedicated.upper()}_API_KEY")
                p = LLMProvider(dedicated, api_key=api_key)
                if p.supports_embedding:
                    return p
            except Exception:
                pass

        # 2. Providers cloud com embedding e API key configurada via env
        for pid, pconfig in PROVIDERS.items():
            if pid == "ollama" or not pconfig.get("embedding"):
                continue
            env_key = os.environ.get(f"{pid.upper()}_API_KEY")
            if env_key:
                try:
                    p = LLMProvider(pid, api_key=env_key)
                    if p.supports_embedding:
                        return p
                except Exception:
                    continue

        # 3. Ollama local (se disponivel)
        try:
            import requests
            resp = requests.get("http://localhost:11434/api/version", timeout=2)
            if resp.status_code == 200:
                return LLMProvider("ollama")
        except Exception:
            pass

        return None

    def gather_context(self, intent, message, entities, environment_id):
        """Consulta fontes de dados conforme a intenção detectada."""
        context = {
            "memory_results": [],
            "kb_articles": [],
            "alerts": [],
            "pipelines": [],
            "environments": [],
            "tdn_results": [],
        }

        # Busca na memória — híbrida (BM25 + embedding) se disponível, senão BM25 puro
        # Usa embed_provider (pode ser diferente do chat provider)
        embed_prov = getattr(self, "_embed_provider", self._llm_provider)
        try:
            context["memory_results"] = self.memory.search_hybrid(
                message, llm_provider=embed_prov, limit=5, environment_id=environment_id
            )
        except Exception as e:
            logger.warning("Erro na busca de memória: %s", e)

        # Busca na base TDN (full-text search no PostgreSQL)
        try:
            self._fetch_tdn_context(context, message, intent)
        except Exception as e:
            logger.warning("Busca TDN indisponivel: %s", e)

        # Consultas específicas por intent
        handlers = {
            "error_analysis": self._ctx_error_analysis,
            "pipeline_status": self._ctx_pipeline_status,
            "table_info": self._ctx_table_info,
            "procedure_lookup": self._ctx_procedure_lookup,
            "alert_recurrence": self._ctx_alert_recurrence,
            "environment_status": self._ctx_environment_status,
            "knowledge_search": self._ctx_knowledge_search,
            "user_context": self._ctx_user_context,
            "general": self._ctx_general,
        }

        handler = handlers.get(intent, self._ctx_general)
        try:
            handler(context, message, entities, environment_id)
        except Exception as e:
            logger.warning("Erro no handler de contexto %s: %s", intent, e)

        return context

    def _ctx_error_analysis(self, context, message, entities, env_id):
        """Busca artigos da KB + tendencias de alertas para erros."""
        for code in entities["error_codes"]:
            article = find_matching_article("database", code)
            if article and article not in context["kb_articles"]:
                context["kb_articles"].append(article)

        if not context["kb_articles"]:
            try:
                articles = search_articles(message, limit=3)
                context["kb_articles"] = articles if articles else []
            except Exception:
                pass

        if env_id:
            # Usa alert_trends (view materializada) em vez de alertas brutos
            trends = self._fetch_alert_trends(env_id)
            if trends:
                context["alert_trends"] = trends
            else:
                # Fallback para alertas brutos se view nao existir
                self._fetch_recent_alerts(context, env_id, limit=5)

    def _ctx_pipeline_status(self, context, message, entities, env_id):
        """Busca últimas execuções de pipeline."""
        if not env_id:
            return

        conn = get_db()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT pr.id, pr.pipeline_id, p.name as pipeline_name,
                       pr.status, pr.started_at, pr.finished_at
                FROM pipeline_runs pr
                JOIN pipelines p ON p.id = pr.pipeline_id
                WHERE p.environment_id = %s
                ORDER BY pr.started_at DESC
                LIMIT 5
            """,
                (env_id,),
            )
            context["pipelines"] = [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.warning("Erro ao buscar pipelines: %s", e)
        finally:
            release_db_connection(conn)

    def _ctx_table_info(self, context, message, entities, env_id):
        """Busca info de tabelas na SX2 + memória semântica."""
        sx2_results = []
        for table in entities["table_names"]:
            results = self.memory.search_sx2(table, limit=5)
            sx2_results.extend(results)

        if not sx2_results and not entities["table_names"]:
            sx2_results = self.memory.search_sx2(message, limit=10)

        if sx2_results:
            if "sx2_tables" not in context:
                context["sx2_tables"] = []
            context["sx2_tables"].extend(sx2_results)

        for table in entities["table_names"]:
            results = self.memory.search_bm25(table, chunk_type="semantic", limit=3)
            for r in results:
                if r not in context["memory_results"]:
                    context["memory_results"].append(r)

        for field in entities["field_names"]:
            try:
                articles = search_articles(field, limit=2)
                if articles:
                    context["kb_articles"].extend(articles)
            except Exception:
                pass

    def _ctx_procedure_lookup(self, context, message, entities, env_id):
        """Busca procedimentos na memória procedural (TOOLS.md)."""
        results = self.memory.search_bm25(message, chunk_type="procedural", limit=5)
        for r in results:
            if r not in context["memory_results"]:
                context["memory_results"].append(r)

    def _ctx_alert_recurrence(self, context, message, entities, env_id):
        """Busca erros recorrentes."""
        try:
            recurring = get_recurring_errors(environment_id=env_id, min_count=2, days=7, limit=10)
            context["alerts"] = recurring if recurring else []
        except Exception as e:
            logger.warning("Erro ao buscar recorrências: %s", e)

    def _ctx_environment_status(self, context, message, entities, env_id):
        """Busca informações de ambientes."""
        conn = get_db()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT id, name, description, created_at
                FROM environments
                ORDER BY name
            """)
            context["environments"] = [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.warning("Erro ao buscar ambientes: %s", e)
        finally:
            release_db_connection(conn)

    def _ctx_knowledge_search(self, context, message, entities, env_id):
        """Busca textual na base de conhecimento."""
        try:
            articles = search_articles(message, limit=5)
            context["kb_articles"] = articles if articles else []
        except Exception:
            pass

    def _ctx_user_context(self, context, message, entities, env_id):
        """Para perguntas sobre o usuario logado — contexto minimo."""
        pass

    def _ctx_general(self, context, message, entities, env_id):
        """Fallback — busca geral na memória."""
        pass

    def _fetch_tdn_context(self, context, message, intent):
        """Busca inteligente na base TDN usando ProtheusIntelligence.

        Pipeline:
        1. ProtheusIntelligence analisa a mensagem (sem LLM, puro heuristica)
        2. Gera multiplas queries otimizadas (modulo, tabelas, rotinas, conceitos)
        3. Busca multi-estrategia (tsvector + titulo + fallback ILIKE)
        4. Deduplica e ranqueia resultados
        5. Injeta context_hint (dicas do grafo de conhecimento)
        """
        from app.services.tdn_intelligence import ProtheusIntelligence
        from app.services.tdn_ingestor import TDNIngestor

        pi = ProtheusIntelligence()
        analysis = pi.analyze(message)
        ingestor = TDNIngestor()

        # Busca multi-query (queries geradas pela inteligencia)
        results = ingestor.search_multi(analysis.search_queries, limit=5)

        # Se multi-query nao achou, tentar busca por titulo
        if not results and (analysis.detected_modules or analysis.detected_routines):
            title_terms = " ".join(analysis.detected_modules + analysis.detected_routines)
            results = ingestor.search_by_title(title_terms, limit=5)

        if results:
            context["tdn_results"] = [dict(r) for r in results]
            logger.info(
                "TDN: %d chunks (queries=%d, modulos=%s, intent=%s)",
                len(results), len(analysis.search_queries),
                analysis.detected_modules, analysis.protheus_intent
            )

        # Injetar context_hint (dicas do grafo de conhecimento Protheus)
        if analysis.context_hint:
            context["protheus_hint"] = analysis.context_hint

    def inject_system_snapshot(self, context, env_id):
        """Injeta resumo do estado atual do sistema no contexto."""
        conn = get_db()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT id, name, description, created_at
                FROM environments ORDER BY id
            """)
            context["environments"] = [dict(row) for row in cursor.fetchall()]

            if not env_id:
                return

            cursor.execute(
                """
                SELECT p.name, pr.status, pr.started_at, pr.finished_at
                FROM pipeline_runs pr
                JOIN pipelines p ON p.id = pr.pipeline_id
                WHERE p.environment_id = %s
                ORDER BY pr.started_at DESC LIMIT 3
            """,
                (env_id,),
            )
            context["pipelines"] = [dict(row) for row in cursor.fetchall()]

            cursor.execute(
                """
                SELECT category, severity, message, created_at
                FROM log_alerts
                WHERE environment_id = %s
                ORDER BY created_at DESC LIMIT 3
            """,
                (env_id,),
            )
            context["alerts"] = [dict(row) for row in cursor.fetchall()]

            cursor.execute(
                """
                SELECT name, html_url, default_branch
                FROM repositories
                WHERE environment_id = %s
                ORDER BY name
            """,
                (env_id,),
            )
            repos = [dict(row) for row in cursor.fetchall()]
            if repos:
                context["repositories"] = repos

            cursor.execute(
                """
                SELECT name, server_name
                FROM server_services
                WHERE environment_id = %s
                ORDER BY name
            """,
                (env_id,),
            )
            services = [dict(row) for row in cursor.fetchall()]
            if services:
                context["services"] = services

            cursor.execute(
                """
                SELECT id, name, driver, host, database_name
                FROM database_connections
                WHERE environment_id = %s
                ORDER BY name
            """,
                (env_id,),
            )
            db_conns = [dict(row) for row in cursor.fetchall()]
            if db_conns:
                context["db_connections"] = db_conns

        except Exception as e:
            logger.warning("Erro ao injetar snapshot do sistema: %s", e)
        finally:
            release_db_connection(conn)

    def fetch_recent_alerts(self, context, env_id, limit=5):
        """Busca alertas recentes do ambiente."""
        conn = get_db()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT id, category, severity, message, source_file,
                       thread_id, created_at
                FROM log_alerts
                WHERE environment_id = %s
                ORDER BY created_at DESC
                LIMIT %s
            """,
                (env_id, limit),
            )
            context["alerts"] = [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.warning("Erro ao buscar alertas: %s", e)
        finally:
            release_db_connection(conn)

    # Alias interno para retrocompatibilidade
    _fetch_recent_alerts = fetch_recent_alerts

    def _fetch_alert_trends(self, env_id):
        """Busca tendencias agregadas de alertas (view materializada).

        Retorna resumo compacto em vez de alertas brutos, economizando ~1800 tokens.
        """
        conn = get_db()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT category, total, last_hour, last_24h,
                       critical_count, error_count, trend, last_seen
                FROM alert_trends
                WHERE environment_id = %s
                ORDER BY total DESC
                LIMIT 10
            """, (env_id,))
            return [dict(row) for row in cursor.fetchall()]
        except Exception:
            # View pode nao existir ainda (migration pendente)
            return []
        finally:
            release_db_connection(conn)

    @staticmethod
    def build_user_context(user_info):
        """Monta bloco de contexto do usuario para o system prompt."""
        if not user_info:
            return "Usuário não identificado."

        name = user_info.get("name", "Desconhecido")
        username = user_info.get("username", "?")
        profile = user_info.get("profile", "viewer")
        env_name = user_info.get("environment_name", "Nenhum selecionado")
        env_id = user_info.get("environment_id", "?")

        profile_labels = {
            "admin": "Administrador (acesso total)",
            "operator": "Operador (CI/CD, servicos, repos)",
            "viewer": "Visualizador (somente leitura)",
        }
        profile_desc = profile_labels.get(profile, profile)

        lines = [
            f"- **Nome:** {name} (`{username}`)",
            f"- **Perfil:** {profile_desc}",
            f"- **Ambiente ativo:** {env_name} (ID: {env_id})",
        ]

        if profile == "admin":
            lines.append("- **Permissões:** Todas — incluindo configurações, usuarios, LLM, seeds")
        elif profile == "operator":
            lines.append("- **Permissões:** Pipelines, repositórios, serviços, deploy, git")
        else:
            lines.append("- **Permissões:** Somente visualização — sem ações destrutivas")

        lines.append("")
        lines.append("**IMPORTANTE:** Use esses dados diretamente. NUNCA pergunte ao usuário informações que já estão aqui.")

        return "\n".join(lines)

    @staticmethod
    def build_context_text(intent, entities, context):
        """Formata os dados do contexto como texto para o system prompt."""
        parts = []

        # Dicas do grafo de conhecimento Protheus (antes de tudo)
        if context.get("protheus_hint"):
            parts.append("### Contexto Protheus detectado")
            parts.append(context["protheus_hint"])

        if context.get("memory_results"):
            parts.append("### Memória do Agente")
            for r in context["memory_results"][:3]:
                title = r.get("section_title", "")
                # Usar summary se disponivel, senao truncar content
                content = r.get("summary") or r.get("content", "")[:250]
                parts.append(f"- **{title}**: {content}")

        if context.get("kb_articles"):
            parts.append("### Base de Conhecimento")
            for a in context["kb_articles"][:3]:
                if isinstance(a, dict):
                    # Usar solution_summary se disponivel (max 200 chars vs ~800 do solution)
                    solution = (
                        a.get("solution_summary")
                        or a.get("solution")
                        or a.get("description", "")
                    )
                    parts.append(f"- **{a.get('title', '')}** [{a.get('category', '')}]: {solution}")

        # Alert trends (view materializada) — formato compacto (~200 tokens vs ~2000)
        if context.get("alert_trends"):
            parts.append("### Tendências de Alertas")
            for t in context["alert_trends"][:5]:
                trend_icon = {"crescente": "↑", "estavel": "→", "inativo": "·"}.get(t.get("trend", ""), "?")
                parts.append(
                    f"- {trend_icon} **{t.get('category', '?')}**: "
                    f"{t.get('total', 0)} total, {t.get('last_hour', 0)} última hora, "
                    f"{t.get('critical_count', 0)} críticos ({t.get('trend', '?')})"
                )

        # Fallback: alertas brutos (quando view nao existe)
        elif context.get("alerts"):
            parts.append("### Alertas Recentes")
            for a in context["alerts"][:5]:
                if isinstance(a, dict):
                    parts.append(
                        f"- [{a.get('severity', '?')}] {a.get('category', '')}: "
                        f"{str(a.get('message', ''))[:150]}"
                    )

        if context.get("pipelines"):
            parts.append("### Pipelines Recentes")
            for p in context["pipelines"][:3]:
                parts.append(
                    f"- {p.get('pipeline_name', '?')}: {p.get('status', '?')} "
                    f"({p.get('started_at', '?')})"
                )

        if context.get("sx2_tables"):
            parts.append("### Dicionário SX2 do Protheus")
            for t in context["sx2_tables"][:10]:
                parts.append(f"- **{t['alias']}** — {t['description_pt']}")

        if context.get("tdn_results"):
            parts.append("### Documentacao oficial TDN (TOTVS Developer Network)")
            parts.append("Use estas informacoes como base factual para sua resposta:")
            for r in context["tdn_results"][:5]:
                title = r.get("section_title") or r.get("page_title", "")
                content = str(r.get("content", ""))[:600]
                url = r.get("page_url", "")
                parts.append(f"\n**{title}**\n{content}\n> Fonte: {url}")

        if context.get("environments"):
            parts.append("### Ambientes")
            for e in context["environments"]:
                parts.append(f"- {e.get('name', '?')}: {e.get('description', '')}")

        # Resultados de chain (19B)
        chain_result = context.get("_chain_result")
        if chain_result and chain_result.get("results"):
            import json as _json

            parts.append(f"\n### Dados coletados automaticamente (chain: {chain_result.get('chain', '?')})")
            for step in chain_result["results"]:
                tool = step.get("tool", "?")
                data = step.get("data")
                warning = step.get("warning", "")
                if warning:
                    parts.append(f"\n**{tool}** {warning}")
                else:
                    parts.append(f"\n**{tool}:**")
                if data:
                    data_text = _json.dumps(data, ensure_ascii=False, default=str)
                    if len(data_text) > 1500:
                        data_text = data_text[:1500] + "... (truncado)"
                    parts.append(f"```json\n{data_text}\n```")
            if chain_result.get("errors"):
                for err in chain_result["errors"]:
                    parts.append(f"- ⚠️ {err['tool']}: {err['error']}")

        if not parts:
            return "Nenhum dado adicional encontrado."

        return "\n".join(parts)
