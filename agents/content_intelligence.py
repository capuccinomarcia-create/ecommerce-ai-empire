"""AGENTE 12 - CONTENT INTELLIGENCE: pauta, calendário e desempenho."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from agents.base import AgentContext, AgentResult, BaseAgent, MarketContext
from core.utils import local_now


class ContentIntelligenceAgent(BaseAgent):
    name = "content_intelligence"
    role = "Content Intelligence"
    description = (
        "Planeja pauta e calendário de Reels, Shorts e TikTok, analisa desempenho quando "
        "existem dados e propõe reaproveitamento apenas de conteúdo próprio ou licenciado."
    )
    capabilities = ["planejar_conteudo", "calendario_editorial", "analisar_desempenho",
                    "reaproveitar_conteudo"]
    tools = [
        {"name": "plan", "description": "Calendário com pauta e formato por canal."},
        {"name": "performance", "description": "Analisa métricas de conteúdo fornecidas."},
        {"name": "repurpose", "description": "Plano de reaproveitamento de conteúdo próprio."},
    ]

    PILLARS = [
        "demonstração do produto",
        "dúvida frequente respondida",
        "antes e depois",
        "bastidor da operação",
        "comparativo de modelos",
        "prova social",
        "oferta com prazo",
    ]

    def execute(self) -> AgentResult:
        payload = self.ctx.payload()
        mode = payload.get("mode", "plan")
        if mode == "performance":
            return self._performance(payload)
        if mode == "repurpose":
            return self._repurpose(payload)
        return self._plan(payload)

    # ------------------------------------------------------------------ plano --
    def _plan(self, payload: dict[str, Any]) -> AgentResult:
        days = int(payload.get("days", 14) or 14)
        channels = payload.get("channels") or ["instagram", "tiktok_shop", "youtube_shorts"]
        market = MarketContext(self.ctx)
        scored = market.scored_products()
        products = [row["name"] for row in scored[:5]] or ["Produto principal"]
        today = local_now(self.ctx.settings.timezone)

        calendar = []
        for day in range(days):
            channel = channels[day % len(channels)]
            pillar = self.PILLARS[day % len(self.PILLARS)]
            product = products[day % len(products)]
            format_name = {
                "instagram": "Reels 20-30s",
                "tiktok_shop": "TikTok 15-30s",
                "youtube_shorts": "Shorts 30-45s",
            }.get(channel, "Vídeo curto")
            calendar.append(
                {
                    "date": today.fromordinal(today.toordinal() + day).strftime("%Y-%m-%d"),
                    "channel": channel,
                    "format": format_name,
                    "pillar": pillar,
                    "product": product,
                    "objective": "salvamentos" if pillar == "dúvida frequente respondida"
                                 else "cliques no link",
                }
            )

        findings = [
            f"Calendário de {days} dias em {len(channels)} canais.",
            f"Produtos priorizados: {', '.join(products[:3])}",
            "Formatos: vertical 9:16, legenda na tela e CTA nos 3 primeiros segundos.",
        ]
        gaps = [
            "Tendências em alta exigem fonte externa (Google Trends, TikTok Creative Center) "
            "ou dados importados; nada foi inventado.",
            "Sem métricas históricas, o calendário é hipótese a testar.",
        ]
        narrative, provider = self.narrate(f"Plano de conteúdo de {days} dias.", findings)
        return AgentResult(
            summary=f"Calendário de {len(calendar)} publicações criado.",
            data={"calendar": calendar, "channels": channels,
                  "demo_mode": any(r.get("is_demo") for r in scored)},
            findings=findings,
            data_gaps=gaps,
            next_actions=[
                "Gravar em lote 3 vídeos por vez.",
                "Marcar quais pautas geraram clique para repetir o formato.",
            ],
            narrative=narrative,
            ai_provider=provider,
        )

    # ------------------------------------------------------------ desempenho --
    def _performance(self, payload: dict[str, Any]) -> AgentResult:
        metrics = payload.get("content_metrics") or []

        if not metrics:
            # tenta ler do conector Instagram, se conectado
            try:
                from integrations import build_connector

                connector = build_connector("instagram", self.ctx.settings, self.ctx.repo)
                if connector.status().connected:
                    metrics = connector.fetch_products(limit=30)
                    source = "instagram_graph_api"
                else:
                    source = ""
            except Exception:  # noqa: BLE001 - falha de API não deve derrubar o agente
                source = ""
        else:
            source = payload.get("source", "dados fornecidos")

        if not metrics:
            return AgentResult(
                summary="Sem dados de desempenho de conteúdo.",
                data={"metrics": [], "source": ""},
                data_gaps=[
                    "Conecte o Instagram (Meta Graph API) ou importe um CSV com "
                    "data, canal, alcance, curtidas e cliques."
                ],
                next_actions=["Coletar 30 dias de métricas antes de tirar conclusão."],
            )

        by_channel: dict[str, list[dict]] = defaultdict(list)
        for item in metrics:
            by_channel[item.get("channel") or "instagram"].append(item)

        summary_rows = []
        for channel, items in by_channel.items():
            reach = [float(i.get("reach") or i.get("likes") or 0) for i in items]
            engagements = [float(i.get("engagements") or i.get("comments") or 0) for i in items]
            summary_rows.append(
                {
                    "channel": channel,
                    "posts": len(items),
                    "avg_reach": round(sum(reach) / len(reach), 1) if reach else None,
                    "avg_engagements": round(sum(engagements) / len(engagements), 1)
                    if engagements else None,
                }
            )
        findings = [
            f"{row['channel']}: {row['posts']} conteúdos, alcance médio {row['avg_reach']}, "
            f"engajamento médio {row['avg_engagements']}"
            for row in summary_rows
        ]
        findings.append("Recomendação: repetir o formato com melhor média e cortar o pior.")
        narrative, provider = self.narrate("Análise de desempenho de conteúdo.", findings)
        return AgentResult(
            summary=f"{len(metrics)} conteúdos analisados de {len(by_channel)} canal(is).",
            data={"rows": summary_rows, "source": source, "demo_mode": False},
            findings=findings,
            data_gaps=["Métricas de conversão exigem dados de vendas vinculados ao conteúdo."],
            next_actions=["Dobrar a frequência do formato com melhor média de salvamentos."],
            narrative=narrative,
            ai_provider=provider,
        )

    # ------------------------------------------------------------ reaproveitar --
    def _repurpose(self, payload: dict[str, Any]) -> AgentResult:
        asset = payload.get("content") or "vídeo principal de 60s"
        plan = [
            {"derivado": "corte de 15s", "destino": "TikTok / Reels", "esforço": "baixo"},
            {"derivado": "corte de 30s com legenda", "destino": "Shorts", "esforço": "baixo"},
            {"derivado": "carrossel com 5 frames", "destino": "Instagram feed", "esforço": "médio"},
            {"derivado": "texto do roteiro como descrição", "destino": "anúncio Shopee/ML", "esforço": "baixo"},
        ]
        return AgentResult(
            summary=f"{len(plan)} derivados planejados a partir de conteúdo próprio.",
            data={"source_content": asset, "plan": plan},
            findings=[f"{p['derivado']} -> {p['destino']}" for p in plan],
            warnings=[
                "Reaproveite somente conteúdo próprio ou licenciado. Não use vídeos de "
                "terceiros nem remova marca d'água."
            ],
            next_actions=["Autorizar o uso dos seus próprios vídeos antes de derivar."],
        )
