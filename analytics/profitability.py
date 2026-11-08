"""Calculadora financeira determinística para e-commerce.

REGRA DO PROJETO: nenhum número aqui vem de "estimativa da IA". Tudo é
calculado por código. A IA só pode *explicar* o resultado.

Taxas de marketplace NÃO são inventadas: o proprietário informa comissão,
taxa fixa e frete subsidiado em Configurações > Marketplaces, ou o campo
fica 0% e o relatório marca "taxa não informada".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field, model_validator

from core.utils import clamp


class CostStructure(BaseModel):
    """Custos de aquisição e operação de 1 unidade."""

    purchase_price: float = Field(0.0, ge=0, description="Preço de compra unitário")
    acquisition_shipping: float = Field(0.0, ge=0, description="Frete de aquisição unitário")
    packaging: float = Field(0.0, ge=0, description="Embalagem por unidade")
    other_costs: float = Field(0.0, ge=0, description="Outros custos por unidade")


class SaleTerms(BaseModel):
    """Termos da venda no canal."""

    sale_price: float = Field(..., gt=0, description="Preço de venda unitário")
    commission_pct: float = Field(0.0, ge=0, le=100, description="Comissão do marketplace (%)")
    fixed_fee: float = Field(0.0, ge=0, description="Taxa fixa por item")
    subsidized_shipping: float = Field(0.0, ge=0, description="Frete pago pelo vendedor")
    tax_pct: float = Field(0.0, ge=0, le=100, description="Impostos sobre a receita (%)")
    discount: float = Field(0.0, ge=0, description="Desconto concedido por unidade")
    ad_cost: float = Field(0.0, ge=0, description="Custo de anúncios atribuído à unidade")


class FinancialInput(BaseModel):
    product_name: str = "Produto sem nome"
    marketplace: str = "loja_propria"
    quantity: int = Field(1, ge=1, description="Unidades vendidas no período")
    costs: CostStructure = Field(default_factory=CostStructure)
    terms: SaleTerms
    fixed_monthly_costs: float = Field(0.0, ge=0, description="Custos fixos mensais do negócio")
    target_margin_pct: float = Field(20.0, ge=0, lt=100, description="Margem líquida desejada (%)")
    commission_source: str = "informado pelo proprietário"

    @model_validator(mode="after")
    def _discount_not_above_price(self) -> "FinancialInput":
        if self.terms.discount >= self.terms.sale_price:
            raise ValueError("o desconto não pode ser maior ou igual ao preço de venda")
        return self


@dataclass
class FinancialResult:
    product_name: str
    marketplace: str
    quantity: int
    revenue: float
    goods_cost: float
    fees: float
    taxes: float
    ad_cost: float
    total_cost: float
    gross_profit: float
    net_profit: float
    margin_pct: float
    roi_pct: float
    markup_pct: float
    net_profit_per_unit: float
    min_price_breakeven: float | None
    min_price_target_margin: float | None
    breakeven_units: int | None
    health: str
    warnings: list[str] = field(default_factory=list)
    breakdown: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_name": self.product_name,
            "marketplace": self.marketplace,
            "quantity": self.quantity,
            "revenue": round(self.revenue, 2),
            "goods_cost": round(self.goods_cost, 2),
            "fees": round(self.fees, 2),
            "taxes": round(self.taxes, 2),
            "ad_cost": round(self.ad_cost, 2),
            "total_cost": round(self.total_cost, 2),
            "gross_profit": round(self.gross_profit, 2),
            "net_profit": round(self.net_profit, 2),
            "margin_pct": round(self.margin_pct, 2),
            "roi_pct": round(self.roi_pct, 2),
            "markup_pct": round(self.markup_pct, 2),
            "net_profit_per_unit": round(self.net_profit_per_unit, 2),
            "min_price_breakeven": _r(self.min_price_breakeven),
            "min_price_target_margin": _r(self.min_price_target_margin),
            "breakeven_units": self.breakeven_units,
            "health": self.health,
            "warnings": self.warnings,
            "breakdown": self.breakdown,
        }


def _r(value: float | None) -> float | None:
    return round(value, 2) if value is not None else None


def _solve_price(fixed_cost: float, rate: float, target_rate: float = 0.0) -> float | None:
    """Preço que zera (ou atinge target) a margem.

    receita = p; custos = fixed_cost + rate * p; lucro = p - fixed - rate*p.
    Para lucro = target_rate * p  ->  p = fixed / (1 - rate - target_rate).
    """
    denominator = 1 - rate - target_rate
    if denominator <= 0:
        return None
    return round(fixed_cost / denominator, 2)


def calculate(data: FinancialInput | dict[str, Any]) -> FinancialResult:
    """Calcula o resultado financeiro completo, unidade e período."""
    if isinstance(data, dict):
        data = FinancialInput(**data)

    qty = data.quantity
    costs, terms = data.costs, data.terms

    gross_revenue = terms.sale_price * qty
    revenue = gross_revenue - terms.discount * qty

    goods_cost = (
        costs.purchase_price + costs.acquisition_shipping + costs.packaging + costs.other_costs
    ) * qty
    commission = revenue * (terms.commission_pct / 100)
    fixed_fees = terms.fixed_fee * qty
    shipping = terms.subsidized_shipping * qty
    fees = commission + fixed_fees + shipping
    taxes = revenue * (terms.tax_pct / 100)
    ad_cost = terms.ad_cost * qty

    total_cost = goods_cost + fees + taxes + ad_cost
    gross_profit = revenue - goods_cost
    net_profit = revenue - total_cost
    net_per_unit = net_profit / qty

    margin_pct = (net_profit / revenue * 100) if revenue else 0.0
    invested = goods_cost + ad_cost
    roi_pct = (net_profit / invested * 100) if invested else 0.0
    markup_pct = (
        (terms.sale_price - costs.purchase_price) / costs.purchase_price * 100
        if costs.purchase_price
        else 0.0
    )

    # Custos que não variam com o preço (por unidade) para achar preço mínimo
    per_unit_fixed = (
        costs.purchase_price + costs.acquisition_shipping + costs.packaging
        + costs.other_costs + terms.fixed_fee + terms.subsidized_shipping + terms.ad_cost
        + terms.discount
    )
    rate = (terms.commission_pct + terms.tax_pct) / 100
    min_breakeven = _solve_price(per_unit_fixed, rate, 0.0)
    min_target = _solve_price(per_unit_fixed, rate, data.target_margin_pct / 100)

    breakeven_units = None
    if data.fixed_monthly_costs > 0 and net_per_unit > 0:
        import math

        breakeven_units = math.ceil(data.fixed_monthly_costs / net_per_unit)

    warnings: list[str] = []
    if terms.commission_pct == 0 and terms.fixed_fee == 0:
        warnings.append(
            "Comissão e taxa fixa estão em 0. Se o canal cobra taxas, informe os valores "
            "em Configurações > Marketplaces para não superestimar o lucro."
        )
    if terms.tax_pct == 0:
        warnings.append("Impostos em 0%. Informe o percentual aplicável ao seu regime.")
    if gross_profit > 0 and net_profit <= 0:
        warnings.append(
            "Lucro bruto positivo, mas o lucro líquido é negativo: taxas, frete, impostos "
            "ou anúncios consomem toda a margem."
        )
    if net_profit < 0:
        warnings.append("Prejuízo estimado nesta configuração.")
    if terms.sale_price < costs.purchase_price:
        warnings.append("O preço de venda está abaixo do custo de compra.")
    if min_target is None:
        warnings.append(
            "Não é possível atingir a margem desejada: comissão + imposto + margem "
            "somam 100% ou mais da receita."
        )

    health = _health(margin_pct)

    return FinancialResult(
        product_name=data.product_name,
        marketplace=data.marketplace,
        quantity=qty,
        revenue=revenue,
        goods_cost=goods_cost,
        fees=fees,
        taxes=taxes,
        ad_cost=ad_cost,
        total_cost=total_cost,
        gross_profit=gross_profit,
        net_profit=net_profit,
        margin_pct=margin_pct,
        roi_pct=roi_pct,
        markup_pct=markup_pct,
        net_profit_per_unit=net_per_unit,
        min_price_breakeven=min_breakeven,
        min_price_target_margin=min_target,
        breakeven_units=breakeven_units,
        health=health,
        warnings=warnings,
        breakdown={
            "commission": round(commission, 2),
            "fixed_fees": round(fixed_fees, 2),
            "shipping": round(shipping, 2),
            "per_unit_fixed_cost": round(per_unit_fixed, 2),
            "variable_rate_pct": round(rate * 100, 3),
            "commission_source": data.commission_source,
        },
    )


def _health(margin_pct: float) -> str:
    if margin_pct < 0:
        return "prejuizo"
    if margin_pct < 8:
        return "critico"
    if margin_pct < 15:
        return "atencao"
    if margin_pct < 25:
        return "saudavel"
    return "excelente"


def compare_marketplaces(
    base: FinancialInput, rules: dict[str, dict[str, float]]
) -> list[dict[str, Any]]:
    """Compara o mesmo produto em vários canais, usando regras informadas.

    ``rules`` = {"shopee": {"commission_pct": 14, "fixed_fee": 0}, ...}
    Canais sem regra informada aparecem com aviso, não com taxa inventada.
    """
    results: list[dict[str, Any]] = []
    for channel, rule in rules.items():
        payload = base.model_dump()
        payload["marketplace"] = channel
        payload["terms"] = {
            **base.terms.model_dump(),
            "commission_pct": float(rule.get("commission_pct", 0) or 0),
            "fixed_fee": float(rule.get("fixed_fee", 0) or 0),
            "subsidized_shipping": float(rule.get("subsidized_shipping", 0) or 0),
        }
        payload["commission_source"] = rule.get("source", "regra informada")
        result = calculate(FinancialInput(**payload))
        row = result.to_dict()
        row["commission_pct"] = payload["terms"]["commission_pct"]
        results.append(row)
    results.sort(key=lambda r: r["net_profit"], reverse=True)
    return results


def margin_score(margin_pct: float) -> float:
    """Converte margem líquida em nota 0-100 para o Product Opportunity Score."""
    if margin_pct < 0:
        return 0.0
    if margin_pct >= 30:
        return 100.0
    if margin_pct >= 20:
        return 80.0 + (margin_pct - 20) * 2
    if margin_pct >= 10:
        return 50.0 + (margin_pct - 10) * 3
    if margin_pct >= 5:
        return 25.0 + (margin_pct - 5) * 5
    return clamp(margin_pct * 5)
