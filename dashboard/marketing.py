"""Página 12 - Marketing."""

from __future__ import annotations

import streamlit as st

from dashboard.common import notice, orch, page_header, render_result, run_agent, table


def render() -> None:
    o = orch()
    page_header("Marketing", "Campanhas orgânicas, textos e calendário. Orçamento de mídia: R$ 0.")

    channels = st.multiselect("Canais", ["instagram", "tiktok_shop", "shopee", "mercadolivre",
                                         "youtube_shorts"], default=["instagram", "tiktok_shop"])
    products = o.repo.find("products", {}, limit=100)
    options = ["(melhor score)"] + [p["name"] for p in products]
    focus = st.selectbox("Produto foco", options)

    if st.button("Gerar plano de marketing", type="primary"):
        payload = {"channels": channels}
        if focus != "(melhor score)":
            payload["product"] = focus
        st.session_state["mkt"] = run_agent("marketing", "plan", "Criar campanhas orgânicas", payload)

    result = st.session_state.get("mkt")
    if result:
        render_result(result)
        if result["ok"]:
            data = result["result"]["data"]
            st.subheader("Campanhas")
            table([{"Canal": c["channel"], "Ângulo": c["angle"], "Gancho": c["hook"],
                    "CTA": c["cta"], "Orçamento": c["budget"]} for c in data.get("campaigns", [])],
                  key="mkt_campaigns")
            st.subheader("Calendário sugerido")
            table(data.get("calendar", []), key="mkt_calendar")
            st.download_button(
                "Baixar calendário (CSV)",
                "\n".join(";".join(str(v) for v in row.values())
                          for row in data.get("calendar", [])),
                file_name="calendario_marketing.csv", mime="text/csv",
            )
    notice("warn", "Sem dados de público real, o direcionamento é hipótese a validar com teste.")
