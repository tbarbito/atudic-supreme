# -*- coding: utf-8 -*-
"""
Pipeline de Documentacao IA — 3 Agentes Sequenciais.

Gera documentacao completa de um modulo Protheus:
1. Dicionarista → Secoes 1-7 (dicionario)
2. Analista de Fontes → Secoes 15-17 (codigo)
3. Documentador → Consolida 19 secoes (humano + ia)

Origem: ExtraiRPO (Joni) adaptado para BiizHubOps Supreme.
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.services.workspace.workspace_db import Database
from app.services.workspace.knowledge import KnowledgeService

logger = logging.getLogger(__name__)


class DocPipeline:
    """Pipeline de geracao de documentacao com 3 agentes LLM."""

    def __init__(self, db: Database, llm_provider=None):
        """
        Args:
            db: Database do workspace (SQLite)
            llm_provider: Instancia do LLMProvider para chamadas LLM.
                          Se None, gera apenas contexto sem chamar LLM.
        """
        self.db = db
        self.ks = KnowledgeService(db)
        self.llm = llm_provider

    def get_available_modules(self) -> list[str]:
        """Lista modulos disponiveis no workspace."""
        rows = self.db.execute(
            "SELECT DISTINCT modulo FROM fontes WHERE modulo != '' ORDER BY modulo"
        ).fetchall()
        return [r[0] for r in rows]

    def generate_for_module(self, modulo: str, output_dir: Optional[Path] = None,
                            progress_callback=None) -> dict:
        """Executa pipeline completa para um modulo.

        Args:
            modulo: Nome do modulo (ex: compras, faturamento, estoque)
            output_dir: Diretorio para salvar docs gerados (opcional)
            progress_callback: Funcao(fase, detalhe) para progresso

        Returns:
            dict com context, dicionario, fontes, documento_humano, documento_ia
        """
        start = time.time()
        result = {"modulo": modulo, "generated_at": datetime.now().isoformat()}

        def _report(fase, detalhe=""):
            if progress_callback:
                progress_callback(fase, detalhe)
            logger.info(f"DocPipeline [{modulo}] {fase}: {detalhe}")

        # ── Fase 0: Coletar contexto ──
        _report("context", "Coletando contexto do modulo")
        context = self.ks.build_context_for_module(modulo)
        result["context"] = context
        result["context_chars"] = len(context)

        # ── Fase 1: Dicionarista (Secoes 1-7) ──
        _report("dicionarista", "Analisando dicionario de dados")
        dicionarista_prompt = self._build_dicionarista_prompt(modulo, context)
        result["dicionarista_prompt"] = dicionarista_prompt

        if self.llm:
            dicionarista_result = self._call_llm(
                system_prompt=self._load_specialist_prompt("dicionarista"),
                user_message=dicionarista_prompt,
                temperature=0.2,
                max_tokens=4096,
            )
            result["dicionarista"] = dicionarista_result
        else:
            result["dicionarista"] = "[LLM nao configurado — apenas contexto gerado]"

        # ── Fase 2: Analista de Fontes (Secoes 15-17) ──
        _report("analista_fontes", "Analisando codigo-fonte")
        fontes_prompt = self._build_fontes_prompt(modulo, context)
        result["fontes_prompt"] = fontes_prompt

        if self.llm:
            fontes_result = self._call_llm(
                system_prompt=self._load_specialist_prompt("analista_fontes"),
                user_message=fontes_prompt,
                temperature=0.2,
                max_tokens=4096,
            )
            result["analista_fontes"] = fontes_result
        else:
            result["analista_fontes"] = "[LLM nao configurado — apenas contexto gerado]"

        # ── Fase 3: Documentador (19 secoes consolidadas) ──
        _report("documentador", "Consolidando documentacao")
        doc_prompt = self._build_documentador_prompt(
            modulo, result.get("dicionarista", ""), result.get("analista_fontes", "")
        )
        result["documentador_prompt"] = doc_prompt

        if self.llm:
            # Versao humano
            doc_humano = self._call_llm(
                system_prompt=self._load_specialist_prompt("documentador"),
                user_message=doc_prompt + "\n\nGere a versao HUMANO (Markdown puro para consultores).",
                temperature=0.3,
                max_tokens=6144,
            )
            result["documento_humano"] = doc_humano

            # Versao IA (com frontmatter YAML)
            doc_ia = self._call_llm(
                system_prompt=self._load_specialist_prompt("documentador"),
                user_message=doc_prompt + "\n\nGere a versao IA (Markdown com frontmatter YAML).",
                temperature=0.3,
                max_tokens=6144,
            )
            result["documento_ia"] = doc_ia
        else:
            result["documento_humano"] = "[LLM nao configurado]"
            result["documento_ia"] = "[LLM nao configurado]"

        # ── Salvar em disco (se output_dir) ──
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            self._save_docs(output_dir, modulo, result)
            _report("save", f"Docs salvos em {output_dir}")

        elapsed = time.time() - start
        result["elapsed_seconds"] = round(elapsed, 2)
        _report("done", f"Concluido em {elapsed:.1f}s")

        return result

    # ========================================================================
    # PROMPTS
    # ========================================================================

    def _build_dicionarista_prompt(self, modulo: str, context: str) -> str:
        """Prompt para o agente Dicionarista."""
        return f"""Analise o dicionario de dados do modulo **{modulo.upper()}** do Protheus.

