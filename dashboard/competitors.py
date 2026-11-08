"""Página 5 - Concorrentes."""

from __future__ import annotations

import streamlit as st

from dashboard.common import (csv_import_widget, demo_badge, money_brl, notice, orch,
                              page_header, render_result, run_agent, table)


def render() -> None:
    o = orch()
    page_header("Concorrentes", "Só dados coletados: preço, avaliação e diferenciais informados.")

    competitors = o.repo.find("competitors", {}, order_by="-collected_at", limit=300)
    products = o.repo.find("products", {}, limit=200)
    names = {p["id"]: p["name"] for p in products}

    table(
        [{"Produto": names.get(c.get("product_id"), "-"), "Concorrente": c["name"],
          "Canal": c.get("marketplace") or "-", "Preço": money_brl(c.get("price")),
          "Nota": c.get("rating"), "Avaliações": c.get("reviews"),
          "Coletado": (c.get("collected_at") or "")[:10],
          "Origem": demo_badge(c.get("is_demo"))} for c in competitors],
        key="competitors_table",
    )

    if st.button("Analisar concorrência", type="primary"):
        with st.spinner("Comparando preços e posicionamento..."):
            st.session_state["comp_result"] = run_agent(
                "market_analyst", "competitor_scan", "Analisar concorrência e preços", {}
            )
    if st.session_state.get("comp_result"):
        render_result(st.session_state["comp_result"])
        data = st.session_state["comp_result"].get("result", {}).get("data", {})
        for item in data.get("analyses", []):
            analysis = item["analysis"]
            if analysis["sample_size"]:
                with st.expander(f"{item['product']} — {analysis['sample_size']} concorrentes"):
                    table([{"Métrica": k, "Valor": v} for k, v in analysis.items()
                           if not isinstance(v, list)], key=f"an_{item['product'][:10]}")

    st.divider()
    csv_import_widget("competitors", "concorrentes")
    notice("info", "O CSV precisa da coluna 'product_name' igual ao nome do produto no catálogo.")
