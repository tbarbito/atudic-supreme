# -*- coding: utf-8 -*-
"""Testes da aplicacao Flask."""

import pytest
from app import create_app


@pytest.fixture
def client():
    """Cria test client Flask."""
    app = create_app({"TESTING": True})
    with app.test_client() as client:
        yield client


def test_health_check(client):
    """GET /api/health deve retornar ok."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ok"
    assert data["service"] == "atudic-supreme"


def test_workspace_page(client):
    """GET / deve retornar pagina workspace."""
    response = client.get("/")
    assert response.status_code == 200
    assert b"AtuDIC" in response.data


def test_list_workspaces_empty(client):
    """GET /api/workspace/workspaces deve retornar lista (possivelmente vazia)."""
    response = client.get("/api/workspace/workspaces")
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)
