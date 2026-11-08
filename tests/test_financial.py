"""Testes dos cálculos financeiros (determinísticos)."""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from analytics.profitability import (FinancialInput, calculate, compare_marketplaces,
                                     margin_score)


def make(**overrides):
    base = {
        "product_name": "Livro",
        "marketplace": "shopee",
        "quantity": 10,
        "costs": {"purchase_price": 12, "acquisition_shipping": 2, "packaging": 1},
        "terms": {"sale_price": 39.9, "commission_pct": 14, "tax_pct": 6},
        "fixed_monthly_costs": 500,
        "target_margin_pct": 20,
    }
    base.update(overrides)
    return FinancialInput(**base)


def test_calculo_completo():
    result = calculate(make())
    assert result.revenue == pytest.approx(399.0)
    assert result.goods_cost == pytest.approx(150.0)
    assert result.fees == pytest.approx(55.86)
    assert result.taxes == pytest.approx(23.94)
    assert result.total_cost == pytest.approx(229.80)
    assert result.gross_profit == pytest.approx(249.0)
    assert result.net_profit == pytest.approx(169.20)
    assert result.margin_pct == pytest.approx(42.406, abs=0.01)
    assert result.roi_pct == pytest.approx(112.8, abs=0.01)
    assert result.net_profit_per_unit == pytest.approx(16.92)


def test_preco_minimo_e_alvo():
    result = calculate(make())
    # custo fixo por unidade 15; taxa variável 20%
    assert result.min_price_breakeven == pytest.approx(18.75)
    assert result.min_price_target_margin == pytest.approx(25.0)


def test_ponto_de_equilibrio():
    result = calculate(make())
    # 500 / 16.92 = 29,55 -> 30 unidades
    assert result.breakeven_units == math.ceil(500 / 16.92)


def test_prejuizo_detectado():
    result = calculate(make(terms={"sale_price": 16.5, "commission_pct": 14, "tax_pct": 6}))
    assert result.net_profit < 0
    assert result.health == "prejuizo"
    assert any("Prejuízo" in w for w in result.warnings)


def test_desconto_e_anuncio():
    com = calculate(make(terms={"sale_price": 39.9, "discount": 4, "ad_cost": 2}))
    sem = calculate(make(terms={"sale_price": 39.9}))
    # desconto de 4 por unidade x 10 unidades reduz a receita
    assert com.revenue == pytest.approx(sem.revenue - 40)
    # anúncio de 2 por unidade x 10 unidades aumenta o custo
    assert com.total_cost == pytest.approx(sem.total_cost + 20)
    assert com.net_profit == pytest.approx(sem.net_profit - 60)


def test_sem_taxas_gera_aviso():
    result = calculate(make(terms={"sale_price": 39.9}))
    assert any("Comissão" in w for w in result.warnings)
    assert any("Impostos" in w for w in result.warnings)


def test_margem_alvo_impossivel():
    result = calculate(make(terms={"sale_price": 39.9, "commission_pct": 80, "tax_pct": 30}))
    assert result.min_price_target_margin is None
    assert any("margem desejada" in w for w in result.warnings)


def test_desconto_invalido_rejeitado():
    with pytest.raises(ValidationError):
        make(terms={"sale_price": 10, "discount": 10})


def test_comparacao_entre_canais():
    base = make(terms={"sale_price": 39.9})
    rows = compare_marketplaces(
        base,
        {
            "shopee": {"commission_pct": 14, "fixed_fee": 0, "source": "contrato"},
            "mercadolivre": {"commission_pct": 16, "fixed_fee": 0, "source": "contrato"},
        },
    )
    assert rows[0]["net_profit"] >= rows[1]["net_profit"]
    assert {r["marketplace"] for r in rows} == {"shopee", "mercadolivre"}


def test_margin_score_faixas():
    assert margin_score(-5) == 0
    assert margin_score(30) == 100
    assert 0 < margin_score(12) < 100
