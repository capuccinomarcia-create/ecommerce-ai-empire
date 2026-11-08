"""Página 4 - Pesquisa de produtos e Product Opportunity Score."""

from __future__ import annotations

import streamlit as st

from dashboard.common import (csv_import_widget, demo_badge, kpis, money_brl, notice, orch,
                              page_header, pct_br, render_result, run_agent, table)


def render() -> None:
    o = orch()
    page_header("Pesquisa de produtos",
                "Product Opportunity Score de 0 a 100 com explicação por critério e fonte.")

    with st.expander("Como a nota é calculada", expanded=False):
        st.markdown(
            "- Demanda e procura: **25**\n- Margem de lucro: **25**\n"
            "- Concorrência: **15**\n- Tendência: **15**\n"
            "- Logística: **10**\n- Tráfego orgânico: **10**\n\n"
            "Classificação: 90-100 prioritária · 75-89 interessante · 60-74 análise adicional · "
            "abaixo de 60 não recomendar.\n\n"
            "Sem dado não vira zero: o critério é marcado como ausente e a nota final é limitada "
            "pela confiança. Margem fraca limita a nota a 74, porque popularidade não é lucro."
        )

    col1, col2 = st.columns([1, 1])
    with col1:
        limit = st.number_input("Candidatos a analisar", 3, 50, 10)
    with col2:
        top = st.number_input("Quantos priorizar", 1, 10, 5)

    if st.button("Rodar pesquisa de produtos", type="primary"):
        with st.spinner("Analisando candidatos..."):
            st.session_state["hunt"] = run_agent(
                "product_hunter", "research", "Pesquisar e pontuar produtos",
                {"limit": int(limit), "top": int(top)},
            )

    result = st.session_state.get("hunt")
    if result:
        if not result["ok"]:
            notice("bad", f"Falha: {result['error']}")
        else:
            data = result["result"]["data"]
            rows = data.get("top") or []
            kpis([
                ("Analisados", data.get("count", 0), "candidatos no banco"),
                ("Priorizados", len(rows), "melhores scores"),
                ("DEMO", demo_badge(data.get("demo_mode")), "origem dos dados"),
            ])
            table(
                [{"#": i + 1, "Produto": r["name"], "Score": r["score"],
                  "Classificação": r["classification_label"], "Margem": pct_br(r["margin_pct"]),
                  "Lucro/un": money_brl(r["net_profit"]), "Canal": r["channel_label"],
                  "Confiança": f"{r['confidence']:.0%}", "Origem": demo_badge(r["is_demo"])}
                 for i, r in enumerate(rows)],
                key="hunt_table",
            )
            for row in rows:
                with st.expander(f"{row['name']} — score {row['score']} ({row['classification_label']})"):
                    st.markdown(f"**Fonte dos dados:** {row.get('sources') or 'não informada'}")
                    table(
                        [{"Critério": e["criterio"], "Peso": e["peso"], "Nota": e["nota"],
                          "Contribuição": e["contribuicao"], "Fonte": e["fonte"],
                          "Observação": e["observacao"]} for e in row["explanation"]],
                        key=f"exp_{row['name'][:12]}",
                    )
                    if row["missing"]:
                        notice("warn", "Sem dado: " + ", ".join(row["missing"]))
                    for warning in row["warnings"]:
                        notice("warn", warning)
            st.divider()
            with st.expander("Achados, lacunas e próximas ações"):
                render_result(result)

    st.divider()
    st.subheader("Base de candidatos")
    opportunities = o.repo.find("opportunities", {}, order_by="-created_at", limit=200)
    table(
        [{"Produto": row["name"], "Canal": row.get("marketplace"),
          "Preço": money_brl(row.get("price_found")), "Custo": money_brl(row.get("cost_estimate")),
          "Fonte": row.get("source"), "Origem": demo_badge(row.get("is_demo"))}
         for row in opportunities],
        key="opp_table",
    )
    csv_import_widget("opportunities", "oportunidades")
