import gc
import re
import json
import asyncio
import functools
import os
from pathlib import Path
from typing import Optional, AsyncGenerator
from app.services.workspace.workspace_db import Database
from app.services.workspace.parser_sx import parse_sx2, parse_sx3, parse_six, parse_sx7, parse_sx1, parse_sx5, parse_sx6, parse_sx9, parse_sxa, parse_sxb, parse_mpmenu, parse_jobs, parse_schedules, _read_csv, _safe_int
from app.services.workspace.parser_sx import parse_padrao_sx2, parse_padrao_sx3, parse_padrao_six, parse_padrao_sx7, parse_padrao_sx6
from app.services.workspace.parser_source import parse_source, MAX_CHUNK_CHARS, _read_file, _extract_tables, _extract_fields_ref, _extract_calls_u, _extract_params, _find_func_body_end
from app.services.workspace.vectorstore import VectorStore

# Memory limits
BATCH_COMMIT_SIZE = 5         # Commit DB every N files (smaller = less RAM)
BATCH_GC_SIZE = 10            # Force garbage collection every N files
MAX_CHUNKS_PER_BATCH = 100    # Max chunks to send to ChromaDB at once
MAX_RAM_MB = 512              # Pause and GC if Python process exceeds this

# Pre-compiled regex for chunk splitting (avoids recompiling per file)
_FUNC_RE = re.compile(r'((?:Static\s+|User\s+|Main\s+)?Function\s+(\w+))', re.IGNORECASE)


def _get_mem_mb() -> float:
    """Get current process memory in MB (works on Windows)."""
    try:
        import psutil
        return psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
    except ImportError:
        return 0

MAPA_PATH = Path(__file__).parent.parent.parent / "templates" / "processos" / "mapa-modulos.json"

@functools.lru_cache(maxsize=1)
def _load_mapa():
    if not MAPA_PATH.exists():
        return {}
    return json.loads(MAPA_PATH.read_text(encoding="utf-8"))

# Heuristic: filename prefix → module mapping
# NOTE: Client-specific prefixes (MGF*) are optional hints, NOT reliable across clients.
# Standard Protheus prefixes (MATA*, FINA*, CTBA*) are universal.
# Priority: mapa-modulos.json rotinas > table overlap > prefix (lowest priority)
_PREFIX_TO_MODULE = {
    # Standard Protheus rotinas (universal)
    "MATA1": "compras", "MATA4": "faturamento",
    "FINA": "financeiro", "CTBA": "contabilidade",
    "MATA9": "estoque", "MATA2": "estoque", "MATA3": "estoque",
    # Client-specific (Marfrig naming convention — may not apply to other clients)
    "MGFCOM": "compras", "MGFFAT": "faturamento", "MGFFIN": "financeiro",
    "MGFEST": "estoque", "MGFFIS": "fiscal", "MGFCTB": "contabilidade",
    "MGFEEC": "engenharia", "MGFGFE": "gestao_frota", "MGFCRM": "crm",
    "MGFINT": "integracao", "MGFWSS": "webservice", "MGFWSC": "webservice",
    "MGFTAE": "tae", "MGFPCP": "pcp", "MGFRH": "rh",
}


def _detect_by_prefix(arquivo: str) -> Optional[str]:
    """Detect module from filename prefix heuristic."""
    nome = Path(arquivo).stem.upper()
    # Try longest prefixes first (MGFCOM before MGF)
    for prefix in sorted(_PREFIX_TO_MODULE.keys(), key=len, reverse=True):
        if nome.startswith(prefix):
            return _PREFIX_TO_MODULE[prefix]
    return None


def _detect_module_fast(tabelas_ref: list[str], arquivo: str, mapa: dict) -> Optional[str]:
    """Detect module — priority: rotina name > table overlap > filename prefix."""
    nome = Path(arquivo).stem.upper()
    # 1. Check rotinas in mapa (universal — works for any client)
    for modulo, info in mapa.items():
        if nome in [r.upper() for r in info["rotinas"]]:
            return modulo
    # 2. Check table overlap (universal — analyzes actual code references)
    if tabelas_ref:
        scores = {}
        for modulo, info in mapa.items():
            count = len(set(t.upper() for t in tabelas_ref) & set(t.upper() for t in info["tabelas"]))
            if count > 0:
                scores[modulo] = count
        if scores:
            return max(scores, key=scores.get)
    # 3. Filename prefix heuristic (lowest priority — may be client-specific)
    by_prefix = _detect_by_prefix(arquivo)
    if by_prefix:
        return by_prefix
    return None


def detect_module(tabelas_ref: list[str], arquivo: str) -> Optional[str]:
    mapa = _load_mapa()
    return _detect_module_fast(tabelas_ref, arquivo, mapa)


