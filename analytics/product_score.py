"""Product Opportunity Score (0-100).

Pesos iniciais (obrigatórios pelo projeto):
  demanda 25 | margem 25 | concorrência 15 | tendência 15 | logística 10 | tráfego 10

Regras:
1. Nunca inventar dado: critério sem informação fica ``None`` e é listado
   como "sem dado".
2. O score final é normalizado pelo peso *disponível* e reduzido pela
   confiança dos dados (poucos dados => score menor, não igual).
3. Popularidade não é lucratividade: margem fraca limita o score a 74.
4. Score alto exige dados: a nota é limitada pela confiança (peso disponível).
     confiança >= 75% -> sem limite
     confiança >= 50% -> limite 84
     confiança >= 25% -> limite 74
     confiança <  25% -> limite 59
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from core.utils import clamp

WEIGHTS: dict[str, int] = {
    "demanda": 25,
    "margem": 25,
    "concorrencia": 15,
    "tendencia": 15,
    "logistica": 10,
    "trafego": 10,
}

LABELS: dict[str, str] = {
    "demanda": "Demanda e procura",
    "margem": "Margem de lucro",
    "concorrencia": "Concorrência (quanto maior a nota, menos saturado)",
    "tendencia": "Tendência de crescimento",
    "logistica": "Facilidade logística",
    "trafego": "Potencial de tráfego orgânico",
}

CLASSIFICATIONS: tuple[tuple[int, str, str], ...] = (
    (90, "prioritaria", "Oportunidade prioritária"),
    (75, "interessante", "Oportunidade interessante"),
    (60, "analise_adicional", "Necessita análise adicional"),
    (0, "nao_recomendar", "Não recomendar inicialmente"),
)


class ScoreInput(BaseModel):
    name: str = "Produto"
    demanda: float | None = Field(None, ge=0, le=100)
    margem: float | None = Field(None, ge=0, le=100)
    concorrencia: float | None = Field(None, ge=0, le=100)
    tendencia: float | None = Field(None, ge=0, le=100)
    logistica: float | None = Field(None, ge=0, le=100)
    trafego: float | None = Field(None, ge=0, le=100)
    sources: dict[str, str] = Field(default_factory=dict)
    notes: str = ""

    def criteria(self) -> dict[str, float | None]:
        return {
            "demanda": self.demanda,
            "margem": self.margem,
            "concorrencia": self.concorrencia,
            "tendencia": self.tendencia,
            "logistica": self.logistica,
            "trafego": self.trafego,
        }


@dataclass
class ScoreResult:
    name: str
    score: float
    raw_score: float
    confidence: float
    classification: str
    classification_label: str
    explanations: list[dict[str, Any]] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sources: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "score": round(self.score, 1),
            "raw_score": round(self.raw_score, 1),
            "confidence": round(self.confidence, 2),
            "classification": self.classification,
            "classification_label": self.classification_label,
            "explanations": self.explanations,
            "missing": self.missing,
            "warnings": self.warnings,
            "sources": self.sources,
        }


def _confidence_cap(confidence: float) -> float:
    if confidence >= 0.75:
        return 100.0
    if confidence >= 0.50:
        return 84.0
    if confidence >= 0.25:
        return 74.0
    return 59.0


def classify(score: float) -> tuple[str, str]:
    for threshold, code, label in CLASSIFICATIONS:
        if score >= threshold:
            return code, label
    return "nao_recomendar", "Não recomendar inicialmente"


def score_product(data: ScoreInput | dict[str, Any]) -> ScoreResult:
    if isinstance(data, dict):
        data = ScoreInput(**data)

    criteria = data.criteria()
    available_weight = sum(WEIGHTS[k] for k, v in criteria.items() if v is not None)
    missing = [LABELS[k] for k, v in criteria.items() if v is None]
    explanations: list[dict[str, Any]] = []

    if available_weight == 0:
        return ScoreResult(
            name=data.name,
            score=0.0,
            raw_score=0.0,
            confidence=0.0,
            classification="sem_dados",
            classification_label="Sem dados para avaliar",
            explanations=[
                {
                    "criterio": LABELS[k],
                    "peso": WEIGHTS[k],
                    "nota": None,
                    "contribuicao": 0.0,
                    "fonte": data.sources.get(k, "não informada"),
                    "observacao": "sem dado",
                }
                for k in WEIGHTS
            ],
            missing=[LABELS[k] for k in WEIGHTS],
            warnings=["Nenhum critério informado: impossível pontuar sem dados."],
            sources=data.sources,
        )

    weighted = sum((criteria[k] or 0) * WEIGHTS[k] for k in WEIGHTS)
    raw_score = weighted / available_weight
    confidence = available_weight / sum(WEIGHTS.values())

    for key, weight in WEIGHTS.items():
        value = criteria[key]
        contribution = (value * weight / 100) if value is not None else 0.0
        explanations.append(
            {
                "criterio": LABELS[key],
                "peso": weight,
                "nota": value,
                "contribuicao": round(contribution, 2),
                "fonte": data.sources.get(key, "não informada"),
                "observacao": "sem dado" if value is None else "ok",
            }
        )

    # Penalidade leve + limite duro por confiança (nunca premia quem tem menos dados)
    score = raw_score * (0.85 + 0.15 * confidence)
    confidence_cap = _confidence_cap(confidence)
    score = min(score, confidence_cap)

    warnings: list[str] = []
    if confidence < 1.0:
        warnings.append(
            f"Score limitado a {confidence_cap:.0f} por confiança de {confidence:.0%} "
            "dos pesos com dados reais."
        )
    margin = criteria.get("margem")
    demand = criteria.get("demanda")
    if margin is not None and margin < 40:
        if score > 74:
            warnings.append(
                "Score limitado a 74: demanda/popularidade alta, mas a margem de lucro é "
                "insuficiente. Popularidade não é lucratividade."
            )
        elif demand is not None and demand >= 70:
            warnings.append(
                "Produto popular, porém com margem fraca: validar custos e taxas antes de "
                "investir. Popularidade não é lucratividade."
            )
        score = min(score, 74)
    if confidence < 0.6:
        warnings.append(
            f"Confiança baixa ({confidence:.0%} dos pesos com dados). "
            "Colete mais informações antes de investir."
        )
    if data.notes:
        warnings.append(f"Observação do analista: {data.notes}")

    score = clamp(round(score, 1))
    code, label = classify(score)
    return ScoreResult(
        name=data.name,
        score=score,
        raw_score=raw_score,
        confidence=confidence,
        classification=code,
        classification_label=label,
        explanations=explanations,
        missing=missing,
        warnings=warnings,
        sources=data.sources,
    )


def score_from_product(
    product: dict[str, Any],
    margin_pct: float | None = None,
    extra: dict[str, Any] | None = None,
) -> ScoreResult:
    """Monta o ScoreInput a partir de um produto do catálogo.

    Só usa dados existentes. O que não existe fica ``None`` (e é reportado).
    """
    from analytics.profitability import margin_score

    extra = extra or {}
    sources: dict[str, str] = {}

    margem_nota: float | None = None
    if margin_pct is not None:
        margem_nota = margin_score(margin_pct)
        sources["margem"] = "cálculo determinístico (analytics/profitability.py)"

    payload: dict[str, Any] = {
        "name": product.get("name", "Produto"),
        "margem": margem_nota,
        "demanda": extra.get("demanda"),
        "concorrencia": extra.get("concorrencia"),
        "tendencia": extra.get("tendencia"),
        "logistica": extra.get("logistica"),
        "trafego": extra.get("trafego"),
        "sources": sources,
        "notes": extra.get("notes", ""),
    }
    for key, value in (extra.get("sources") or {}).items():
        sources[key] = value
    for key in ("demanda", "concorrencia", "tendencia", "logistica", "trafego"):
        if extra.get(key) is not None and key not in sources:
            sources[key] = "dado fornecido pelo proprietário/CSV"
    return score_product(ScoreInput(**payload))
