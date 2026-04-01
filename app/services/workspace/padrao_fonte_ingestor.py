"""Ingestor de fontes padrão Protheus — pipeline completo de ingestão.

Escaneia recursivamente o diretório padrão, parseia cada fonte, popula padrao.db
com metadados, funções, ExecBlocks detalhados e chunks para vetorização.
"""
import gc
import re
import json
import asyncio
import os
from pathlib import Path
from typing import Optional, AsyncGenerator

from app.services.workspace.padrao_database import PadraoDB
from app.services.workspace.padrao_parser import (
    parse_padrao_source, _find_func_body_end, MAX_CHUNK_CHARS,
)

# Memory limits
BATCH_COMMIT_SIZE = 5
BATCH_GC_SIZE = 10
MAX_CHUNKS_PER_BATCH = 100
MAX_RAM_MB = 512

# Extensions to parse
SOURCE_EXTENSIONS = {'.prw', '.tlpp', '.prx', '.prg'}

# Pre-compiled regex for chunk splitting
_FUNC_RE = re.compile(r'((?:Static\s+|User\s+|Main\s+)?Function\s+(\w+))', re.IGNORECASE)

# Module detection from directory path
_DIR_MODULE_MAP = {
    "materiais": "compras",
    "compras": "compras",
    "faturamento": "faturamento",
    "financeiro": "financeiro",
    "fiscal": "fiscal",
    "contabilidade": "contabilidade",
    "estoque": "estoque",
    "ativo": "ativo_fixo",
    "ponto": "rh",
    "rh": "rh",
    "gestao": "gestao",
    "livros": "fiscal",
    "call": "call_center",
    "crm": "crm",
    "manutencao": "manutencao",
    "pcp": "pcp",
    "qualidade": "qualidade",
    "sigaloja": "loja",
    "totvs": "framework",
    "fwclasses": "framework",
    "aplib": "framework",
}

# Filename prefix → module (heuristic fallback)
_PREFIX_TO_MODULE = {
    "MATA1": "compras", "MATA4": "faturamento",
    "FINA": "financeiro", "CTBA": "contabilidade",
    "MATA9": "estoque", "MATA2": "estoque", "MATA3": "estoque",
    "MATR": "ativo_fixo", "PONA": "rh",
    "GPEA": "rh", "TMKA": "call_center",
}


def _get_mem_mb() -> float:
    try:
        import psutil
        return psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
    except ImportError:
        return 0


def _detect_module_from_path(file_path: Path, tabelas_ref: list[str] = None) -> Optional[str]:
    """Detect module from directory path and filename prefix.

    Priority:
    1. Directory name mapping (most reliable for padrao structure)
    2. Filename prefix heuristic
    """
    # 1. Directory-based detection
    parts = [p.lower() for p in file_path.parts]
    for part in reversed(parts):
        for key, module in _DIR_MODULE_MAP.items():
            if key in part:
                return module

    # 2. Filename prefix
    nome = file_path.stem.upper()
    for prefix in sorted(_PREFIX_TO_MODULE.keys(), key=len, reverse=True):
        if nome.startswith(prefix):
            return _PREFIX_TO_MODULE[prefix]

    return None


def _scan_source_files(padrao_dir: Path) -> list[Path]:
    """Recursively find all source files in the padrao directory.

    Uses os.walk (single directory traversal) instead of rglob (one traversal per pattern).
    Much faster on Windows with large directory trees.
    """
    files = []
    exts = {e.lower() for e in SOURCE_EXTENSIONS}  # {'.prw', '.tlpp', '.prx', '.prg'}
    for dirpath, dirnames, filenames in os.walk(padrao_dir):
        for fname in filenames:
            if Path(fname).suffix.lower() in exts:
                files.append(Path(dirpath) / fname)
    return sorted(files, key=lambda f: f.name.lower())


