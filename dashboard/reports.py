"""Página 16 - Relatórios."""

from __future__ import annotations

import streamlit as st

from dashboard.common import demo_badge, notice, orch, page_header, run_agent, table


def render() -> None:
    o = orch()
    page_header("Relatórios", "Histórico persistente: sobrevive a reinícios da aplicação.")

    reports = o.repo.find("reports", {}, order_by="-created_at", limit=100)
    table(
        [{"Quando": r["created_at"][:19], "Tipo": r["kind"], "Título": r["title"][:70],
          "Origem": demo_badge(r.get("is_demo"))} for r in reports],
        key="reports_table",
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Gerar relatório diário", width="stretch"):
            products = o.repo.find("products", {}, limit=200)
            result = run_agent("automation", "report", "Relatório diário",
                               {"products": products, "kind": "daily"})
            notice("ok" if result["ok"] else "bad",
                   "Gerado." if result["ok"] else result.get("error", ""))
            st.rerun()
    with col2:
        if st.button("Gerar relatório semanal", width="stretch"):
            market_rows = []
            result = run_agent("financial", "evaluate", "Margens do período", {})
            if result["ok"]:
                market_rows = result["result"]["data"].get("rows", [])
            result2 = run_agent("automation", "report", "Relatório semanal",
                                {"financial_rows": market_rows, "kind": "weekly"})
            notice("ok" if result2["ok"] else "bad",
                   "Gerado." if result2["ok"] else result2.get("error", ""))
            st.rerun()

    st.divider()
    if reports:
        options = {f"{r['created_at'][:16]} · {r['title'][:50]}": r for r in reports}
        chosen = st.selectbox("Abrir relatório", list(options))
        report = options[chosen]
        st.markdown(report["body"])
        st.download_button("Baixar (.md)", report["body"],
                           file_name=f"relatorio_{report['id']}.md", mime="text/markdown")
    else:
        st.caption("Nenhum relatório ainda.")
