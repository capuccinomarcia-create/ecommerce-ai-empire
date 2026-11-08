"""Testes do Product Opportunity Score."""

from __future__ import annotations

import pytest

from analytics.product_score import ScoreInput, classify, score_product

FULL = {
    "name": "Produto completo",
    "demanda": 100,
    "margem": 100,
    "concorrencia": 100,
    "tendencia": 100,
    "logistica": 100,
    "trafego": 100,
}


def test_score_maximo():
    result = score_product(FULL)
    assert result.score == 100.0
    assert result.confidence == 1.0
    assert result.classification == "prioritaria"


def test_sem_dados_nao_pontua():
    result = score_product({"name": "Sem dados"})
    assert result.score == 0.0
    assert result.classification == "sem_dados"
    assert len(result.missing) == 6


def test_dado_faltante_reduz_confianca_e_limita_nota():
    result = score_product({"name": "Parcial", "demanda": 95})
    assert result.confidence == pytest.approx(0.25)
    assert result.score <= 74
    assert any("limite" in w.lower() or "limitado" in w.lower() for w in result.warnings)


def test_popularidade_nao_e_lucro():
    result = score_product({**FULL, "margem": 30})
    assert result.score <= 74
    assert any("Popularidade não é lucratividade" in w or "margem fraca" in w.lower()
               for w in result.warnings)


def test_classificacao_faixas():
    assert classify(95)[0] == "prioritaria"
    assert classify(80)[0] == "interessante"
    assert classify(65)[0] == "analise_adicional"
    assert classify(40)[0] == "nao_recomendar"


def test_explicacoes_e_pesos():
    result = score_product(FULL)
    weights = {item["criterio"]: item["peso"] for item in result.explanations}
    assert sum(weights.values()) == 100
    assert all(item["fonte"] for item in result.explanations)


def test_fonte_registrada():
    result = score_product({**FULL, "sources": {"demanda": "CSV de tendências"}})
    demanda = next(e for e in result.explanations if e["criterio"].startswith("Demanda"))
    assert demanda["fonte"] == "CSV de tendências"


def test_nota_fora_da_faixa_rejeitada():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ScoreInput(name="x", demanda=150)
