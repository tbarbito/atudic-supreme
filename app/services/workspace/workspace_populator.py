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


def _find_csv_ci(directory: Path, filename: str) -> Optional[Path]:
    """Busca arquivo CSV case-insensitive (modo offline). Retorna Path ou None."""
    exact = directory / filename
    if exact.exists():
        return exact
    # Fallback: busca case-insensitive
    lower = filename.lower()
    try:
        for f in directory.iterdir():
            if f.name.lower() == lower:
                return f
    except Exception:
        pass
    return None


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

        # Processar cada SX (busca case-insensitive para modo offline/CSV)
        for filename, parser_func, table_name, sql, mapper in sx_map:
            csv_path = _find_csv_ci(csv_dir, filename)
            if not csv_path:
                logger.warning(f"CSV nao encontrado: {csv_dir / filename}")
                continue

            _report("parse_csv", filename)
            rows = parser_func(csv_path)
            if rows:
                self.db.executemany(sql, [mapper(r) for r in rows])
                stats[table_name] = len(rows)
                logger.info(f"  {table_name}: {len(rows)} registros")

        # mpmenu (opcional — precisa de mpmenu_menu.csv, mpmenu_item.csv, mpmenu_function.csv, mpmenu_i18n.csv)
        mpmenu_menu = _find_csv_ci(csv_dir, "mpmenu_menu.csv")
        if mpmenu_menu:
            _report("parse_csv", "mpmenu")
            logger.info(f"  mpmenu_menu.csv encontrado: {mpmenu_menu}")
            try:
                menus = parser_sx.parse_mpmenu(csv_dir)
                logger.info(f"  parse_mpmenu retornou {len(menus) if menus else 0} registros")
                if menus:
                    self.db.executemany(
                        "INSERT OR REPLACE INTO menus (modulo, rotina, nome, menu, ordem) VALUES (?,?,?,?,?)",
                        [(m["modulo"], m["rotina"], m["nome"], m["menu"], m["ordem"]) for m in menus]
                    )
                    self.db.commit()
                    stats["menus"] = len(menus)
                    logger.info(f"  menus: {len(menus)} registros ingeridos e commitados")
                else:
                    logger.warning("  parse_mpmenu retornou lista vazia")
            except Exception as e:
                import traceback
                logger.warning(f"Erro ao parsear mpmenu: {e}")
                traceback.print_exc()
        else:
            logger.info("  mpmenu_menu.csv nao encontrado em %s — menus nao ingeridos", csv_dir)

        # jobs (opcional)
        jobs_path = _find_csv_ci(csv_dir, "job_detalhado_bash.csv")
        if jobs_path:
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
        schedules_path = _find_csv_ci(csv_dir, "schedule_decodificado.csv")
        if schedules_path:
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

    def _load_mapa_modulos(self) -> dict:
        """Carrega mapa de modulos do SQLite (autocontido)."""
        mapa = {}
        try:
            rows = self.db.execute("SELECT modulo, tabelas, rotinas FROM mapa_modulos").fetchall()
            for r in rows:
                mapa[r[0]] = {
                    "tabelas": json.loads(r[1]) if r[1] else [],
                    "rotinas": json.loads(r[2]) if r[2] else [],
                }
        except Exception:
            pass
        return mapa

    def parse_fontes(self, fontes_dir: Path, mapa_modulos_path: Optional[Path] = None,
                     progress_callback=None) -> dict:
        """Parseia codigo-fonte ADVPL/TLPP e popula workspace.

        Args:
            fontes_dir: Diretorio com arquivos .prw/.tlpp
            mapa_modulos_path: Path para mapa-modulos.json (override opcional)
            progress_callback: Funcao(fase, item, total) para progresso

        Returns:
            dict com contadores
        """
        start = time.time()
        stats = {"fontes": 0, "chunks": 0, "operacoes_escrita": 0}

        # Carregar mapa de modulos do SQLite (padrao) ou arquivo externo (override)
        if mapa_modulos_path and mapa_modulos_path.exists():
            mapa_modulos = json.loads(mapa_modulos_path.read_text(encoding="utf-8"))
        else:
            mapa_modulos = self._load_mapa_modulos()

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
        # Garantir que nao ha transacao ativa antes de mudar PRAGMAs
        try:
            conn.commit()
        except Exception:
            pass
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

        try:
            conn.commit()
        except Exception:
            pass
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

    # Prefixos de rotina → modulo (padrao Protheus + clientes comuns)
    _PREFIX_TO_MODULE = {
        "MATA1": "compras", "MATA2": "estoque", "MATA4": "faturamento", "MATA6": "pcp",
        "MATA9": "fiscal", "FINA": "financeiro", "CTBA": "contabilidade",
        "GPEA": "rh", "GPEM": "rh", "GPER": "rh",
        "TMSA": "logistica", "TMSP": "logistica",
        "MGFCOM": "compras", "MGFFAT": "faturamento", "MGFEST": "estoque",
        "MGFFIN": "financeiro", "MGFFIS": "fiscal", "MGFCTB": "contabilidade",
        "MGF02R": "compras", "MGF05R": "estoque", "MGF06R": "fiscal",
    }

    def _detect_module(self, parse_result: dict, mapa_modulos: dict) -> str:
        """Detecta modulo do fonte — 3 estrategias (igual ExtraiRPO).

        Prioridade:
        1. Nome da rotina bate com rotinas do mapa (mais confiavel)
        2. Tabelas referenciadas batem com tabelas do mapa
        3. Prefixo do nome do arquivo (heuristica)
        """
        arquivo = parse_result.get("arquivo", "")
        stem = arquivo.rsplit(".", 1)[0].upper() if arquivo else ""

        # Estrategia 1: rotina name match (mais precisa)
        if mapa_modulos and stem:
            for modulo, info in mapa_modulos.items():
                rotinas = [r.upper() for r in info.get("rotinas", [])]
                if stem in rotinas:
                    return modulo

        # Estrategia 2: table overlap
        if mapa_modulos:
            tabelas = set(t.upper() for t in parse_result.get("tabelas_ref", []))
            best_module = ""
            best_score = 0
            for modulo, info in mapa_modulos.items():
                mod_tabelas = set(t.upper() for t in info.get("tabelas", []))
                score = len(tabelas & mod_tabelas)
                if score > best_score:
                    best_score = score
                    best_module = modulo
            if best_module:
                return best_module

        # Estrategia 3: prefixo do nome do arquivo (heuristica)
        if stem:
            for prefix, modulo in self._PREFIX_TO_MODULE.items():
                if stem.startswith(prefix.upper()):
                    return modulo

        return ""

    # ========================================================================
    # MODO LIVE — Conexao direta ao banco Protheus (futuro)
    # ========================================================================

    def populate_from_db(self, connection_id: int, company_code: str = "01",
                         environment_id: int = None, progress_callback=None) -> dict:
        """Popula workspace lendo SX* diretamente do banco Protheus.

        Usa database_browser e dictionary_compare do AtuDIC para conectar
        ao banco Protheus e ler as tabelas de metadados.

        Args:
            connection_id: ID da conexao em database_connections (PostgreSQL AtuDIC)
            company_code: Codigo da empresa (M0_CODIGO), default "01"
            environment_id: ID do ambiente (opcional, para rastreamento)
            progress_callback: Funcao(fase, item, total) para progresso

        Returns:
            dict com contadores de registros inseridos
        """
        start = time.time()
        stats = {}

        def _report(fase, item, total=0):
            if progress_callback:
                progress_callback(fase, item, total)

        # Importar modulos do AtuDIC
        from app.services.database_browser import get_connection_config, _get_external_connection

        _report("connect", "Conectando ao banco Protheus...")

        # Obter config e conectar
        config = get_connection_config(connection_id)
        if not config:
            raise ValueError(f"Conexao {connection_id} nao encontrada ou inativa")

        driver = config["driver"]
        ext_conn = _get_external_connection(config)
        cursor = ext_conn.cursor()

        logger.info(f"Conectado ao banco Protheus ({driver}) — empresa {company_code}")

        def _make_table(prefix):
            """Monta nome fisico: {PREFIX}{M0_CODIGO}0."""
            return f"{prefix}{company_code}0"

        def _fetch(table_name):
            """Busca todos os registros de uma tabela de metadados."""
            if driver == "mssql":
                query = f"SELECT * FROM [{table_name}]"
            elif driver == "oracle":
                query = f"SELECT * FROM {table_name}"
            elif driver == "postgresql":
                query = f"SELECT * FROM {table_name.lower()}"
            else:
                query = f'SELECT * FROM "{table_name}"'
            try:
                cursor.execute(query)
                if driver == "oracle":
                    columns = [desc[0] for desc in cursor.description]
                    return [dict(zip(columns, row)) for row in cursor.fetchall()]
                else:
                    return [dict(row) for row in cursor.fetchall()]
            except Exception as e:
                logger.warning(f"Erro ao buscar {table_name}: {e}")
                return []

        def _get(row, key, default=""):
            """Obtem valor de row case-insensitive."""
            v = row.get(key, row.get(key.upper(), row.get(key.lower(), default)))
            return str(v).strip() if v is not None else default

        def _safe_int(val):
            try:
                return int(str(val).strip().strip('"') or 0)
            except (ValueError, TypeError):
                return 0

        def _is_custom_table(codigo):
            import re
            return bool(re.match(r"^(SZ[0-9A-Z]|Q[A-Z][0-9A-Z]|Z[0-9A-Z][0-9A-Z]?)$", codigo))

        def _is_custom_field(campo):
            parts = campo.split("_")
            return len(parts) >= 2 and parts[1].startswith("X")

        # ── SX2 (Tabelas) ──
        _report("fetch", "SX2 — Tabelas")
        sx2_rows = _fetch(_make_table("SX2"))
        if sx2_rows:
            data = []
            for r in sx2_rows:
                codigo = _get(r, "X2_CHAVE")
                if not codigo:
                    continue
                data.append((codigo, _get(r, "X2_NOME"), _get(r, "X2_MODO"),
                             1 if _is_custom_table(codigo) else 0))
            self.db.executemany(
                "INSERT OR REPLACE INTO tabelas (codigo, nome, modo, custom) VALUES (?,?,?,?)", data)
            stats["tabelas"] = len(data)

        # ── SX3 (Campos) ──
        _report("fetch", "SX3 — Campos")
        sx3_rows = _fetch(_make_table("SX3"))
        if sx3_rows:
            data = []
            for r in sx3_rows:
                campo = _get(r, "X3_CAMPO")
                if not campo:
                    continue
                proprietario = _get(r, "X3_PROPRI")
                is_custom = 1 if _is_custom_field(campo) else 0
                if proprietario and proprietario != "S":
                    is_custom = 1
                obrig_raw = _get(r, "X3_OBRIGAT")
                obrigatorio = 1 if (obrig_raw.lower().startswith("x") or
                                    obrig_raw.upper() in ("S", "SIM", "1", ".T.")) else 0
                data.append((
                    _get(r, "X3_ARQUIVO"), campo, _get(r, "X3_TIPO"),
                    _safe_int(_get(r, "X3_TAMANHO")), _safe_int(_get(r, "X3_DECIMAL")),
                    _get(r, "X3_TITULO"), _get(r, "X3_DESCRIC"), _get(r, "X3_VALID"),
                    _get(r, "X3_RELACAO"), obrigatorio, is_custom,
                    _get(r, "X3_F3"), _get(r, "X3_CBOX"), _get(r, "X3_VLDUSER"),
                    _get(r, "X3_WHEN"), proprietario,
                    _get(r, "X3_BROWSE"), _get(r, "X3_TRIGGER"), _get(r, "X3_VISUAL"),
                    _get(r, "X3_CONTEXT"), _get(r, "X3_FOLDER"),
                ))
            self.db.executemany(
                "INSERT OR REPLACE INTO campos (tabela, campo, tipo, tamanho, decimal, titulo, descricao, "
                "validacao, inicializador, obrigatorio, custom, f3, cbox, vlduser, when_expr, proprietario, "
                "browse, trigger_flag, visual, context, folder) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                data)
            stats["campos"] = len(data)

        # ── SIX (Indices) ──
        _report("fetch", "SIX — Indices")
        six_rows = _fetch(_make_table("SIX"))
        if six_rows:
            data = []
            for r in six_rows:
                tabela = _get(r, "INDICE")
                ordem = _get(r, "ORDEM")
                if not tabela or not ordem:
                    continue
                proprietario = _get(r, "PROPRI")
                data.append((tabela, ordem, _get(r, "CHAVE"), _get(r, "DESCRICAO"),
                             proprietario, _get(r, "F3"), _get(r, "NICKNAME"),
                             _get(r, "SHOWPESQ"), 1 if proprietario and proprietario != "S" else 0))
            self.db.executemany(
                "INSERT OR REPLACE INTO indices (tabela, ordem, chave, descricao, proprietario, "
                "f3, nickname, showpesq, custom) VALUES (?,?,?,?,?,?,?,?,?)", data)
            stats["indices"] = len(data)

        # ── SX7 (Gatilhos) ──
        _report("fetch", "SX7 — Gatilhos")
        sx7_rows = _fetch(_make_table("SX7"))
        if sx7_rows:
            data = []
            for r in sx7_rows:
                campo_origem = _get(r, "X7_CAMPO")
                if not campo_origem:
                    continue
                campo_destino = _get(r, "X7_CDOMIN")
                proprietario = _get(r, "X7_PROPRI")
                is_custom = 1 if _is_custom_field(campo_destino) else 0
                if proprietario and proprietario != "S":
                    is_custom = 1
                data.append((campo_origem, _get(r, "X7_SEQUENC"), campo_destino,
                             _get(r, "X7_REGRA"), _get(r, "X7_TIPO"),
                             _get(r, "X7_ALIAS"), _get(r, "X7_CONDIC"), proprietario,
                             _get(r, "X7_SEEK"), _get(r, "X7_ALIAS"),
                             _get(r, "X7_ORDEM"), _get(r, "X7_CHAVE"), is_custom))
            self.db.executemany(
                "INSERT OR REPLACE INTO gatilhos (campo_origem, sequencia, campo_destino, regra, tipo, "
                "tabela, condicao, proprietario, seek, alias, ordem, chave, custom) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", data)
            stats["gatilhos"] = len(data)

        # ── SX1 (Perguntas) ──
        _report("fetch", "SX1 — Perguntas")
        sx1_rows = _fetch(_make_table("SX1"))
        if sx1_rows:
            data = []
            for r in sx1_rows:
                grupo = _get(r, "X1_GRUPO")
                ordem = _get(r, "X1_ORDEM")
                if not grupo or not ordem:
                    continue
                data.append((grupo, ordem, _get(r, "X1_PERGUNT"), _get(r, "X1_VARIAVL"),
                             _get(r, "X1_TIPO"), _safe_int(_get(r, "X1_TAMANHO")),
                             _safe_int(_get(r, "X1_DECIMAL")), _get(r, "X1_F3"),
                             _get(r, "X1_VALID"), _get(r, "X1_DEF01")))
            self.db.executemany(
                "INSERT OR REPLACE INTO perguntas (grupo, ordem, pergunta, variavel, tipo, "
                "tamanho, decimal, f3, validacao, conteudo_padrao) VALUES (?,?,?,?,?,?,?,?,?,?)", data)
            stats["perguntas"] = len(data)

        # ── SX5 (Tabelas Genericas) ──
        _report("fetch", "SX5 — Tabelas Genericas")
        sx5_rows = _fetch(_make_table("SX5"))
        if sx5_rows:
            data = []
            for r in sx5_rows:
                tabela = _get(r, "X5_TABELA")
                chave = _get(r, "X5_CHAVE")
                if not tabela or not chave:
                    continue
                data.append((_get(r, "X5_FILIAL"), tabela, chave, _get(r, "X5_DESCRI"),
                             1 if tabela.startswith("Z") or tabela.startswith("X") else 0))
            self.db.executemany(
                "INSERT OR REPLACE INTO tabelas_genericas (filial, tabela, chave, descricao, custom) "
                "VALUES (?,?,?,?,?)", data)
            stats["tabelas_genericas"] = len(data)

        # ── SX6 (Parametros) ──
        _report("fetch", "SX6 — Parametros")
        sx6_rows = _fetch(_make_table("SX6"))
        if sx6_rows:
            data = []
            for r in sx6_rows:
                variavel = _get(r, "X6_VAR")
                if not variavel:
                    continue
                proprietario = _get(r, "X6_PROPRI")
                descricao = (_get(r, "X6_DESCRIC") + " " + _get(r, "X6_DESC1")).strip()
                data.append((_get(r, "X6_FIL"), variavel, _get(r, "X6_TIPO"),
                             descricao, _get(r, "X6_CONTEUD"), proprietario,
                             1 if proprietario != "S" else 0))
            self.db.executemany(
                "INSERT OR REPLACE INTO parametros (filial, variavel, tipo, descricao, conteudo, "
                "proprietario, custom) VALUES (?,?,?,?,?,?,?)", data)
            stats["parametros"] = len(data)

        # ── SX9 (Relacionamentos) ──
        _report("fetch", "SX9 — Relacionamentos")
        sx9_rows = _fetch(_make_table("SX9"))
        if sx9_rows:
            data = []
            for r in sx9_rows:
                tabela_origem = _get(r, "X9_DOM")
                tabela_destino = _get(r, "X9_CDOM")
                if not tabela_origem or not tabela_destino:
                    continue
                proprietario = _get(r, "X9_PROPRI")
                data.append((tabela_origem, _get(r, "X9_IDENT"), tabela_destino,
                             _get(r, "X9_EXPDOM"), _get(r, "X9_EXPCDOM"),
                             proprietario, _get(r, "X9_CONDSQL"),
                             1 if proprietario != "S" else 0))
            self.db.executemany(
                "INSERT OR REPLACE INTO relacionamentos (tabela_origem, identificador, tabela_destino, "
                "expressao_origem, expressao_destino, proprietario, condicao_sql, custom) "
                "VALUES (?,?,?,?,?,?,?,?)", data)
            stats["relacionamentos"] = len(data)

        # Fechar conexao externa
        try:
            ext_conn.close()
        except Exception:
            pass

        self.db.commit()

        elapsed = time.time() - start
        stats["_elapsed_seconds"] = round(elapsed, 2)
        stats["_mode"] = "live"
        stats["_connection_id"] = connection_id
        stats["_company_code"] = company_code
        logger.info(f"Ingestao live completa em {elapsed:.1f}s — {stats}")
        return stats

    # ========================================================================
    # MODO HIBRIDO — DB para dicionario + filesystem para fontes
    # ========================================================================

    def populate_hybrid(self, connection_id: int, company_code: str,
                        fontes_dir: Path, mapa_modulos_path: Optional[Path] = None,
                        environment_id: int = None, progress_callback=None) -> dict:
        """Modo hibrido: dicionario do DB + fontes do filesystem.

        1. Popula dicionario (SX*) direto do banco Protheus
        2. Parseia fontes do filesystem
        3. Constroi vinculos

        Args:
            connection_id: ID da conexao ao banco Protheus
            company_code: Codigo da empresa
            fontes_dir: Diretorio com .prw/.tlpp
            mapa_modulos_path: Path para mapa-modulos.json
            environment_id: ID do ambiente
            progress_callback: Funcao(fase, item, total)

        Returns:
            dict com contadores
        """
        # Fase 1: Dicionario do banco
        stats_db = self.populate_from_db(connection_id, company_code, environment_id, progress_callback)

        # Fase 2: Fontes do filesystem
        stats_fontes = self.parse_fontes(fontes_dir, mapa_modulos_path, progress_callback)

        # Merge stats
        stats = {**stats_db, **stats_fontes}
        stats["_mode"] = "hybrid"
        return stats

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


# ---------------------------------------------------------------------------
# Ingestao de CSVs padrao (standalone — popula tabelas padrao_* para diff)
# ---------------------------------------------------------------------------

_PADRAO_SX_MAP = {
    "SX2": (parser_sx.parse_padrao_sx2, "padrao_tabelas",
            "INSERT OR REPLACE INTO padrao_tabelas (codigo, nome, modo, custom) VALUES (:codigo, :nome, :modo, :custom)"),
    "SX3": (parser_sx.parse_padrao_sx3, "padrao_campos",
            "INSERT OR REPLACE INTO padrao_campos (tabela, campo, tipo, tamanho, decimal, titulo, descricao, "
            "validacao, inicializador, obrigatorio, custom, f3, cbox, vlduser, when_expr, proprietario, browse, "
            "trigger_flag, visual, context, folder) VALUES (:tabela, :campo, :tipo, :tamanho, :decimal, :titulo, "
            ":descricao, :validacao, :inicializador, :obrigatorio, :custom, :f3, :cbox, :vlduser, :when_expr, "
            ":proprietario, :browse, :trigger_flag, :visual, :context, :folder)"),
    "SIX": (parser_sx.parse_padrao_six, "padrao_indices",
            "INSERT OR REPLACE INTO padrao_indices (tabela, ordem, chave, descricao, proprietario, f3, nickname, "
            "showpesq, custom) VALUES (:tabela, :ordem, :chave, :descricao, :proprietario, :f3, :nickname, "
            ":showpesq, :custom)"),
    "SX7": (parser_sx.parse_padrao_sx7, "padrao_gatilhos",
            "INSERT OR REPLACE INTO padrao_gatilhos (campo_origem, sequencia, campo_destino, regra, tipo, tabela, "
            "condicao, proprietario, seek, alias, ordem, chave, custom) VALUES (:campo_origem, :sequencia, "
            ":campo_destino, :regra, :tipo, :tabela, :condicao, :proprietario, :seek, :alias, :ordem, :chave, :custom)"),
    "SX6": (parser_sx.parse_padrao_sx6, "padrao_parametros",
            "INSERT OR REPLACE INTO padrao_parametros (filial, variavel, tipo, descricao, conteudo, proprietario, "
            "custom) VALUES (:filial, :variavel, :tipo, :descricao, :conteudo, :proprietario, :custom)"),
}


def ingest_padrao_sxs(db: Database, padrao_csv_dir: Path) -> dict:
    """Ingere CSVs SX padrao nas tabelas padrao_* para comparacao diff.

    Args:
        db: Database do workspace (ja inicializado)
        padrao_csv_dir: Diretorio com CSVs do dicionario padrao TOTVS

    Returns:
        dict: {sx_name: count_ou_erro, ...}
    """
    import gc
    summary = {}
    conn = db.get_raw_conn()
    # Garantir que nao ha transacao ativa antes de mudar PRAGMAs
    try:
        conn.commit()
    except Exception:
        pass
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    for sx_name, (parser_fn, table_name, insert_sql) in _PADRAO_SX_MAP.items():
        csv_path = _find_csv_ci(padrao_csv_dir, f"{sx_name}.csv")
        if not csv_path:
            summary[sx_name] = "skipped"
            continue

        try:
            conn.execute(f"DELETE FROM {table_name}")
            conn.commit()

            rows = parser_fn(csv_path)
            batch = []
            for i, row in enumerate(rows):
                batch.append(row)
                if len(batch) >= 1000:
                    conn.executemany(insert_sql, batch)
                    conn.commit()
                    batch = []
                if (i + 1) % 5000 == 0:
                    gc.collect()
            if batch:
                conn.executemany(insert_sql, batch)
                conn.commit()

            count = len(rows)
            del rows, batch
            gc.collect()

            db.execute(
                "INSERT OR REPLACE INTO ingest_progress (item, fase, status) VALUES (?, 1, 'done')",
                (f"padrao_{sx_name}",))
            db.commit()
            summary[sx_name] = count
            logger.info("Padrao %s: %d registros ingeridos", sx_name, count)
        except Exception as e:
            db.execute(
                "INSERT OR REPLACE INTO ingest_progress (item, fase, status, error_msg) VALUES (?, 1, 'error', ?)",
                (f"padrao_{sx_name}", str(e)))
            db.commit()
            summary[sx_name] = f"error: {e}"
            logger.warning("Erro ingestao padrao %s: %s", sx_name, e)

    try:
        conn.commit()
    except Exception:
        pass
    conn.execute("PRAGMA synchronous=FULL")
    conn.commit()
    return summary


def calculate_diff(db: Database) -> dict:
    """Compara tabelas do cliente vs padrao e popula tabela diff.

    Compara: campos (SX3) e gatilhos (SX7).

    Returns:
        dict: {campos: {adicionado: N, alterado: N, removido: N}, gatilhos: {...}}
    """
    conn = db.get_raw_conn()
    conn.execute("DELETE FROM diff")
    conn.commit()

    summary = {}

    # ── Campos diff (SX3) ──
    stats = {"adicionado": 0, "alterado": 0, "removido": 0}

    # ADDED: no cliente mas nao no padrao
    added = conn.execute("""
        SELECT c.tabela, c.campo
        FROM campos c
        LEFT JOIN padrao_campos p ON c.tabela = p.tabela AND c.campo = p.campo
        WHERE p.campo IS NULL
    """).fetchall()
    batch = []
    for tabela, campo in added:
        batch.append(("campo", tabela, campo, "adicionado", "", "", "", ""))
        if len(batch) >= 1000:
            conn.executemany(
                "INSERT OR REPLACE INTO diff (tipo_sx, tabela, chave, acao, campo_diff, valor_padrao, valor_cliente, modulo) VALUES (?,?,?,?,?,?,?,?)",
                batch)
            conn.commit()
            batch = []
    if batch:
        conn.executemany(
            "INSERT OR REPLACE INTO diff (tipo_sx, tabela, chave, acao, campo_diff, valor_padrao, valor_cliente, modulo) VALUES (?,?,?,?,?,?,?,?)",
            batch)
        conn.commit()
    stats["adicionado"] = len(added)
    del added, batch

    # REMOVED: no padrao mas nao no cliente
    removed = conn.execute("""
        SELECT p.tabela, p.campo
        FROM padrao_campos p
        LEFT JOIN campos c ON p.tabela = c.tabela AND p.campo = c.campo
        WHERE c.campo IS NULL
    """).fetchall()
    batch = []
    for tabela, campo in removed:
        batch.append(("campo", tabela, campo, "removido", "", "", "", ""))
        if len(batch) >= 1000:
            conn.executemany(
                "INSERT OR REPLACE INTO diff (tipo_sx, tabela, chave, acao, campo_diff, valor_padrao, valor_cliente, modulo) VALUES (?,?,?,?,?,?,?,?)",
                batch)
            conn.commit()
            batch = []
    if batch:
        conn.executemany(
            "INSERT OR REPLACE INTO diff (tipo_sx, tabela, chave, acao, campo_diff, valor_padrao, valor_cliente, modulo) VALUES (?,?,?,?,?,?,?,?)",
            batch)
        conn.commit()
    stats["removido"] = len(removed)
    del removed, batch

    # ALTERED: existe nos dois mas validacao, tamanho ou tipo difere
    altered = conn.execute("""
        SELECT c.tabela, c.campo,
               p.validacao, c.validacao,
               p.tamanho, c.tamanho,
               p.tipo, c.tipo
        FROM campos c
        INNER JOIN padrao_campos p ON c.tabela = p.tabela AND c.campo = p.campo
        WHERE c.validacao != p.validacao
           OR c.tamanho != p.tamanho
           OR c.tipo != p.tipo
    """).fetchall()
    batch = []
    for tabela, campo, p_valid, c_valid, p_tam, c_tam, p_tipo, c_tipo in altered:
        if p_valid != c_valid:
            batch.append(("campo", tabela, campo, "alterado", "validacao", str(p_valid), str(c_valid), ""))
        if p_tam != c_tam:
            batch.append(("campo", tabela, campo, "alterado", "tamanho", str(p_tam), str(c_tam), ""))
        if p_tipo != c_tipo:
            batch.append(("campo", tabela, campo, "alterado", "tipo", str(p_tipo), str(c_tipo), ""))
        if len(batch) >= 1000:
            conn.executemany(
                "INSERT OR REPLACE INTO diff (tipo_sx, tabela, chave, acao, campo_diff, valor_padrao, valor_cliente, modulo) VALUES (?,?,?,?,?,?,?,?)",
                batch)
            conn.commit()
            batch = []
    if batch:
        conn.executemany(
            "INSERT OR REPLACE INTO diff (tipo_sx, tabela, chave, acao, campo_diff, valor_padrao, valor_cliente, modulo) VALUES (?,?,?,?,?,?,?,?)",
            batch)
        conn.commit()
    stats["alterado"] = len(altered)
    del altered, batch
    summary["campos"] = stats

    # ── Gatilhos diff (SX7) ──
    stats = {"adicionado": 0, "alterado": 0, "removido": 0}

    added = conn.execute("""
        SELECT c.campo_origem, c.sequencia
        FROM gatilhos c
        LEFT JOIN padrao_gatilhos p ON c.campo_origem = p.campo_origem AND c.sequencia = p.sequencia
        WHERE p.campo_origem IS NULL
    """).fetchall()
    batch = [("gatilho", r[0], r[1], "adicionado", "", "", "", "") for r in added]
    if batch:
        conn.executemany(
            "INSERT OR REPLACE INTO diff (tipo_sx, tabela, chave, acao, campo_diff, valor_padrao, valor_cliente, modulo) VALUES (?,?,?,?,?,?,?,?)",
            batch)
        conn.commit()
    stats["adicionado"] = len(added)

    removed = conn.execute("""
        SELECT p.campo_origem, p.sequencia
        FROM padrao_gatilhos p
        LEFT JOIN gatilhos c ON p.campo_origem = c.campo_origem AND p.sequencia = c.sequencia
        WHERE c.campo_origem IS NULL
    """).fetchall()
    batch = [("gatilho", r[0], r[1], "removido", "", "", "", "") for r in removed]
    if batch:
        conn.executemany(
            "INSERT OR REPLACE INTO diff (tipo_sx, tabela, chave, acao, campo_diff, valor_padrao, valor_cliente, modulo) VALUES (?,?,?,?,?,?,?,?)",
            batch)
        conn.commit()
    stats["removido"] = len(removed)

    summary["gatilhos"] = stats
    logger.info("Diff calculado: campos=%s, gatilhos=%s", summary.get("campos"), summary.get("gatilhos"))
    return summary
