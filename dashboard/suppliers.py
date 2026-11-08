"""Página 14 - Fornecedores."""

from __future__ import annotations

import streamlit as st

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
    csv_import_widget("suppliers", "fornecedores")
