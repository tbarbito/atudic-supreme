"""
Composição de resposta rule-based do GolIAs.

Responsabilidades:
- Montar resposta estruturada (seções, links, fontes) a partir do contexto
- Gerar texto por intent no modo rule-based (sem LLM)
- Construir seções expansíveis e links para módulos
"""

import logging

logger = logging.getLogger(__name__)


class ResponseComposer:
    """Compõe respostas rule-based a partir do contexto coletado."""

    def compose_response(self, intent, confidence, message, entities, context):
        """Compõe resposta estruturada com seções e links."""
        sections = []
        links = []
        sources = []

        # Resultados da memória BM25
        if context["memory_results"]:
            sources.append("agent_memory_bm25")
            for r in context["memory_results"][:3]:
                sections.append(
                    {
                        "type": "memory",
                        "title": r.get("section_title", ""),
                        "content": r.get("content", "")[:500],
                        "source_file": r.get("source_file", ""),
                        "score": round(abs(r.get("rank", 0)), 2),
                    }
                )

        # Artigos da KB
        if context["kb_articles"]:
            sources.append("knowledge_articles")
            for a in context["kb_articles"][:3]:
                article = a if isinstance(a, dict) else {}
                sections.append(
                    {
                        "type": "article",
                        "title": article.get("title", ""),
                        "content": article.get("solution") or article.get("description", ""),
                        "article_id": article.get("id"),
                        "category": article.get("category", ""),
                    }
                )
                if article.get("id"):
                    links.append(
                        {
                            "label": f"Ver artigo: {article.get('title', '')[:40]}",
                            "page": "knowledge",
                            "icon": "fa-book",
                        }
                    )

        # Alertas
        if context["alerts"]:
            sources.append("log_alerts")
            for alert in context["alerts"][:5]:
                if isinstance(alert, dict):
                    sections.append(
                        {
                            "type": "alert",
                            "title": alert.get("category", ""),
                            "content": alert.get("message", "")[:300],
                            "severity": alert.get("severity", ""),
                            "created_at": str(alert.get("created_at", "")),
                        }
                    )
            links.append(
                {
                    "label": "Ver Monitoramento",
                    "page": "observability",
                    "icon": "fa-satellite-dish",
                }
            )

        # Pipelines
        if context["pipelines"]:
            sources.append("pipeline_runs")
            for p in context["pipelines"][:3]:
                sections.append(
                    {
                        "type": "pipeline",
                        "title": p.get("pipeline_name", f"Pipeline #{p.get('pipeline_id', '')}"),
                        "content": f"Status: {p.get('status', '?')} | Início: {p.get('started_at', '?')}",
                        "status": p.get("status", ""),
                    }
                )
            links.append(
                {
                    "label": "Ver Pipelines",
                    "page": "pipelines",
                    "icon": "fa-cogs",
                }
            )

        # Ambientes
        if context["environments"]:
            sources.append("environments")
            for env in context["environments"]:
                sections.append(
                    {
                        "type": "environment",
                        "title": env.get("name", ""),
                        "content": env.get("description", ""),
                    }
                )

        # Compor texto principal
        text = self._compose_text(intent, entities, sections, context)

        return {
            "intent": intent,
            "confidence": round(confidence, 2),
            "text": text,
            "sections": sections,
            "links": links,
            "sources_consulted": sources,
            "entities": entities,
            "mode": "rule-based",
        }

    def _compose_text(self, intent, entities, sections, context):
        """Gera texto principal da resposta baseado na intenção."""
        texts = {
            "error_analysis": self._text_error_analysis,
            "pipeline_status": self._text_pipeline_status,
            "table_info": self._text_table_info,
            "procedure_lookup": self._text_procedure_lookup,
            "alert_recurrence": self._text_alert_recurrence,
            "environment_status": self._text_environment_status,
            "knowledge_search": self._text_knowledge_search,
            "user_context": self._text_user_context,
            "general": self._text_general,
        }

        fn = texts.get(intent, self._text_general)
        return fn(entities, sections, context)

    def _text_error_analysis(self, entities, sections, context):
        parts = []
        codes = entities.get("error_codes", [])
        if codes:
            parts.append(f"Analisando o(s) erro(s): **{', '.join(codes)}**")

        articles = [s for s in sections if s["type"] == "article"]
        if articles:
            parts.append("\n**Artigos relevantes encontrados na Base de Conhecimento:**")
            for a in articles:
                parts.append(f"- **{a['title']}**: {a['content'][:200]}")

        memory = [s for s in sections if s["type"] == "memory"]
        if memory:
            parts.append("\n**Da memória do agente:**")
            for m in memory[:2]:
                parts.append(f"- **{m['title']}** ({m['source_file']})")

        alerts = [s for s in sections if s["type"] == "alert"]
        if alerts:
            parts.append(f"\n**{len(alerts)} alerta(s) recente(s) no ambiente.**")

        if not parts:
            parts.append(
                "Não encontrei informações específicas sobre esse erro na base de dados. "
                "Tente verificar o console.log do AppServer para mais detalhes."
            )

        return "\n".join(parts)

    def _text_pipeline_status(self, entities, sections, context):
        pipes = [s for s in sections if s["type"] == "pipeline"]
        if not pipes:
            return "Nenhuma execução de pipeline encontrada para o ambiente atual."

        parts = [f"**Últimas {len(pipes)} execuções de pipeline:**"]
        for p in pipes:
            icon = "✅" if p["status"] == "success" else "❌" if p["status"] == "failed" else "⏳"
            parts.append(f"- {icon} **{p['title']}** — {p['content']}")

        return "\n".join(parts)

    def _text_table_info(self, entities, sections, context):
        tables = entities.get("table_names", [])
        parts = []

        if tables:
            parts.append(f"Informações sobre: **{', '.join(tables)}**")

        sx2 = context.get("sx2_tables", [])
        if sx2:
            parts.append("\n**Dicionário SX2 do Protheus:**")
            for t in sx2[:10]:
                parts.append(f"- **{t['alias']}** — {t['description_pt']}")

        memory = [s for s in sections if s["type"] == "memory"]
        if memory:
            for m in memory[:3]:
                parts.append(f"\n**{m['title']}**\n{m['content'][:400]}")

        if not parts:
            parts.append(
                "Não encontrei informações sobre essa tabela. "
                "Verifique o módulo Banco de Dados para explorar a estrutura."
            )

        return "\n".join(parts)

    def _text_procedure_lookup(self, entities, sections, context):
        memory = [s for s in sections if s["type"] == "memory"]
        if memory:
            parts = ["**Procedimento(s) encontrado(s):**"]
            for m in memory[:3]:
                parts.append(f"\n### {m['title']}\n{m['content'][:600]}")
            return "\n".join(parts)

        return (
            "Não encontrei um procedimento específico para essa solicitação. "
            "Consulte a aba Arquivos para ver os procedimentos disponíveis no TOOLS.md."
        )

    def _text_alert_recurrence(self, entities, sections, context):
        alerts = context.get("alerts", [])
        if not alerts:
            return "Nenhum erro recorrente encontrado nos últimos 7 dias."

        parts = [f"**Top {len(alerts)} erros recorrentes (últimos 7 dias):**"]
        for a in alerts:
            if isinstance(a, dict):
                count = a.get("occurrence_count", a.get("count", "?"))
                cat = a.get("category", "?")
                msg = a.get("message", a.get("sample_message", ""))[:100]
                parts.append(f"- **{cat}** ({count}x): {msg}")

        return "\n".join(parts)

    def _text_environment_status(self, entities, sections, context):
        envs = [s for s in sections if s["type"] == "environment"]
        if not envs:
            return "Nenhum ambiente ativo encontrado."

        parts = ["**Ambientes disponíveis:**"]
        for e in envs:
            icon = "🟢" if e.get("is_active") else "🔴"
            parts.append(f"- {icon} **{e['title']}** — {e['content']}")

        return "\n".join(parts)

    def _text_knowledge_search(self, entities, sections, context):
        articles = [s for s in sections if s["type"] == "article"]
        if articles:
            parts = [f"**{len(articles)} artigo(s) encontrado(s):**"]
            for a in articles:
                parts.append(f"- **{a['title']}** [{a.get('category', '')}]: {a['content'][:200]}")
            return "\n".join(parts)

        return "Nenhum artigo encontrado na Base de Conhecimento para essa busca."

    def _text_user_context(self, entities, sections, context):
        user_info = context.get("_user_info", {})
        if user_info:
            name = user_info.get("name", "Desconhecido")
            username = user_info.get("username", "?")
            profile = user_info.get("profile", "viewer")
            env_name = user_info.get("environment_name", "Nao selecionado")
            return f"Voce e **{name}** (`{username}`), perfil **{profile}**, logado no ambiente **{env_name}**."
        return "Voce esta logado no BiizHubOps. Selecione um ambiente no seletor do topo da pagina para comecar."

    def _text_general(self, entities, sections, context):
        memory = [s for s in sections if s["type"] == "memory"]
        if memory:
            parts = ["Encontrei as seguintes informacoes relevantes:"]
            for m in memory[:3]:
                parts.append(f"\n**{m['title']}** ({m['source_file']})\n{m['content'][:300]}")
            return "\n".join(parts)

        return (
            "Nao encontrei informacoes especificas na memoria. "
            "Posso ajudar com consultas ao banco, status de pipelines, alertas, "
            "repositorios ou servicos. O que precisa?"
        )

    @staticmethod
    def build_sections_from_context(context):
        """Extrai seções do contexto para exibir no frontend (modo LLM)."""
        sections = []
        for r in (context.get("memory_results") or [])[:3]:
            sections.append(
                {
                    "type": "memory",
                    "title": r.get("section_title", ""),
                    "content": r.get("content", "")[:500],
                    "source_file": r.get("source_file", ""),
                    "score": round(abs(r.get("rank", 0)), 2),
                }
            )
        for a in (context.get("kb_articles") or [])[:2]:
            if isinstance(a, dict):
                sections.append(
                    {
                        "type": "article",
                        "title": a.get("title", ""),
                        "content": (a.get("solution") or a.get("description", ""))[:300],
                    }
                )
        return sections

    @staticmethod
    def build_links_from_context(context):
        """Extrai links para módulos relevantes."""
        links = []
        if context.get("alerts"):
            links.append({"label": "Ver Monitoramento", "page": "observability", "icon": "fa-satellite-dish"})
        if context.get("pipelines"):
            links.append({"label": "Ver Pipelines", "page": "pipelines", "icon": "fa-cogs"})
        if context.get("kb_articles"):
            links.append({"label": "Ver Base de Conhecimento", "page": "knowledge", "icon": "fa-book"})
        return links

    @staticmethod
    def list_sources(context):
        """Lista fontes consultadas para atribuição."""
        sources = []
        if context.get("memory_results"):
            sources.append("agent_memory_bm25")
        if context.get("kb_articles"):
            sources.append("knowledge_articles")
        if context.get("alerts"):
            sources.append("log_alerts")
        if context.get("pipelines"):
            sources.append("pipeline_runs")
        if context.get("environments"):
            sources.append("environments")
        return sources
