"""Conector Mercado Livre (OAuth 2.0 + API pública/autenticada).

Fluxo: o proprietário cria o app em https://developers.mercadolivre.com.br,
autoriza a URL de callback e o sistema troca o ``code`` por
``access_token``/``refresh_token``. Sem tokens, status "Não conectado".
"""

from __future__ import annotations

import urllib.parse
from typing import Any

from integrations.base import APIError, MarketplaceConnector, NotConfigured

DOCS = "https://developers.mercadolivre.com.br/pt_br/autenticacao-e-autorizacao"


class MercadoLivreConnector(MarketplaceConnector):
    channel = "mercadolivre"
    label = "Mercado Livre"
    docs_url = DOCS
    title_max_chars = 60
    description_max_chars = 50000

    # -------------------------------------------------------------------- OAuth --
    def authorization_url(self, state: str = "empire") -> str:
        if not self.settings.ml_client_id or not self.settings.ml_redirect_uri:
            raise NotConfigured("Configure ML_CLIENT_ID e ML_REDIRECT_URI para iniciar o OAuth")
        params = {
            "response_type": "code",
            "client_id": self.settings.ml_client_id,
            "redirect_uri": self.settings.ml_redirect_uri,
            "state": state,
        }
        return "https://auth.mercadolivre.com.br/authorization?" + urllib.parse.urlencode(params)

    def exchange_code(self, code: str) -> dict[str, Any]:
        import httpx

        if not self.settings.ml_client_id or not self.settings.ml_client_secret:
            raise NotConfigured("Configure ML_CLIENT_ID e ML_CLIENT_SECRET")
        response = httpx.post(
            "https://api.mercadolibre.com/oauth/token",
            data={
                "grant_type": "authorization_code",
                "client_id": self.settings.ml_client_id,
                "client_secret": self.settings.ml_client_secret,
                "code": code,
                "redirect_uri": self.settings.ml_redirect_uri,
            },
            headers={"Accept": "application/json"},
            timeout=20.0,
        )
        if response.status_code >= 400:
            raise APIError(f"Mercado Livre {response.status_code}: {response.text[:300]}")
        token = response.json()
        # Nunca versionar/expor: grave no .env do proprietário
        return {
            "access_token": token.get("access_token"),
            "refresh_token": token.get("refresh_token"),
            "expires_in": token.get("expires_in"),
            "user_id": token.get("user_id"),
            "note": "Salve os tokens apenas no .env local (nunca no repositório).",
        }

    def _headers(self) -> dict[str, str]:
        token = self.settings.ml_access_token
        if not token:
            raise NotConfigured("ML_ACCESS_TOKEN ausente: conclua o OAuth do Mercado Livre")
        return {"Authorization": f"Bearer {token}"}

    # ------------------------------------------------------------------- dados --
    def me(self) -> dict[str, Any]:
        import httpx

        response = httpx.get(
            f"{self.settings.ml_base_url}/users/me", headers=self._headers(), timeout=20.0
        )
        if response.status_code >= 400:
            raise APIError(f"Mercado Livre {response.status_code}: {response.text[:300]}")
        return response.json()

    def fetch_products(self, limit: int = 50) -> list[dict[str, Any]]:
        import httpx

        user = self.me()
        response = httpx.get(
            f"{self.settings.ml_base_url}/users/{user['id']}/items/search",
            headers=self._headers(),
            params={"limit": limit},
            timeout=20.0,
        )
        if response.status_code >= 400:
            raise APIError(f"Mercado Livre {response.status_code}: {response.text[:300]}")
        ids = response.json().get("results", [])[:limit]
        return [{"external_id": item_id, "source": "mercadolivre_api"} for item_id in ids]

    def search_market(self, query: str, site: str = "MLB", limit: int = 20) -> dict[str, Any]:
        """Pesquisa pública de anúncios (não requer token). Serve para concorrência."""
        import httpx

        response = httpx.get(
            f"{self.settings.ml_base_url}/sites/{site}/search",
            params={"q": query, "limit": limit},
            timeout=20.0,
        )
        if response.status_code >= 400:
            raise APIError(f"Mercado Livre {response.status_code}: {response.text[:300]}")
        data = response.json()
        return {
            "query": query,
            "total_results": data.get("paging", {}).get("total"),
            "items": [
                {
                    "title": item.get("title"),
                    "price": item.get("price"),
                    "permalink": item.get("permalink"),
                    "sold_quantity": item.get("sold_quantity"),
                    "available_quantity": item.get("available_quantity"),
                }
                for item in data.get("results", [])
            ],
            "source": "mercadolivre_api_publica",
        }

    def prepare_listing(self, product, title="", description="", price=None):
        listing = super().prepare_listing(product, title, description, price)
        listing["api_endpoint"] = "/items"
        listing["payload_preview"] = {
            "title": listing["title"],
            "category_id": product.get("ml_category_id"),
            "price": listing["price"],
            "currency_id": "BRL",
            "available_quantity": product.get("stock", 1),
            "buying_mode": "buy_it_now",
            "condition": product.get("condition", "new"),
            "listing_type_id": "gold_special",
            "description": {"plain_text": listing["description"]},
        }
        return listing