def reingest_fonte(file_path: Path, db_path: Path) -> dict:
    """Re-ingest a single fonte after ProtheusDoc injection.

    Updates both metadados (tabela fontes) and chunks (tabela fonte_chunks).
    Lightweight: reads, parses, updates, commits — one file only.
    """
    import sqlite3

    parsed = parse_source(file_path, include_chunks=True)
    modulo = detect_module(
        parsed["tabelas_ref"] + parsed.get("write_tables", []),
        parsed["arquivo"]
    )
    arquivo = parsed["arquivo"]

    conn = sqlite3.connect(str(db_path))
    try:
        # Update metadados
        try:
            conn.execute("ALTER TABLE fontes ADD COLUMN reclock_tables TEXT DEFAULT '[]'")
        except Exception:
            pass
        conn.execute(
            "INSERT OR REPLACE INTO fontes (arquivo, caminho, tipo, modulo, funcoes, user_funcs, pontos_entrada, tabelas_ref, write_tables, reclock_tables, includes, calls_u, calls_execblock, fields_ref, lines_of_code, hash, encoding) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (arquivo, parsed["caminho"], "custom", modulo,
             json.dumps(parsed["funcoes"]), json.dumps(parsed["user_funcs"]),
             json.dumps(parsed["pontos_entrada"]), json.dumps(parsed["tabelas_ref"]),
             json.dumps(parsed.get("write_tables", [])),
             json.dumps(parsed.get("reclock_tables", [])),
             json.dumps(parsed["includes"]),
             json.dumps(parsed.get("calls_u", [])),
             json.dumps(parsed.get("calls_execblock", [])),
             json.dumps(parsed.get("fields_ref", [])),
             parsed.get("lines_of_code", 0),
             parsed["hash"],
             parsed.get("encoding", "cp1252")))

        # Replace chunks
        conn.execute("DELETE FROM fonte_chunks WHERE arquivo=?", (arquivo,))
        chunks = parsed.get("chunks", [])
        for c in chunks:
            body = c["content"]
            if len(body) > MAX_CHUNK_CHARS:
                body = body[:MAX_CHUNK_CHARS]
            conn.execute(
                "INSERT INTO fonte_chunks (id, arquivo, funcao, content, modulo) VALUES (?,?,?,?,?)",
                (c["id"], arquivo, c["funcao"], body, modulo or ""))

        conn.commit()
    finally:
        conn.close()

    return {"arquivo": arquivo, "funcoes": len(parsed["funcoes"]), "chunks": len(chunks)}


