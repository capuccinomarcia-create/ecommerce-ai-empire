"""AGENTE 2 - PRODUCT HUNTER: encontra e ranqueia oportunidades."""

from __future__ import annotations

from typing import Any

from agents.base import AgentContext, AgentResult, BaseAgent, MarketContext
from analytics.product_score import ScoreInput, score_product
from core.utils import pct


class ProductHunterAgent(BaseAgent):
    name = "product_hunter"
    role = "Product Hunter"
    description = (
        "Pesquisa produtos com potencial: calcula margem com as taxas informadas, "
        "pontua demanda/concorrência/tendência/logística/tráfego quando esses dados "
        "existem e monta a lista de oportunidades priorizadas."
    )
    capabilities = ["pesquisar_produtos", "estimar_margem", "pontuar_oportunidade",
                    "listar_oportunidades"]
    tools = [
        {"name": "research", "description": "Ranqueia candidatos pelo Product Opportunity Score."},
        {"name": "score", "description": "Calcula e explica a nota de um produto específico."},
    ]

    def execute(self) -> AgentResult:
        payload = self.ctx.payload()
        if payload.get("mode") == "score":
            return self._score_single(payload)
        return self._research(payload)

    # ---------------------------------------------------------------- pesquisa --
    def _research(self, payload: dict[str, Any]) -> AgentResult:
        market = MarketContext(self.ctx)
        limit = int(payload.get("limit", 10) or 10)
        top_n = int(payload.get("top", 5) or 5)
        channels = payload.get("channels") or self.ctx.settings.enabled_channels

        candidates: list[dict[str, Any]] = list(payload.get("candidates") or [])
        if not candidates:
            candidates = market.candidates()
        candidates = candidates[: max(limit * 3, limit)]

        scored: list[dict[str, Any]] = []
        gaps: list[str] = []
        warnings: list[str] = []

        for candidate in candidates:
            name = candidate.get("name", "Produto")
            channel = candidate.get("channel") or (channels[0] if channels else "shopee")
            rule = market.rule_for(channel)
            cost = float(candidate.get("cost_estimate") or 0)
            price = float(candidate.get("price_found") or 0)

            if price <= 0:
                gaps.append(f"{name}: sem preço de venda/referência.")
            if cost <= 0:
                gaps.append(f"{name}: sem custo de aquisição informado.")

            margin_pct = None
            net_profit = None
            min_price = None
            if price > 0:
                financial = market.financial(
                    {
                        "name": name,
                        "purchase_price": cost,
                        "sale_price": price,
                        "marketplace": channel,
                    },
                    channel,
                )
                margin_pct = round(financial.margin_pct, 2)
                net_profit = round(financial.net_profit, 2)
                min_price = financial.min_price_target_margin
                warnings.extend(financial.warnings[:2])

            criteria = candidate.get("criteria") or {}
            sources = candidate.get("sources") or {}
            if margin_pct is not None:
                from analytics.profitability import margin_score

                criteria = {**criteria, "margem": margin_score(margin_pct)}
                sources = {**sources, "margem": "cálculo determinístico com taxas informadas"}

            score = score_product(
                ScoreInput(
                    name=name,
                    demanda=criteria.get("demanda"),
                    margem=criteria.get("margem"),
                    concorrencia=criteria.get("concorrencia"),
                    tendencia=criteria.get("tendencia"),
                    logistica=criteria.get("logistica"),
                    trafego=criteria.get("trafego"),
                    sources=sources,
                )
            )
            scored.append(
                {
                    "name": name,
                    "category": candidate.get("category"),
                    "channel": channel,
                    "channel_label": rule.get("label", channel),
                    "price_found": price or None,
                    "cost_estimate": cost or None,
                    "margin_pct": margin_pct,
                    "net_profit": net_profit,
                    "min_price_target_margin": min_price,
                    "score": score.score,
                    "classification": score.classification,
                    "classification_label": score.classification_label,
                    "confidence": round(score.confidence, 2),
                    "missing": score.missing,
                    "warnings": score.warnings,
                    "sources": sources,
                    "explanation": score.explanations,
                    "marketplace_id": candidate.get("id"),
                    "is_demo": bool(candidate.get("is_demo")),
                }
            )

        scored.sort(key=lambda row: (row["score"], row["margin_pct"] or -999), reverse=True)
        top = scored[:top_n]

        if not scored:
            gaps.append(
                "Nenhum candidato disponível. Importe um CSV de oportunidades, conecte uma API "
                "autorizada ou cadastre produtos manualmente."
            )
        if all(row["score"] == 0 for row in scored):
            gaps.append("Nenhum candidato pôde ser pontuado: faltam critérios de mercado.")

        findings = []
        for index, row in enumerate(top, start=1):
            margin_txt = pct(row["margin_pct"]) if row["margin_pct"] is not None else "sem margem calculada"
            findings.append(
                f"{index}. {row['name']} - score {row['score']} ({row['classification_label']}), "
                f"margem líquida {margin_txt} em {row['channel_label']}"
            )
        for row in top[: top_n]:
            if row["missing"]:
                gaps.append(f"{row['name']}: critérios sem dado -> {', '.join(row['missing'])}")

        demo_mode = any(row["is_demo"] for row in top)
        narrative, provider = self.narrate(
            f"Análise de {len(scored)} candidatos, {len(top)} selecionados.",
            findings + warnings[:4],
            closing=(
                "Popularidade não foi tratada como lucratividade: produtos com margem fraca "
                "tiveram a nota limitada." if scored else ""
            ),
        )

        return AgentResult(
            summary=f"{len(top)} oportunidades priorizadas de {len(scored)} candidatos analisados.",
            data={
                "opportunities": scored,
                "top": top,
                "count": len(scored),
                "demo_mode": demo_mode,
                "rules_used": market.rules(),
            },
            findings=findings,
            warnings=warnings[:10],
            data_gaps=list(dict.fromkeys(gaps))[:12],
            next_actions=[
                "Validar preço e custo reais dos 3 primeiros antes de qualquer compra.",
                "Importar concorrentes em CSV para elevar a confiança da nota.",
                "Rodar a calculadora financeira com as taxas reais do canal escolhido.",
            ],
            narrative=narrative,
            ai_provider=provider,
        )

    # ------------------------------------------------------------ nota isolada --
    def _score_single(self, payload: dict[str, Any]) -> AgentResult:
        criteria = payload.get("criteria") or payload
        result = score_product(
            ScoreInput(
                name=payload.get("name", "Produto"),
                demanda=criteria.get("demanda"),
                margem=criteria.get("margem"),
                concorrencia=criteria.get("concorrencia"),
                tendencia=criteria.get("tendencia"),
                logistica=criteria.get("logistica"),
                trafego=criteria.get("trafego"),
                sources=criteria.get("sources") or {},
            )
        )
        return AgentResult(
            summary=f"{result.name}: score {result.score} - {result.classification_label}",
            data=result.to_dict(),
            findings=[f"{e['criterio']}: nota {e['nota']} (peso {e['peso']})" for e in result.explanations],
            warnings=result.warnings,
            data_gaps=[f"Sem dado: {m}" for m in result.missing],
        )
