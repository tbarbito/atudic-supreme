# -*- coding: utf-8 -*-
"""Origem: ExtraiRPO (Joni) — Construcao do grafo de vinculos (11 tipos de relacionamento)."""

"""Build vinculos table from existing database data.

Crosses all extracted data to create a relationship graph:
campo -> funcao, gatilho -> funcao, fonte -> tabela, PE -> rotina, etc.
"""
import sqlite3
import json
import re
import time
from pathlib import Path


def _extract_function_name(rotina_raw: str) -> str:
    """Extract clean function name from rotina field."""
    m = re.match(r'^([A-Za-z_]\w+)', rotina_raw.strip())
    return m.group(1) if m else rotina_raw.strip()


# PE name -> (rotina padrao, modulo)
PE_ROTINA_MAP = {
    "A010": ("MATA010", "estoque"), "A020": ("MATA020", "estoque"),
    "A050": ("MATA050", "estoque"), "A100": ("MATA100", "compras"),
    "A103": ("MATA103", "compras"), "A105": ("MATA105", "compras"),
    "A110": ("MATA110", "compras"), "A116": ("MATA116", "compras"),
    "A120": ("MATA120", "compras"), "A121": ("MATA121", "compras"),
    "A131": ("MATA131", "compras"), "A140": ("MATA140", "compras"),
    "A160": ("MATA160", "compras"), "A220": ("MATA220", "estoque"),
    "A241": ("MATA241", "estoque"), "A250": ("MATA250", "estoque"),
    "A261": ("MATA261", "estoque"), "A330": ("MATA330", "estoque"),
    "A340": ("MATA340", "estoque"), "A350": ("MATA350", "estoque"),
    "A410": ("MATA410", "faturamento"), "A415": ("MATA415", "faturamento"),
    "A440": ("MATA440", "faturamento"), "A450": ("MATA450", "faturamento"),
    "A460": ("MATA460", "faturamento"), "A461": ("MATA461", "faturamento"),
    "A521": ("MATA521", "faturamento"),
    "A910": ("MATA910", "estoque"), "A920": ("MATA920", "estoque"),
    "F040": ("FINA040", "financeiro"), "F050": ("FINA050", "financeiro"),
    "F060": ("FINA060", "financeiro"), "F070": ("FINA070", "financeiro"),
    "F090": ("FINA090", "financeiro"), "F100": ("FINA100", "financeiro"),
    "F110": ("FINA110", "financeiro"), "F150": ("FINA150", "financeiro"),
    "F200": ("FINA200", "financeiro"), "F580": ("FINA580", "financeiro"),
}

# Module integration map (from padrao templates)
MODULE_INTEGRATIONS = [
    ("compras", "estoque", "Doc Entrada (SF1/SD1) gera mov. estoque (SB2)"),
    ("compras", "financeiro", "Doc Entrada (SF1) gera titulo a pagar (SE2)"),
    ("compras", "fiscal", "Doc Entrada gera livro fiscal (SF3/SFT)"),
    ("compras", "contabilidade", "Doc Entrada contabiliza via LP 650/655/660"),
    ("faturamento", "estoque", "Doc Saida (SF2/SD2) baixa estoque (SB2)"),
    ("faturamento", "financeiro", "Doc Saida (SF2) gera titulo a receber (SE1)"),
    ("faturamento", "fiscal", "Doc Saida gera livro fiscal (SF3/SFT)"),
    ("faturamento", "contabilidade", "Doc Saida contabiliza via LP"),
    ("estoque", "contabilidade", "Movimentacoes contabilizam via LP"),
    ("financeiro", "contabilidade", "Baixas e movimentos contabilizam via LP"),
    ("fiscal", "contabilidade", "Apuracao gera lancamentos contabeis"),
]


