# -*- coding: utf-8 -*-
"""Testes do parser de codigo-fonte ADVPL/TLPP."""

import pytest
from pathlib import Path
from app.services.workspace.parser_source import (
    parse_source, _extract_functions, _extract_tables,
    _extract_user_functions, _extract_point_of_entry,
    _extract_calls_u, _extract_write_tables, _extract_reclock_tables,
    _extract_fields_ref, _detect_source_type,
)


# ── Fixtures ──

SAMPLE_ADVPL = """
#Include "Protheus.ch"

User Function MATA410PE()
    Local cMsg := "Teste"
    DbSelectArea("SC5")
    SC5->(dbSetOrder(1))
    If SC5->C5_NUM > 0
        MsgInfo("Pedido: " + SC5->C5_NUM)
    EndIf
    U_ValidaCustom()
Return

Static Function ValidaCustom()
    DbSelectArea("SA1")
    SA1->(dbSeek(xFilial("SA1") + cCodCli))
    If SA1->A1_NOME != ""
        RecLock("SC5", .F.)
            SC5->C5_XOBS := "Validado"
        MsUnlock()
    EndIf
Return
"""


@pytest.fixture
def sample_file(tmp_path):
    """Cria arquivo .prw temporario."""
    f = tmp_path / "TESTE.prw"
    f.write_text(SAMPLE_ADVPL, encoding="cp1252")
    return f


# ── Testes de extracao ──

def test_extract_functions():
    funcs = _extract_functions(SAMPLE_ADVPL)
    assert "MATA410PE" in funcs
    assert "ValidaCustom" in funcs


def test_extract_user_functions():
    uf = _extract_user_functions(SAMPLE_ADVPL)
    assert "MATA410PE" in uf
    assert "ValidaCustom" not in uf  # Static, nao User


def test_extract_tables():
    tables = _extract_tables(SAMPLE_ADVPL)
    assert "SC5" in tables
    assert "SA1" in tables


def test_extract_point_of_entry():
    user_funcs = ["MATA410PE", "OutraFunc"]
    pes = _extract_point_of_entry(user_funcs)
    # MATA410PE nao e PE padrao (nao segue pattern A410xxx)
    # Mas funcoes como MT410GRV seriam
    assert isinstance(pes, list)


def test_extract_calls_u():
    calls = _extract_calls_u(SAMPLE_ADVPL)
    assert "ValidaCustom" in calls


def test_extract_write_tables():
    writes = _extract_write_tables(SAMPLE_ADVPL)
    assert "SC5" in writes


def test_extract_reclock_tables():
    reclocks = _extract_reclock_tables(SAMPLE_ADVPL)
    assert "SC5" in reclocks


def test_extract_fields_ref():
    fields = _extract_fields_ref(SAMPLE_ADVPL)
    assert "C5_NUM" in fields or "C5_XOBS" in fields
    assert "A1_NOME" in fields


def test_detect_source_type():
    assert _detect_source_type(SAMPLE_ADVPL) == "user_function"
    assert _detect_source_type("WSSERVICE MyWS") == "webservice"
    assert _detect_source_type("CLASS MyClass") == "class"


# ── Teste de parse completo ──

def test_parse_source_complete(sample_file):
    result = parse_source(sample_file, include_chunks=False)

    assert result["arquivo"] == "TESTE.prw"
    assert "MATA410PE" in result["funcoes"]
    assert "SC5" in result["tabelas_ref"]
    assert "SC5" in result["write_tables"]
    assert result["lines_of_code"] > 0
    assert result["hash"]


def test_parse_source_with_chunks(sample_file):
    result = parse_source(sample_file, include_chunks=True)

    assert "chunks" in result
    assert len(result["chunks"]) > 0
    assert all("id" in c and "content" in c for c in result["chunks"])
