# -*- coding: utf-8 -*-
"""
Benchmark REST Ingest — testa ingestao completa via API REST do Protheus.

Ambiente de teste:
  - Protheus: http://192.168.122.41:8019/rest (admin/protheus)
  - Workspace: "base_local" (SQLite em workspace/clients/base_local/)

Uso:
  python -m tests.benchmark_rest_ingest
  python -m tests.benchmark_rest_ingest --tabela SX3   (testa apenas uma tabela)
"""

import sys
import os
import time
import asyncio
import argparse
from pathlib import Path

# Adicionar raiz do projeto ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.workspace.rest_client import ProtheusRESTClient
from app.services.workspace.rest_ingestor import RESTIngestor
from app.services.workspace.workspace_db import Database

# ── Config do benchmark ──────────────────────────────────────────────
REST_URL = "http://192.168.122.41:8019/rest"
REST_USER = "admin"
REST_PASSWORD = "protheus"
WORKSPACE_SLUG = "base_local"
WORKSPACE_DIR = Path("workspace/clients") / WORKSPACE_SLUG


def _fmt_time(seconds: float) -> str:
    """Formata tempo em formato legivel."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes}m {secs:.1f}s"


def _fmt_num(n: int) -> str:
    """Formata numero com separador de milhar."""
    return f"{n:,}".replace(",", ".")


def benchmark_connection():
    """Testa conectividade e mede latencia."""
    print("\n" + "=" * 70)
    print("BENCHMARK REST INGEST — Protheus API")
    print("=" * 70)
    print(f"  URL:       {REST_URL}")
    print(f"  User:      {REST_USER}")
    print(f"  Workspace: {WORKSPACE_SLUG}")
    print("=" * 70)

    client = ProtheusRESTClient(REST_URL, REST_USER, REST_PASSWORD)

    # Teste de conexao
    print("\n[1/4] Testando conexao...")
    t0 = time.time()
    result = client.test_connection()
    latency = time.time() - t0

    if not result.get("ok"):
        print(f"  FALHA: {result.get('message', 'erro desconhecido')}")
        return None

    tables_count = result.get("tables_count", "?")
    print(f"  OK — {tables_count} tabelas, latencia: {latency*1000:.0f}ms")
    return client


def benchmark_single_table(client: ProtheusRESTClient, sx_name: str):
    """Benchmark de uma tabela SX individual."""
    print(f"\n  {sx_name}... ", end="", flush=True)
    t0 = time.time()
    try:
        items = client.query_sx_table(sx_name)
        elapsed = time.time() - t0
        rate = len(items) / elapsed if elapsed > 0 else 0
        print(f"{_fmt_num(len(items))} registros em {_fmt_time(elapsed)} ({rate:.0f} reg/s)")
        return {"name": sx_name, "count": len(items), "time": elapsed, "error": None}
    except Exception as e:
        elapsed = time.time() - t0
        print(f"ERRO em {_fmt_time(elapsed)}: {e}")
        return {"name": sx_name, "count": 0, "time": elapsed, "error": str(e)}


def benchmark_fetch_all(client: ProtheusRESTClient, only_table: str = None):
    """Benchmark de busca de todas as tabelas SX."""
    print("\n[2/4] Buscando dados via REST API...")

    sx_tables = ["SX2", "SX3", "SIX", "SX7", "SX1", "SX5", "SX6", "SX9", "SXA", "SXB"]

    if only_table:
        sx_tables = [only_table.upper()]

    results = []
    total_start = time.time()
    for sx in sx_tables:
        r = benchmark_single_table(client, sx)
        results.append(r)
    total_elapsed = time.time() - total_start

    # Resumo
    total_records = sum(r["count"] for r in results)
    errors = [r for r in results if r["error"]]
    print(f"\n  Total: {_fmt_num(total_records)} registros em {_fmt_time(total_elapsed)}")
    if errors:
        print(f"  Erros: {len(errors)} tabela(s) com falha")
        for e in errors:
            print(f"    - {e['name']}: {e['error'][:80]}")

    return results, total_elapsed


def benchmark_ingest(only_table: str = None):
    """Benchmark completo: REST → transform → SQLite."""
    print("\n[3/4] Ingestao completa (REST → SQLite)...")

    # Preparar workspace
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    db_path = WORKSPACE_DIR / "workspace.db"
    db = Database(db_path)
    db.initialize()

    client = ProtheusRESTClient(REST_URL, REST_USER, REST_PASSWORD)
    ingestor = RESTIngestor(db, client)

    results = {}
    errors = []
    total_start = time.time()

    async def _run():
        async for progress in ingestor.run_fase1():
            item = progress.get("item", "")
            status = progress.get("status", "")
            if only_table and item.upper() != only_table.upper():
                continue
            if status == "fetching":
                print(f"  {item}: buscando...", end="", flush=True)
            elif status == "done":
                count = progress.get("count", 0)
                results[item] = count
                print(f"\r  {item}: {_fmt_num(count)} registros inseridos no SQLite")
            elif status == "error":
                msg = progress.get("msg", "")
                errors.append(f"{item}: {msg}")
                print(f"\r  {item}: ERRO — {msg[:80]}")

    asyncio.run(_run())
    total_elapsed = time.time() - total_start

    total_records = sum(results.values())
    print(f"\n  Ingestao total: {_fmt_num(total_records)} registros em {_fmt_time(total_elapsed)}")

    db.close()
    return results, errors, total_elapsed


def benchmark_verify():
    """Verifica dados no SQLite apos ingestao."""
    print("\n[4/4] Verificando dados no SQLite...")

    db_path = WORKSPACE_DIR / "workspace.db"
    if not db_path.exists():
        print("  Workspace nao encontrado — pule esta etapa")
        return

    db = Database(db_path)
    db.initialize()

    checks = [
        ("tabelas",           "SELECT COUNT(*) FROM tabelas"),
        ("campos",            "SELECT COUNT(*) FROM campos"),
        ("campos_custom",     "SELECT COUNT(*) FROM campos WHERE custom=1"),
        ("indices",           "SELECT COUNT(*) FROM indices"),
        ("gatilhos",          "SELECT COUNT(*) FROM gatilhos"),
        ("perguntas",         "SELECT COUNT(*) FROM perguntas"),
        ("tabelas_genericas", "SELECT COUNT(*) FROM tabelas_genericas"),
        ("parametros",        "SELECT COUNT(*) FROM parametros"),
        ("relacionamentos",   "SELECT COUNT(*) FROM relacionamentos"),
        ("pastas",            "SELECT COUNT(*) FROM pastas"),
        ("consultas",         "SELECT COUNT(*) FROM consultas"),
    ]

    print(f"\n  {'Item':<22} {'Registros':>12}")
    print(f"  {'—'*22} {'—'*12}")
    for label, query in checks:
        try:
            count = db.execute(query).fetchone()[0]
            print(f"  {label:<22} {_fmt_num(count):>12}")
        except Exception as e:
            print(f"  {label:<22} {'ERRO':>12}  ({e})")

    # Top 5 tabelas com mais campos
    print(f"\n  Top 5 tabelas com mais campos:")
    rows = db.execute(
        "SELECT tabela, COUNT(*) as cnt FROM campos GROUP BY tabela ORDER BY cnt DESC LIMIT 5"
    ).fetchall()
    for r in rows:
        print(f"    {r[0]:<6} {_fmt_num(r[1]):>8} campos")

    # Tamanho do arquivo SQLite
    size_mb = db_path.stat().st_size / (1024 * 1024)
    print(f"\n  Tamanho do workspace.db: {size_mb:.1f} MB")

    db.close()


def main():
    parser = argparse.ArgumentParser(description="Benchmark REST Ingest")
    parser.add_argument("--tabela", type=str, default=None, help="Testar apenas uma tabela SX (ex: SX3)")
    parser.add_argument("--skip-fetch", action="store_true", help="Pular teste de fetch isolado")
    args = parser.parse_args()

    t_global = time.time()

    # 1. Conexao
    client = benchmark_connection()
    if not client:
        sys.exit(1)

    # 2. Fetch isolado (mede velocidade da API sem gravar)
    if not args.skip_fetch:
        benchmark_fetch_all(client, args.tabela)

    # 3. Ingestao completa
    results, errors, elapsed = benchmark_ingest(args.tabela)

    # 4. Verificacao
    benchmark_verify()

    # Resumo final
    total_elapsed = time.time() - t_global
    print("\n" + "=" * 70)
    print(f"BENCHMARK CONCLUIDO em {_fmt_time(total_elapsed)}")
    if errors:
        print(f"  {len(errors)} erro(s): {'; '.join(errors)}")
    else:
        print(f"  Sem erros!")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