Abaixo esta o contexto completo extraido do workspace (tabelas, campos, indices, gatilhos, parametros, vinculos):

{context}

Produza as Secoes 1 a 7 conforme seu template:
1. Resumo quantitativo
2. Parametrizacao (MV_)
3. Cadastros — Campos customizados por tabela
4. Indices customizados
5. Gatilhos customizados
6. Tipos e classificacoes (CBOX + SX5)
7. Tabelas do modulo

Use tabelas markdown. Seja preciso e factual — nao invente dados."""

    def _build_fontes_prompt(self, modulo: str, context: str) -> str:
        """Prompt para o agente Analista de Fontes."""
        # Buscar fontes do modulo
        fontes = self.ks.get_fontes_for_module(modulo)
        vinculos = self.ks.get_vinculos_for_module(modulo)

        fontes_summary = []
        for f in fontes[:30]:  # Limitar
            parts = [f"**{f['arquivo']}**"]
            if f.get("funcoes"):
                parts.append(f"Funcoes: {', '.join(f['funcoes'][:8])}")
            if f.get("pontos_entrada"):
                parts.append(f"PEs: {', '.join(f['pontos_entrada'])}")
            if f.get("tabelas_ref"):
                parts.append(f"Tabelas: {', '.join(f['tabelas_ref'])}")
            fontes_summary.append(" | ".join(parts))

        vinculos_by_type = {}
        for v in vinculos:
            vinculos_by_type.setdefault(v["tipo"], []).append(v)

        vinculos_summary = []
        for tipo, items in vinculos_by_type.items():
            vinculos_summary.append(f"- **{tipo}**: {len(items)} vinculos")

        return f"""Analise os fontes customizados do modulo **{modulo.upper()}** do Protheus.

## Fontes do Modulo ({len(fontes)} arquivos)

{chr(10).join(fontes_summary)}

## Vinculos ({len(vinculos)} total)

{chr(10).join(vinculos_summary)}

## Contexto do Dicionario

{context[:15000]}

Produza as Secoes 15 a 17:
15. Fontes custom detalhados
16. Mapa de vinculos (campo→funcao, gatilho→funcao, PE→rotina)
17. Grafo de dependencias (descreva textualmente ou use Mermaid)

Destaque PEs, integrações via MsExecAuto e operacoes de escrita (RecLock)."""

    def _build_documentador_prompt(self, modulo: str, dicionario: str, fontes: str) -> str:
        """Prompt para o agente Documentador."""
        return f"""Consolide as analises abaixo em um documento tecnico completo do modulo **{modulo.upper()}**.

## Analise do Dicionarista (Secoes 1-7)

{dicionario[:12000]}

## Analise do Analista de Fontes (Secoes 15-17)

{fontes[:12000]}

Produza um documento com TODAS as 19 secoes do template:
1-7: Dicionario (ja analisado acima — consolide)
8: Fluxo geral do processo
9: Integracoes entre modulos
10: Controles especiais
11: Comparativo padrao x cliente
12: Pontos de atencao (OBRIGATORIO — liste riscos)
13: Recomendacoes
14: Glossario
15-17: Fontes (ja analisado acima — consolide)
18: Operacoes de escrita
19: Anexos

Mantenha consistencia. Use tabelas markdown e diagramas Mermaid quando util."""

    # ========================================================================
    # LLM
    # ========================================================================

    def _call_llm(self, system_prompt: str, user_message: str,
                  temperature: float = 0.3, max_tokens: int = 4096) -> str:
        """Chama o LLM provider."""
        if not self.llm:
            return "[LLM nao configurado]"

        try:
            result = self.llm.chat(
                messages=[{"role": "user", "content": user_message}],
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return result.get("content", "")
        except Exception as e:
            logger.error(f"Erro na chamada LLM: {e}")
            return f"[Erro LLM: {e}]"

    def _load_specialist_prompt(self, specialist_name: str) -> str:
        """Carrega prompt do specialist de prompt/specialists/{name}.md."""
        prompt_path = Path(f"prompt/specialists/{specialist_name}.md")
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        return f"Voce e o especialista {specialist_name} do BiizHubOps Supreme."

    # ========================================================================
    # SAVE
    # ========================================================================

    def _save_docs(self, output_dir: Path, modulo: str, result: dict):
        """Salva documentos gerados em disco."""
        # Contexto
        (output_dir / f"{modulo}_contexto.md").write_text(
            result.get("context", ""), encoding="utf-8"
        )

        # Documento humano
        if result.get("documento_humano"):
            (output_dir / f"{modulo}_humano.md").write_text(
                result["documento_humano"], encoding="utf-8"
            )

        # Documento IA
        if result.get("documento_ia"):
            (output_dir / f"{modulo}_ia.md").write_text(
                result["documento_ia"], encoding="utf-8"
            )

        # Metadata JSON
        meta = {
            "modulo": modulo,
            "generated_at": result.get("generated_at"),
            "elapsed_seconds": result.get("elapsed_seconds"),
            "context_chars": result.get("context_chars"),
        }
        (output_dir / f"{modulo}_meta.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
        )
