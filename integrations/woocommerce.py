"""Conector WooCommerce (REST API v3) e loja própria.

A loja própria usa a mesma REST API do WooCommerce (plugin gratuito), então um
único conector cobre os dois casos. Sem credenciais, status "Não conectado".
"""

from __future__ import annotations

from typing import Any

from integrations.base import APIError, MarketplaceConnector

DOCS = "https://woocommerce.github.io/woocommerce-rest-api-docs/"


class WooCommerceConnector(MarketplaceConnector):
    channel = "woocommerce"
    label = "WooCommerce / Loja própria"
    docs_url = DOCS
    title_max_chars = 200
    description_max_chars = 20000

    def _request(self, method: str, path: str, **kwargs) -> Any:
        self.require()
        import httpx

        if not self.settings.woocommerce_url:
            raise APIError("WOOCOMMERCE_URL ausente")
        url = self.settings.woocommerce_url.rstrip("/") + "/wp-json/wc/v3" + path
        response = httpx.request(
            method,
            url,
            auth=(self.settings.woocommerce_consumer_key, self.settings.woocommerce_consumer_secret),
            timeout=25.0,
            **kwargs,
        )
        if response.status_code >= 400:
            raise APIError(f"WooCommerce {response.status_code}: {response.text[:300]}")
        return response.json()

    def fetch_products(self, limit: int = 50) -> list[dict[str, Any]]:
        data = self._request("GET", "/products", params={"per_page": limit})
        return [
            {
                "external_id": str(item.get("id")),
                "name": item.get("name"),
                "price": float(item.get("price") or 0),
                "stock": item.get("stock_quantity"),
                "status": item.get("status"),
                "permalink": item.get("permalink"),
                "source": "woocommerce_api",
            }
            for item in (data or [])
        ]

    def fetch_orders(self, limit: int = 50) -> list[dict[str, Any]]:
        data = self._request("GET", "/orders", params={"per_page": limit})
        return [
            {
                "external_id": str(item.get("id")),
                "total": float(item.get("total") or 0),
                "status": item.get("status"),
                "date_created": item.get("date_created"),
                "source": "woocommerce_api",
            }
            for item in (data or [])
        ]

    def update_price(self, product_id: str, price: float) -> dict[str, Any]:
        """Alteração de preço: só deve ser chamada após aprovação (permissions)."""
        return self._request("PUT", f"/products/{product_id}", json={"regular_price": str(price)})

    def prepare_listing(self, product, title="", description="", price=None):
        listing = super().prepare_listing(product, title, description, price)
        listing["api_endpoint"] = "/products"
        listing["payload_preview"] = {
            "name": listing["title"],
            "description": listing["description"],
            "regular_price": str(listing["price"]),
            "status": "draft",
        }
        return listing
