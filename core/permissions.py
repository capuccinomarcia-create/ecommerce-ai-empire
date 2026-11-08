"""Permissões, aprovações e auditoria.

O proprietário tem controle absoluto: nenhuma ação de risco acontece sem um
registro de aprovação aprovado por ele.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from database.models import ApprovalStatus, RiskLevel
from core.utils import new_id, now_iso

# Ações que SEMPRE exigem aprovação humana (seção 13 do projeto)
APPROVAL_ACTIONS: dict[str, dict[str, str]] = {
    "purchase": {"risk": RiskLevel.CRITICO.value, "label": "Compra de produto/insumo"},
    "payment": {"risk": RiskLevel.CRITICO.value, "label": "Pagamento / transferência"},
    "price_change": {"risk": RiskLevel.ALTO.value, "label": "Alteração de preço"},
    "publish_listing": {"risk": RiskLevel.ALTO.value, "label": "Publicação de anúncio"},
    "delete_product": {"risk": RiskLevel.ALTO.value, "label": "Exclusão de produto"},
    "bulk_message": {"risk": RiskLevel.ALTO.value, "label": "Envio de mensagens em massa"},
    "campaign_change": {"risk": RiskLevel.ALTO.value, "label": "Alteração em campanha"},
    "financial_transaction": {"risk": RiskLevel.CRITICO.value, "label": "Operação financeira"},
    "connector_write": {"risk": RiskLevel.MEDIO.value, "label": "Escrita em API externa"},
}

# Ações permitidas sem aprovação (somente leitura/análise)
SAFE_ACTIONS: set[str] = {
    "read", "analyze", "score", "report", "draft", "simulate", "csv_import",
    "csv_export", "list", "search", "calculate",
}

# Matriz de papéis do painel
ROLE_CAPABILITIES: dict[str, set[str]] = {
    "owner": {"*"},
    "admin": {"read", "analyze", "score", "report", "draft", "simulate", "csv_import",
              "csv_export", "list", "search", "calculate", "approve", "configure"},
    "analyst": {"read", "analyze", "score", "report", "draft", "simulate", "csv_import",
                "csv_export", "list", "search", "calculate"},
    "viewer": {"read", "list", "search"},
}


@dataclass
class PermissionDecision:
    allowed: bool
    requires_approval: bool
    risk_level: str
    reason: str
    approval_id: str = ""


class PermissionGate:
    def __init__(self, repo, settings=None):
        self.repo = repo
        self.settings = settings

    # --------------------------------------------------------------- regras --
    def requires_approval(self, action: str) -> bool:
        return action in APPROVAL_ACTIONS

    def check(self, action: str, approved: bool = False) -> PermissionDecision:
        if action in SAFE_ACTIONS:
            return PermissionDecision(True, False, RiskLevel.BAIXO.value, "ação segura (somente leitura/análise)")
        if action in APPROVAL_ACTIONS:
            risk = APPROVAL_ACTIONS[action]["risk"]
            label = APPROVAL_ACTIONS[action]["label"]
            if approved:
                return PermissionDecision(True, False, risk, f"aprovado pelo proprietário: {label}")
            return PermissionDecision(
                False, True, risk, f"requer aprovação do proprietário: {label}"
            )
        return PermissionDecision(False, True, RiskLevel.ALTO.value, f"ação desconhecida: {action}")

    # ------------------------------------------------------------ aprovações --
    def request(
        self,
        action: str,
        payload: dict[str, Any] | None = None,
        resource_type: str = "",
        resource_id: str = "",
        agent: str = "",
        requested_by: str = "ceo_ai",
    ) -> dict[str, Any]:
        info = APPROVAL_ACTIONS.get(action, {"risk": RiskLevel.ALTO.value, "label": action})
        approval = self.repo.insert(
            "approvals",
            {
                "id": new_id("apr"),
                "action": action,
                "risk_level": info["risk"],
                "resource_type": resource_type or None,
                "resource_id": resource_id or None,
                "payload": payload or {},
                "status": ApprovalStatus.PENDENTE.value,
                "requested_by_agent": agent or None,
                "requested_by": requested_by,
                "created_at": now_iso(),
            },
        )
        self.audit(requested_by, f"approval_requested:{action}", resource_type, resource_id,
                   {"approval_id": approval["id"], "agent": agent})
        return approval

    def decide(self, approval_id: str, decision: str, decided_by: str, note: str = "") -> dict:
        if decision not in {ApprovalStatus.APROVADO.value, ApprovalStatus.REJEITADO.value,
                            ApprovalStatus.CANCELADO.value}:
            raise ValueError("decisão inválida")
        approval = self.repo.get("approvals", approval_id)
        if not approval:
            raise ValueError("aprovação não encontrada")
        updated = self.repo.update(
            "approvals",
            approval_id,
            {"status": decision, "decided_by": decided_by, "decided_at": now_iso(), "note": note},
        )
        self.audit(decided_by, f"approval_{decision}", "approval", approval_id,
                   {"action": approval["action"], "note": note})
        return updated or approval

    def approve(self, approval_id: str, decided_by: str = "proprietario", note: str = "") -> dict:
        return self.decide(approval_id, ApprovalStatus.APROVADO.value, decided_by, note)

    def reject(self, approval_id: str, decided_by: str = "proprietario", note: str = "") -> dict:
        return self.decide(approval_id, ApprovalStatus.REJEITADO.value, decided_by, note)

    def cancel(self, approval_id: str, decided_by: str = "proprietario", note: str = "") -> dict:
        return self.decide(approval_id, ApprovalStatus.CANCELADO.value, decided_by, note)

    def is_approved(self, action: str, resource_id: str = "") -> bool:
        filters: dict[str, Any] = {"action": action, "status": ApprovalStatus.APROVADO.value}
        if resource_id:
            filters["resource_id"] = resource_id
        return self.repo.count("approvals", filters) > 0

    def pending(self, limit: int = 50) -> list[dict]:
        return self.repo.find(
            "approvals", {"status": ApprovalStatus.PENDENTE.value},
            order_by="-created_at", limit=limit,
        )

    def history(self, limit: int = 100) -> list[dict]:
        return self.repo.find("approvals", {}, order_by="-created_at", limit=limit)

    # ------------------------------------------------------------- execução --
    def execute_guarded(
        self,
        action: str,
        func: Callable[[], Any],
        resource_id: str = "",
        actor: str = "ceo_ai",
    ) -> tuple[bool, Any]:
        """Executa somente se houver aprovação válida para a ação."""
        if not self.requires_approval(action):
            return True, func()
        if self.is_approved(action, resource_id):
            result = func()
            self.audit(actor, f"executed:{action}", "resource", resource_id, {})
            return True, result
        return False, {"blocked": True, "reason": f"ação '{action}' aguarda aprovação"}

    # ------------------------------------------------------------- auditoria --
    def audit(
        self,
        actor: str,
        action: str,
        resource_type: str = "",
        resource_id: str = "",
        details: dict[str, Any] | None = None,
    ) -> dict:
        return self.repo.insert(
            "audit_logs",
            {
                "id": new_id("log"),
                "actor": actor or "sistema",
                "action": action,
                "resource_type": resource_type or None,
                "resource_id": resource_id or None,
                "details": details or {},
                "created_at": now_iso(),
            },
        )

    def audit_trail(self, limit: int = 100) -> list[dict]:
        return self.repo.find("audit_logs", {}, order_by="-created_at", limit=limit)

    # -------------------------------------------------------------- papéis --
    @staticmethod
    def role_can(role: str, capability: str) -> bool:
        allowed = ROLE_CAPABILITIES.get(role, set())
        return "*" in allowed or capability in allowed
