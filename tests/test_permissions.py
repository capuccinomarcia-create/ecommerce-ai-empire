"""Testes de permissões, aprovações e auditoria."""

from __future__ import annotations

from core.permissions import APPROVAL_ACTIONS, PermissionGate


def test_acoes_de_risco_exigem_aprovacao(repo):
    gate = PermissionGate(repo)
    for action in ("purchase", "payment", "price_change", "publish_listing",
                   "delete_product", "bulk_message", "campaign_change",
                   "financial_transaction"):
        decision = gate.check(action)
        assert decision.requires_approval is True
        assert decision.allowed is False


def test_acao_segura_liberada(repo):
    gate = PermissionGate(repo)
    assert gate.check("analyze").allowed is True
    assert gate.check("csv_import").requires_approval is False


def test_fluxo_de_aprovacao(repo):
    gate = PermissionGate(repo)
    approval = gate.request("purchase", {"item": "livro", "valor": 500},
                            resource_type="product", resource_id="p1", agent="supplier_hunter")
    assert approval["status"] == "pendente"
    assert gate.is_approved("purchase", "p1") is False

    gate.approve(approval["id"], "proprietario", "ok")
    assert gate.is_approved("purchase", "p1") is True
    assert repo.get("approvals", approval["id"])["decided_by"] == "proprietario"


def test_rejeicao(repo):
    gate = PermissionGate(repo)
    approval = gate.request("price_change", {}, resource_type="product", resource_id="p2")
    gate.reject(approval["id"], "proprietario", "margem insuficiente")
    assert gate.is_approved("price_change", "p2") is False


def test_execucao_bloqueada_sem_aprovacao(repo):
    gate = PermissionGate(repo)
    executed = {"value": False}

    def action():
        executed["value"] = True
        return "comprado"

    ok, result = gate.execute_guarded("purchase", action, resource_id="p9")
    assert ok is False
    assert executed["value"] is False
    assert result["blocked"] is True


def test_execucao_liberada_com_aprovacao(repo):
    gate = PermissionGate(repo)
    approval = gate.request("publish_listing", {}, resource_type="listing", resource_id="l1")
    gate.approve(approval["id"])

    ok, result = gate.execute_guarded("publish_listing", lambda: "publicado", resource_id="l1")
    assert ok is True
    assert result == "publicado"


def test_auditoria_registra_ator(repo):
    gate = PermissionGate(repo)
    gate.audit("proprietario", "teste", "product", "p1", {"x": 1})
    trail = gate.audit_trail()
    assert trail[0]["actor"] == "proprietario"
    assert trail[0]["details"] == {"x": 1}


def test_papeis(repo):
    gate = PermissionGate(repo)
    assert gate.role_can("viewer", "read") is True
    assert gate.role_can("viewer", "approve") is False
    assert gate.role_can("owner", "qualquer_coisa") is True


def test_lista_de_acoes_protegidas_completa():
    assert {"purchase", "payment", "price_change", "publish_listing", "delete_product",
            "bulk_message", "campaign_change", "financial_transaction"} <= set(APPROVAL_ACTIONS)
