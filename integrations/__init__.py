"""Conectores de marketplace e importação/exportação de dados."""

from __future__ import annotations

from typing import Any

from core.config import Settings, get_settings
from integrations.base import APIError, ConnectorStatus, MarketplaceConnector, NotConfigured
from integrations.instagram import InstagramConnector
from integrations.mercadolivre import MercadoLivreConnector
from integrations.shopee import ShopeeConnector
from integrations.tiktok import TikTokShopConnector
from integrations.woocommerce import WooCommerceConnector

CONNECTOR_CLASSES = {
    "shopee": ShopeeConnector,
    "mercadolivre": MercadoLivreConnector,
    "tiktok_shop": TikTokShopConnector,
    "instagram": InstagramConnector,
    "woocommerce": WooCommerceConnector,
}

__all__ = [
    "APIError", "ConnectorStatus", "MarketplaceConnector", "NotConfigured",
    "CONNECTOR_CLASSES", "build_connector", "connector_statuses", "label_for",
]


def label_for(channel: str) -> str:
    from database.models import MARKETPLACE_LABELS

    return MARKETPLACE_LABELS.get(channel, channel)


def build_connector(channel: str, settings: Settings | None = None, repo=None) -> MarketplaceConnector:
    settings = settings or get_settings()
    if channel == "loja_propria":
        channel = "woocommerce"
    connector_cls = CONNECTOR_CLASSES.get(channel)
    if not connector_cls:
        raise ValueError(f"canal sem conector: {channel}")
    return connector_cls(settings=settings, repo=repo)


def connector_statuses(settings: Settings | None = None, repo=None) -> list[dict[str, Any]]:
    """Status de todos os canais, sempre honesto sobre o que falta."""
    settings = settings or get_settings()
    items = []
    for channel in CONNECTOR_CLASSES:
        connector = build_connector(channel, settings=settings, repo=repo)
        items.append(connector.status().to_dict())
    return items
