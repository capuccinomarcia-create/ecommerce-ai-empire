"""AGENTE 5 - FINANCIAL AI: números, margem e ponto de equilíbrio."""

from __future__ import annotations

from typing import Any

from agents.base import AgentContext, AgentResult, BaseAgent, MarketContext
from core.utils import money, pct


class FinancialAgent(BaseAgent):
    name = "financial"
    role = "Financial AI"
    description = (
        "Calcula custos, taxas, impostos, margem, ROI, preço mínimo e ponto de equilíbrio "
        "por canal. Toda a matemática é determinística; a IA apenas explica."
    )
    capabilities = ["calcular_margem", "calcular_preco_minimo", "ponto_de_equilibrio",
                    "comparar_canais", "detectar_prejuizo"]
    tools = [
        {"name": "evaluate", "description": "Calcula o resultado financeiro por produto e canal."},
        {"name": "compare_channels", "description": "Compara o mesmo produto em vários canais."},
        {"name": "price_floor", "description": "Sugere preço mínimo para margem desejada."},
    ]

    def execute(self) -> AgentResult:
        payload = self.ctx.payload()
        market = MarketContext(self.ctx)
        products = market.products()
        if payload.get("product_ids"):
            products = [p for p in products if p["id"] in payload["product_ids"]]
        if not products:
            return AgentResult(
                summary="Sem produtos para calcular.",
                data_gaps=["Cadastre produtos com custo e preço para gerar a análise financeira."],
            )

        target_margin = float(payload.get("target_margin_pct", 20) or 20)
        channels = payload.get("channels") or self.ctx.settings.enabled_channels
        rows: list[dict[str, Any]] = []
        alerts: list[str] = []
        findings: list[str] = []
        gaps: list[str] = []

        for product in products[:25]:
            channel = product.get("marketplace") or (channels[0] if channels else "shopee")
            quantity = int(payload.get("quantity", 1) or 1)
            result = market.financial(product, channel, quantity=quantity,
                                      target_margin=target_margin)
            row = {
                "product_id": product["id"],
                "product_name": product.get("name"),
                "channel": channel,
                "is_demo": bool(product.get("is_demo")),
                **result.to_dict(),
            }
            rows.append(row)

            if result.margin_pct < 0:
                alerts.append(
                    f"{product.get('name')} em {channel}: prejuízo de "
                    f"{money(abs(result.net_profit))} ({pct(result.margin_pct)})."
                )
            elif result.margin_pct < 8:
                alerts.append(
                    f"{product.get('name')} em {channel}: margem crítica de {pct(result.margin_pct)}."
                )
            if not product.get("purchase_price"):
                gaps.append(f"{product.get('name')}: custo de compra não informado.")

        rows.sort(key=lambda r: r["margin_pct"], reverse=True)
        best = rows[0] if rows else None
        worst = rows[-1] if rows else None
        if best:
            findings.append(
                f"Melhor margem: {best['product_name']} em {best['channel']} -> "
                f"{pct(best['margin_pct'])} (lucro {money(best['net_profit'])})."
            )
        if worst and worst is not best:
            findings.append(
                f"Pior margem: {worst['product_name']} em {worst['channel']} -> "
                f"{pct(worst['margin_pct'])}."
            )
        breakeven_rows = [r for r in rows if r.get("breakeven_units")]
        if breakeven_rows:
            findings.append(
                "Ponto de equilíbrio calculado para "
                + ", ".join(f"{r['product_name']}: {r['breakeven_units']} un/mês"
                            for r in breakeven_rows[:3])
            )

        # Comparação entre canais para o produto com melhor margem
        comparison: list[dict[str, Any]] = []
        if best and len(channels) > 1:
            product = next((p for p in products if p["id"] == best["product_id"]), None)
            if product:
                rules = market.rules()
                for channel in channels:
                    if channel not in rules:
                        continue
                    result = market.financial(product, channel, target_margin=target_margin)
                    comparison.append(
                        {
                            "channel": channel,
                            "commission_pct": rules[channel]["commission_pct"],
                            "net_profit": round(result.net_profit, 2),
                            "margin_pct": round(result.margin_pct, 2),
                        }
                    )
                comparison.sort(key=lambda r: r["net_profit"], reverse=True)

        narrative, provider = self.narrate(
            f"Análise financeira de {len(rows)} combinações produto/canal (margem alvo {pct(target_margin)}).",
            findings + alerts[:4],
            closing="Cálculos feitos por código; taxas não informadas entram como zero e são sinalizadas.",
        )

        return AgentResult(
            summary=(
                f"{len(rows)} produtos calculados. Melhor margem: "
                f"{pct(best['margin_pct']) if best else 'n/d'}. "
                f"{len(alerts)} alerta(s) de margem."
            ),
            data={
                "rows": rows,
                "alerts": alerts,
                "channel_comparison": comparison,
                "target_margin_pct": target_margin,
                "demo_mode": any(r.get("is_demo") for r in rows),
            },
            findings=findings,
            warnings=alerts,
            data_gaps=list(dict.fromkeys(gaps))[:10],
            next_actions=[
                "Informar comissão e taxa fixa reais em Configurações > Marketplaces.",
                "Descartar ou reprecificar produtos com margem abaixo de 8%.",
            ],
            narrative=narrative,
            ai_provider=provider,
        )
