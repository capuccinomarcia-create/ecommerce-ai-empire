"""AGENTE 6 - MARKETING AI: campanhas orgânicas e textos comerciais."""

from __future__ import annotations

from typing import Any

from agents.base import AgentContext, AgentResult, BaseAgent, MarketContext
from core.utils import local_now, pct


class MarketingAgent(BaseAgent):
    name = "marketing"
    role = "Marketing AI"
    description = (
        "Monta estratégia de divulgação priorizando orgânico, com ângulos de campanha, "
        "textos por canal e calendário de publicações. Não promete resultado."
    )
    capabilities = ["estrategia_marketing", "texto_comercial", "calendario_editorial",
                    "publico_alvo", "divulgacao_organica"]
    tools = [
        {"name": "campaign_plan", "description": "Cria campanhas orgânicas com ângulos e canais."},
        {"name": "copy", "description": "Escreve título, descrição curta e CTA por canal."},
        {"name": "content_calendar", "description": "Distribui posts nos próximos dias."},
    ]

    PILLARS = [
        ("prova", "Mostrar o produto em uso real"),
        ("duvida", "Responder a dúvida mais comum do cliente"),
        ("comparacao", "Comparar antes/depois ou com o problema que resolve"),
        ("bastidor", "Mostrar rotina, embalagem, envio"),
        ("oferta", "Apresentar a oferta e a chamada para ação"),
    ]

    def execute(self) -> AgentResult:
        payload = self.ctx.payload()
        market = MarketContext(self.ctx)
        scored = market.scored_products()
        focus = payload.get("product") or (scored[0]["name"] if scored else "")
        focus_row = next((r for r in scored if r["name"] == focus), scored[0] if scored else None)
        channels = payload.get("channels") or ["instagram", "tiktok_shop"]

        if not focus_row:
            return AgentResult(
                summary="Sem produto para campanha.",
                data_gaps=["Cadastre um produto para gerar estratégia de marketing."],
            )

        benefits = self._benefits(focus_row)
        campaigns = []
        for channel in channels:
            angle = self.PILLARS[len(campaigns) % len(self.PILLARS)]
            campaigns.append(
                {
                    "channel": channel,
                    "objective": "vendas orgânicas" if channel != "instagram" else "alcance e salvamentos",
                    "angle": angle[1],
                    "hook": self._hook(focus_row, benefits, channel),
                    "cta": "Comente 'quero' que eu te mando o link." if channel == "instagram"
                           else "Toque no carrinho do vídeo antes que acabe o estoque.",
                    "format": "Reels 20-30s" if channel == "instagram" else "Vídeo 15-25s no feed",
                    "budget": "R$ 0 (orgânico)",
                }
            )

        calendar = self._calendar(focus_row, channels)
        findings = [
            f"Produto foco: {focus_row['name']} (margem {pct(focus_row['margin_pct'])}, "
            f"score {focus_row['score']})",
            f"{len(campaigns)} campanhas orgânicas desenhadas para {', '.join(channels)}",
            f"{len(calendar)} publicações planejadas",
        ]
        gaps = [
            "Sem dados de público real (idade, gênero, região): o direcionamento é hipótese a validar.",
            "Métricas de alcance e conversão só entram depois de conectar Instagram/TikTok.",
        ]
        if focus_row["margin_pct"] is not None and focus_row["margin_pct"] < 10:
            gaps.append(
                "Margem abaixo de 10%: evite qualquer mídia paga até reprecificar o produto."
            )

        narrative, provider = self.narrate(
            f"Plano de marketing orgânico para {focus_row['name']}.",
            findings + [f"Gancho sugerido: {campaigns[0]['hook']}" if campaigns else ""],
        )
        return AgentResult(
            summary=f"Estratégia orgânica criada para {focus_row['name']} em {len(channels)} canais.",
            data={
                "product": focus_row["name"],
                "campaigns": campaigns,
                "calendar": calendar,
                "benefits": benefits,
                "demo_mode": focus_row.get("is_demo", False),
            },
            findings=findings,
            warnings=[
                "Orçamento de mídia paga permanece R$ 0: o plano é 100% orgânico."
            ],
            data_gaps=gaps,
            next_actions=[
                "Gravar os 3 primeiros vídeos do calendário.",
                "Publicar nos horários definidos e medir salvamentos e cliques.",
            ],
            narrative=narrative,
            ai_provider=provider,
        )

    def _benefits(self, row: dict) -> list[str]:
        benefits = []
        if row.get("category"):
            benefits.append(f"Bom para quem procura {row['category']}")
        if row.get("margin_pct") is not None:
            benefits.append("Preço competitivo com margem validada")
        if row.get("score", 0) >= 75:
            benefits.append("Alta pontuação de oportunidade na nossa análise")
        if not benefits:
            benefits.append("Destaque o benefício principal do produto na primeira frase")
        return benefits

    def _hook(self, row: dict, benefits: list[str], channel: str) -> str:
        name = row["name"]
        if channel == "instagram":
            return f"Ninguém te contou isso sobre {name}..."
        return f"Pare de rolar: {name} resolve {benefits[0].lower()}."

    def _calendar(self, row: dict, channels: list[str]) -> list[dict[str, Any]]:
        today = local_now(self.ctx.settings.timezone)
        entries = []
        for day in range(7):
            for index, channel in enumerate(channels[:2]):
                pillar = self.PILLARS[(day + index) % len(self.PILLARS)]
                entries.append(
                    {
                        "date": (today.fromordinal(today.toordinal() + day)).strftime("%Y-%m-%d"),
                        "channel": channel,
                        "pillar": pillar[1],
                        "product": row["name"],
                        "format": "Reels" if channel == "instagram" else "Vídeo curto",
                    }
                )
        return entries
