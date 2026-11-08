"""AGENTE 3 - MARKET ANALYST: concorrência, preço e posicionamento."""

from __future__ import annotations

from typing import Any

from agents.base import AgentContext, AgentResult, BaseAgent, MarketContext
from analytics import competitors as competitor_tools
from core.utils import money


class MarketAnalystAgent(BaseAgent):
    name = "market_analyst"
    role = "Market Analyst"
    description = (
        "Analisa concorrentes e posicionamento usando apenas dados coletados: preço, "
        "avaliações, diferenciais. Não inventa volume de vendas nem demanda."
    )
    capabilities = ["analisar_concorrentes", "comparar_precos", "identificar_diferenciais",
                    "posicionar_oferta"]
    tools = [
        {"name": "competitor_scan", "description": "Compara nosso preço com a amostra coletada."},
        {"name": "listing_differentials", "description": "Lista diferenciais objetivos possíveis."},
    ]

    def execute(self) -> AgentResult:
        payload = self.ctx.payload()
        market = MarketContext(self.ctx)
        product_ids = payload.get("product_ids") or []
        products = market.products()
        if product_ids:
            products = [p for p in products if p.get("id") in product_ids]

        analyses: list[dict[str, Any]] = []
        findings: list[str] = []
        gaps: list[str] = []
        warnings: list[str] = []

        for product in products[:20]:
            collected = self.ctx.repo.find(
                "competitors", {"product_id": product["id"]}, order_by="-collected_at", limit=50
            )
            analysis = competitor_tools.analyze(collected, our_price=product.get("sale_price"))
            analyses.append({"product": product.get("name"), "analysis": analysis})

            if analysis["sample_size"] == 0:
                gaps.append(
                    f"{product.get('name')}: nenhum concorrente coletado. Importe um CSV com "
                    "preço, avaliação e link para gerar comparação real."
                )
                continue

            findings.append(
                f"{product.get('name')}: {analysis['sample_size']} concorrentes, mediana "
                f"{money(analysis['median'])}, posição {analysis['position']}"
            )
            for recommendation in analysis["recommendations"][:2]:
                findings.append(f"  - {recommendation}")
            for differentiator in analysis["differentiators"][:2]:
                warnings.append(f"{product.get('name')}: {differentiator}")

        if not products:
            gaps.append("Catálogo vazio: cadastre produtos para analisar concorrência.")

        narrative, provider = self.narrate(
            f"Análise de concorrência em {len(analyses)} produtos.",
            findings[:10] or ["Sem amostra de concorrentes suficiente para conclusão."],
        )

        return AgentResult(
            summary=(
                f"{len(analyses)} produtos comparados com concorrentes; "
                f"{sum(1 for a in analyses if a['analysis']['sample_size'])} com amostra válida."
            ),
            data={"analyses": analyses, "demo_mode": any(p.get("is_demo") for p in products)},
            findings=findings,
            warnings=warnings,
            data_gaps=gaps[:10],
            next_actions=[
                "Coletar preço e avaliação de pelo menos 5 concorrentes por produto.",
                "Revisar título e fotos dos produtos posicionados acima do mercado.",
            ],
            narrative=narrative,
            ai_provider=provider,
        )