class Ingestor:
    def __init__(self, db: Database, vectorstore: VectorStore):
        self.db = db
        self.vs = vectorstore

    async def run_fase1(self, csv_dir: Path) -> AsyncGenerator[dict, None]:
        files = {"SX2": parse_sx2, "SX3": parse_sx3, "SIX": parse_six, "SX7": parse_sx7, "SX1": parse_sx1, "SX5": parse_sx5, "SX6": parse_sx6, "SX9": parse_sx9, "SXA": parse_sxa, "SXB": parse_sxb}
        for sx_name, parser_fn in files.items():
            csv_path = csv_dir / f"{sx_name}.csv"
            if not csv_path.exists():
                csv_path = csv_dir / f"{sx_name.lower()}.csv"
            if not csv_path.exists():
                yield {"fase": 1, "item": sx_name, "status": "skipped", "msg": f"{sx_name}.csv not found"}
                continue
            try:
                rows = parser_fn(csv_path)
                self._store_sx(sx_name, rows)
                self.db.execute(
                    "INSERT OR REPLACE INTO ingest_progress (item, fase, status) VALUES (?, 1, 'done')",
                    (f"{sx_name}.csv",))
                self.db.commit()
                yield {"fase": 1, "item": sx_name, "status": "done", "count": len(rows)}
            except Exception as e:
                self.db.execute(
                    "INSERT OR REPLACE INTO ingest_progress (item, fase, status, error_msg) VALUES (?, 1, 'error', ?)",
                    (f"{sx_name}.csv", str(e)))
                self.db.commit()
                yield {"fase": 1, "item": sx_name, "status": "error", "msg": str(e)}

        # ── mpmenu (menus) ──
        mpmenu_check = csv_dir / "mpmenu_menu.csv"
        if not mpmenu_check.exists():
            # Case-insensitive fallback (Linux)
            for f in csv_dir.iterdir():
                if f.name.lower() == "mpmenu_menu.csv":
                    mpmenu_check = f
                    break
        if mpmenu_check.exists():
            try:
                menu_rows = parse_mpmenu(csv_dir)
                conn = self.db.get_raw_conn()
                conn.execute("DELETE FROM menus")
                batch = []
                for i, row in enumerate(menu_rows):
                    batch.append((row["modulo"], row["rotina"], row["nome"], row["menu"], row["ordem"]))
                    if len(batch) >= 1000:
                        conn.executemany(
                            "INSERT OR REPLACE INTO menus (modulo, rotina, nome, menu, ordem) VALUES (?,?,?,?,?)",
                            batch)
                        conn.commit()
                        batch = []
                        if i % 5000 == 0:
                            gc.collect()
                if batch:
                    conn.executemany(
                        "INSERT OR REPLACE INTO menus (modulo, rotina, nome, menu, ordem) VALUES (?,?,?,?,?)",
                        batch)
                    conn.commit()
                del menu_rows, batch
                gc.collect()
                self.db.execute(
                    "INSERT OR REPLACE INTO ingest_progress (item, fase, status) VALUES (?, 1, 'done')",
                    ("mpmenu",))
                self.db.commit()
                yield {"fase": 1, "item": "mpmenu", "status": "done", "count": conn.execute("SELECT COUNT(*) FROM menus").fetchone()[0]}
            except Exception as e:
                self.db.execute(
                    "INSERT OR REPLACE INTO ingest_progress (item, fase, status, error_msg) VALUES (?, 1, 'error', ?)",
                    ("mpmenu", str(e)))
                self.db.commit()
                yield {"fase": 1, "item": "mpmenu", "status": "error", "msg": str(e)}

        # ── jobs ──
        job_csv = csv_dir / "job_detalhado_bash.csv"
        if not job_csv.exists():
            job_csv = csv_dir / "job_detalhado.csv"
        if job_csv.exists():
            try:
                job_rows = parse_jobs(job_csv)
                conn = self.db.get_raw_conn()
                conn.execute("DELETE FROM jobs")
                conn.executemany(
                    "INSERT OR REPLACE INTO jobs (arquivo_ini, sessao, rotina, refresh_rate, parametros) "
                    "VALUES (:arquivo_ini, :sessao, :rotina, :refresh_rate, :parametros)",
                    job_rows)
                conn.commit()
                del job_rows
                gc.collect()
                self.db.execute(
                    "INSERT OR REPLACE INTO ingest_progress (item, fase, status) VALUES (?, 1, 'done')",
                    ("jobs",))
                self.db.commit()
                yield {"fase": 1, "item": "jobs", "status": "done", "count": conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]}
            except Exception as e:
                self.db.execute(
                    "INSERT OR REPLACE INTO ingest_progress (item, fase, status, error_msg) VALUES (?, 1, 'error', ?)",
                    ("jobs", str(e)))
                self.db.commit()
                yield {"fase": 1, "item": "jobs", "status": "error", "msg": str(e)}
        else:
            yield {"fase": 1, "item": "jobs", "status": "skipped", "msg": "job CSV not found"}

        # ── schedules ──
        sched_csv = csv_dir / "schedule_decodificado.csv"
        if sched_csv.exists():
            try:
                sched_rows = parse_schedules(sched_csv)
                conn = self.db.get_raw_conn()
                conn.execute("DELETE FROM schedules")
                conn.executemany(
                    "INSERT OR REPLACE INTO schedules (codigo, rotina, empresa_filial, environment, modulo, status, "
                    "tipo_recorrencia, detalhe_recorrencia, execucoes_dia, intervalo, hora_inicio, "
                    "data_criacao, ultima_execucao, ultima_hora, recorrencia_raw) "
                    "VALUES (:codigo, :rotina, :empresa_filial, :environment, :modulo, :status, "
                    ":tipo_recorrencia, :detalhe_recorrencia, :execucoes_dia, :intervalo, :hora_inicio, "
                    ":data_criacao, :ultima_execucao, :ultima_hora, :recorrencia_raw)",
                    sched_rows)
                conn.commit()
                del sched_rows
                gc.collect()
                self.db.execute(
                    "INSERT OR REPLACE INTO ingest_progress (item, fase, status) VALUES (?, 1, 'done')",
                    ("schedules",))
                self.db.commit()
                yield {"fase": 1, "item": "schedules", "status": "done", "count": conn.execute("SELECT COUNT(*) FROM schedules").fetchone()[0]}
            except Exception as e:
                self.db.execute(
                    "INSERT OR REPLACE INTO ingest_progress (item, fase, status, error_msg) VALUES (?, 1, 'error', ?)",
                    ("schedules", str(e)))
                self.db.commit()
                yield {"fase": 1, "item": "schedules", "status": "error", "msg": str(e)}
        else:
            yield {"fase": 1, "item": "schedules", "status": "skipped", "msg": "schedule CSV not found"}

        # ── SXG (grupos de campo) ──
        sxg_csv = csv_dir / "SXG.csv"
        if not sxg_csv.exists():
            for f in csv_dir.iterdir():
                if f.name.lower() == "sxg.csv":
                    sxg_csv = f
                    break
        if sxg_csv.exists():
            try:
                sxg_rows = _read_csv(sxg_csv)
                conn = self.db.get_raw_conn()
                conn.execute("DELETE FROM grupos_campo")
                batch = []
                for row in sxg_rows:
                    grupo = row.get("XG_GRUPO", "").strip()
                    if not grupo:
                        continue
                    # Count campos in this group
                    total = conn.execute("SELECT COUNT(*) FROM campos WHERE grpsxg=?", (grupo,)).fetchone()[0]
                    batch.append((
                        grupo,
                        row.get("XG_DESCRI", "").strip(),
                        _safe_int(row.get("XG_SIZEMAX", "0")),
                        _safe_int(row.get("XG_SIZEMIN", "0")),
                        _safe_int(row.get("XG_SIZE", "0")),
                        total,
                    ))
                conn.executemany(
                    "INSERT OR REPLACE INTO grupos_campo (grupo, descricao, tamanho_max, tamanho_min, tamanho, total_campos) VALUES (?,?,?,?,?,?)",
                    batch)
                conn.commit()
                yield {"fase": 1, "item": "SXG", "status": "done", "count": len(batch)}
            except Exception as e:
                yield {"fase": 1, "item": "SXG", "status": "error", "msg": str(e)}
        else:
            yield {"fase": 1, "item": "SXG", "status": "skipped", "msg": "SXG.csv not found"}

    def _store_sx(self, sx_name: str, rows: list[dict]):
        if sx_name == "SX2":
            self.db.executemany(
                "INSERT OR REPLACE INTO tabelas (codigo, nome, modo, custom) VALUES (:codigo, :nome, :modo, :custom)", rows)
        elif sx_name == "SX3":
            self.db.executemany(
                "INSERT OR REPLACE INTO campos (tabela, campo, tipo, tamanho, decimal, titulo, descricao, validacao, inicializador, obrigatorio, custom, f3, cbox, vlduser, when_expr, proprietario, browse, trigger_flag, visual, context, folder, grpsxg) VALUES (:tabela, :campo, :tipo, :tamanho, :decimal, :titulo, :descricao, :validacao, :inicializador, :obrigatorio, :custom, :f3, :cbox, :vlduser, :when_expr, :proprietario, :browse, :trigger_flag, :visual, :context, :folder, :grpsxg)", rows)
        elif sx_name == "SIX":
            self.db.executemany(
                "INSERT OR REPLACE INTO indices (tabela, ordem, chave, descricao, proprietario, f3, nickname, showpesq, custom) VALUES (:tabela, :ordem, :chave, :descricao, :proprietario, :f3, :nickname, :showpesq, :custom)", rows)
        elif sx_name == "SX7":
            self.db.executemany(
                "INSERT OR REPLACE INTO gatilhos (campo_origem, sequencia, campo_destino, regra, tipo, tabela, condicao, proprietario, seek, alias, ordem, chave, custom) VALUES (:campo_origem, :sequencia, :campo_destino, :regra, :tipo, :tabela, :condicao, :proprietario, :seek, :alias, :ordem, :chave, :custom)", rows)
        elif sx_name == "SX1":
            self.db.executemany(
                "INSERT OR REPLACE INTO perguntas (grupo, ordem, pergunta, variavel, tipo, tamanho, decimal, f3, validacao, conteudo_padrao) VALUES (:grupo, :ordem, :pergunta, :variavel, :tipo, :tamanho, :decimal, :f3, :validacao, :conteudo_padrao)", rows)
        elif sx_name == "SX5":
            self.db.executemany(
                "INSERT OR REPLACE INTO tabelas_genericas (filial, tabela, chave, descricao, custom) VALUES (:filial, :tabela, :chave, :descricao, :custom)", rows)
        elif sx_name == "SX6":
            self.db.executemany(
                "INSERT OR REPLACE INTO parametros (filial, variavel, tipo, descricao, conteudo, proprietario, custom) VALUES (:filial, :variavel, :tipo, :descricao, :conteudo, :proprietario, :custom)", rows)
        elif sx_name == "SX9":
            self.db.executemany(
                "INSERT OR REPLACE INTO relacionamentos (tabela_origem, identificador, tabela_destino, expressao_origem, expressao_destino, proprietario, condicao_sql, custom) VALUES (:tabela_origem, :identificador, :tabela_destino, :expressao_origem, :expressao_destino, :proprietario, :condicao_sql, :custom)", rows)
        elif sx_name == "SXA":
            self.db.executemany(
                "INSERT OR REPLACE INTO pastas (alias, ordem, descricao, proprietario, agrupamento) VALUES (:alias, :ordem, :descricao, :proprietario, :agrupamento)", rows)
        elif sx_name == "SXB":
            self.db.executemany(
                "INSERT OR REPLACE INTO consultas (alias, tipo, sequencia, coluna, descricao, conteudo) VALUES (:alias, :tipo, :sequencia, :coluna, :descricao, :conteudo)", rows)

    async def run_fase2(self, fontes_custom: Path, fontes_padrao: Optional[Path] = None) -> AsyncGenerator[dict, None]:
        """Fase 2: Parse fontes — 2 passadas para controle de memória.

        Pass 1: metadados (leve — só extrai nomes, tabelas, funções)
        Pass 2: chunks (pesado — usa sqlite3 direto com PRAGMAs otimizados)
          - Commit a cada arquivo (não acumula)
          - Lê, chunka, insere e descarta — 1 arquivo na RAM por vez
          - PRAGMAs: journal_mode=WAL, synchronous=NORMAL, cache_size=2000
        """
        for folder, tipo in [(fontes_custom, "custom"), (fontes_padrao, "padrao")]:
            if not folder or not folder.exists():
                continue
            files = sorted(folder.glob("*.prw")) + sorted(folder.glob("*.PRW")) + sorted(folder.glob("*.tlpp")) + sorted(folder.glob("*.TLPP"))
            # Deduplicate (in case filesystem is case-insensitive)
            seen_names = set()
            unique_files = []
            for f in files:
                if f.name.lower() not in seen_names:
                    seen_names.add(f.name.lower())
                    unique_files.append(f)
            files = unique_files
            total = len(files)

            # ── Pass 1: metadados (sem chunks — rápido e leve) ──
            done_count = 0
            error_count = 0
            yield {"fase": 2, "status": "started", "tipo": tipo, "total": total, "pass": "metadata"}

            # Ensure optional columns exist (idempotent)
            for col_def in ["encoding TEXT", "reclock_tables TEXT DEFAULT '[]'"]:
                try:
                    self.db.execute(f"ALTER TABLE fontes ADD COLUMN {col_def}")
                except Exception:
                    pass

            # Clear operacoes_escrita for re-ingest (avoid duplicates)
            try:
                self.db.execute("DELETE FROM operacoes_escrita WHERE arquivo IN (SELECT arquivo FROM fontes WHERE tipo=?)", (tipo,))
                self.db.commit()
            except Exception:
                pass  # Table may not exist yet on first run

            for f in files:
                try:
                    parsed = parse_source(f, include_chunks=False)
                    modulo = detect_module(parsed["tabelas_ref"] + parsed.get("write_tables", []), parsed["arquivo"])

                    self.db.execute(
                        "INSERT OR REPLACE INTO fontes (arquivo, caminho, tipo, modulo, funcoes, user_funcs, pontos_entrada, tabelas_ref, write_tables, reclock_tables, includes, calls_u, calls_execblock, fields_ref, lines_of_code, hash, encoding) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (parsed["arquivo"], parsed["caminho"], tipo, modulo,
                         json.dumps(parsed["funcoes"]), json.dumps(parsed["user_funcs"]),
                         json.dumps(parsed["pontos_entrada"]), json.dumps(parsed["tabelas_ref"]),
                         json.dumps(parsed.get("write_tables", [])),
                         json.dumps(parsed.get("reclock_tables", [])),
                         json.dumps(parsed["includes"]),
                         json.dumps(parsed.get("calls_u", [])),
                         json.dumps(parsed.get("calls_execblock", [])),
                         json.dumps(parsed.get("fields_ref", [])),
                         parsed.get("lines_of_code", 0),
                         parsed["hash"],
                         parsed.get("encoding", "cp1252")))

                    # Insert operacoes_escrita (structured write operations)
                    ops = parsed.get("operacoes_escrita", [])
                    if ops:
                        for op in ops:
                            self.db.execute(
                                "INSERT INTO operacoes_escrita (arquivo, funcao, tipo, tabela, campos, origens, condicao, linha) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                (parsed["arquivo"], op["funcao"], op["tipo"], op["tabela"],
                                 json.dumps(op.get("campos", []), ensure_ascii=False),
                                 json.dumps(op.get("origens", {}), ensure_ascii=False),
                                 op.get("condicao", ""), op.get("linha", 0)))

                    del parsed
                    done_count += 1

                    if done_count % BATCH_COMMIT_SIZE == 0:
                        self.db.commit()

                    if done_count % 500 == 0:
                        mem = _get_mem_mb()
                        gc.collect()
                        yield {"fase": 2, "status": "progress", "pass": "metadata", "done": done_count, "total": total, "mem_mb": round(mem)}

                except Exception as e:
                    error_count += 1
                    if error_count <= 5:
                        yield {"fase": 2, "item": f.name, "status": "error", "msg": str(e)[:200]}

            self.db.commit()
            gc.collect()
            yield {"fase": 2, "status": "pass_complete", "pass": "metadata", "done": done_count, "errors": error_count, "total": total}

            # ── Pass 2: chunks (pesado — sqlite3 direto, commit por arquivo) ──
            chunk_count = 0
            done_count = 0
            error_count = 0
            yield {"fase": 2, "status": "started", "tipo": tipo, "total": total, "pass": "chunks"}

            # Use raw connection with optimized PRAGMAs for bulk insert
            conn = self.db.get_raw_conn()
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=2000")

            # Pre-load module map once (avoid reloading per file)
            mapa = _load_mapa()

            for f in files:
                try:
                    # Read file as bytes, decode once, extract chunks inline
                    raw = f.read_bytes()
                    if not raw or len(raw) > 5_000_000:  # Skip empty or >5MB files
                        done_count += 1
                        continue

                    # Decode: cp1252 fast path (99% of Protheus files)
                    try:
                        content = raw.decode("cp1252")
                    except UnicodeDecodeError:
                        content = raw.decode("latin-1")
                    del raw  # Free bytes immediately

                    # Extract function boundaries with regex
                    matches = list(_FUNC_RE.finditer(content))

                    # Detect module from content (lightweight — just regex, no full parse)
                    tables = set()
                    tables.update(re.findall(r'DbSelectArea\s*\(\s*["\'](\w+)', content, re.IGNORECASE))
                    tables.update(re.findall(r'\b(S[A-Z][0-9A-Z])\s*->', content))
                    tables.update(re.findall(r'\b([ZQ][A-Z][0-9A-Z])\s*->', content))
                    modulo = _detect_module_fast(list(tables), f.name, mapa)

                    # Build chunk tuples directly — no intermediate dicts
                    chunk_tuples = []
                    if matches:
                        for i, m in enumerate(matches):
                            start = m.start()
                            end = _find_func_body_end(content, matches[i + 1].start(), start) if i + 1 < len(matches) else len(content)
                            body = content[start:end].strip()
                            if len(body) > MAX_CHUNK_CHARS:
                                body = body[:MAX_CHUNK_CHARS]
                            chunk_tuples.append((
                                f"{f.name}::{m.group(2)}",
                                f.name,
                                m.group(2),
                                body,
                                modulo or ""
                            ))
                    else:
                        body = content[:MAX_CHUNK_CHARS]
                        chunk_tuples.append((f"{f.name}::full", f.name, "_full", body, modulo or ""))

                    del content, matches  # Free content immediately

                    # Insert + commit per file (no accumulation)
                    if chunk_tuples:
                        conn.executemany(
                            "INSERT OR REPLACE INTO fonte_chunks (id, arquivo, funcao, content, modulo) VALUES (?,?,?,?,?)",
                            chunk_tuples)
                        conn.commit()
                        chunk_count += len(chunk_tuples)
                        del chunk_tuples

                    done_count += 1

                    # Report progress every 500 files
                    if done_count % 500 == 0:
                        gc.collect()
                        mem = _get_mem_mb()
                        yield {"fase": 2, "status": "progress", "pass": "chunks", "done": done_count, "total": total, "chunks": chunk_count, "mem_mb": round(mem)}

                except Exception as e:
                    error_count += 1
                    try:
                        conn.commit()  # Commit even on error to free buffer
                    except Exception:
                        pass
                    if error_count <= 5:
                        yield {"fase": 2, "item": f.name, "status": "error", "msg": str(e)[:200]}

            # Restore default PRAGMAs
            conn.execute("PRAGMA synchronous=FULL")
            conn.commit()
            gc.collect()
            yield {"fase": 2, "status": "complete", "tipo": tipo, "done": done_count, "errors": error_count, "total": total, "chunks": chunk_count}

    async def run_fase3(self, llm, knowledge_dir: Path, modules: list[str] = None, max_concurrent: int = 2) -> AsyncGenerator[dict, None]:
        from app.services.workspace.knowledge import KnowledgeService
        from app.services.workspace.doc_generator import save_doc

        if modules is None:
            modules = self.get_detected_modules()
        semaphore = asyncio.Semaphore(max_concurrent)
        ks = KnowledgeService(self.db)
        results_queue = asyncio.Queue()

        async def _process_module(modulo: str):
            async with semaphore:
                try:
                    context_dicionario = ks.build_context_for_module(modulo)
                    context_fontes_parts = []
                    source_results = self.vs.search("fontes_custom", modulo, n_results=10)
                    for r in source_results:
                        context_fontes_parts.append(f"### Fonte: {r['metadata'].get('arquivo', '')}\n{r['content']}")
                    context_fontes = "\n\n".join(context_fontes_parts) if context_fontes_parts else "Sem fontes customizados."

                    await results_queue.put({"fase": 3, "item": modulo, "status": "agent_dicionarista"})
                    analise_dict = await asyncio.to_thread(llm.run_agent_dicionarista, context_dicionario, modulo)

                    await results_queue.put({"fase": 3, "item": modulo, "status": "agent_analista"})
                    analise_fontes = await asyncio.to_thread(llm.run_agent_analista_fontes, context_fontes, modulo)

                    await results_queue.put({"fase": 3, "item": modulo, "status": "agent_documentador"})
                    docs = await asyncio.to_thread(llm.run_agent_documentador, analise_dict, analise_fontes, modulo)

                    save_doc(knowledge_dir, modulo, "humano", docs.get("humano", ""))
                    save_doc(knowledge_dir, modulo, "ia", docs.get("ia", ""))
                    for camada in ["humano", "ia"]:
                        content = docs.get(camada, "")
                        if content:
                            self.vs.add_source_chunks("knowledge_cliente", [{
                                "id": f"{modulo}_{camada}", "content": content,
                                "processo": modulo, "modulo": modulo,
                            }])
                    self.db.execute(
                        "INSERT OR REPLACE INTO ingest_progress (item, fase, status) VALUES (?, 3, 'done')",
                        (f"module_{modulo}",))
                    self.db.commit()
                    await results_queue.put({"fase": 3, "item": modulo, "status": "done"})
                except Exception as e:
                    self.db.execute(
                        "INSERT OR REPLACE INTO ingest_progress (item, fase, status, error_msg) VALUES (?, 3, 'error', ?)",
                        (f"module_{modulo}", str(e)))
                    self.db.commit()
                    await results_queue.put({"fase": 3, "item": modulo, "status": "error", "msg": str(e)})

        # Launch all module tasks (semaphore controls concurrency)
        tasks = [asyncio.create_task(_process_module(m)) for m in modules]

        # Yield results as they come in
        done_count = 0
        total = len(modules)
        while done_count < total:
            item = await results_queue.get()
            yield item
            if item.get("status") in ("done", "error"):
                done_count += 1

        # Ensure all tasks complete
        await asyncio.gather(*tasks, return_exceptions=True)

    def get_detected_modules(self) -> list[str]:
        mapa = _load_mapa()
        detected = set()
        rows = self.db.execute("SELECT DISTINCT modulo FROM fontes WHERE modulo IS NOT NULL").fetchall()
        for row in rows:
            detected.add(row[0])
        tabelas = [r[0] for r in self.db.execute("SELECT codigo FROM tabelas").fetchall()]
        for modulo, info in mapa.items():
            if set(t.upper() for t in tabelas) & set(t.upper() for t in info["tabelas"]):
                detected.add(modulo)
        return sorted(detected)

    def get_fase3_estimate(self) -> dict:
        modules = self.get_detected_modules()
        return {"modules": modules, "count": len(modules), "estimated_calls": len(modules)}


