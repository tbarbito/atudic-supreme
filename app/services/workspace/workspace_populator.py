# -*- coding: utf-8 -*-
"""
WorkspacePopulator — Alimenta SQLite do workspace a partir de multiplas fontes.

Modos de operacao:
- offline: CSVs exportados do Protheus (parser_sx)
- live: Conexao direta ao banco Protheus (database_connections do AtuDIC)
- hibrido: Dicionario do DB + fontes do filesystem

Este modulo e a ponte entre ExtraiRPO (CSV-based) e AtuDIC (DB-based).
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional

from app.services.workspace.workspace_db import Database
from app.services.workspace import parser_sx
from app.services.workspace import parser_source
from app.services.workspace.build_vinculos import build_vinculos

logger = logging.getLogger(__name__)


class WorkspacePopulator:
    """Popula workspace SQLite a partir de CSVs, DB direto ou hibrido."""

    def __init__(self, workspace_path: Path):
        self.workspace_path = workspace_path
        self.db_path = workspace_path / "workspace.db"
        self.db = Database(self.db_path)

    def initialize(self):
        """Cria diretorio e inicializa schema SQLite."""
        self.workspace_path.mkdir(parents=True, exist_ok=True)
        self.db.initialize()
        logger.info(f"Workspace inicializado em {self.workspace_path}")

    # ========================================================================
    # MODO OFFLINE — CSVs exportados do Protheus
    # ========================================================================

    def populate_from_csv(self, csv_dir: Path, progress_callback=None) -> dict:
        """Popula workspace a partir de CSVs SX exportados do Protheus.

        Args:
            csv_dir: Diretorio com os CSVs (SX2.csv, SX3.csv, etc.)
            progress_callback: Funcao(fase, item, total) para progresso

        Returns:
            dict com contadores de registros inseridos
        """
        start = time.time()
        stats = {}

        def _report(fase, item, total=0):
            if progress_callback:
                progress_callback(fase, item, total)

        # Mapa de arquivos CSV -> parser -> tabela destino -> SQL
        sx_map = [
            ("SX2.csv", parser_sx.parse_sx2, "tabelas",
             "INSERT OR REPLACE INTO tabelas (codigo, nome, modo, custom) VALUES (?,?,?,?)",
             lambda r: (r["codigo"], r["nome"], r["modo"], r["custom"])),
            ("SX3.csv", parser_sx.parse_sx3, "campos",
             "INSERT OR REPLACE INTO campos (tabela, campo, tipo, tamanho, decimal, titulo, descricao, "
             "validacao, inicializador, obrigatorio, custom, f3, cbox, vlduser, when_expr, proprietario, "
             "browse, trigger_flag, visual, context, folder) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
             lambda r: (r["tabela"], r["campo"], r["tipo"], r["tamanho"], r["decimal"],
                        r["titulo"], r["descricao"], r["validacao"], r["inicializador"],
                        r["obrigatorio"], r["custom"], r["f3"], r["cbox"], r["vlduser"],
                        r["when_expr"], r["proprietario"], r["browse"], r["trigger_flag"],
                        r["visual"], r["context"], r["folder"])),
            ("SIX.csv", parser_sx.parse_six, "indices",
             "INSERT OR REPLACE INTO indices (tabela, ordem, chave, descricao, proprietario, f3, nickname, showpesq, custom) "
             "VALUES (?,?,?,?,?,?,?,?,?)",
             lambda r: (r["tabela"], r["ordem"], r["chave"], r["descricao"], r["proprietario"],
                        r["f3"], r["nickname"], r["showpesq"], r["custom"])),
            ("SX7.csv", parser_sx.parse_sx7, "gatilhos",
             "INSERT OR REPLACE INTO gatilhos (campo_origem, sequencia, campo_destino, regra, tipo, tabela, "
             "condicao, proprietario, seek, alias, ordem, chave, custom) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
             lambda r: (r["campo_origem"], r["sequencia"], r["campo_destino"], r["regra"], r["tipo"],
                        r["tabela"], r["condicao"], r["proprietario"], r["seek"], r["alias"],
                        r["ordem"], r["chave"], r["custom"])),
            ("SX1.csv", parser_sx.parse_sx1, "perguntas",
             "INSERT OR REPLACE INTO perguntas (grupo, ordem, pergunta, variavel, tipo, tamanho, decimal, f3, validacao, conteudo_padrao) "
             "VALUES (?,?,?,?,?,?,?,?,?,?)",
             lambda r: (r["grupo"], r["ordem"], r["pergunta"], r["variavel"], r["tipo"],
                        r["tamanho"], r["decimal"], r["f3"], r["validacao"], r["conteudo_padrao"])),
            ("SX5.csv", parser_sx.parse_sx5, "tabelas_genericas",
             "INSERT OR REPLACE INTO tabelas_genericas (filial, tabela, chave, descricao, custom) VALUES (?,?,?,?,?)",
             lambda r: (r["filial"], r["tabela"], r["chave"], r["descricao"], r["custom"])),
            ("SX6.csv", parser_sx.parse_sx6, "parametros",
             "INSERT OR REPLACE INTO parametros (filial, variavel, tipo, descricao, conteudo, proprietario, custom) "
             "VALUES (?,?,?,?,?,?,?)",
             lambda r: (r["filial"], r["variavel"], r["tipo"], r["descricao"], r["conteudo"],
                        r["proprietario"], r["custom"])),
            ("SX9.csv", parser_sx.parse_sx9, "relacionamentos",
             "INSERT OR REPLACE INTO relacionamentos (tabela_origem, identificador, tabela_destino, "
             "expressao_origem, expressao_destino, proprietario, condicao_sql, custom) VALUES (?,?,?,?,?,?,?,?)",
             lambda r: (r["tabela_origem"], r["identificador"], r["tabela_destino"],
                        r["expressao_origem"], r["expressao_destino"], r["proprietario"],
                        r["condicao_sql"], r["custom"])),
            ("SXA.csv", parser_sx.parse_sxa, "pastas",
             "INSERT OR REPLACE INTO pastas (alias, ordem, descricao, proprietario, agrupamento) VALUES (?,?,?,?,?)",
             lambda r: (r["alias"], r["ordem"], r["descricao"], r["proprietario"], r["agrupamento"])),
            ("SXB.csv", parser_sx.parse_sxb, "consultas",
             "INSERT OR REPLACE INTO consultas (alias, tipo, sequencia, coluna, descricao, conteudo) VALUES (?,?,?,?,?,?)",
             lambda r: (r["alias"], r["tipo"], r["sequencia"], r["coluna"], r["descricao"], r["conteudo"])),
        ]

        # Processar cada SX
        for filename, parser_func, table_name, sql, mapper in sx_map:
            csv_path = csv_dir / filename
            if not csv_path.exists():
                logger.warning(f"CSV nao encontrado: {csv_path}")
                continue

            _report("parse_csv", filename)
            rows = parser_func(csv_path)
            if rows:
                self.db.executemany(sql, [mapper(r) for r in rows])
                stats[table_name] = len(rows)
                logger.info(f"  {table_name}: {len(rows)} registros")

        # mpmenu (opcional)
        mpmenu_menu = csv_dir / "mpmenu_menu.csv"
        if mpmenu_menu.exists():
            _report("parse_csv", "mpmenu")
            try:
                menus = parser_sx.parse_mpmenu(csv_dir)
                if menus:
                    self.db.executemany(
                        "INSERT OR REPLACE INTO menus (modulo, rotina, nome, menu, ordem) VALUES (?,?,?,?,?)",
                        [(m["modulo"], m["rotina"], m["nome"], m["menu"], m["ordem"]) for m in menus]
                    )
                    stats["menus"] = len(menus)
            except Exception as e:
                logger.warning(f"Erro ao parsear mpmenu: {e}")

        # jobs (opcional)
        jobs_path = csv_dir / "job_detalhado_bash.csv"
        if jobs_path.exists():
            _report("parse_csv", "jobs")
            try:
                jobs = parser_sx.parse_jobs(jobs_path)
                if jobs:
                    self.db.executemany(
                        "INSERT OR REPLACE INTO jobs (arquivo_ini, sessao, rotina, refresh_rate, parametros) "
                        "VALUES (?,?,?,?,?)",
                        [(j["arquivo_ini"], j["sessao"], j["rotina"], j["refresh_rate"], j["parametros"]) for j in jobs]
                    )
                    stats["jobs"] = len(jobs)
            except Exception as e:
                logger.warning(f"Erro ao parsear jobs: {e}")

        # schedules (opcional)
        schedules_path = csv_dir / "schedule_decodificado.csv"
        if schedules_path.exists():
            _report("parse_csv", "schedules")
            try:
                schedules = parser_sx.parse_schedules(schedules_path)
                if schedules:
                    self.db.executemany(
                        "INSERT OR REPLACE INTO schedules (codigo, rotina, empresa_filial, environment, modulo, "
                        "status, tipo_recorrencia, detalhe_recorrencia, execucoes_dia, intervalo, hora_inicio, "
                        "data_criacao, ultima_execucao, ultima_hora, recorrencia_raw) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        [(s["codigo"], s["rotina"], s["empresa_filial"], s["environment"], s["modulo"],
                          s["status"], s["tipo_recorrencia"], s["detalhe_recorrencia"], s["execucoes_dia"],
                          s["intervalo"], s["hora_inicio"], s["data_criacao"], s["ultima_execucao"],
                          s["ultima_hora"], s["recorrencia_raw"]) for s in schedules]
                    )
                    stats["schedules"] = len(schedules)
            except Exception as e:
                logger.warning(f"Erro ao parsear schedules: {e}")

        elapsed = time.time() - start
        stats["_elapsed_seconds"] = round(elapsed, 2)
        logger.info(f"CSV ingestao completa em {elapsed:.1f}s — {stats}")
        return stats

    # ========================================================================
    # PARSE DE FONTES — Codigo ADVPL/TLPP
    # ========================================================================

    def parse_fontes(self, fontes_dir: Path, mapa_modulos_path: Optional[Path] = None,
                     progress_callback=None) -> dict:
        """Parseia codigo-fonte ADVPL/TLPP e popula workspace.

        Args:
            fontes_dir: Diretorio com arquivos .prw/.tlpp
            mapa_modulos_path: Path para mapa-modulos.json (deteccao de modulo)
            progress_callback: Funcao(fase, item, total) para progresso

        Returns:
            dict com contadores
        """
        start = time.time()
        stats = {"fontes": 0, "chunks": 0, "operacoes_escrita": 0}

        # Carregar mapa de modulos
        mapa_modulos = {}
        if mapa_modulos_path and mapa_modulos_path.exists():
            mapa_modulos = json.loads(mapa_modulos_path.read_text(encoding="utf-8"))

        # Descobrir arquivos
        extensions = {".prw", ".prx", ".tlpp", ".aph"}
        arquivos = [
            f for f in fontes_dir.rglob("*")
            if f.suffix.lower() in extensions and f.stat().st_size < 5_000_000
        ]

        if not arquivos:
            logger.warning(f"Nenhum fonte encontrado em {fontes_dir}")
            return stats

        logger.info(f"Encontrados {len(arquivos)} fontes para parsear")

        # Pass 1: Metadata
        for i, arquivo in enumerate(arquivos):
            if progress_callback:
                progress_callback("parse_fontes", arquivo.name, len(arquivos))

            try:
                result = parser_source.parse_source(arquivo, include_chunks=False)
            except Exception as e:
                logger.warning(f"Erro ao parsear {arquivo.name}: {e}")
                continue

            # Detectar modulo
            modulo = self._detect_module(result, mapa_modulos)

            # Inserir metadata
            self.db.execute(
                "INSERT OR REPLACE INTO fontes (arquivo, caminho, tipo, modulo, funcoes, user_funcs, "
                "pontos_entrada, tabelas_ref, write_tables, includes, calls_u, calls_execblock, "
                "fields_ref, lines_of_code, hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (result["arquivo"], result["caminho"], result.get("source_type", "custom"),
                 modulo, json.dumps(result["funcoes"]), json.dumps(result["user_funcs"]),
                 json.dumps(result["pontos_entrada"]), json.dumps(result["tabelas_ref"]),
                 json.dumps(result["write_tables"]), json.dumps(result["includes"]),
                 json.dumps(result["calls_u"]), json.dumps(result["calls_execblock"]),
                 json.dumps(result["fields_ref"]), result["lines_of_code"], result["hash"])
            )

            # Operacoes de escrita
            for op in result.get("operacoes_escrita", []):
                self.db.execute(
                    "INSERT INTO operacoes_escrita (arquivo, funcao, tipo, tabela, campos, origens, condicao, linha) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (result["arquivo"], op["funcao"], op["tipo"], op["tabela"],
                     json.dumps(op["campos"]), json.dumps(op["origens"]),
                     op["condicao"], op["linha"])
                )
                stats["operacoes_escrita"] += 1

            stats["fontes"] += 1

            if (i + 1) % 5 == 0:
                self.db.commit()

        self.db.commit()

        # Pass 2: Chunks (com PRAGMAs otimizadas)
        conn = self.db.get_raw_conn()
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=2000")

        for arquivo in arquivos:
            try:
                result = parser_source.parse_source(arquivo, include_chunks=True)
            except Exception:
                continue

            modulo = self._detect_module(result, mapa_modulos)
            chunks = result.get("chunks", [])

            for chunk in chunks:
                conn.execute(
                    "INSERT OR REPLACE INTO fonte_chunks (id, arquivo, funcao, content, modulo) VALUES (?,?,?,?,?)",
                    (chunk["id"], result["arquivo"], chunk["funcao"], chunk["content"], modulo)
                )
                stats["chunks"] += 1

        conn.execute("PRAGMA synchronous=FULL")
        conn.commit()

        # Build vinculos
        if progress_callback:
            progress_callback("build_vinculos", "vinculos", 0)

        mapa_path = mapa_modulos_path if mapa_modulos_path and mapa_modulos_path.exists() else None
        build_vinculos(self.db_path, mapa_path)

        elapsed = time.time() - start
        stats["_elapsed_seconds"] = round(elapsed, 2)
        logger.info(f"Parse de fontes completo em {elapsed:.1f}s — {stats}")
        return stats

    def _detect_module(self, parse_result: dict, mapa_modulos: dict) -> str:
        """Detecta modulo do fonte baseado nas tabelas referenciadas."""
        if not mapa_modulos:
            return ""

        tabelas = set(parse_result.get("tabelas_ref", []))
        best_module = ""
        best_score = 0

        for modulo, info in mapa_modulos.items():
            mod_tabelas = set(info.get("tabelas", []))
            score = len(tabelas & mod_tabelas)
            if score > best_score:
                best_score = score
                best_module = modulo

        return best_module

    # ========================================================================
    # MODO LIVE — Conexao direta ao banco Protheus (futuro)
    # ========================================================================

    def populate_from_db(self, conn_config: dict, company_code: str = "01",
                         progress_callback=None) -> dict:
        """Popula workspace lendo SX* diretamente do banco Protheus.

        Args:
            conn_config: Config de conexao (host, port, user, password, database, driver)
            company_code: Codigo da empresa (M0_CODIGO), default "01"
            progress_callback: Funcao(fase, item, total) para progresso

        Returns:
            dict com contadores

        TODO: Implementar na Fase 2 — requer database_browser do AtuDIC
        """
        raise NotImplementedError(
            "Modo live sera implementado na Fase 2. "
            "Requer integracao com database_browser do AtuDIC."
        )

    # ========================================================================
    # MODO HIBRIDO — DB para dicionario + filesystem para fontes
    # ========================================================================

    def populate_hybrid(self, conn_config: dict, company_code: str,
                        fontes_dir: Path, mapa_modulos_path: Optional[Path] = None,
                        progress_callback=None) -> dict:
        """Modo hibrido: dicionario do DB + fontes do filesystem.

        TODO: Implementar na Fase 2
        """
        raise NotImplementedError(
            "Modo hibrido sera implementado na Fase 2."
        )

    # ========================================================================
    # UTILIDADES
    # ========================================================================

    def get_stats(self) -> dict:
        """Retorna estatisticas do workspace."""
        stats = {}
        tables = [
            "tabelas", "campos", "indices", "gatilhos", "perguntas",
            "tabelas_genericas", "parametros", "relacionamentos",
            "fontes", "fonte_chunks", "vinculos", "menus",
        ]
        for table in tables:
            try:
                count = self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                stats[table] = count
            except Exception:
                stats[table] = 0
        return stats

    def close(self):
        """Fecha conexao com o banco."""
        self.db.close()
