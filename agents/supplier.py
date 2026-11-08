"""AGENTE 9 - SUPPLIER HUNTER: fornecedores e custo total (sem comprar)."""

from __future__ import annotations

from typing import Any

from agents.base import AgentContext, AgentResult, BaseAgent
from analytics.fulfillment import deadline_from_marketplace, rank_suppliers
from core.utils import money


class SupplierHunterAgent(BaseAgent):
    name = "supplier_hunter"
    role = "Supplier Hunter"
    description = (
        "Compara fornecedores por custo total de aquisição (produto + frete + prazo), "
        "aponta riscos de quantidade mínima e lead time. Nunca realiza compras."
    )
    capabilities = ["comparar_fornecedores", "calcular_custo_total", "avaliar_risco",
                    "sugerir_quantidade"]
    tools = [
        {"name": "compare", "description": "Ranqueia fornecedores por custo total."},
        {"name": "risk", "description": "Aponta riscos de prazo e estoque."},
    ]

    def execute(self) -> AgentResult:
        payload = self.ctx.payload()
        quantity = int(payload.get("quantity", 0) or 0)
        suppliers = self.ctx.repo.find("suppliers", {}, order_by="unit_price", limit=100)
        if not suppliers:
            return AgentResult(
                summary="Nenhum fornecedor cadastrado.",
                data_gaps=[
                    "Cadastre fornecedores (nome, preço unitário, frete, prazo, quantidade mínima) "
                    "ou importe o CSV de fornecedores."
                ],
                next_actions=["Importar CSV de fornecedores para comparar custo total."],
            )

        rows: list[dict[str, Any]] = []
        for supplier in suppliers:
            min_qty = int(supplier.get("min_qty") or 1)
            qty = quantity or min_qty
            unit = float(supplier.get("unit_price") or 0)
            shipping = float(supplier.get("shipping_cost") or 0)
            total = unit * qty + shipping
            unit_total = total / qty if qty else 0
            lead_time = int(supplier.get("lead_time_days") or 0)
            risk_points: list[str] = []
            if lead_time >= 15:
                risk_points.append(f"Prazo longo ({lead_time} dias): exige estoque de segurança.")
            if min_qty >= 50:
                risk_points.append(f"Quantidade mínima alta ({min_qty} un): imobiliza capital.")
            if shipping == 0:
                risk_points.append("Frete não informado: o custo total pode estar subestimado.")
            rows.append(
                {
                    "name": supplier.get("name"),
                    "quantity": qty,
                    "unit_price": unit,
                    "shipping_cost": shipping,
                    "total_cost": round(total, 2),
                    "unit_total_cost": round(unit_total, 2),
                    "lead_time_days": lead_time,
                    "min_qty": min_qty,
                    "risks": risk_points,
                    "contact": supplier.get("contact"),
                    "url": supplier.get("url"),
                    "is_demo": bool(supplier.get("is_demo")),
                }
            )
        rows.sort(key=lambda r: r["unit_total_cost"])

        best = rows[0]
        findings = [
            f"Melhor custo total unitário: {best['name']} -> {money(best['unit_total_cost'])} "
            f"para {best['quantity']} unidade(s)."
        ]
        for row in rows[1:4]:
            diff = (row["unit_total_cost"] - best["unit_total_cost"]) / best["unit_total_cost"] * 100 \
                if best["unit_total_cost"] else 0
            findings.append(
                f"{row['name']}: {money(row['unit_total_cost'])} por unidade "
                f"({diff:+.1f}% vs melhor), prazo {row['lead_time_days']} dias."
            )
        risks = [f"{r['name']}: {risk}" for r in rows for risk in r["risks"]]

        # --- quem consegue despachar dentro do prazo de cada canal ---
        viability: list[dict[str, Any]] = []
        prazos_pendentes: list[str] = []
        channel = str(payload.get("channel") or payload.get("marketplace") or "").strip()
        regras = self.ctx.repo.find("marketplaces", {}, order_by="name")
        if channel:
            regras = [r for r in regras if r.get("slug") == channel]
        for regra in regras:
            prazo = deadline_from_marketplace(regra)
            ranking = rank_suppliers(suppliers, prazo, quantity or None)
            viability.append(
                {
                    "channel": prazo.slug,
                    "channel_name": prazo.name,
                    "handling_days": prazo.handling_days,
                    "delivery_days": prazo.delivery_days,
                    "deadline_informed": prazo.informado,
                    "source": prazo.source,
                    "ranking": [v.to_dict() for v in ranking],
                }
            )
            if not prazo.informado:
                prazos_pendentes.append(
                    f"Informe o prazo de despacho da {prazo.name} em "
                    "Configurações > Marketplaces para saber quem entrega no prazo."
                )
                continue
            dentro = [v for v in ranking if v.on_time]
            if dentro:
                melhor = dentro[0]
                findings.append(
                    f"{prazo.name}: {len(dentro)} fornecedor(es) despacham dentro de "
                    f"{prazo.handling_days} dia(s) útil(eis). Melhor: {melhor.supplier} "
                    f"({melhor.mode}) a {money(melhor.landed_unit_cost)}/unidade."
                )
            else:
                findings.append(
                    f"{prazo.name}: nenhum fornecedor cumpre o prazo de "
                    f"{prazo.handling_days} dia(s) útil(eis). Vender agora derruba o anúncio."
                )

        narrative, provider = self.narrate(
            f"Comparação de {len(rows)} fornecedores.", findings + risks[:3]
        )
        return AgentResult(
            summary=f"{len(rows)} fornecedores comparados; melhor custo unitário: {money(best['unit_total_cost'])}.",
            data={"suppliers": rows, "viability": viability,
                  "demo_mode": any(r["is_demo"] for r in rows)},
            findings=findings,
            warnings=risks[:10],
            data_gaps=prazos_pendentes + [
                "Preços de fornecedor mudam: reconfirme antes de comprar.",
                "Nenhuma compra é feita por este agente; a decisão é sempre sua.",
            ],
            next_actions=[
                "Pedir amostra ao fornecedor com melhor custo total.",
                "Considerar o prazo no cálculo do ponto de reposição.",
            ],
            narrative=narrative,
            ai_provider=provider,
        )
