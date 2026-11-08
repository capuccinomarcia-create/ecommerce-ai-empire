"""Páginas de canal (Shopee, Mercado Livre, TikTok Shop, Instagram, loja própria)."""

from __future__ import annotations

import streamlit as st

from dashboard.common import (csv_import_widget, demo_badge, money_brl, notice, orch,
                              page_header, render_result, run_agent, table)
from core.utils import now_iso
from integrations import APIError, NotConfigured, build_connector, label_for

CHANNEL_HELP = {
    "shopee": "Open Platform v2: partner_id, partner_key e shop_id. "
              "App gratuito em open.shopee.com.",
    "mercadolivre": "OAuth 2.0: ML_CLIENT_ID, ML_CLIENT_SECRET e tokens. "
                    "App gratuito em developers.mercadolivre.com.br.",
    "tiktok_shop": "TikTok Shop Partner Center: app_key, app_secret, access_token e shop_cipher.",
    "instagram": "Meta Graph API: token de página e IG business id com permissões de "
                 "leitura e publicação.",
    "woocommerce": "REST API v3 com consumer key/secret. Serve também para a loja própria.",
}


def render_channel(channel: str) -> None:
    o = orch()
    connector = build_connector(channel, o.settings, o.repo)
    status = connector.status()
    page_header(label_for(channel), "Integração oficial quando configurada; CSV sempre disponível.")

    if status.connected:
        notice("ok", "Conectado. Leituras usam a API oficial; publicações exigem aprovação.")
    else:
        notice("warn", "**Não conectado.** Faltam: " + ", ".join(status.missing))
        st.caption(CHANNEL_HELP.get(channel, ""))
        st.markdown(f"Documentação: {status.docs_url}")

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Testar conexão", width="stretch"):
            if not status.connected:
                notice("bad", "Sem credenciais: nada foi simulado. Configure o .env.")
            else:
                try:
                    items = connector.fetch_products(limit=10)
                    st.success(f"{len(items)} itens lidos da API.")
                    table(items, key=f"api_{channel}")
                except (NotConfigured, APIError) as exc:
                    st.error(f"Falha real da API: {exc}")
    with col2:
        if st.button("Gerar rascunho de anúncio", width="stretch"):
            products = o.repo.find("products", {"marketplace": channel}, limit=1) or \
                       o.repo.find("products", {}, limit=1)
            if not products:
                notice("warn", "Cadastre um produto antes de gerar o rascunho.")
            else:
                st.session_state[f"draft_{channel}"] = run_agent(
                    "marketplace_manager", "prepare", f"Rascunho {label_for(channel)}",
                    {"product_id": products[0]["id"], "channel": channel,
                     "request_approvals": True},
                )
    with col3:
        if st.button("Auditar anúncios do canal", width="stretch"):
            st.session_state[f"audit_{channel}"] = run_agent(
                "marketplace_manager", "audit", f"Auditar {label_for(channel)}",
                {"marketplace": channel},
            )

    for key in (f"draft_{channel}", f"audit_{channel}"):
        if st.session_state.get(key):
            render_result(st.session_state[key])
            result_data = st.session_state[key].get("result", {}).get("data", {})
            if result_data.get("draft"):
                st.json(result_data["draft"].get("payload_preview", result_data["draft"]))

    st.divider()
    st.subheader("Prazo desta plataforma")
    st.caption(
        "É esse prazo que decide se o fornecedor entrega sem derrubar o anúncio. "
        "O sistema não chuta o número: informe a política vigente do canal."
    )
    regra = o.repo.find_one("marketplaces", {"slug": channel}) or {}
    with st.form(f"sla_form_{channel}"):
        c1, c2, c3 = st.columns(3)
        handling = c1.number_input("Dias úteis para despachar", 0, 60,
                                   int(regra.get("handling_days") or 0), key=f"hd_{channel}")
        delivery = c2.number_input("Dias úteis de entrega ao cliente", 0, 120,
                                   int(regra.get("delivery_days") or 0), key=f"dd_{channel}")
        fonte = c3.text_input("Fonte do prazo", regra.get("sla_source") or "",
                              key=f"src_{channel}")
        if st.form_submit_button("Salvar prazo", type="primary"):
            dados = {
                "handling_days": int(handling),
                "delivery_days": int(delivery),
                "sla_source": fonte or "não informado pelo proprietário",
                "updated_at": now_iso(),
            }
            if regra.get("id"):
                o.repo.update("marketplaces", regra["id"], dados)
            else:
                o.repo.insert("marketplaces", {"slug": channel, "name": label_for(channel),
                                               "commission_pct": 0.0, "fixed_fee": 0.0,
                                               "notes": "Criado ao salvar o prazo.",
                                               "source": "proprietário", **dados})
            st.success("Prazo salvo. A análise de fornecedores já usa esse número.")
            st.rerun()
    if int(regra.get("handling_days") or 0) == 0:
        notice("warn", "**Prazo não informado.** Sem ele, o sistema não afirma que "
                       "um fornecedor entrega a tempo.")

    st.divider()
    st.subheader("Anúncios neste canal")
    listings = o.repo.find("listings", {"marketplace": channel}, order_by="-updated_at", limit=100)
    table(
        [{"Título": l.get("title"), "Preço": money_brl(l.get("price")),
          "Status": l.get("status"), "Score": l.get("score"),
          "Origem": demo_badge(l.get("is_demo"))} for l in listings],
        key=f"listings_{channel}",
    )

    st.divider()
    csv_import_widget("products", f"produtos para {label_for(channel)}")
    notice("info", "Importação e exportação em CSV funcionam sem qualquer credencial.")
