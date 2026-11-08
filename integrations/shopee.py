"""Conector Shopee (Open Platform v2).

Autenticação: partner_id + partner_key (assinatura HMAC-SHA256) e, para
operações de loja, access_token + shop_id obtidos no fluxo OAuth da Shopee.
Documentação: https://open.shopee.com/documents

Sem credenciais o conector fica "Não conectado". Nada é publicado aqui:
``prepare_listing`` só monta o rascunho; publicar exige aprovação.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

from integrations.base import APIError, MarketplaceConnector, NotConfigured

DOCS = "https://open.shopee.com/documents"


def sign_request(partner_id: str, partner_key: str, path: str, timestamp: int,
                 access_token: str = "", shop_id: str = "") -> str:
    """Assinatura oficial: sha256(partner_key, partner_id+path+timestamp+token+shop_id)."""
    base = f"{partner_id}{path}{timestamp}{access_token}{shop_id}"
    return hmac.new(partner_key.encode(), base.encode(), hashlib.sha256).hexdigest()


class ShopeeConnector(MarketplaceConnector):
    channel = "shopee"
    label = "Shopee"
    docs_url = DOCS
    title_max_chars = 120
    description_max_chars = 3000

    # --------------------------------------------------------------- helpers --
    def _signed_query(self, path: str) -> dict[str, Any]:
        timestamp = int(time.time())
        return {
            "partner_id": self.settings.shopee_partner_id,
            "timestamp": timestamp,
            "sign": sign_request(
                self.settings.shopee_partner_id,
                self.settings.shopee_partner_key,
                path,
                timestamp,
                self.settings.shopee_shop_id,
            ),
        }

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        self.require()
        import httpx

        query = {**self._signed_query(path), **(params or {})}
        response = httpx.get(
            f"{self.settings.shopee_base_url}{path}", params=query, timeout=20.0
        )
        if response.status_code >= 400:
            raise APIError(f"Shopee {response.status_code}: {response.text[:300]}")
        return response.json()

    # ------------------------------------------------------------------ dados --
    def fetch_products(self, limit: int = 50) -> list[dict[str, Any]]:
        data = self._get("/api/v2/product/get_item_list", {"offset": 0, "page_size": limit})
        items = (data.get("response") or {}).get("item", []) or []
        return [
            {
                "external_id": str(item.get("item_id")),
                "status": item.get("item_status"),
                "source": "shopee_api",
            }
            for item in items
        ]

    def prepare_listing(self, product, title="", description="", price=None):
        listing = super().prepare_listing(product, title, description, price)
        listing["api_endpoint"] = "/api/v2/product/add_item"
        listing["payload_preview"] = {
            "item_name": listing["title"],
            "description": listing["description"],
            "original_price": listing["price"],
            "weight": product.get("weight_kg"),
            "item_status": "DRAFT",
        }
        return listing