# ---------------------------------------------------------------------------
# Padrão SX ingestion (standalone functions, no Ingestor instance needed)
# ---------------------------------------------------------------------------

_PADRAO_SX_MAP = {
    "SX2": (parse_padrao_sx2, "padrao_tabelas",
            "INSERT OR REPLACE INTO padrao_tabelas (codigo, nome, modo, custom) VALUES (:codigo, :nome, :modo, :custom)"),
    "SX3": (parse_padrao_sx3, "padrao_campos",
            "INSERT OR REPLACE INTO padrao_campos (tabela, campo, tipo, tamanho, decimal, titulo, descricao, validacao, inicializador, obrigatorio, custom, f3, cbox, vlduser, when_expr, proprietario, browse, trigger_flag, visual, context, folder) VALUES (:tabela, :campo, :tipo, :tamanho, :decimal, :titulo, :descricao, :validacao, :inicializador, :obrigatorio, :custom, :f3, :cbox, :vlduser, :when_expr, :proprietario, :browse, :trigger_flag, :visual, :context, :folder)"),
    "SIX": (parse_padrao_six, "padrao_indices",
            "INSERT OR REPLACE INTO padrao_indices (tabela, ordem, chave, descricao, proprietario, f3, nickname, showpesq, custom) VALUES (:tabela, :ordem, :chave, :descricao, :proprietario, :f3, :nickname, :showpesq, :custom)"),
    "SX7": (parse_padrao_sx7, "padrao_gatilhos",
            "INSERT OR REPLACE INTO padrao_gatilhos (campo_origem, sequencia, campo_destino, regra, tipo, tabela, condicao, proprietario, seek, alias, ordem, chave, custom) VALUES (:campo_origem, :sequencia, :campo_destino, :regra, :tipo, :tabela, :condicao, :proprietario, :seek, :alias, :ordem, :chave, :custom)"),
    "SX6": (parse_padrao_sx6, "padrao_parametros",
            "INSERT OR REPLACE INTO padrao_parametros (filial, variavel, tipo, descricao, conteudo, proprietario, custom) VALUES (:filial, :variavel, :tipo, :descricao, :conteudo, :proprietario, :custom)"),
}


