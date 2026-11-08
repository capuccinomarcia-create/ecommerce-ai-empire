"""Análise de concorrentes baseada apenas em dados coletados/informados."""

from __future__ import annotations

import statistics
from typing import Any


def _prices(competitors: list[dict[str, Any]]) -> list[float]:
    return [float(c["price"]) for c in competitors if c.get("price") not in (None, "", 0)]


def analyze(competitors: list[dict[str, Any]], our_price: float | None = None) -> dict[str, Any]:
    """Estatísticas de preço/avaliação e posicionamento do nosso anúncio."""
    prices = _prices(competitors)
    ratings = [float(c["rating"]) for c in competitors if c.get("rating") not in (None, "")]
    reviews = [int(c["reviews"]) for c in competitors if c.get("reviews") not in (None, "")]

    if not prices:
        return {
            "sample_size": 0,
            "average": None,
            "median": None,
            "min": None,
            "max": None,
            "position": "sem_dados",
            "recommendations": [
                "Nenhum preço de concorrente disponível. Importe um CSV ou cadastre "
                "concorrentes manualmente para gerar análise real."
            ],
            "differentiators": [],
        }

    average = statistics.fmean(prices)
    median = statistics.median(prices)
    result: dict[str, Any] = {
        "sample_size": len(prices),
        "average": round(average, 2),
        "median": round(median, 2),
        "min": round(min(prices), 2),
        "max": round(max(prices), 2),
        "rating_average": round(statistics.fmean(ratings), 2) if ratings else None,
        "reviews_total": sum(reviews) if reviews else None,
        "recommendations": [],
        "differentiators": [],
    }

    if our_price:
        diff = (our_price - median) / median * 100
        result["our_price"] = round(float(our_price), 2)
        result["price_gap_vs_median_pct"] = round(diff, 1)
        if diff <= -15:
            result["position"] = "abaixo_do_mercado"
            result["recommendations"].append(
                "Seu preço está bem abaixo da mediana: confira se a margem cobre taxas "
                "e frete antes de manter este posicionamento."
            )
        elif diff <= 5:
            result["position"] = "competitivo"
            result["recommendations"].append(
                "Preço alinhado ao mercado. Diferencie por título, fotos, prazo e prova social."
            )
        else:
            result["position"] = "acima_do_mercado"
            result["recommendations"].append(
                "Preço acima da mediana: justifique com diferenciais (kit, garantia, "
                "brinde, frete rápido) ou ajuste a oferta."
            )
    else:
        result["position"] = "nao_informado"

    if result.get("reviews_total") is not None and result["reviews_total"] < 50:
        result["differentiators"].append(
            "Categoria com pouca prova social acumulada: avaliações reais podem gerar vantagem."
        )
    spread = (max(prices) - min(prices)) / median if median else 0
    if spread > 0.6:
        result["differentiators"].append(
            "Grande dispersão de preços: existe espaço para posicionamento por faixa."
        )
    if result.get("rating_average") is not None and result["rating_average"] < 4.3:
        result["differentiators"].append(
            "Nota média dos concorrentes abaixo de 4,3: qualidade e atendimento são diferenciais."
        )
    return result
