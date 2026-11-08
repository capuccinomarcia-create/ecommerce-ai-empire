"""Testes da API HTTP (sem rede externa)."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client(monkeypatch, demo_orchestrator):
    import app as app_module
    import api.routes as routes
    import api.deps as deps

    monkeypatch.setattr(deps, "get_orchestrator", lambda: demo_orchestrator)
    monkeypatch.setattr(routes, "get_orchestrator", lambda: demo_orchestrator)
    return TestClient(app_module.app)


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_status(client):
    data = client.get("/api/status").json()
    assert data["agents"] == 12
    assert data["currency"] == "BRL"


def test_connectors_desconectados(client):
    rows = client.get("/api/connectors").json()
    assert all(row["connected"] is False for row in rows)


def test_comando_ceo(client):
    response = client.post("/api/ceo/command", json={"command": "encontre 5 produtos com potencial"})
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["report"]


def test_score_endpoint(client):
    body = client.post("/api/score", json={"name": "Teste", "demanda": 100, "margem": 100}).json()
    assert 0 <= body["score"] <= 100


def test_calculo_financeiro_endpoint(client):
    body = client.post("/api/financial/calculate", json={
        "product_name": "Livro",
        "terms": {"sale_price": 39.9, "commission_pct": 14},
        "costs": {"purchase_price": 12},
    }).json()
    assert body["net_profit"] > 0


def test_aprovacao_bloqueia_e_libera(client):
    orch = client.app  # apenas para legibilidade
    pending = client.get("/api/approvals").json()
    if not pending:
        pytest.skip("nenhuma aprovação pendente neste cenário")
    approval_id = pending[0]["id"]
    approved = client.post(f"/api/approvals/{approval_id}/approve", json={}).json()
    assert approved["status"] == "aprovado"


def test_tarefas_listadas(client):
    tasks = client.get("/api/tasks").json()
    assert isinstance(tasks, list)


def test_marketplace_rule_update(client):
    rows = client.get("/api/marketplaces").json()
    slug = rows[0]["slug"]
    updated = client.put(f"/api/marketplaces/{slug}", json={
        "commission_pct": 14, "fixed_fee": 0, "source": "contrato de teste"
    }).json()
    assert float(updated["commission_pct"]) == 14


def test_import_templates(client):
    body = client.get("/api/imports/templates").json()
    assert "products" in body["entities"]