class PadraoFonteIngestor:
    """Ingests standard Protheus sources into padrao.db."""

    def __init__(self, db: PadraoDB, padrao_dir: Path):
        self.db = db
        self.padrao_dir = padrao_dir

    async def run_ingest(self, vs=None) -> AsyncGenerator[dict, None]:
        """Full ingestion pipeline:

        Pass 1: Parse metadata — fontes, funcoes, execblocks
        Pass 2: Chunks — fonte_chunks (+ optional ChromaDB vectorization)

        Yields progress events for SSE streaming.
        """
        self.db.initialize()

        files = _scan_source_files(self.padrao_dir)
        total = len(files)

        if total == 0:
            yield {"status": "error", "msg": f"No source files found in {self.padrao_dir}"}
            return

        yield {"status": "started", "total": total, "pass": "metadata", "dir": str(self.padrao_dir)}

        # Save ingest metadata
        self.db.execute(
            "INSERT OR REPLACE INTO ingest_meta (key, value) VALUES (?, ?)",
            ("padrao_dir", str(self.padrao_dir))
        )
        self.db.execute(
            "INSERT OR REPLACE INTO ingest_meta (key, value) VALUES (?, ?)",
            ("total_files", str(total))
        )
        self.db.commit()

        # ── Pass 1: Metadata (fontes + funcoes + execblocks) ──────────────
        done_count = 0
        error_count = 0
        total_funcoes = 0
        total_execblocks = 0

        conn = self.db.get_raw_conn()
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=2000")

        for f in files:
            try:
                parsed = parse_padrao_source(f, include_chunks=False)

                # Relative path from padrao_dir
                try:
                    caminho_rel = str(f.relative_to(self.padrao_dir))
                except ValueError:
                    caminho_rel = str(f)

                modulo = _detect_module_from_path(f, parsed["tabelas_ref"])

                # Insert fonte metadata
                conn.execute(
                    """INSERT OR REPLACE INTO fontes
                    (arquivo, caminho, caminho_rel, tipo, modulo, funcoes, user_funcs,
                     tabelas_ref, write_tables, reclock_tables, includes,
                     calls_u, calls_execblock, fields_ref, source_type,
                     lines_of_code, hash, encoding)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (parsed["arquivo"], parsed["caminho"], caminho_rel,
                     f.suffix.lower().lstrip('.'), modulo,
                     json.dumps(parsed["funcoes"]),
                     json.dumps(parsed["user_funcs"]),
                     json.dumps(parsed["tabelas_ref"]),
                     json.dumps(parsed.get("write_tables", [])),
                     json.dumps(parsed.get("reclock_tables", [])),
                     json.dumps(parsed["includes"]),
                     json.dumps(parsed.get("calls_u", [])),
                     json.dumps(parsed.get("calls_execblock", [])),
                     json.dumps(parsed.get("fields_ref", [])),
                     parsed.get("source_type", ""),
                     parsed.get("lines_of_code", 0),
                     parsed["hash"],
                     parsed.get("encoding", "cp1252")))

                # Insert detailed ExecBlocks
                for eb in parsed.get("execblocks_detailed", []):
                    conn.execute(
                        """INSERT INTO execblocks
                        (arquivo, funcao, nome_pe, linha, linha_existblock,
                         parametros, variavel_retorno, retorno_usado,
                         tipo_retorno_inferido, comentario, operacao,
                         contexto, uso_condicional)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (parsed["arquivo"], eb["funcao"], eb["nome_pe"],
                         eb["linha"], eb.get("linha_existblock"),
                         eb["parametros"], eb["variavel_retorno"],
                         1 if eb["retorno_usado"] else 0,
                         eb["tipo_retorno_inferido"], eb["comentario"],
                         eb["operacao"], eb["contexto"],
                         1 if eb["uso_condicional"] else 0))
                    total_execblocks += 1

                # Insert function details (already extracted in parse_padrao_source)
                for block in parsed.get("func_blocks", []):
                    conn.execute(
                        """INSERT OR REPLACE INTO funcoes
                        (arquivo, nome, tipo, assinatura, tabelas_ref, campos_ref, calls, params)
                        VALUES (?,?,?,?,?,?,?,?)""",
                        (parsed["arquivo"], block["funcao"], block["tipo"],
                         block["assinatura"],
                         json.dumps(block["tabelas_ref"]),
                         json.dumps(block["campos_ref"]),
                         json.dumps(block["calls"]),
                         json.dumps(block["params"])))
                    total_funcoes += 1

                del parsed
                done_count += 1

                if done_count % BATCH_COMMIT_SIZE == 0:
                    conn.commit()

                if done_count % BATCH_GC_SIZE == 0:
                    gc.collect()

                if done_count % 500 == 0:
                    mem = _get_mem_mb()
                    yield {
                        "status": "progress", "pass": "metadata",
                        "done": done_count, "total": total,
                        "funcoes": total_funcoes, "execblocks": total_execblocks,
                        "mem_mb": round(mem),
                    }

            except Exception as e:
                error_count += 1
                if error_count <= 10:
                    yield {"status": "error", "item": f.name, "msg": str(e)[:200]}

        conn.commit()
        gc.collect()

        yield {
            "status": "pass_complete", "pass": "metadata",
            "done": done_count, "errors": error_count, "total": total,
            "funcoes": total_funcoes, "execblocks": total_execblocks,
        }

        # ── Pass 2: Chunks ────────────────────────────────────────────────
        chunk_count = 0
        done_count = 0
        error_count = 0

        yield {"status": "started", "total": total, "pass": "chunks"}

        for f in files:
            try:
                raw = f.read_bytes()
                if not raw or len(raw) > 5_000_000:
                    done_count += 1
                    continue

                try:
                    content = raw.decode("cp1252")
                except UnicodeDecodeError:
                    content = raw.decode("latin-1")
                del raw

                matches = list(_FUNC_RE.finditer(content))

                # Detect module from path
                modulo = _detect_module_from_path(f) or ""

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
                            modulo,
                        ))
                else:
                    body = content[:MAX_CHUNK_CHARS]
                    chunk_tuples.append((f"{f.name}::full", f.name, "_full", body, modulo))

                del content, matches

                if chunk_tuples:
                    conn.executemany(
                        "INSERT OR REPLACE INTO fonte_chunks (id, arquivo, funcao, content, modulo) VALUES (?,?,?,?,?)",
                        chunk_tuples)
                    conn.commit()
                    chunk_count += len(chunk_tuples)
                    del chunk_tuples

                done_count += 1

                if done_count % 500 == 0:
                    gc.collect()
                    mem = _get_mem_mb()
                    yield {
                        "status": "progress", "pass": "chunks",
                        "done": done_count, "total": total,
                        "chunks": chunk_count, "mem_mb": round(mem),
                    }

            except Exception as e:
                error_count += 1
                try:
                    conn.commit()
                except Exception:
                    pass
                if error_count <= 10:
                    yield {"status": "error", "item": f.name, "msg": str(e)[:200]}

        conn.execute("PRAGMA synchronous=FULL")
        conn.commit()
        gc.collect()

        # Save final stats
        self.db.execute(
            "INSERT OR REPLACE INTO ingest_meta (key, value) VALUES (?, ?)",
            ("ingest_complete", "true")
        )
        self.db.execute(
            "INSERT OR REPLACE INTO ingest_meta (key, value) VALUES (?, ?)",
            ("total_execblocks", str(total_execblocks))
        )
        self.db.commit()

        yield {
            "status": "complete",
            "done": done_count, "errors": error_count, "total": total,
            "chunks": chunk_count, "funcoes": total_funcoes,
            "execblocks": total_execblocks,
        }

    async def run_vectorize(self, vs) -> AsyncGenerator[dict, None]:
        """Vectorize chunks into ChromaDB (separate step after ingest)."""
        conn = self.db.get_raw_conn()

        total = conn.execute("SELECT COUNT(*) FROM fonte_chunks").fetchone()[0]
        if total == 0:
            yield {"status": "error", "msg": "No chunks to vectorize. Run ingest first."}
            return

        yield {"status": "started", "total": total, "pass": "vectorize"}

        vs.reset_collection("padrao_fontes")

        offset = 0
        batch_size = MAX_CHUNKS_PER_BATCH
        done = 0

        while True:
            rows = conn.execute(
                "SELECT id, arquivo, funcao, content, modulo FROM fonte_chunks LIMIT ? OFFSET ?",
                (batch_size, offset)
            ).fetchall()

            if not rows:
                break

            chunks = [{
                "id": r[0],
                "content": r[3],
                "arquivo": r[1],
                "funcao": r[2],
                "modulo": r[4] or "",
                "tipo": "padrao_fonte",
            } for r in rows]

            vs.add_source_chunks("padrao_fontes", chunks)
            done += len(chunks)
            offset += batch_size

            if done % 500 == 0:
                yield {"status": "progress", "pass": "vectorize", "done": done, "total": total}

        # Also vectorize ExecBlock contexts into a separate collection
        eb_total = conn.execute("SELECT COUNT(*) FROM execblocks").fetchone()[0]
        if eb_total > 0:
            vs.reset_collection("padrao_execblocks")
            offset = 0
            eb_done = 0

            while True:
                rows = conn.execute(
                    "SELECT id, nome_pe, arquivo, funcao, comentario, contexto, operacao FROM execblocks LIMIT ? OFFSET ?",
                    (batch_size, offset)
                ).fetchall()

                if not rows:
                    break

                chunks = [{
                    "id": f"eb_{r[0]}",
                    "content": f"PE: {r[1]}\nArquivo: {r[2]}\nFuncao: {r[3]}\nOperacao: {r[6]}\nDescricao: {r[4]}\n\n{r[5]}",
                    "nome_pe": r[1],
                    "arquivo": r[2],
                    "funcao": r[3],
                    "tipo": "padrao_execblock",
                } for r in rows]

                vs.add_source_chunks("padrao_execblocks", chunks)
                eb_done += len(chunks)
                offset += batch_size

        yield {
            "status": "complete", "pass": "vectorize",
            "chunks_vectorized": done, "execblocks_vectorized": eb_total,
        }
