"""Página 6 - Calculadora financeira (determinística)."""

from __future__ import annotations

import streamlit as st

from analytics.profitability import FinancialInput, calculate, compare_marketplaces
from core.utils import money, pct
from dashboard.common import kpis, notice, orch, page_header, table


def render() -> None:
    o = orch()
    page_header("Calculadora financeira",
                "Receita, custos, taxas, margem, ROI, preço mínimo e ponto de equilíbrio.")

    rules = {m["slug"]: m for m in o.repo.find("marketplaces", {}, order_by="name")}
    with st.form("financial_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            name = st.text_input("Nome do produto", "Produto")
            channel = st.selectbox("Canal", list(rules) or ["loja_propria"])
            quantity = st.number_input("Quantidade", 1, 10000, 1)
        with col2:
            purchase = st.number_input("Preço de compra (un.)", 0.0, step=1.0)
            acq_shipping = st.number_input("Frete de aquisição (un.)", 0.0, step=0.5)
            packaging = st.number_input("Embalagem (un.)", 0.0, step=0.5)
            other_costs = st.number_input("Outros custos (un.)", 0.0, step=0.5)
        with col3:
            sale_price = st.number_input("Preço de venda (un.)", 1.0, step=1.0)
            rule = rules.get(channel, {})
            commission = st.number_input("Comissão (%)", 0.0, 100.0,
                                         value=float(rule.get("commission_pct") or 0))
            fixed_fee = st.number_input("Taxa fixa (un.)", 0.0,
                                        value=float(rule.get("fixed_fee") or 0))
            tax_pct = st.number_input("Impostos (%)", 0.0, 100.0, value=0.0)

        col4, col5, col6 = st.columns(3)
        with col4:
            shipping_out = st.number_input("Frete subsidiado (un.)", 0.0)
            ad_cost = st.number_input("Anúncios (un.)", 0.0)
        with col5:
            discount = st.number_input("Desconto (un.)", 0.0)
            fixed_monthly = st.number_input("Custos fixos mensais (R$)", 0.0, step=50.0)
        with col6:
            target_margin = st.number_input("Margem desejada (%)", 0.0, 99.0, 20.0)
            st.caption(f"Regra carregada: {rule.get('source', 'não informada')}")

        submitted = st.form_submit_button("Calcular", type="primary")

    if submitted:
        try:
            result = calculate(FinancialInput(
                product_name=name, marketplace=channel, quantity=int(quantity),
                costs={"purchase_price": purchase, "acquisition_shipping": acq_shipping,
                       "packaging": packaging, "other_costs": other_costs},
                terms={"sale_price": sale_price, "commission_pct": commission,
                       "fixed_fee": fixed_fee, "subsidized_shipping": shipping_out,
                       "tax_pct": tax_pct, "discount": discount, "ad_cost": ad_cost},
                fixed_monthly_costs=fixed_monthly, target_margin_pct=target_margin,
                commission_source=rule.get("source", "informado no formulário"),
            ))
            data = result.to_dict()
            kpis([
                ("Receita", money(data["revenue"]), f"{quantity} unidade(s)"),
                ("Custo total", money(data["total_cost"]),
                 f"taxas {money(data['fees'])}"),
                ("Lucro líquido", money(data["net_profit"]), f"margem {pct(data['margin_pct'])}"),
                ("ROI", pct(data["roi_pct"]), data["health"]),
            ])
            st.write("")
            kpis([
                ("Lucro/unidade", money(data["net_profit_per_unit"]), "após todas as taxas"),
                ("Preço mínimo (equilíbrio)", money(data["min_price_breakeven"] or 0), "lucro zero"),
                ("Preço p/ margem alvo", money(data["min_price_target_margin"] or 0),
                 f"{pct(target_margin)} líquido"),
                ("Ponto de equilíbrio", f"{data['breakeven_units'] or '—'} un/mês",
                 "cobre custos fixos"),
            ])
            for warning in data["warnings"]:
                notice("warn", warning)
            with st.expander("Composição do cálculo"):
                table([{"Item": k, "Valor": v} for k, v in data["breakdown"].items()],
                      key="fin_breakdown")

            if len(rules) > 1:
                base = FinancialInput(
                    product_name=name, marketplace=channel, quantity=int(quantity),
                    costs={"purchase_price": purchase, "acquisition_shipping": acq_shipping,
                           "packaging": packaging, "other_costs": other_costs},
                    terms={"sale_price": sale_price, "tax_pct": tax_pct, "discount": discount,
                           "ad_cost": ad_cost},
                    fixed_monthly_costs=fixed_monthly, target_margin_pct=target_margin,
                )
                comparison = compare_marketplaces(
                    base,
                    {slug: {"commission_pct": float(r.get("commission_pct") or 0),
                            "fixed_fee": float(r.get("fixed_fee") or 0),
                            "source": r.get("source") or "não informado"}
                     for slug, r in rules.items()},
                )
                st.subheader("Comparativo entre canais")
                table([{"Canal": c["marketplace"], "Comissão %": c["commission_pct"],
                        "Lucro líquido": money(c["net_profit"]),
                        "Margem": pct(c["margin_pct"])} for c in comparison],
                      key="fin_channels")
                notice("info", "Canais com taxa não informada aparecem com 0% e ficam "
                               "marcados: informe os valores reais em Configurações.")
        except ValueError as exc:
            st.error(f"Verifique os valores: {exc}")
