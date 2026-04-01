# -*- coding: utf-8 -*-
"""Origem: ExtraiRPO (Joni) — Schema SQLite e classe Database para workspace."""

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS tabelas (
    codigo      TEXT PRIMARY KEY,
    nome        TEXT,
    modo        TEXT,
    custom      INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS campos (
    tabela      TEXT REFERENCES tabelas(codigo),
    campo       TEXT,
    tipo        TEXT,
    tamanho     INTEGER,
    decimal     INTEGER DEFAULT 0,
    titulo      TEXT,
    descricao   TEXT,
    validacao   TEXT DEFAULT '',
    inicializador TEXT DEFAULT '',
    obrigatorio INTEGER DEFAULT 0,
    custom      INTEGER DEFAULT 0,
    f3          TEXT DEFAULT '',
    cbox        TEXT DEFAULT '',
    vlduser     TEXT DEFAULT '',
    when_expr   TEXT DEFAULT '',
    proprietario TEXT DEFAULT 'S',
    browse      TEXT DEFAULT '',
    trigger_flag TEXT DEFAULT '',
    visual      TEXT DEFAULT '',
    context     TEXT DEFAULT '',
    folder      TEXT DEFAULT '',
    grpsxg      TEXT DEFAULT '',
    PRIMARY KEY (tabela, campo)
);

CREATE TABLE IF NOT EXISTS grupos_campo (
    grupo       TEXT PRIMARY KEY,
    descricao   TEXT DEFAULT '',
    tamanho_max INTEGER DEFAULT 0,
    tamanho_min INTEGER DEFAULT 0,
    tamanho     INTEGER DEFAULT 0,
    total_campos INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS indices (
    tabela      TEXT,
    ordem       TEXT,
    chave       TEXT,
    descricao   TEXT,
    proprietario TEXT DEFAULT 'S',
    f3          TEXT DEFAULT '',
    nickname    TEXT DEFAULT '',
    showpesq    TEXT DEFAULT 'S',
    custom      INTEGER DEFAULT 0,
    PRIMARY KEY (tabela, ordem)
);

CREATE TABLE IF NOT EXISTS gatilhos (
    campo_origem TEXT,
    sequencia   TEXT,
    campo_destino TEXT,
    regra       TEXT DEFAULT '',
    tipo        TEXT DEFAULT '',
    tabela      TEXT DEFAULT '',
    condicao    TEXT DEFAULT '',
    proprietario TEXT DEFAULT 'S',
    seek        TEXT DEFAULT '',
    alias       TEXT DEFAULT '',
    ordem       TEXT DEFAULT '',
    chave       TEXT DEFAULT '',
    custom      INTEGER DEFAULT 0,
    PRIMARY KEY (campo_origem, sequencia)
);

CREATE TABLE IF NOT EXISTS perguntas (
    grupo       TEXT,
    ordem       TEXT,
    pergunta    TEXT,
    variavel    TEXT,
    tipo        TEXT,
    tamanho     INTEGER,
    decimal     INTEGER,
    f3          TEXT,
    validacao   TEXT,
    conteudo_padrao TEXT,
    PRIMARY KEY (grupo, ordem)
);

CREATE TABLE IF NOT EXISTS tabelas_genericas (
    filial      TEXT,
    tabela      TEXT,
    chave       TEXT,
    descricao   TEXT,
    custom      INTEGER DEFAULT 0,
    PRIMARY KEY (filial, tabela, chave)
);

CREATE TABLE IF NOT EXISTS parametros (
    filial      TEXT,
    variavel    TEXT,
    tipo        TEXT,
    descricao   TEXT,
    conteudo    TEXT,
    proprietario TEXT,
    custom      INTEGER DEFAULT 0,
    PRIMARY KEY (filial, variavel)
);

CREATE TABLE IF NOT EXISTS relacionamentos (
    tabela_origem TEXT,
    identificador TEXT,
    tabela_destino TEXT,
    expressao_origem TEXT,
    expressao_destino TEXT,
    proprietario TEXT,
    condicao_sql TEXT,
    custom       INTEGER DEFAULT 0,
    PRIMARY KEY (tabela_origem, identificador, tabela_destino)
);

CREATE TABLE IF NOT EXISTS pastas (
    alias       TEXT,
    ordem       TEXT,
    descricao   TEXT,
    proprietario TEXT,
    agrupamento TEXT,
    PRIMARY KEY (alias, ordem)
);

CREATE TABLE IF NOT EXISTS consultas (
    alias       TEXT,
    tipo        TEXT,
    sequencia   TEXT,
    coluna      TEXT,
    descricao   TEXT,
    conteudo    TEXT,
    PRIMARY KEY (alias, sequencia, coluna)
);

CREATE TABLE IF NOT EXISTS propositos (
    chave           TEXT PRIMARY KEY,
    proposito       TEXT DEFAULT '',
    proposito_auto  TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS conceitos_aprendidos (
    conceito    TEXT PRIMARY KEY,
    rotinas     TEXT DEFAULT '[]',
    tabelas     TEXT DEFAULT '[]',
    modulos     TEXT DEFAULT '[]',
    fonte       TEXT DEFAULT 'auto',
    hits        INTEGER DEFAULT 1,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS fonte_analise_tecnica (
    arquivo     TEXT PRIMARY KEY,
    analise_markdown TEXT DEFAULT NULL,
    analise_json TEXT DEFAULT NULL,
    processos_vinculados TEXT DEFAULT '[]',
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS fontes (
    arquivo     TEXT PRIMARY KEY,
    caminho     TEXT,
    tipo        TEXT,
    modulo      TEXT,
    funcoes     TEXT,
    user_funcs  TEXT,
    pontos_entrada TEXT,
    tabelas_ref TEXT,
    write_tables TEXT,
    includes    TEXT,
    calls_u     TEXT DEFAULT '',
    calls_execblock TEXT DEFAULT '',
    fields_ref  TEXT DEFAULT '',
    lines_of_code INTEGER DEFAULT 0,
    hash        TEXT,
    reclock_tables TEXT DEFAULT '[]',
    encoding TEXT DEFAULT 'cp1252'
);

CREATE TABLE IF NOT EXISTS chat_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    role        TEXT,
    content     TEXT,
    sources     TEXT,
    doc_updated TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS fonte_chunks (
    id          TEXT PRIMARY KEY,
    arquivo     TEXT REFERENCES fontes(arquivo),
    funcao      TEXT,
    content     TEXT,
    modulo      TEXT
);

CREATE TABLE IF NOT EXISTS operacoes_escrita (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    arquivo     TEXT NOT NULL,
    funcao      TEXT NOT NULL,
    tipo        TEXT NOT NULL,
    tabela      TEXT NOT NULL,
    campos      TEXT DEFAULT '[]',
    origens     TEXT DEFAULT '{}',
    condicao    TEXT DEFAULT '',
    linha       INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_oe_tabela ON operacoes_escrita(tabela);
CREATE INDEX IF NOT EXISTS idx_oe_arquivo ON operacoes_escrita(arquivo);

CREATE TABLE IF NOT EXISTS ingest_progress (
    item        TEXT PRIMARY KEY,
    fase        INTEGER,
    status      TEXT,
    error_msg   TEXT,
    updated_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS vinculos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo         TEXT NOT NULL,
    origem_tipo  TEXT NOT NULL,
    origem       TEXT NOT NULL,
    destino_tipo TEXT NOT NULL,
    destino      TEXT NOT NULL,
    modulo       TEXT DEFAULT '',
    contexto     TEXT DEFAULT '',
    peso         INTEGER DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_vinculos_tipo ON vinculos(tipo);
CREATE INDEX IF NOT EXISTS idx_vinculos_origem ON vinculos(origem);
CREATE INDEX IF NOT EXISTS idx_vinculos_destino ON vinculos(destino);
CREATE INDEX IF NOT EXISTS idx_vinculos_modulo ON vinculos(modulo);

CREATE TABLE IF NOT EXISTS menus (
    modulo   TEXT,
    rotina   TEXT,
    nome     TEXT,
    menu     TEXT,
    ordem    INTEGER,
    PRIMARY KEY (modulo, rotina)
);

-- Padrão (standard) SX tables for diff comparison
CREATE TABLE IF NOT EXISTS padrao_tabelas (
    codigo      TEXT PRIMARY KEY,
    nome        TEXT,
    modo        TEXT,
    custom      INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS padrao_campos (
    tabela      TEXT,
    campo       TEXT,
    tipo        TEXT,
    tamanho     INTEGER,
    decimal     INTEGER DEFAULT 0,
    titulo      TEXT,
    descricao   TEXT,
    validacao   TEXT DEFAULT '',
    inicializador TEXT DEFAULT '',
    obrigatorio INTEGER DEFAULT 0,
    custom      INTEGER DEFAULT 0,
    f3          TEXT DEFAULT '',
    cbox        TEXT DEFAULT '',
    vlduser     TEXT DEFAULT '',
    when_expr   TEXT DEFAULT '',
    proprietario TEXT DEFAULT 'S',
    browse      TEXT DEFAULT '',
    trigger_flag TEXT DEFAULT '',
    visual      TEXT DEFAULT '',
    context     TEXT DEFAULT '',
    folder      TEXT DEFAULT '',
    grpsxg      TEXT DEFAULT '',
    PRIMARY KEY (tabela, campo)
);

CREATE TABLE IF NOT EXISTS padrao_indices (
    tabela      TEXT,
    ordem       TEXT,
    chave       TEXT,
    descricao   TEXT,
    proprietario TEXT DEFAULT 'S',
    f3          TEXT DEFAULT '',
    nickname    TEXT DEFAULT '',
    showpesq    TEXT DEFAULT 'S',
    custom      INTEGER DEFAULT 0,
    PRIMARY KEY (tabela, ordem)
);

CREATE TABLE IF NOT EXISTS padrao_gatilhos (
    campo_origem TEXT,
    sequencia   TEXT,
    campo_destino TEXT,
    regra       TEXT DEFAULT '',
    tipo        TEXT DEFAULT '',
    tabela      TEXT DEFAULT '',
    condicao    TEXT DEFAULT '',
    proprietario TEXT DEFAULT 'S',
    seek        TEXT DEFAULT '',
    alias       TEXT DEFAULT '',
    ordem       TEXT DEFAULT '',
    chave       TEXT DEFAULT '',
    custom      INTEGER DEFAULT 0,
    PRIMARY KEY (campo_origem, sequencia)
);

CREATE TABLE IF NOT EXISTS padrao_parametros (
    filial      TEXT,
    variavel    TEXT,
    tipo        TEXT,
    descricao   TEXT,
    conteudo    TEXT,
    proprietario TEXT,
    custom      INTEGER DEFAULT 0,
    PRIMARY KEY (filial, variavel)
);

CREATE TABLE IF NOT EXISTS diff (
    tipo_sx      TEXT,
    tabela       TEXT,
    chave        TEXT,
    acao         TEXT,
    campo_diff   TEXT,
    valor_padrao TEXT,
    valor_cliente TEXT,
    modulo       TEXT,
    PRIMARY KEY (tipo_sx, tabela, chave, acao, campo_diff)
);

CREATE TABLE IF NOT EXISTS funcao_docs (
    arquivo     TEXT,
    funcao      TEXT,
    tipo        TEXT,
    assinatura  TEXT,
    resumo      TEXT,
    tabelas_ref TEXT,
    campos_ref  TEXT,
    chama       TEXT,
    chamada_por TEXT,
    retorno     TEXT,
    params      TEXT,
    fonte       TEXT DEFAULT 'auto',
    updated_at  TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (arquivo, funcao)
);

CREATE TABLE IF NOT EXISTS anotacoes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo        TEXT,
    chave       TEXT,
    texto       TEXT,
    autor       TEXT DEFAULT 'consultor',
    tags        TEXT DEFAULT '[]',
    data        TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_anotacoes_tipo_chave ON anotacoes(tipo, chave);
CREATE INDEX IF NOT EXISTS idx_tabelas_custom ON tabelas(custom);
CREATE INDEX IF NOT EXISTS idx_campos_custom ON campos(custom);
CREATE INDEX IF NOT EXISTS idx_campos_tabela ON campos(tabela);
CREATE INDEX IF NOT EXISTS idx_indices_custom ON indices(custom);
CREATE INDEX IF NOT EXISTS idx_gatilhos_custom ON gatilhos(custom);
CREATE INDEX IF NOT EXISTS idx_fontes_modulo ON fontes(modulo);
CREATE INDEX IF NOT EXISTS idx_diff_tipo_acao ON diff(tipo_sx, acao);
CREATE INDEX IF NOT EXISTS idx_diff_tabela ON diff(tabela);
CREATE INDEX IF NOT EXISTS idx_menus_rotina ON menus(rotina);

CREATE TABLE IF NOT EXISTS jobs (
    arquivo_ini  TEXT,
    sessao       TEXT,
    rotina       TEXT,
    refresh_rate INTEGER,
    parametros   TEXT DEFAULT '',
    PRIMARY KEY (arquivo_ini, sessao)
);
CREATE INDEX IF NOT EXISTS idx_jobs_rotina ON jobs(rotina);

CREATE TABLE IF NOT EXISTS schedules (
    codigo              TEXT,
    rotina              TEXT,
    empresa_filial      TEXT,
    environment         TEXT DEFAULT '',
    modulo              INTEGER DEFAULT 0,
    status              TEXT DEFAULT '',
    tipo_recorrencia    TEXT DEFAULT '',
    detalhe_recorrencia TEXT DEFAULT '',
    execucoes_dia       INTEGER,
    intervalo           TEXT DEFAULT '',
    hora_inicio         TEXT DEFAULT '',
    data_criacao        TEXT DEFAULT '',
    ultima_execucao     TEXT DEFAULT '',
    ultima_hora         TEXT DEFAULT '',
    recorrencia_raw     TEXT DEFAULT '',
    PRIMARY KEY (codigo, empresa_filial)
);
CREATE INDEX IF NOT EXISTS idx_schedules_rotina ON schedules(rotina);
CREATE INDEX IF NOT EXISTS idx_schedules_status ON schedules(status);

CREATE TABLE IF NOT EXISTS record_counts (
    tabela      TEXT PRIMARY KEY,
    registros   INTEGER DEFAULT 0,
    updated_at  TEXT DEFAULT (datetime('now'))
);

-- Processos de negocio detectados no ambiente do cliente
CREATE TABLE IF NOT EXISTS processos_detectados (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nome        TEXT NOT NULL,
    tipo        TEXT NOT NULL,
    descricao   TEXT DEFAULT '',
    criticidade TEXT DEFAULT 'media',
    tabelas     TEXT DEFAULT '[]',
    evidencias  TEXT DEFAULT '{}',
    metodo      TEXT DEFAULT 'pipeline',
    score       REAL DEFAULT 0.0,
    validado    INTEGER DEFAULT 0,
    fluxo_mermaid TEXT DEFAULT NULL,
    analise_markdown TEXT DEFAULT NULL,
    analise_json TEXT DEFAULT NULL,
    analise_updated_at TEXT DEFAULT NULL,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_processos_tipo ON processos_detectados(tipo);
CREATE INDEX IF NOT EXISTS idx_processos_validado ON processos_detectados(validado);

-- Historico de chat por processo
CREATE TABLE IF NOT EXISTS processo_mensagens (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    processo_id INTEGER NOT NULL REFERENCES processos_detectados(id),
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_proc_msg_processo ON processo_mensagens(processo_id);

-- Configuracoes persistentes do workspace (REST credentials, etc.)
CREATE TABLE IF NOT EXISTS workspace_config (
    chave       TEXT PRIMARY KEY,
    valor       TEXT NOT NULL DEFAULT '',
    updated_at  TEXT DEFAULT (datetime('now'))
);

-- Mapa de modulos Protheus (autocontido — dados padrao do ERP)
CREATE TABLE IF NOT EXISTS mapa_modulos (
    modulo      TEXT PRIMARY KEY,
    tabelas     TEXT NOT NULL DEFAULT '[]',
    rotinas     TEXT NOT NULL DEFAULT '[]'
);
"""

# Dados padrao do Protheus — seed automatico
_MAPA_MODULOS_DEFAULT = [
    ("compras",       '["SC7","SC8","SA2","SCR","SCJ"]', '["MATA120","MATA121","MATA103"]'),
    ("faturamento",   '["SC5","SC6","SF2","SD2","SA1"]', '["MATA410","MATA411","MATA460","MATA461"]'),
    ("financeiro",    '["SE1","SE2","SE5","SA6","SEA"]', '["FINA040","FINA050","FINA080"]'),
    ("estoque",       '["SB1","SB2","SB5","SD1","SD3"]', '["MATA240","MATA241","MATA250","MATA260"]'),
    ("fiscal",        '["SF3","SF4","SFT","CDA","CDH"]', '["MATA950","MATA953"]'),
    ("pcp",           '["SC2","SG1","SG2","SD4","SHB"]', '["MATA630","MATA650","MATA680"]'),
    ("rh",            '["SRA","SRB","SRC","SRD","SRE"]', '["GPEA010","GPEA020","GPEM020"]'),
    ("contabilidade", '["CT1","CT2","CT5","CTS","CVD"]', '["CTBA010","CTBA020","CTBA102"]'),
]

_initialized_dbs: set[str] = set()

class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._conn = None

    def initialize(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        key = str(self.db_path)
        # Verificar se DB existe e tem tabelas (pode ter sido excluido)
        needs_init = key not in _initialized_dbs
        if not needs_init:
            try:
                self._conn.execute("SELECT 1 FROM tabelas LIMIT 1")
            except Exception:
                needs_init = True  # DB existe mas schema nao — reinicializar
        if needs_init:
            self._conn.executescript(SCHEMA)
            # Seed mapa de modulos padrao Protheus
            existing = self._conn.execute("SELECT COUNT(*) FROM mapa_modulos").fetchone()[0]
            if existing == 0:
                self._conn.executemany(
                    "INSERT OR IGNORE INTO mapa_modulos (modulo, tabelas, rotinas) VALUES (?,?,?)",
                    _MAPA_MODULOS_DEFAULT
                )
            self._conn.commit()
            _initialized_dbs.add(key)
        # Migration idempotente para workspaces existentes
        for col_ddl in [
            "ALTER TABLE processos_detectados ADD COLUMN fluxo_mermaid TEXT DEFAULT NULL",
            "ALTER TABLE processos_detectados ADD COLUMN analise_markdown TEXT DEFAULT NULL",
            "ALTER TABLE processos_detectados ADD COLUMN analise_json TEXT DEFAULT NULL",
            "ALTER TABLE processos_detectados ADD COLUMN analise_updated_at TEXT DEFAULT NULL",
            "ALTER TABLE fontes ADD COLUMN reclock_tables TEXT DEFAULT '[]'",
            "ALTER TABLE fontes ADD COLUMN encoding TEXT DEFAULT 'cp1252'",
            "ALTER TABLE campos ADD COLUMN grpsxg TEXT DEFAULT ''",
            "ALTER TABLE funcao_docs ADD COLUMN resumo_auto TEXT DEFAULT ''",
        ]:
            try:
                self._conn.execute(col_ddl)
                self._conn.commit()
            except Exception:
                pass  # coluna ja existe ou tabela nao existe ainda

        # Tabelas novas (idempotente — CREATE IF NOT EXISTS)
        for tbl_ddl in [
            """CREATE TABLE IF NOT EXISTS record_counts (
                tabela      TEXT PRIMARY KEY,
                registros   INTEGER DEFAULT 0,
                updated_at  TEXT DEFAULT (datetime('now'))
            )""",
        ]:
            try:
                self._conn.execute(tbl_ddl)
                self._conn.commit()
            except Exception:
                pass

    def execute(self, sql: str, params: tuple = ()):
        return self._conn.execute(sql, params)

    def executemany(self, sql: str, params_list: list):
        self._conn.executemany(sql, params_list)
        self._conn.commit()

    def commit(self):
        self._conn.commit()

    def get_raw_conn(self) -> sqlite3.Connection:
        """Return raw sqlite3 connection for bulk operations with custom PRAGMAs."""
        return self._conn

    def close(self):
        if self._conn:
            self._conn.close()