def build_vinculos(db_path: Path, mapa_path: Path = None):
    """Build vinculos table from all existing data."""
    db = sqlite3.connect(str(db_path))
    start = time.time()

    # Recreate table
    db.execute("DROP TABLE IF EXISTS vinculos")
    db.execute("""
    CREATE TABLE vinculos (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        tipo         TEXT NOT NULL,
        origem_tipo  TEXT NOT NULL,
        origem       TEXT NOT NULL,
        destino_tipo TEXT NOT NULL,
        destino      TEXT NOT NULL,
        modulo       TEXT DEFAULT '',
        contexto     TEXT DEFAULT '',
        peso         INTEGER DEFAULT 1
    )""")
    db.commit()

    vinculos = []

    # 1. funcao_definida_em: funcao -> fonte
    print("1. funcao_definida_em...")
    for arquivo, funcoes_json, modulo in db.execute(
            "SELECT arquivo, funcoes, modulo FROM fontes").fetchall():
        for func in json.loads(funcoes_json):
            vinculos.append(('funcao_definida_em', 'funcao', func, 'fonte', arquivo, modulo or '', '', 3))
    print(f"   {len(vinculos)}")

    # 2. fonte_chama_funcao: fonte -> funcao (calls_u)
    print("2. fonte_chama_funcao...")
    c = len(vinculos)
    for arquivo, calls_json, modulo in db.execute(
            "SELECT arquivo, calls_u, modulo FROM fontes WHERE calls_u != '[]'").fetchall():
        for func in json.loads(calls_json):
            vinculos.append(('fonte_chama_funcao', 'fonte', arquivo, 'funcao', func, modulo or '', '', 2))
    print(f"   {len(vinculos) - c}")

    # 3. fonte_le_tabela + fonte_escreve_tabela
    print("3. fonte <-> tabela...")
    c = len(vinculos)
    for arquivo, tab_json, write_json, modulo in db.execute(
            "SELECT arquivo, tabelas_ref, write_tables, modulo FROM fontes").fetchall():
        for t in json.loads(tab_json):
            vinculos.append(('fonte_le_tabela', 'fonte', arquivo, 'tabela', t, modulo or '', '', 1))
        for t in json.loads(write_json):
            vinculos.append(('fonte_escreve_tabela', 'fonte', arquivo, 'tabela', t, modulo or '', '', 2))
    print(f"   {len(vinculos) - c}")

    # 4. campo_valida_funcao
    print("4. campo_valida_funcao...")
    c = len(vinculos)
    for tabela, campo, valid, vlduser in db.execute(
            "SELECT tabela, campo, validacao, vlduser FROM campos WHERE validacao != '' OR vlduser != ''").fetchall():
        combined = (valid or '') + ' ' + (vlduser or '')
        funcs = re.findall(r'\bU_(\w+)\s*\(', combined)
        for func in set(funcs):
            source = 'vlduser' if vlduser and func in vlduser else 'valid'
            vinculos.append(('campo_valida_funcao', 'campo', f'{tabela}.{campo}', 'funcao', func, '', source, 4))
    print(f"   {len(vinculos) - c}")

    # 5. gatilho_executa_funcao
    print("5. gatilho_executa_funcao...")
    c = len(vinculos)
    for co, cd, regra, cond in db.execute(
            "SELECT campo_origem, campo_destino, regra, condicao FROM gatilhos").fetchall():
        combined = (regra or '') + ' ' + (cond or '')
        funcs = re.findall(r'\bU_(\w+)\s*\(', combined)
        for func in set(funcs):
            vinculos.append(('gatilho_executa_funcao', 'gatilho', f'{co}->{cd}', 'funcao', func, '', '', 4))
    print(f"   {len(vinculos) - c}")

    # 6. pe_afeta_rotina
    print("6. pe_afeta_rotina...")
    c = len(vinculos)
    for arquivo, pes_json, modulo in db.execute(
            "SELECT arquivo, pontos_entrada, modulo FROM fontes WHERE pontos_entrada != '[]'").fetchall():
        for pe in json.loads(pes_json):
            pe_upper = pe.upper()
            matched = False
            for prefix, (rotina, mod) in sorted(PE_ROTINA_MAP.items(), key=lambda x: -len(x[0])):
                if pe_upper.startswith(prefix) or pe_upper.startswith("MT" + prefix[1:]) or pe_upper.startswith("MTA" + prefix[1:]):
                    vinculos.append(('pe_afeta_rotina', 'pe', pe, 'rotina', rotina, mod, arquivo, 5))
                    matched = True
                    break
            if not matched and modulo:
                vinculos.append(('pe_afeta_rotina', 'pe', pe, 'rotina', 'desconhecida', modulo or '', arquivo, 2))
    print(f"   {len(vinculos) - c}")

    # 7. campo_consulta_tabela (F3)
    print("7. campo_consulta_tabela (F3)...")
    c = len(vinculos)
    for tabela, campo, f3 in db.execute(
            "SELECT tabela, campo, f3 FROM campos WHERE f3 != '' AND custom = 1").fetchall():
        f3_tables = re.findall(r'\b([A-Z][A-Z0-9][A-Z0-9])\b', f3)
        for t in set(f3_tables):
            if len(t) == 3 and t[0] in "SZDNQ":
                vinculos.append(('campo_consulta_tabela', 'campo', f'{tabela}.{campo}', 'tabela', t, '', f'F3={f3[:30]}', 2))
    print(f"   {len(vinculos) - c}")

    # 8. tabela_pertence_modulo
    print("8. tabela_pertence_modulo...")
    c = len(vinculos)
    # Prioridade: 1) mapa_path externo, 2) tabela mapa_modulos no SQLite
    mapa = {}
    if mapa_path and mapa_path.exists():
        mapa = json.loads(mapa_path.read_text(encoding='utf-8'))
    else:
        try:
            for row in db.execute("SELECT modulo, tabelas FROM mapa_modulos").fetchall():
                mapa[row[0]] = {"tabelas": json.loads(row[1]) if row[1] else []}
        except Exception:
            pass
    for modulo, info in mapa.items():
        for tab in info.get("tabelas", []):
            vinculos.append(('tabela_pertence_modulo', 'tabela', tab.upper(), 'modulo', modulo, modulo, '', 1))
    print(f"   {len(vinculos) - c}")

    # 9. modulo_integra_modulo
    print("9. modulo_integra_modulo...")
    c = len(vinculos)
    for origem, destino, contexto in MODULE_INTEGRATIONS:
        vinculos.append(('modulo_integra_modulo', 'modulo', origem, 'modulo', destino, '', contexto, 3))
    print(f"   {len(vinculos) - c}")

    # 10. job_executa_funcao
    print("10. job_executa_funcao...")
    c = len(vinculos)
    try:
        for arquivo_ini, sessao, rotina in db.execute(
                "SELECT arquivo_ini, sessao, rotina FROM jobs WHERE rotina != ''").fetchall():
            func_name = _extract_function_name(rotina)
            # Strip U_ prefix — User Functions are declared without U_ in source
            clean_name = func_name[2:] if func_name.upper().startswith("U_") else func_name
            vinculos.append(('job_executa_funcao', 'job', sessao, 'funcao', clean_name, '', f'ini={arquivo_ini}', 3))
    except Exception:
        pass  # Table may not exist
    print(f"   {len(vinculos) - c}")

    # 11. schedule_executa_funcao
    print("11. schedule_executa_funcao...")
    c = len(vinculos)
    try:
        for codigo, rotina, empresa, status in db.execute(
                "SELECT codigo, rotina, empresa_filial, status FROM schedules WHERE rotina != ''").fetchall():
            func_name = _extract_function_name(rotina)
            clean_name = func_name[2:] if func_name.upper().startswith("U_") else func_name
            vinculos.append(('schedule_executa_funcao', 'schedule', codigo, 'funcao', clean_name, '', f'filial={empresa}|{status}', 3))
    except Exception:
        pass  # Table may not exist
    print(f"   {len(vinculos) - c}")

    # INSERT ALL
    print(f"\nInserting {len(vinculos):,} vinculos...")
    db.executemany(
        "INSERT INTO vinculos (tipo, origem_tipo, origem, destino_tipo, destino, modulo, contexto, peso) "
        "VALUES (?,?,?,?,?,?,?,?)",
        vinculos)

    # Create indexes
    db.execute("CREATE INDEX IF NOT EXISTS idx_vinculos_tipo ON vinculos(tipo)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_vinculos_origem ON vinculos(origem)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_vinculos_destino ON vinculos(destino)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_vinculos_modulo ON vinculos(modulo)")
    db.commit()

    elapsed = time.time() - start
    print(f"Done in {elapsed:.1f}s")

    # Stats
    print("\n=== VINCULOS POR TIPO ===")
    for row in db.execute("SELECT tipo, COUNT(*) FROM vinculos GROUP BY tipo ORDER BY COUNT(*) DESC").fetchall():
        print(f"  {row[0]}: {row[1]:,}")
    total = db.execute("SELECT COUNT(*) FROM vinculos").fetchone()[0]
    print(f"\n  TOTAL: {total:,}")

    db.close()
    return total


if __name__ == "__main__":
    db_path = Path("workspace/clients/marfrig/db/extrairpo.db")
    mapa_path = Path("templates/processos/mapa-modulos.json")
    build_vinculos(db_path, mapa_path)
