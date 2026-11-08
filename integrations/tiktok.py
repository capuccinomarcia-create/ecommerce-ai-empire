"""Conector TikTok Shop (Open API v2).

Autenticação: app_key + app_secret (assinatura HMAC-SHA256) e access_token
da loja. Documentação: https://partner.tiktokshop.com/doc

O conector apenas LÊ catálogo/pedidos e monta rascunhos de anúncio.
Publicar exige aprovação explícita do proprietário.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any
from urllib.parse import urlencode

from integrations.base import APIError, MarketplaceConnector, NotConfigured

DOCS = "https://partner.tiktokshop.com/doc"


def sign_request(app_secret: str, path: str, params: dict[str, Any], body: str = "") -> str:
    """Assinatura TikTok Shop: HMAC-SHA256(secret, path + params ordenados + body)."""
    filtered = {
        k: v for k, v in sorted(params.items())
        if k not in {"sign", "access_token"} and v not in (None, "")
    }
    base = path + urlencode(filtered) + body
    return hmac.new(app_secret.encode(), base.encode(), hashlib.sha256).hexdigest()


class TikTokShopConnector(MarketplaceConnector):
    channel = "tiktok_shop"
    label = "TikTok Shop"
    docs_url = DOCS
    title_max_chars = 255
    description_max_chars = 10000

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        self.require()
        import httpx

        query = {
            "app_key": self.settings.tiktok_app_key,
            "timestamp": int(time.time()),
            "shop_cipher": self.settings.tiktok_shop_cipher,
            **(params or {}),
        }
        query["sign"] = sign_request(self.settings.tiktok_app_secret, path, query)
        response = httpx.get(
            f"{self.settings.tiktok_base_url}{path}",
            params=query,
            headers={"x-tts-access-token": self.settings.tiktok_access_token},
            timeout=20.0,
        )
        if response.status_code >= 400:
            raise APIError(f"TikTok Shop {response.status_code}: {response.text[:300]}")
        return response.json()

    def fetch_products(self, limit: int = 50) -> list[dict[str, Any]]:
        data = self._get("/product/202309/products/search", {"page_size": limit})
        items = (data.get("data") or {}).get("products", []) or []
        return [
            {
                "external_id": str(item.get("id")),
                "title": item.get("title"),
                "status": item.get("status"),
                "source": "tiktok_shop_api",
            }
            for item in items
        ]

    def prepare_listing(self, product, title="", description="", price=None):
        listing = super().prepare_listing(product, title, description, price)
        listing["api_endpoint"] = "/product/202309/products"
        listing["payload_preview"] = {
            "title": listing["title"],
            "description": listing["description"],
            "skus": [{"price": {"amount": str(listing["price"]), "currency": "BRL"}}],
        }
        return listing