def ingest_padrao_sxs(db: Database, padrao_csv_dir: Path) -> dict:
    """Ingest padrão (standard) SX CSVs into padrao_* tables.

    Returns summary dict: {sx_name: count_or_error, ...}
    """
    summary = {}
    conn = db.get_raw_conn()
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    for sx_name, (parser_fn, table_name, insert_sql) in _PADRAO_SX_MAP.items():
        csv_path = padrao_csv_dir / f"{sx_name}.csv"
        if not csv_path.exists():
            csv_path = padrao_csv_dir / f"{sx_name.lower()}.csv"
        if not csv_path.exists():
            summary[sx_name] = "skipped"
            continue

        try:
            # Clear existing data
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
        except Exception as e:
            db.execute(
                "INSERT OR REPLACE INTO ingest_progress (item, fase, status, error_msg) VALUES (?, 1, 'error', ?)",
                (f"padrao_{sx_name}", str(e)))
            db.commit()
            summary[sx_name] = f"error: {e}"

    conn.execute("PRAGMA synchronous=FULL")
    conn.commit()
    return summary


def calculate_diff(db: Database) -> dict:
    """Compare cliente tables vs padrao tables and populate the diff table.

    Currently diffs: campos (SX3) and gatilhos (SX7).
    Returns summary: {campos: {added: N, altered: N, removed: N}, gatilhos: {...}}
    """
    conn = db.get_raw_conn()
    conn.execute("DELETE FROM diff")
    conn.commit()

    summary = {}

    # ── Campos diff (SX3) ──
    stats = {"adicionado": 0, "alterado": 0, "removido": 0}

    # ADDED: in cliente but not in padrao
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

    # REMOVED: in padrao but not in cliente
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

    # ALTERED: exists in both but validacao, tamanho, or tipo differs
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

    # ADDED
    added = conn.execute("""
        SELECT g.campo_origem, g.sequencia, g.campo_destino
        FROM gatilhos g
        LEFT JOIN padrao_gatilhos p
            ON g.campo_origem = p.campo_origem
           AND g.sequencia = p.sequencia
           AND g.campo_destino = p.campo_destino
        WHERE p.campo_origem IS NULL
    """).fetchall()
    batch = []
    for co, seq, cd in added:
        key = f"{co}|{seq}|{cd}"
        batch.append(("gatilho", "", key, "adicionado", "", "", "", ""))
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

    # REMOVED
    removed = conn.execute("""
        SELECT p.campo_origem, p.sequencia, p.campo_destino
        FROM padrao_gatilhos p
        LEFT JOIN gatilhos g
            ON p.campo_origem = g.campo_origem
           AND p.sequencia = g.sequencia
           AND p.campo_destino = g.campo_destino
        WHERE g.campo_origem IS NULL
    """).fetchall()
    batch = []
    for co, seq, cd in removed:
        key = f"{co}|{seq}|{cd}"
        batch.append(("gatilho", "", key, "removido", "", "", "", ""))
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

    summary["gatilhos"] = stats

    gc.collect()
    return summary


