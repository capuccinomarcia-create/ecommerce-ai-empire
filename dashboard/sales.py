"""Vendas registradas e importação."""

from __future__ import annotations

import streamlit as st

from dashboard.common import csv_import_widget, money_brl, orch, page_header, table


def render() -> None:
    o = orch()
    page_header("Vendas", "Registros usados no relatório semanal e na análise de canais.")

    sales = o.repo.find("sales", {}, order_by="-sold_at", limit=500)
    total_revenue = sum(float(s.get("total") or 0) for s in sales)
    total_fees = sum(float(s.get("fees") or 0) + float(s.get("taxes") or 0) for s in sales)
    table(
        [{"Data": (s.get("sold_at") or "")[:10], "Canal": s.get("marketplace") or "-",
          "Qtd": s.get("quantity"), "Preço un.": money_brl(s.get("unit_price")),
          "Taxas": money_brl(s.get("fees")), "Total": money_brl(s.get("total"))} for s in sales],
        key="sales_table",
    )
    st.caption(f"{len(sales)} vendas · receita {money_brl(total_revenue)} · "
               f"taxas {money_brl(total_fees)}")
    st.divider()
    csv_import_widget("sales", "vendas")
    if st.button("Exportar vendas em CSV"):
        from integrations.generic_csv import export_csv
        from pathlib import Path

        path = export_csv(sales, Path("exports") / "vendas.csv")
        st.download_button("Baixar arquivo", path.read_bytes(), file_name="vendas.csv",
                           mime="text/csv")
