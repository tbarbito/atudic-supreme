# -*- coding: utf-8 -*-
"""Testes do workspace database (schema SQLite)."""

import pytest
from pathlib import Path
from app.services.workspace.workspace_db import Database


@pytest.fixture
def db(tmp_path):
    """Cria database em diretorio temporario."""
    db = Database(tmp_path / "test.db")
    db.initialize()
    return db


def test_initialize_creates_tables(db):
    """Schema deve criar todas as tabelas."""
    tables = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    table_names = [t[0] for t in tables]

    # Tabelas essenciais
    assert "tabelas" in table_names
    assert "campos" in table_names
    assert "indices" in table_names
    assert "gatilhos" in table_names
    assert "fontes" in table_names
    assert "fonte_chunks" in table_names
    assert "vinculos" in table_names
    assert "operacoes_escrita" in table_names
    assert "diff" in table_names


def test_insert_tabela(db):
    """Deve inserir e recuperar tabela."""
    db.execute(
        "INSERT INTO tabelas (codigo, nome, modo, custom) VALUES (?,?,?,?)",
        ("SA1", "Clientes", "C", 0)
    )
    db.commit()

    row = db.execute("SELECT * FROM tabelas WHERE codigo = 'SA1'").fetchone()
    assert row[0] == "SA1"
    assert row[1] == "Clientes"


def test_insert_campo_custom(db):
    """Deve inserir campo customizado."""
    db.execute(
        "INSERT INTO tabelas (codigo, nome, modo, custom) VALUES (?,?,?,?)",
        ("SA1", "Clientes", "C", 0)
    )
    db.execute(
        "INSERT INTO campos (tabela, campo, tipo, tamanho, decimal, titulo, custom) "
        "VALUES (?,?,?,?,?,?,?)",
        ("SA1", "A1_XCODINT", "C", 10, 0, "Cod Interno", 1)
    )
    db.commit()

    rows = db.execute("SELECT * FROM campos WHERE custom = 1").fetchall()
    assert len(rows) == 1
    assert rows[0][1] == "A1_XCODINT"


def test_executemany(db):
    """Deve inserir multiplos registros em batch."""
    tabelas = [
        ("SA1", "Clientes", "C", 0),
        ("SA2", "Fornecedores", "C", 0),
        ("SB1", "Produtos", "C", 0),
    ]
    db.executemany(
        "INSERT INTO tabelas (codigo, nome, modo, custom) VALUES (?,?,?,?)",
        tabelas
    )

    count = db.execute("SELECT COUNT(*) FROM tabelas").fetchone()[0]
    assert count == 3


def test_double_initialize(db):
    """Inicializar 2x nao deve dar erro."""
    db.initialize()  # Segunda vez
    tables = db.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
    ).fetchone()[0]
    assert tables > 0
