"""Catálogo de produtos (CRUD real)."""

from __future__ import annotations

import streamlit as st

from dashboard.common import csv_import_widget, demo_badge, money_brl, notice, orch, page_header, table


def render() -> None:
    o = orch()
    page_header("Catálogo", "Produtos usados em todos os cálculos de margem e anúncios.")

    products = o.repo.find("products", {}, order_by="-updated_at", limit=500)
    table(
        [{"Produto": p["name"], "SKU": p.get("sku") or "-", "Categoria": p.get("category") or "-",
          "Custo": money_brl(p.get("purchase_price")), "Venda": money_brl(p.get("sale_price")),
          "Canal": p.get("marketplace") or "-", "Status": p.get("status"),
          "Origem": demo_badge(p.get("is_demo"))} for p in products],
        key="catalog_table",
    )

    st.divider()
    tab_new, tab_import, tab_edit = st.tabs(["Novo produto", "Importar CSV", "Editar / excluir"])

    with tab_new:
        with st.form("new_product"):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("Nome *")
                sku = st.text_input("SKU")
                category = st.text_input("Categoria")
                marketplace = st.selectbox("Canal principal",
                                           ["shopee", "mercadolivre", "tiktok_shop",
                                            "loja_propria", "woocommerce", "instagram"])
            with col2:
                purchase = st.number_input("Preço de compra (R$)", 0.0, step=1.0)
                extra = st.number_input("Custo extra por unidade (R$)", 0.0, step=0.5)
                sale = st.number_input("Preço de venda (R$)", 0.0, step=1.0)
                description = st.text_area("Descrição", height=80)
            if st.form_submit_button("Salvar produto", type="primary"):
                if not name.strip():
                    st.error("Informe o nome do produto.")
                else:
                    o.repo.insert("products", {
                        "name": name.strip(), "sku": sku, "category": category,
                        "description": description, "purchase_price": purchase,
                        "extra_cost": extra, "sale_price": sale, "marketplace": marketplace,
                        "status": "ativo", "source": "manual", "is_demo": False,
                    })
                    o.permissions.audit("proprietario", "product_create", "product", "",
                                        {"name": name})
                    notice("ok", "Produto cadastrado.")
                    st.rerun()

    with tab_import:
        csv_import_widget("products", "produtos")

    with tab_edit:
        if not products:
            st.caption("Nenhum produto cadastrado.")
        else:
            options = {f"{p['name']} ({p.get('sku') or p['id'][:6]})": p for p in products}
            selected = st.selectbox("Produto", list(options), key="edit_product")
            product = options[selected]
            with st.form("edit_product_form"):
                new_sale = st.number_input("Preço de venda (R$)", 0.0,
                                           value=float(product.get("sale_price") or 0), step=1.0)
                new_purchase = st.number_input("Preço de compra (R$)", 0.0,
                                               value=float(product.get("purchase_price") or 0), step=1.0)
                new_status = st.selectbox("Status", ["ativo", "pausado", "arquivado"],
                                          index=["ativo", "pausado", "arquivado"].index(
                                              product.get("status") or "ativo"))
                if st.form_submit_button("Salvar alterações"):
                    price_changed = abs(new_sale - float(product.get("sale_price") or 0)) > 0.001
                    if price_changed and not o.permissions.is_approved("price_change", product["id"]):
                        approval = o.permissions.request(
                            "price_change",
                            {"from": product.get("sale_price"), "to": new_sale},
                            resource_type="product", resource_id=product["id"], agent="painel",
                        )
                        notice("warn",
                               "Alteração de preço é ação de risco: solicitação de aprovação "
                               f"criada ({approval['id']}). Aprove em Configurações > Aprovações.")
                    else:
                        o.repo.update("products", product["id"], {
                            "sale_price": new_sale, "purchase_price": new_purchase,
                            "status": new_status})
                        o.permissions.audit("proprietario", "product_update", "product",
                                            product["id"], {"sale_price": new_sale})
                        notice("ok", "Produto atualizado.")
                        st.rerun()
            if st.button("Excluir produto", type="secondary"):
                if o.permissions.require_approval:
                    approval = o.permissions.request(
                        "delete_product", {"name": product["name"]},
                        resource_type="product", resource_id=product["id"], agent="painel",
                    )
                    notice("warn", f"Exclusão exige aprovação ({approval['id']}). "
                                   "Aprove em Configurações > Aprovações.")
                else:
                    o.repo.delete("products", product["id"])
                    notice("ok", "Produto excluído.")
                    st.rerun()
