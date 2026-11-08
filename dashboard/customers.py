"""Página 15 - Clientes e atendimento."""

from __future__ import annotations

import streamlit as st

from dashboard.common import notice, orch, page_header, render_result, run_agent, table


def render() -> None:
    o = orch()
    page_header("Clientes", "FAQ, modelos de resposta e regras de atendimento.")
    notice("info", "Nada é enviado automaticamente. Envio em massa exige aprovação explícita.")

    products = o.repo.find("products", {}, limit=100)
    options = ["(produto principal)"] + [p["name"] for p in products]
    focus = st.selectbox("Produto", options)
    handling = st.number_input("Prazo de envio informado (dias úteis)", 1, 30, 3)

    if st.button("Gerar FAQ e modelos", type="primary"):
        payload = {"handling_days": int(handling)}
        if not focus.startswith("("):
            payload["product"] = focus
        st.session_state["cust"] = run_agent("customer", "faq",
                                             "Preparar FAQ e modelos de resposta", payload)

    result = st.session_state.get("cust")
    if result and result["ok"]:
        data = result["result"]["data"]
        st.subheader("Perguntas frequentes")
        table([{"Pergunta": f["pergunta"], "Resposta": f["resposta"]} for f in data["faq"]],
              key="faq_table")
        st.subheader("Modelos de resposta")
        for key, text in data["templates"].items():
            st.text_area(key.replace("_", " ").title(), text, height=80, key=f"tpl_{key}")
        st.subheader("Regras de atendimento")
        for note in data["policy_notes"]:
            st.markdown(f"- {note}")
        render_result(result)
