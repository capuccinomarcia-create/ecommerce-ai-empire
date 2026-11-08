"""Rotas REST. Tudo que o painel faz, a API também faz."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from agents.base import MarketContext
from analytics.profitability import FinancialInput, calculate, compare_marketplaces
from analytics.product_score import ScoreInput, score_product
from api.deps import get_orchestrator
from core.utils import local_now
from integrations import APIError, NotConfigured, build_connector, connector_statuses
from integrations.generic_csv import TEMPLATES, export_csv, import_csv

router = APIRouter(prefix="/api", tags=["empire"])


# --------------------------------------------------------------------- modelos --
class CommandBody(BaseModel):
    command: str = Field(..., min_length=3, max_length=2000)
    requested_by: str = "proprietario"


class ChatBody(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)
    user: str = "proprietario"


class ScoreBody(BaseModel):
    name: str = "Produto"
    demanda: float | None = None
    margem: float | None = None
    concorrencia: float | None = None
    tendencia: float | None = None
    logistica: float | None = None
    trafego: float | None = None
    sources: dict[str, str] = Field(default_factory=dict)


class DecisionBody(BaseModel):
    decided_by: str = "proprietario"
    note: str = ""


class MarketplaceRuleBody(BaseModel):
    commission_pct: float = Field(0, ge=0, le=100)
    fixed_fee: float = Field(0, ge=0)
    notes: str = ""
    source: str = "informado pelo proprietário"


class ProductBody(BaseModel):
    name: str
    sku: str = ""
    category: str = ""
    description: str = ""
    purchase_price: float = 0
    extra_cost: float = 0
    sale_price: float = 0
    marketplace: str = "shopee"


class ToggleBody(BaseModel):
    enabled: bool = True


# --------------------------------------------------------------------- sistema --
@router.get("/health")
def health() -> dict[str, Any]:
    orch = get_orchestrator()
    return {
        "ok": True,
        "app": orch.settings.app_name,
        "version": orch.settings.version,
        "time": local_now(orch.settings.timezone).isoformat(),
        "database": getattr(orch.repo, "backend", "desconhecido"),
    }


@router.get("/status")
def status() -> dict[str, Any]:
    return get_orchestrator().status()


@router.get("/ai/status")
def ai_status() -> dict[str, Any]:
    orch = get_orchestrator()
    return {"providers": orch.ai.status(), "usage": orch.ai.usage_summary()}


# ------------------------------------------------------------------------ CEO --
@router.post("/chat")
def chat(body: ChatBody) -> dict[str, Any]:
    """Comando em linguagem natural no mesmo motor do chat do terminal/Telegram."""
    from core.chat_agent import ChatAgent

    agente = ChatAgent(orchestrator=get_orchestrator(), user=body.user)
    resposta = agente.handle_message(body.text)
    return {
        "reply": resposta.reply,
        "kind": resposta.kind,
        "wait_for_approval": resposta.wait_for_approval,
        "history": agente.historico(6),
    }


@router.get("/chat/history")
def chat_history(limit: int = 20) -> list[dict[str, Any]]:
    from core.chat_agent import ChatAgent

    return ChatAgent(orchestrator=get_orchestrator()).historico(min(limit, 100))


@router.post("/ceo/command")
def ceo_command(body: CommandBody) -> dict[str, Any]:
    return get_orchestrator().handle(body.command, requested_by=body.requested_by)


# --------------------------------------------------------------------- agentes --
@router.get("/agents")
def list_agents() -> list[dict[str, Any]]:
    return get_orchestrator().repo.find("agents", {}, order_by="name")


@router.get("/tasks")
def list_tasks(status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    return get_orchestrator().tasks.list_tasks(status=status, limit=limit)


@router.get("/tasks/{task_id}")
def get_task(task_id: str) -> dict[str, Any]:
    orch = get_orchestrator()
    task = orch.tasks.get(task_id)
    if not task:
        raise HTTPException(404, "tarefa não encontrada")
    return {"task": task, "events": orch.tasks.events(task_id)}


@router.post("/tasks/{task_id}/cancel")
def cancel_task(task_id: str, reason: str = "cancelada pelo proprietário") -> dict[str, Any]:
    orch = get_orchestrator()
    task = orch.tasks.get(task_id)
    if not task:
        raise HTTPException(404, "tarefa não encontrada")
    orch.permissions.audit("proprietario", "task_cancel", "task", task_id, {"reason": reason})
    return orch.tasks.cancel(task_id, reason) or {}


# -------------------------------------------------------------------- aprovações --
@router.get("/approvals")
def list_approvals(status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    orch = get_orchestrator()
    filters = {"status": status} if status else {}
    return orch.repo.find("approvals", filters, order_by="-created_at", limit=limit)


@router.post("/approvals/{approval_id}/approve")
def approve(approval_id: str, body: DecisionBody) -> dict[str, Any]:
    return _decide(approval_id, "aprovar", body)


@router.post("/approvals/{approval_id}/reject")
def reject(approval_id: str, body: DecisionBody) -> dict[str, Any]:
    return _decide(approval_id, "rejeitar", body)


@router.post("/approvals/{approval_id}/cancel")
def cancel_approval(approval_id: str, body: DecisionBody) -> dict[str, Any]:
    return _decide(approval_id, "cancelar", body)


def _decide(approval_id: str, action: str, body: DecisionBody) -> dict[str, Any]:
    gate = get_orchestrator().permissions
    try:
        if action == "aprovar":
            return gate.approve(approval_id, body.decided_by, body.note)
        if action == "rejeitar":
            return gate.reject(approval_id, body.decided_by, body.note)
        return gate.cancel(approval_id, body.decided_by, body.note)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/audit")
def audit_trail(limit: int = 100) -> list[dict[str, Any]]:
    return get_orchestrator().permissions.audit_trail(limit)


# --------------------------------------------------------------------- catálogo --
@router.get("/products")
def list_products(limit: int = 200) -> list[dict[str, Any]]:
    return get_orchestrator().repo.find("products", {}, order_by="-updated_at", limit=limit)


@router.post("/products")
def create_product(body: ProductBody) -> dict[str, Any]:
    repo = get_orchestrator().repo
    return repo.insert("products", body.model_dump())


@router.get("/opportunities")
def list_opportunities(limit: int = 200) -> list[dict[str, Any]]:
    return get_orchestrator().repo.find("opportunities", {}, order_by="-created_at", limit=limit)


# -------------------------------------------------------------------- cálculos --
@router.post("/financial/calculate")
def financial_calculate(body: FinancialInput) -> dict[str, Any]:
    return calculate(body).to_dict()


@router.get("/financial/compare")
def financial_compare(product_id: str, target_margin_pct: float = 20.0) -> dict[str, Any]:
    orch = get_orchestrator()
    product = orch.repo.get("products", product_id)
    if not product:
        raise HTTPException(404, "produto não encontrado")
    market = MarketContext(_ctx_like(orch))
    rules = market.rules()
    base = FinancialInput(
        product_name=product["name"],
        marketplace=product.get("marketplace") or "shopee",
        costs={
            "purchase_price": float(product.get("purchase_price") or 0),
            "other_costs": float(product.get("extra_cost") or 0),
        },
        terms={"sale_price": float(product.get("sale_price") or 1)},
        target_margin_pct=target_margin_pct,
    )
    return {"rows": compare_marketplaces(base, rules)}


@router.post("/score")
def score(body: ScoreBody) -> dict[str, Any]:
    return score_product(ScoreInput(**body.model_dump())).to_dict()


def _ctx_like(orch):
    """Adaptador mínimo para reutilizar MarketContext fora de uma tarefa."""
    from types import SimpleNamespace

    return SimpleNamespace(repo=orch.repo, settings=orch.settings)


# --------------------------------------------------------------------- canais --
@router.get("/connectors")
def connectors() -> list[dict[str, Any]]:
    orch = get_orchestrator()
    return connector_statuses(orch.settings, orch.repo)


@router.post("/connectors/{channel}/test")
def test_connector(channel: str) -> dict[str, Any]:
    orch = get_orchestrator()
    try:
        connector = build_connector(channel, orch.settings, orch.repo)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    status = connector.status().to_dict()
    if not status["connected"]:
        return {"connected": False, "status": status, "items": [],
                "message": "Não conectado: credenciais ausentes. Use CSV."}
    try:
        items = connector.fetch_products(limit=10)
        return {"connected": True, "status": status, "items": items}
    except (NotConfigured, APIError) as exc:
        return {"connected": False, "status": status, "items": [], "message": str(exc)}


@router.get("/marketplaces")
def marketplaces() -> list[dict[str, Any]]:
    return get_orchestrator().repo.find("marketplaces", {}, order_by="name")


@router.put("/marketplaces/{slug}")
def update_marketplace(slug: str, body: MarketplaceRuleBody) -> dict[str, Any]:
    orch = get_orchestrator()
    row = orch.repo.find_one("marketplaces", {"slug": slug})
    if not row:
        raise HTTPException(404, "canal não encontrado")
    updated = orch.repo.update(
        "marketplaces", row["id"],
        {"commission_pct": body.commission_pct, "fixed_fee": body.fixed_fee,
         "notes": body.notes, "source": body.source},
    )
    orch.permissions.audit("proprietario", "marketplace_rule_update", "marketplace", slug,
                           body.model_dump())
    return updated or row


# ---------------------------------------------------------------------- CSV --
@router.get("/imports/templates")
def csv_templates() -> dict[str, Any]:
    return {"entities": list(TEMPLATES), "templates": TEMPLATES}


@router.post("/imports/csv")
async def import_csv_upload(
    entity: str,
    file: UploadFile = File(...),
    is_demo: bool = False,
) -> dict[str, Any]:
    if entity not in TEMPLATES:
        raise HTTPException(400, f"entidade inválida. Use: {', '.join(TEMPLATES)}")
    orch = get_orchestrator()
    suffix = Path(file.filename or "upload.csv").suffix or ".csv"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name
    try:
        result = import_csv(tmp_path, entity, orch.repo, is_demo=is_demo, source="upload_csv")
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    orch.permissions.audit("proprietario", "csv_import", entity, "", {
        "file": file.filename, "imported": result["imported"], "skipped": result["skipped"]})
    return {k: v for k, v in result.items() if k != "rows"}


@router.get("/exports/{entity}")
def export_entity(entity: str, limit: int = 500) -> dict[str, Any]:
    if entity not in TEMPLATES:
        raise HTTPException(400, "entidade inválida")
    orch = get_orchestrator()
    rows = orch.repo.find(entity, {}, limit=limit)
    path = Path("exports") / f"{entity}_{local_now().strftime('%Y%m%d_%H%M')}.csv"
    export_csv(rows, path)
    return {"path": str(path), "rows": len(rows)}


# ------------------------------------------------------------------ relatórios --
@router.get("/reports")
def list_reports(limit: int = 50) -> list[dict[str, Any]]:
    return get_orchestrator().repo.find("reports", {}, order_by="-created_at", limit=limit)


@router.get("/reports/{report_id}")
def get_report(report_id: str) -> dict[str, Any]:
    report = get_orchestrator().repo.get("reports", report_id)
    if not report:
        raise HTTPException(404, "relatório não encontrado")
    return report


# ------------------------------------------------------------------ automações --
@router.get("/automations")
def list_automations() -> list[dict[str, Any]]:
    return get_orchestrator().repo.find("automations", {}, order_by="name")


@router.post("/automations/register-defaults")
def register_defaults() -> dict[str, Any]:
    orch = get_orchestrator()
    agent = orch.agents["automation"]
    from agents.base import AgentContext

    task = orch.tasks.create("automation", "register_defaults",
                             "Cadastrar rotinas padrão", {})
    orch.tasks.start(task["id"])
    result = agent.run(AgentContext(
        repo=orch.repo, settings=orch.settings, ai=orch.ai, memory=orch.memory,
        tasks=orch.tasks, permissions=orch.permissions, task=task,
    ))
    orch.tasks.complete(task["id"], result.to_dict())
    return result.to_dict()


@router.post("/automations/{name}/toggle")
def toggle_automation(name: str, body: ToggleBody) -> dict[str, Any]:
    orch = get_orchestrator()
    row = orch.repo.find_one("automations", {"name": name})
    if not row:
        raise HTTPException(404, "automação não encontrada")
    updated = orch.repo.update("automations", row["id"], {"enabled": body.enabled})
    orch.permissions.audit("proprietario", "automation_toggle", "automation", name,
                           {"enabled": body.enabled})
    return updated or row


# ------------------------------------------------------------------ demo data --
@router.post("/demo/seed")
def seed_demo_data() -> dict[str, Any]:
    from scripts.seed_demo import seed_demo

    orch = get_orchestrator()
    report = seed_demo(orch.repo)
    orch.permissions.audit("proprietario", "demo_seed", "demo", "", {})
    return {"ok": True, "report": {k: v.get("imported") for k, v in report.items()}}


@router.delete("/demo")
def clear_demo_data() -> dict[str, Any]:
    from scripts.seed_demo import clear_demo

    orch = get_orchestrator()
    removed = clear_demo(orch.repo)
    orch.permissions.audit("proprietario", "demo_clear", "demo", "", {"removed": removed})
    return {"ok": True, "removed": removed}
