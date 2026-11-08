"""Conector Instagram (Meta Graph API).

Requisitos: conta profissional, app Meta com permissões
instagram_basic, instagram_content_publish e pages_show_list.
Sem token, status "Não conectado".

Nenhuma publicação é feita automaticamente: ``prepare_post`` cria o rascunho
e a publicação real passa pela tela de aprovação.
"""

from __future__ import annotations

from typing import Any

from integrations.base import APIError, MarketplaceConnector

DOCS = "https://developers.facebook.com/docs/instagram-platform"


class InstagramConnector(MarketplaceConnector):
    channel = "instagram"
    label = "Instagram"
    docs_url = DOCS
    title_max_chars = 2200       # limite de legenda
    description_max_chars = 2200

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        self.require()
        import httpx

        response = httpx.get(
            f"{self.settings.instagram_base_url}{path}",
            params={"access_token": self.settings.instagram_access_token, **(params or {})},
            timeout=20.0,
        )
        if response.status_code >= 400:
            raise APIError(f"Instagram {response.status_code}: {response.text[:300]}")
        return response.json()

    def fetch_products(self, limit: int = 50) -> list[dict[str, Any]]:
        """Instagram não tem catálogo de produtos por esta API: devolve mídias."""
        data = self._get(
            f"/{self.settings.instagram_business_id}/media",
            {"fields": "id,caption,media_type,permalink,timestamp,like_count,comments_count",
             "limit": limit},
        )
        return [
            {
                "external_id": item.get("id"),
                "caption": item.get("caption"),
                "media_type": item.get("media_type"),
                "permalink": item.get("permalink"),
                "timestamp": item.get("timestamp"),
                "likes": item.get("like_count"),
                "comments": item.get("comments_count"),
                "source": "instagram_graph_api",
            }
            for item in data.get("data", [])
        ]

    def prepare_post(self, caption: str, image_url: str = "", video_url: str = "") -> dict[str, Any]:
        status = self.status()
        return {
            "channel": self.channel,
            "caption": caption[: self.title_max_chars],
            "media": video_url or image_url,
            "media_type": "REELS" if video_url else "IMAGE",
            "status": "rascunho",
            "connected": status.connected,
            "requires_approval_to_publish": True,
            "note": (
                "Publicação via API exige container + publish com aprovação do proprietário."
                if status.connected
                else "Sem token da Meta: use o rascunho para publicar manualmente."
            ),
        }