# ── Fase 0: populate funcao_docs ──

# Pre-compiled regex for function signature extraction
_FUNC_SIG_RE = re.compile(
    r'((?:Static\s+|User\s+|Main\s+)?Function\s+(\w+)\s*(\([^)]*\))?)',
    re.IGNORECASE,
)

# Re-use the function boundary regex from _split_into_chunks
_FUNC_BOUNDARY_RE = re.compile(
    r'((?:Static\s+|User\s+|Main\s+)?Function\s+(\w+))',
    re.IGNORECASE,
)


def _detect_func_tipo(sig_line: str) -> str:
    """Detect function type from the signature line."""
    low = sig_line.strip().lower()
    if low.startswith("user "):
        return "User Function"
    elif low.startswith("static "):
        return "Static Function"
    elif low.startswith("main "):
        return "Main Function"
    return "Function"


def _extract_func_blocks(content: str) -> list[dict]:
    """Split file content into per-function blocks.

    Returns list of dicts with keys: funcao, tipo, assinatura, body.
    Memory-safe: uses indices, not copies until needed.
    """
    matches = list(_FUNC_BOUNDARY_RE.finditer(content))
    if not matches:
        return []

    blocks = []
    for i, match in enumerate(matches):
        start = match.start()
        end = _find_func_body_end(content, matches[i + 1].start(), start) if i + 1 < len(matches) else len(content)
        body = content[start:end]

        # Extract full signature with params from the body
        sig_match = _FUNC_SIG_RE.match(body)
        if sig_match:
            full_sig = sig_match.group(1).strip()
            func_name = sig_match.group(2)
            params = sig_match.group(3) or "()"
            assinatura = f"{func_name}{params}"
        else:
            func_name = match.group(2)
            full_sig = match.group(1).strip()
            assinatura = func_name + "()"

        tipo = _detect_func_tipo(full_sig)

        blocks.append({
            "funcao": func_name,
            "tipo": tipo,
            "assinatura": assinatura,
            "body": body,
        })
    return blocks


