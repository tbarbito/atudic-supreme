# -*- coding: utf-8 -*-
"""Testes do KnowledgeService."""

import json
import pytest
from pathlib import Path
from app.services.workspace.workspace_db import Database
from app.services.workspace.knowledge import KnowledgeService


@pytest.fixture
def populated_db(tmp_path):
    """Cria database com dados de teste."""
    db = Database(tmp_path / "test.db")
    db.initialize()

    # Tabela
    db.execute(
        "INSERT INTO tabelas (codigo, nome, modo, custom) VALUES (?,?,?,?)",
        ("SA1", "Clientes", "C", 0)
    )

    # Campos
    campos = [
        ("SA1", "A1_COD", "C", 6, 0, "Codigo", "Codigo do cliente", "", "", 1, 0, "", "", "", "", "S", "", "", "", "", ""),
        ("SA1", "A1_NOME", "C", 40, 0, "Nome", "Nome do cliente", "", "", 1, 0, "", "", "", "", "S", "", "", "", "", ""),
        ("SA1", "A1_XCODINT", "C", 10, 0, "Cod Interno", "Codigo interno", "U_ValidaCod()", "", 0, 1, "", "", "U_ValidaCod()", "", "N", "", "", "", "", ""),
    ]
    db.executemany(
        "INSERT INTO campos (tabela, campo, tipo, tamanho, decimal, titulo, descricao, "
        "validacao, inicializador, obrigatorio, custom, f3, cbox, vlduser, when_expr, "
        "proprietario, browse, trigger_flag, visual, context, folder) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        campos
    )

    # Indice
    db.execute(
        "INSERT INTO indices (tabela, ordem, chave, descricao, custom) VALUES (?,?,?,?,?)",
        ("SA1", "X", "A1_XCODINT", "Indice Custom", 1)
    )

    # Gatilho
    db.execute(
        "INSERT INTO gatilhos (campo_origem, sequencia, campo_destino, regra, custom) VALUES (?,?,?,?,?)",
        ("A1_COD", "001", "A1_XCODINT", "U_GeraInterno()", 1)
    )

    # Fonte
    db.execute(
        "INSERT INTO fontes (arquivo, caminho, tipo, modulo, funcoes, user_funcs, "
        "pontos_entrada, tabelas_ref, write_tables, includes, lines_of_code, hash) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        ("VALIDA.prw", "/fontes/VALIDA.prw", "custom", "faturamento",
         json.dumps(["ValidaCod", "GeraInterno"]),
         json.dumps(["ValidaCod"]),
         json.dumps([]),
         json.dumps(["SA1", "SC5"]),
         json.dumps(["SA1"]),
         json.dumps([]),
         150, "abc123")
    )

    db.commit()
    return db


def test_get_table_info(populated_db):
    ks = KnowledgeService(populated_db)
    info = ks.get_table_info("SA1")

    assert info is not None
    assert info["codigo"] == "SA1"
    assert len(info["campos"]) == 3
    assert len(info["campos_custom"]) == 1
    assert info["campos_custom"][0]["campo"] == "A1_XCODINT"


def test_get_table_info_not_found(populated_db):
    ks = KnowledgeService(populated_db)
    info = ks.get_table_info("ZZZ")
    assert info is None


def test_get_custom_summary(populated_db):
    ks = KnowledgeService(populated_db)
    summary = ks.get_custom_summary()

    assert summary["campos_custom"] == 1
    assert summary["fontes_custom"] == 1


def test_get_fontes_for_module(populated_db):
    ks = KnowledgeService(populated_db)
    fontes = ks.get_fontes_for_module("faturamento")

    assert len(fontes) == 1
    assert fontes[0]["arquivo"] == "VALIDA.prw"
    assert "ValidaCod" in fontes[0]["funcoes"]


def test_build_context_for_module(populated_db):
    ks = KnowledgeService(populated_db)
    context = ks.build_context_for_module("faturamento")

    assert isinstance(context, str)
    assert len(context) > 0
    assert "SA1" in context


def test_build_deep_field_analysis(populated_db):
    ks = KnowledgeService(populated_db)
    analysis = ks.build_deep_field_analysis("SA1")

    assert isinstance(analysis, str)
    assert "A1_XCODINT" in analysis
