"""Página 14 - Fornecedores."""

from __future__ import annotations

import streamlit as st

from analytics.fulfillment import deadline_from_marketplace, rank_suppliers
from dashboard.common import (csv_import_widget, demo_badge, money_brl, notice, orch,
                              page_header, render_result, run_agent, table)


def render() -> None:
    o = orch()
    page_header("Fornecedores", "Custo total de aquisição, prazo e riscos. Nenhuma compra é feita aqui.")

    suppliers = o.repo.find("suppliers", {}, order_by="unit_price", limit=200)
    table(
        [{"Fornecedor": s["name"], "Preço un.": money_brl(s.get("unit_price")),
          "Qtd mín.": s.get("min_qty"), "Prazo (dias)": s.get("lead_time_days"),
          "Frete": money_brl(s.get("shipping_cost")), "Contato": s.get("contact"),
          "Origem": demo_badge(s.get("is_demo"))} for s in suppliers],
        key="suppliers_table",
    )

    quantity = st.number_input("Quantidade para comparar (0 = quantidade mínima)", 0, 10000, 0)
    if st.button("Comparar fornecedores", type="primary"):
        st.session_state["sup"] = run_agent("supplier_hunter", "compare",
                                            "Comparar fornecedores por custo total",
                                            {"quantity": int(quantity)})
    result = st.session_state.get("sup")
    if result and result["ok"]:
        data = result["result"]["data"]
        table([{"Fornecedor": s["name"], "Qtd": s["quantity"],
                "Custo total": money_brl(s["total_cost"]),
                "Unitário total": money_brl(s["unit_total_cost"]),
                "Prazo": s["lead_time_days"], "Riscos": "; ".join(s["risks"]) or "-"}
               for s in data.get("suppliers", [])], key="sup_compare")
        render_result(result)

    st.divider()
    st.subheader("Quem entrega dentro do prazo")
    st.caption("Cruza o prazo do canal com o prazo de cada fornecedor. "
               "Atraso no despacho derruba o anúncio no ranking.")
    regras = o.repo.find("marketplaces", {}, order_by="name")
    if not regras:
        notice("warn", "Nenhum canal cadastrado. Salve o prazo em uma página de canal.")
    elif not suppliers:
        notice("warn", "Cadastre fornecedores (ou importe o CSV) para avaliar prazo.")
    else:
        por_nome = {r["name"]: r for r in regras}
        escolhido = st.selectbox("Canal", list(por_nome), key="sla_channel")
        qtd = st.number_input("Quantidade por pedido", 1, 1000, 1, key="sla_qty")
        prazo = deadline_from_marketplace(por_nome[escolhido])
        if not prazo.informado:
            notice("warn", f"Prazo da {prazo.name} não informado. Abra a página do canal "
                           f"e salve os dias úteis de despacho.")
        ranking = rank_suppliers(suppliers, prazo, int(qtd))
        table(
            [{"Fornecedor": v.supplier, "Veredito": v.verdict,
              "Despacha em": f"{v.dispatch_date.strftime('%d/%m')}",
              "Dias úteis": v.days_to_dispatch,
              "Folga": "-" if v.slack_days is None else v.slack_days,
              "Modo": v.mode,
              "Custo/un": money_brl(v.landed_unit_cost),
              "Riscos": "; ".join(v.risks) or "-"} for v in ranking],
            key="sla_table",
        )

    st.divider()
    csv_import_widget("suppliers", "fornecedores")
