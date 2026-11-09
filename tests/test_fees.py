"""Testes das taxas de marketplace (fonte, data e cálculo determinístico)."""

from __future__ import annotations

import pytest

from analytics import fees


def test_tabelas_tem_fonte_data_e_aviso_de_provisorio():
    resumo = fees.resumo_tabelas()
    assert {t["canal"] for t in resumo} == {"Mercado Livre", "Shopee", "TikTok Shop"}
    for tabela in resumo:
        assert tabela["fonte"], "tabela sem fonte declarada"
        assert tabela["coletado_em"], "tabela sem data de coleta"
        assert tabela["confianca"] in {"alta", "media", "baixa"}
        assert tabela["provisorio"] is True


def test_shopee_cobra_comissao_e_tarifa_fixa():
    t = fees.tarifa("Shopee", 100.0)
    assert t.comissao_pct == 14.0
    assert t.comissao_valor == 14.0
    assert t.fixo == 4.0
    assert t.total == 18.0


def test_mercado_livre_tem_custo_fixo_abaixo_de_79():
    abaixo = fees.tarifa("Mercado Livre", 50.0)
    acima = fees.tarifa("Mercado Livre", 120.0)
    assert abaixo.fixo == 6.0
    assert acima.fixo == 0.0
    assert acima.comissao_valor == pytest.approx(15.6)


def test_tiktok_muda_de_faixa_no_preco_50():
    barato = fees.tarifa("TikTok Shop", 40.0)
    caro = fees.tarifa("TikTok Shop", 80.0)
    assert (barato.comissao_pct, barato.fixo) == (10.0, 4.0)
    assert (caro.comissao_pct, caro.fixo) == (6.0, 6.0)


def test_preco_para_margem_entrega_a_margem_pedida():
    custo = 40.0
    preco = fees.preco_para_margem("Shopee", custo, 30.0)
    resultado = fees.margem("Shopee", preco, custo)
    assert resultado["margem_pct"] == pytest.approx(30.0, abs=0.3)
    assert resultado["lucro_liquido"] > 0


def test_margem_negativa_quando_preco_nao_cobre_taxa_e_custo():
    resultado = fees.margem("Mercado Livre", 20.0, 19.99)
    assert resultado["lucro_liquido"] < 0
    assert resultado["margem_pct"] < 0


def test_melhor_canal_escolhe_maior_lucro():
    comparativo = fees.melhor_canal(100.0, 40.0)
    lucros = {r["canal"]: r["lucro_liquido"] for r in comparativo["resultados"]}
    assert comparativo["melhor"] == max(lucros, key=lucros.get)
    assert comparativo["melhor"] == "TikTok Shop"


def test_canal_desconhecido_falha_alto():
    with pytest.raises(ValueError):
        fees.tarifa("Amazon", 10.0)


def test_preco_invalido_falha_alto():
    with pytest.raises(ValueError):
        fees.tarifa("Shopee", 0)
