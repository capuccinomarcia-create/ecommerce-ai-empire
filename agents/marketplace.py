"""AGENTE 4 - MARKETPLACE MANAGER: status dos canais, anúncios e ajustes."""

from __future__ import annotations

from typing import Any

from agents.base import AgentContext, AgentResult, BaseAgent
from core.utils import money
from integrations import APIError, NotConfigured, build_connector, connector_statuses


class MarketplaceManagerAgent(BaseAgent):
    name = "marketplace_manager"
    role = "Marketplace Manager"
    description = (
        "Cuida de Shopee, Mercado Livre, TikTok Shop e loja própria: checa conexões, "
        "avalia anúncios, prepara rascunhos e propõe ajustes para aprovação. "
        "Nunca publica sozinho."
    )
    capabilities = ["status_canais", "auditar_anuncios", "preparar_rascunho",
                    "propor_alteracao", "importar_dados"]
    tools = [
        {"name": "channel_status", "description": "Mostra o que está conectado e o que falta."},
        {"name": "audit_listings", "description": "Avalia título, descrição e preço por canal."},
        {"name": "prepare_listing", "description": "Cria o rascunho de anúncio (sem publicar)."},
    ]

    def execute(self) -> AgentResult:
        payload = self.ctx.payload()
        mode = payload.get("mode", "audit")
        if mode == "status":
            return self._status()
        if mode == "prepare":
            return self._prepare(payload)
        return self._audit(payload)

    # ----------------------------------------------------------------- status --
    def _status(self) -> AgentResult:
        statuses = connector_statuses(self.ctx.settings, self.ctx.repo)
        connected = [s for s in statuses if s["connected"]]
        gaps = [
            f"{s['label']}: falta {', '.join(s['missing'])}"
            for s in statuses
            if not s["connected"]
        ]
        findings = [
            f"{s['label']}: {s['status']}" for s in statuses
        ] + [
            "Caminho alternativo ativo: importação/exportação de CSV para todos os canais."
        ]
        return AgentResult(
            summary=f"{len(connected)} de {len(statuses)} canais conectados.",
            data={"statuses": statuses, "connected": len(connected)},
            findings=findings,
            data_gaps=gaps,
            next_actions=[
                "Configurar credenciais no .env quando quiser ler dados oficiais da API.",
                "Usar CSV enquanto a API não estiver conectada.",
            ],
        )

    # ------------------------------------------------------------ auditoria --
    def _audit(self, payload: dict[str, Any]) -> AgentResult:
        listings = self.ctx.repo.find("listings", {}, order_by="-updated_at", limit=100)
        if payload.get("marketplace"):
            listings = [l for l in listings if l.get("marketplace") == payload["marketplace"]]

        if not listings:
            products = self.ctx.repo.find("products", {}, limit=20)
            proposals = []
            for product in products:
                channel = product.get("marketplace") or "shopee"
                connector = build_connector(channel, self.ctx.settings, self.ctx.repo)
                draft = connector.prepare_listing(product)
                evaluation = connector.evaluate_listing(draft)
                proposals.append(
                    {
                        "product": product.get("name"),
                        "channel": channel,
                        "draft": draft,
                        "evaluation": evaluation,
                    }
                )
            gaps = [
                "Nenhum anúncio cadastrado: a auditoria usou rascunhos gerados a partir do catálogo.",
            ]
            findings = [
                f"{p['product']} ({p['channel']}): score de anúncio {p['evaluation']['score']}, "
                f"{len(p['evaluation']['issues'])} ajuste(s)"
                for p in proposals
            ]
            return AgentResult(
                summary=f"{len(proposals)} rascunhos avaliados a partir do catálogo.",
                data={"proposals": proposals, "mode": "draft_audit",
                      "demo_mode": any(p.get("is_demo") for p in products)},
                findings=findings or ["Catálogo vazio: nada para auditar."],
                warnings=[i for p in proposals for i in p["evaluation"]["issues"]][:10],
                data_gaps=gaps,
                next_actions=["Revisar os rascunhos e aprovar a publicação dos que estiverem completos."],
            )

        rows: list[dict[str, Any]] = []
        findings: list[str] = []
        alerts: list[str] = []
        for listing in listings:
            connector = build_connector(
                listing.get("marketplace", "shopee"), self.ctx.settings, self.ctx.repo
            )
            evaluation = connector.evaluate_listing(listing)
            rows.append({"listing": listing, "evaluation": evaluation})
            if not evaluation["ok"]:
                alerts.append(
                    f"{listing.get('title') or listing.get('id')}: "
                    + "; ".join(evaluation["issues"])
                )
            if listing.get("price"):
                findings.append(
                    f"{listing.get('title')}: preço {money(float(listing['price']))} "
                    f"no canal {listing.get('marketplace')}"
                )

        attention = len(alerts)
        return AgentResult(
            summary=f"{len(listings)} anúncios auditados, {attention} precisam de ajuste.",
            data={"rows": rows, "total": len(listings), "needs_attention": attention},
            findings=findings[:15],
            warnings=alerts[:15],
            data_gaps=[] if listings else ["Nenhum anúncio real cadastrado."],
            next_actions=[
                "Corrigir títulos curtos e descrições fracas antes de gastar com anúncios.",
                "Comparar preço com os concorrentes coletados no Market Analyst.",
            ],
        )

    # -------------------------------------------------------------- rascunho --
    def _prepare(self, payload: dict[str, Any]) -> AgentResult:
        product_id = payload.get("product_id")
        product = self.ctx.repo.get("products", product_id) if product_id else None
        if not product:
            products = self.ctx.repo.find("products", {}, limit=1)
            product = products[0] if products else None
        if not product:
            return AgentResult(
                summary="Nenhum produto disponível para montar anúncio.",
                data_gaps=["Cadastre um produto ou importe um CSV de produtos."],
            )
        channel = payload.get("channel") or product.get("marketplace") or "shopee"
        connector = build_connector(channel, self.ctx.settings, self.ctx.repo)
        draft = connector.prepare_listing(
            product,
            title=payload.get("title", ""),
            description=payload.get("description", ""),
            price=payload.get("price"),
        )
        evaluation = connector.evaluate_listing(draft)
        saved = self.ctx.repo.insert(
            "listings",
            {
                "product_id": product["id"],
                "marketplace": channel,
                "title": draft["title"],
                "description": draft["description"],
                "price": draft["price"],
                "status": "rascunho",
                "score": evaluation["score"],
                "is_demo": bool(product.get("is_demo")),
            },
        )
        approvals = []
        if payload.get("request_approvals"):
            approval = self.ctx.permissions.request(
                "publish_listing",
                {"listing_id": saved["id"], "channel": channel, "title": draft["title"]},
                resource_type="listing",
                resource_id=saved["id"],
                agent=self.name,
            )
            approvals.append(approval)
        return AgentResult(
            summary=f"Rascunho de anúncio criado para {product.get('name')} em {channel}.",
            data={"listing": saved, "evaluation": evaluation, "draft": draft},
            findings=[
                f"Título ({len(draft['title'])} caracteres): {draft['title']}",
                f"Score do anúncio: {evaluation['score']}",
            ],
            warnings=evaluation["issues"],
            next_actions=[
                "Aprovar a publicação na tela de aprovações para o anúncio ir ao ar."
                if approvals else "Revisar o rascunho e solicitar publicação.",
            ],
            approvals_requested=approvals,
        )
