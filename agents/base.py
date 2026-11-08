"""Base comum dos agentes + contexto compartilhado (blackboard)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from analytics.profitability import FinancialInput, FinancialResult, calculate
from analytics.product_score import ScoreResult, score_from_product
from core.config import Settings
from core.utils import now_iso


@dataclass
class AgentResult:
    summary: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    findings: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    data_gaps: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    approvals_requested: list[dict[str, Any]] = field(default_factory=list)
    narrative: str = ""
    ai_provider: str = "deterministico"

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "data": self.data,
            "findings": self.findings,
            "warnings": self.warnings,
            "data_gaps": self.data_gaps,
            "next_actions": self.next_actions,
            "approvals_requested": self.approvals_requested,
            "narrative": self.narrative,
            "ai_provider": self.ai_provider,
        }


@dataclass
class AgentContext:
    """Tudo que um agente pode usar, mais o quadro de resultados anteriores."""

    repo: Any
    settings: Settings
    ai: Any
    memory: Any
    tasks: Any
    permissions: Any
    task: dict[str, Any]
    shared: dict[str, Any] = field(default_factory=dict)
    logs: list[str] = field(default_factory=list)

    def payload(self) -> dict[str, Any]:
        return self.task.get("payload") or {}

    def log(self, message: str) -> None:
        self.logs.append(f"[{now_iso()}] {self.task.get('agent')}: {message}")

    def shared_results(self) -> list[dict[str, Any]]:
        return [v for v in self.shared.values() if isinstance(v, dict) and "summary" in v]


class BaseAgent(ABC):
    name: str = "base"
    role: str = "Agente"
    description: str = ""
    capabilities: list[str] = []
    tools: list[dict[str, str]] = []

    def run(self, ctx: AgentContext) -> AgentResult:
        self.ctx = ctx
        result = self.execute()
        if not result.summary:
            result.summary = f"{self.role} concluiu a análise."
        return result

    @abstractmethod
    def execute(self) -> AgentResult:
        """Implementação específica de cada especialista."""

    # ------------------------------------------------------------- utilidades --
    def narrate(self, intro: str, bullets: list[str], closing: str = "",
                allow_remote: bool = True) -> tuple[str, str]:
        """Pede uma redação ao provedor de IA; offline também funciona."""
        response = self.ctx.ai.generate(
            prompt=intro + "\n" + "\n".join(bullets),
            system=(
                "Você é o agente " + self.role + " de uma operação de e-commerce no Brasil. "
                "Escreva em português brasileiro, objetivamente, sem inventar números, "
                "sem prometer resultados e usando apenas os fatos fornecidos."
            ),
            facts={"intro": intro, "bullets": bullets, "closing": closing},
            agent=self.name,
            task_id=self.ctx.task.get("id", ""),
            allow_remote=allow_remote,
        )
        return response.text, response.provider

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role,
            "description": self.description,
            "status": "ativo",
            "capabilities": self.capabilities,
            "tools": self.tools,
        }


class MarketContext:
    """Leitura padronizada de catálogo, regras de canal e cálculos."""

    def __init__(self, ctx: AgentContext):
        self.ctx = ctx
        self.repo = ctx.repo
        self.settings = ctx.settings

    # ------------------------------------------------------------------ regras --
    def rules(self) -> dict[str, dict[str, Any]]:
        rows = self.repo.find("marketplaces")
        rules: dict[str, dict[str, Any]] = {}
        for row in rows:
            rules[row["slug"]] = {
                "commission_pct": float(row.get("commission_pct") or 0),
                "fixed_fee": float(row.get("fixed_fee") or 0),
                "subsidized_shipping": 0.0,
                "source": row.get("source") or "não informado",
                "label": row.get("name") or row["slug"],
            }
        return rules

    def rule_for(self, channel: str) -> dict[str, Any]:
        rules = self.rules()
        if channel in rules:
            return rules[channel]
        from database.models import MARKETPLACE_LABELS

        return {
            "commission_pct": 0.0,
            "fixed_fee": 0.0,
            "subsidized_shipping": 0.0,
            "source": "canal sem regra cadastrada",
            "label": MARKETPLACE_LABELS.get(channel, channel),
        }

    # ---------------------------------------------------------------- catálogo --
    def products(self, limit: int = 200, include_demo: bool = True) -> list[dict]:
        filters = {} if include_demo else {"is_demo": False}
        return self.repo.find("products", filters, order_by="-updated_at", limit=limit)

    def opportunities(self, limit: int = 200) -> list[dict]:
        return self.repo.find("opportunities", {}, order_by="-created_at", limit=limit)

    def candidates(self) -> list[dict]:
        """Candidatos a análise: oportunidades cadastradas ou catálogo."""
        opportunities = self.opportunities()
        if opportunities:
            return [
                {
                    "name": o.get("name"),
                    "category": o.get("category"),
                    "channel": o.get("marketplace") or "shopee",
                    "price_found": o.get("price_found"),
                    "cost_estimate": o.get("cost_estimate"),
                    "criteria": (o.get("breakdown") or {}).get("criteria", {}),
                    "sources": (o.get("breakdown") or {}).get("sources", {}),
                    "id": o.get("id"),
                    "is_demo": o.get("is_demo"),
                }
                for o in opportunities
            ]
        return [
            {
                "name": p.get("name"),
                "category": p.get("category"),
                "channel": p.get("marketplace") or "shopee",
                "price_found": p.get("sale_price"),
                "cost_estimate": float(p.get("purchase_price") or 0) + float(p.get("extra_cost") or 0),
                "criteria": {},
                "sources": {},
                "id": p.get("id"),
                "is_demo": p.get("is_demo"),
            }
            for p in self.products()
        ]

    # --------------------------------------------------------------- cálculos --
    def financial(
        self,
        product: dict,
        channel: str | None = None,
        quantity: int = 1,
        target_margin: float = 20.0,
    ) -> FinancialResult:
        channel = channel or product.get("marketplace") or "shopee"
        rule = self.rule_for(channel)
        data = FinancialInput(
            product_name=product.get("name", "Produto"),
            marketplace=channel,
            quantity=quantity,
            costs={
                "purchase_price": float(product.get("purchase_price") or 0),
                "acquisition_shipping": float(product.get("acquisition_shipping") or 0),
                "packaging": float(product.get("packaging") or 0),
                "other_costs": float(product.get("extra_cost") or 0),
            },
            terms={
                "sale_price": float(product.get("sale_price") or 0) or 1.0,
                "commission_pct": rule["commission_pct"],
                "fixed_fee": rule["fixed_fee"],
                "subsidized_shipping": rule["subsidized_shipping"],
                "tax_pct": float(product.get("tax_pct") or 0),
            },
            fixed_monthly_costs=float(product.get("fixed_monthly_costs") or 0),
            target_margin_pct=target_margin,
            commission_source=rule["source"],
        )
        return calculate(data)

    def scored_products(self, criteria_map: dict[str, dict] | None = None) -> list[dict]:
        criteria_map = criteria_map or {}
        rows = []
        for product in self.products(include_demo=True):
            channel = product.get("marketplace") or "shopee"
            result = self.financial(product, channel)
            score = score_from_product(
                product,
                margin_pct=result.margin_pct,
                extra=criteria_map.get(product.get("name", ""), {}),
            )
            rows.append(
                {
                    **{k: product.get(k) for k in ("id", "name", "category", "marketplace",
                                                    "purchase_price", "sale_price", "is_demo")},
                    "channel": channel,
                    "margin_pct": round(result.margin_pct, 2),
                    "net_profit": round(result.net_profit, 2),
                    "score": score.score,
                    "classification_label": score.classification_label,
                    "confidence": round(score.confidence, 2),
                    "warnings": score.warnings,
                    "financial": result.to_dict(),
                    "score_detail": score.to_dict(),
                }
            )
        rows.sort(key=lambda r: r["score"], reverse=True)
        return rows