def populate_funcao_docs(db: Database, fontes_dir: Path) -> dict:
    """Fase 0: Auto-populate funcao_docs from .prw/.tlpp files.

    Extracts per-function metadata: tipo, assinatura, tabelas_ref, campos_ref, chama.
    Memory-safe: commits per file, gc.collect every 100 files.

    Returns summary dict with counts.
    """
    if not fontes_dir or not fontes_dir.exists():
        return {"status": "error", "msg": f"Directory not found: {fontes_dir}"}

    files = sorted(fontes_dir.glob("*.prw")) + sorted(fontes_dir.glob("*.PRW")) + sorted(fontes_dir.glob("*.tlpp")) + sorted(fontes_dir.glob("*.TLPP"))
    seen_names = set()
    unique_files = []
    for f in files:
        if f.name.lower() not in seen_names:
            seen_names.add(f.name.lower())
            unique_files.append(f)
    files = unique_files
    total = len(files)
    if total == 0:
        return {"status": "ok", "total_files": 0, "total_funcoes": 0}

    conn = db.get_raw_conn()
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    # Ensure params column exists (for existing databases)
    try:
        conn.execute("ALTER TABLE funcao_docs ADD COLUMN params TEXT")
    except Exception:
        pass

    total_funcoes = 0
    errors = 0

    for idx, fpath in enumerate(files):
        try:
            content = _read_file(fpath)
            if not content:
                continue

            blocks = _extract_func_blocks(content)
            arquivo = fpath.name

            for block in blocks:
                tabelas = _extract_tables(block["body"])
                campos = _extract_fields_ref(block["body"])
                chama = _extract_calls_u(block["body"])
                params = _extract_params(block["body"])

                conn.execute(
                    "INSERT OR REPLACE INTO funcao_docs "
                    "(arquivo, funcao, tipo, assinatura, resumo, tabelas_ref, campos_ref, chama, chamada_por, retorno, fonte, params) "
                    "VALUES (?, ?, ?, ?, '', ?, ?, ?, '', '', 'auto', ?)",
                    (
                        arquivo,
                        block["funcao"],
                        block["tipo"],
                        block["assinatura"],
                        json.dumps(tabelas),
                        json.dumps(campos),
                        json.dumps(chama),
                        json.dumps(params),
                    ),
                )
                total_funcoes += 1

            # Commit per file
            conn.commit()

            # Free memory from content and blocks
            del content, blocks

        except Exception:
            errors += 1

        # GC every 100 files
        if (idx + 1) % 100 == 0:
            gc.collect()

    gc.collect()

    # ── Second pass: populate chamada_por (reverse call graph) ──
    _populate_chamada_por(db)

    return {
        "status": "ok",
        "total_files": total,
        "total_funcoes": total_funcoes,
        "errors": errors,
    }


