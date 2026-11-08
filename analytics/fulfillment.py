"""Viabilidade de entrega: o fornecedor consegue cumprir o prazo da plataforma?

Por que isso existe: em marketplace, atrasar o despacho derruba o anúncio no
ranking e queima o tráfego conquistado. Antes de escolher o produto, é preciso
saber se o fornecedor entrega dentro do prazo que a plataforma promete.

Regras do projeto respeitadas aqui:
  * nenhum prazo de plataforma é inventado: se o proprietário não informou
    `handling_days` / `delivery_days`, o veredito é "indefinido" e o sistema
    pede o dado;
  * todo cálculo é determinístico (dias úteis, custo por unidade, folga);
  * a IA não decide nada disso, apenas explica o resultado.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Iterable

VEREDITO_OK = "pode vender hoje"
VEREDITO_LIMITE = "vende no limite"
VEREDITO_RISCO = "vende com risco"
VEREDITO_FORA = "perde o prazo"
VEREDITO_INDEFINIDO = "indefinido (prazo não informado)"

MODO_ENVIO = "envio do fornecedor"
MODO_RETIRADA = "retirada no fornecedor"
MODO_RETIRADA_MESMO_DIA = "retirada no mesmo dia"


def add_business_days(start: date, days: int) -> date:
    """Soma dias úteis (pula sábado e domingo).

    Feriados não são considerados: o sistema não tem calendário oficial
    confiável offline, e chutar feriado seria inventar dado.
    """
    if days <= 0:
        return start
    atual = start
    restantes = days
    while restantes > 0:
        atual += timedelta(days=1)
        if atual.weekday() < 5:  # 0=segunda ... 4=sexta
            restantes -= 1
    return atual


@dataclass
class ChannelDeadline:
    """Prazo que o canal dá ao vendedor. 0 significa 'não informado'."""

    slug: str
    name: str
    handling_days: int = 0
    delivery_days: int = 0
    source: str = "não informado pelo proprietário"

    @property
    def informado(self) -> bool:
        return self.handling_days > 0


@dataclass
class SupplierViability:
    supplier: str
    mode: str
    dispatch_date: date
    days_to_dispatch: int
    handling_days: int
    slack_days: int | None
    on_time: bool | None
    unit_cost: float
    landed_unit_cost: float
    quantity: int
    total_cost: float
    verdict: str
    risks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "supplier": self.supplier,
            "mode": self.mode,
            "dispatch_date": self.dispatch_date.isoformat(),
            "days_to_dispatch": self.days_to_dispatch,
            "handling_days": self.handling_days,
            "slack_days": self.slack_days,
            "on_time": self.on_time,
            "unit_cost": round(self.unit_cost, 2),
            "landed_unit_cost": round(self.landed_unit_cost, 2),
            "quantity": self.quantity,
            "total_cost": round(self.total_cost, 2),
            "verdict": self.verdict,
            "risks": self.risks,
        }


def evaluate_supplier(
    supplier: dict[str, Any],
    deadline: ChannelDeadline,
    quantity: int | None = None,
    today: date | None = None,
) -> SupplierViability:
    """Avalia 1 fornecedor contra o prazo de 1 canal."""
    today = today or date.today()
    min_qty = max(1, int(supplier.get("min_qty") or 1))
    qty = max(min_qty, int(quantity or min_qty))

    unit = float(supplier.get("unit_price") or 0)
    shipping = float(supplier.get("shipping_cost") or 0)
    lead = int(supplier.get("lead_time_days") or 0)
    pickup = bool(supplier.get("pickup_available"))
    same_day = bool(supplier.get("same_day_pickup"))

    if same_day:
        mode = MODO_RETIRADA_MESMO_DIA
        dias = min(lead, 0)  # retirar hoje despacha hoje
    elif pickup:
        mode = MODO_RETIRADA
        dias = lead
    else:
        mode = MODO_ENVIO
        dias = lead

    dispatch = add_business_days(today, dias)

    total = unit * qty + shipping
    landed = total / qty if qty else 0.0

    risks: list[str] = []
    if shipping <= 0:
        risks.append("Frete não informado: o custo por unidade pode estar subestimado.")
    if unit <= 0:
        risks.append("Preço unitário não informado.")
    if min_qty >= 50:
        risks.append(f"Quantidade mínima alta ({min_qty} un): imobiliza capital.")

    if not deadline.informado:
        return SupplierViability(
            supplier=supplier.get("name") or "fornecedor sem nome",
            mode=mode,
            dispatch_date=dispatch,
            days_to_dispatch=dias,
            handling_days=0,
            slack_days=None,
            on_time=None,
            unit_cost=unit,
            landed_unit_cost=landed,
            quantity=qty,
            total_cost=total,
            verdict=VEREDITO_INDEFINIDO,
            risks=risks
            + [
                f"Prazo de despacho da {deadline.name} não informado. "
                "Sem esse número não é possível garantir entrega no prazo."
            ],
        )

    slack = deadline.handling_days - dias
    on_time = slack >= 0
    if not on_time:
        verdict = VEREDITO_FORA
        risks.append(
            f"Despacha em {dias} dia(s) útil(eis), mas a {deadline.name} exige "
            f"{deadline.handling_days}. Anúncio perde relevância."
        )
    elif slack == 0:
        verdict = VEREDITO_LIMITE
        risks.append("Sem folga: qualquer imprevisto atrasa o despacho.")
    elif slack == 1:
        verdict = VEREDITO_RISCO
    else:
        verdict = VEREDITO_OK

    if dias >= 15:
        risks.append(f"Prazo longo ({dias} dias): exige estoque de segurança.")

    return SupplierViability(
        supplier=supplier.get("name") or "fornecedor sem nome",
        mode=mode,
        dispatch_date=dispatch,
        days_to_dispatch=dias,
        handling_days=deadline.handling_days,
        slack_days=slack,
        on_time=on_time,
        unit_cost=unit,
        landed_unit_cost=landed,
        quantity=qty,
        total_cost=total,
        verdict=verdict,
        risks=risks,
    )


def _grupo(v: SupplierViability) -> int:
    """Grupo de confiabilidade do prazo (menor é melhor)."""
    if v.on_time is None:
        return 2                      # prazo do canal não informado
    if not v.on_time:
        return 3                      # perde o prazo
    if (v.slack_days or 0) <= 0:
        return 1                      # entrega, mas sem folga para imprevisto
    return 0                          # entrega com folga


def rank_suppliers(
    suppliers: Iterable[dict[str, Any]],
    deadline: ChannelDeadline,
    quantity: int | None = None,
    today: date | None = None,
) -> list[SupplierViability]:
    """Ordena por confiabilidade de prazo e, dentro do grupo, pelo menor custo.

    Quem entrega com folga vem antes de quem entrega no limite, que vem antes de
    quem perde o prazo. Entre fornecedores igualmente confiáveis, ganha o mais
    barato: pagar mais caro sem ganhar prazo é desperdício de margem.
    """
    avaliados = [evaluate_supplier(s, deadline, quantity, today) for s in suppliers]
    return sorted(avaliados, key=lambda v: (_grupo(v), v.landed_unit_cost))


def best_option(
    suppliers: Iterable[dict[str, Any]],
    deadline: ChannelDeadline,
    quantity: int | None = None,
    today: date | None = None,
) -> SupplierViability | None:
    ranking = rank_suppliers(suppliers, deadline, quantity, today)
    return ranking[0] if ranking else None


def deadline_from_marketplace(row: dict[str, Any]) -> ChannelDeadline:
    """Converte a linha da tabela marketplaces no prazo usado pelo cálculo."""
    return ChannelDeadline(
        slug=str(row.get("slug") or ""),
        name=str(row.get("name") or row.get("slug") or "canal"),
        handling_days=int(row.get("handling_days") or 0),
        delivery_days=int(row.get("delivery_days") or 0),
        source=str(row.get("sla_source") or "não informado pelo proprietário"),
    )
