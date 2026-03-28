#!/usr/bin/env python3
"""
Exporta chunks TDN do PostgreSQL para arquivos .md na pasta memory/.

Gera um arquivo .md por fonte (protheus12.md, framework.md, etc.)
no formato que o AgentMemoryService.ingest_file() espera:
- Seções com ## heading
- Conteúdo textual com código, tabelas, etc.

Uso:
    python export_chunks_to_md.py --db-host 192.168.122.41 --db-name atudir --db-user atudir --db-password atudir --output ../memory/
    python export_chunks_to_md.py --db-host localhost --db-name atudic_supreme --output ../memory/
"""

import argparse
import os
import sys

import psycopg2
import psycopg2.extras


def export_source(cursor, source, output_dir):
    """Exporta todos os chunks de uma fonte para um arquivo .md."""
    cursor.execute("""
        SELECT c.section_title, c.content, c.content_type,
               p.page_title, p.page_url
        FROM tdn_chunks c
        JOIN tdn_pages p ON c.page_id = p.id
        WHERE p.source = %s AND p.status = 'done'
        ORDER BY p.page_title, c.chunk_index
    """, (source,))

    chunks = cursor.fetchall()
    if not chunks:
        print(f"  {source}: 0 chunks, pulando")
        return 0

    output_path = os.path.join(output_dir, f"tdn_{source}.md")

    # Agrupar por page_title para evitar repetir headers
    current_page = None
    lines = [
        f"# Base de Conhecimento TDN — {source}",
        f"",
        f"> Fonte: TOTVS Developer Network (tdn.totvs.com)",
        f"> Total de chunks: {len(chunks)}",
        f"",
        "---",
        "",
    ]

    for chunk in chunks:
        page_title = chunk["page_title"] or ""
        section_title = chunk["section_title"] or ""
        content = chunk["content"] or ""
        url = chunk["page_url"] or ""

        # Novo artigo/pagina
        if page_title != current_page:
            current_page = page_title
            lines.append(f"## {page_title}")
            if url:
                lines.append(f"> {url}")
            lines.append("")

        # Secao dentro do artigo
        if section_title and section_title != page_title:
            lines.append(f"### {section_title}")
            lines.append("")

        lines.append(content)
        lines.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    size_kb = os.path.getsize(output_path) // 1024
    print(f"  {source}: {len(chunks)} chunks → {output_path} ({size_kb} KB)")
    return len(chunks)


def main():
    parser = argparse.ArgumentParser(description="Exporta chunks TDN do PG para .md")
    parser.add_argument("--db-host", default="192.168.122.41")
    parser.add_argument("--db-port", type=int, default=5432)
    parser.add_argument("--db-name", default="atudir")
    parser.add_argument("--db-user", default="atudir")
    parser.add_argument("--db-password", default="atudir")
    parser.add_argument("--output", default="../memory/", help="Pasta de saida para os .md")
    parser.add_argument("--sources", nargs="*", help="Fontes especificas (default: todas)")

    args = parser.parse_args()
    output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), args.output))
    os.makedirs(output_dir, exist_ok=True)

    print(f"Conectando em {args.db_host}:{args.db_port}/{args.db_name}...")
    conn = psycopg2.connect(
        host=args.db_host, port=args.db_port,
        dbname=args.db_name, user=args.db_user, password=args.db_password,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )
    cursor = conn.cursor()

    # Listar fontes
    if args.sources:
        sources = args.sources
    else:
        cursor.execute("SELECT DISTINCT source FROM tdn_pages WHERE status = 'done' ORDER BY source")
        sources = [r["source"] for r in cursor.fetchall()]

    print(f"Fontes: {sources}")
    print(f"Saida: {output_dir}")
    print("=" * 60)

    total = 0
    for source in sources:
        total += export_source(cursor, source, output_dir)

    conn.close()
    print(f"\n{'=' * 60}")
    print(f"Total: {total} chunks exportados para {len(sources)} arquivos .md")


if __name__ == "__main__":
    main()