def _populate_chamada_por(db: Database):
    """Second pass: fill chamada_por by inverting the 'chama' relationships.

    For each function X that calls Y, add X to Y's chamada_por list.
    """
    conn = db.get_raw_conn()

    # Build reverse map: called_func -> set of callers
    reverse_map: dict[str, set[str]] = {}

    rows = conn.execute("SELECT arquivo, funcao, chama FROM funcao_docs").fetchall()
    for arquivo, funcao, chama_json in rows:
        if not chama_json:
            continue
        try:
            called = json.loads(chama_json)
        except (json.JSONDecodeError, TypeError):
            continue
        caller_id = funcao  # Use function name as caller identifier
        for called_func in called:
            called_upper = called_func.upper()
            if called_upper not in reverse_map:
                reverse_map[called_upper] = set()
            reverse_map[called_upper].add(caller_id)

    del rows

    # Now update chamada_por for each function that is called
    # We need to match by function name (case-insensitive)
    all_funcs = conn.execute("SELECT arquivo, funcao FROM funcao_docs").fetchall()
    batch_count = 0
    for arquivo, funcao in all_funcs:
        callers = reverse_map.get(funcao.upper(), set())
        if callers:
            conn.execute(
                "UPDATE funcao_docs SET chamada_por = ? WHERE arquivo = ? AND funcao = ?",
                (json.dumps(sorted(callers)), arquivo, funcao),
            )
            batch_count += 1
            if batch_count % 500 == 0:
                conn.commit()

    conn.commit()
    del all_funcs, reverse_map
    gc.collect()
