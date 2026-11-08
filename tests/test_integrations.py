"""Testes dos conectores (sem rede) e da importação por CSV."""

from __future__ import annotations

import pytest

from integrations import connector_statuses
from integrations.base import ConnectorStatus, NotConfigured
from integrations.mercadolivre import MercadoLivreConnector
from integrations.shopee import ShopeeConnector, sign_request
from integrations.tiktok import sign_request as tiktok_sign
from integrations.woocommerce import WooCommerceConnector


def test_todos_desconectados_sem_credenciais():
    statuses = connector_statuses()
    assert len(statuses) == 5
    for status in statuses:
        assert status["connected"] is False
        assert status["status"] == "Não conectado"
        assert status["missing"], "deve listar o que falta"


def test_assinatura_shopee_deterministica():
    first = sign_request("123", "chave", "/api/v2/product/get_item_list", 1700000000)
    second = sign_request("123", "chave", "/api/v2/product/get_item_list", 1700000000)
    assert first == second
    assert len(first) == 64
    assert first != sign_request("123", "outra", "/api/v2/product/get_item_list", 1700000000)


def test_assinatura_tiktok_ignora_sign():
    params = {"app_key": "k", "timestamp": 1, "shop_cipher": "c"}
    assert tiktok_sign("s", "/product/202309/products/search", params) == tiktok_sign(
        "s", "/product/202309/products/search", {**params, "sign": "xxx"}
    )


def test_limites_por_canal():
    assert ShopeeConnector().listing_limits()["title_max_chars"] == 120
    assert MercadoLivreConnector().listing_limits()["title_max_chars"] == 60
    assert WooCommerceConnector().listing_limits()["title_max_chars"] == 200


def test_fetch_sem_credenciais_falha_explicitamente():
    with pytest.raises(NotConfigured):
        ShopeeConnector().fetch_products()


def test_rascunho_nunca_publica():
    listing = ShopeeConnector().prepare_listing(
        {"id": "p1", "name": "Livro de Colorir", "sale_price": 39.9}
    )
    assert listing["status"] == "rascunho"
    assert listing["requires_approval_to_publish"] is True


def test_titulo_truncado_no_limite():
    listing = MercadoLivreConnector().prepare_listing(
        {"id": "p1", "name": "x" * 200, "sale_price": 10}
    )
    assert len(listing["title"]) == 60


def test_avaliacao_de_anuncio_aponta_problemas():
    connector = MercadoLivreConnector()
    evaluation = connector.evaluate_listing({"title": "curto", "description": "", "price": 0})
    assert evaluation["ok"] is False
    assert len(evaluation["issues"]) >= 3
    assert evaluation["score"] < 100


def test_anuncio_completo_aprovado():
    connector = ShopeeConnector()
    evaluation = connector.evaluate_listing({
        "title": "Livro de Colorir Adulto Jardim Secreto 60 Desenhos",
        "description": "d" * 200,
        "price": 44.9,
    })
    assert evaluation["ok"] is True


def test_status_dataclass_serializa():
    status = ConnectorStatus("x", "Canal", False, "csv", ["A"], "faltando", "http://doc")
    data = status.to_dict()
    assert data["status"] == "Não conectado"
    assert data["last_checked"]
