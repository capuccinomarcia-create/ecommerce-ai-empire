"""Entrada do painel Streamlit.

Execução:
    streamlit run dashboard/streamlit_app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dashboard import (agents, automations, bot_page, ceo_chat, competitors,  # noqa: E402
                       customers, financial, home, instagram, marketing,
                       mercadolivre,
                       own_store, product_research, products, reports, sales,
                       settings, shopee, suppliers, tiktok, video_creator)
from dashboard.common import login_gate, notice, orch, page_header  # noqa: E402

st.set_page_config(
    page_title="E-COMMERCE AI EMPIRE",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded",
)

PAGES = [
    ("Dashboard", home.render),
    ("CEO AI", ceo_chat.render),
    ("Central de agentes", agents.render),
    ("Pesquisa de produtos", product_research.render),
    ("Concorrentes", competitors.render),
    ("Calculadora financeira", financial.render),
    ("Shopee", shopee.render),
    ("Mercado Livre", mercadolivre.render),
    ("TikTok Shop", tiktok.render),
    ("Instagram", instagram.render),
    ("Loja própria", own_store.render),
    ("Marketing", marketing.render),
    ("Criador de vídeos", video_creator.render),
    ("Fornecedores", suppliers.render),
    ("Clientes", customers.render),
    ("Relatórios", reports.render),
    ("Automações", automations.render),
    ("Bot no celular", bot_page.render),
    ("Configurações", settings.render),
    ("Catálogo", products.render),
    ("Vendas", sales.render),
]

if "page" not in st.session_state:
    st.session_state["page"] = PAGES[0][0]

with st.sidebar:
    st.markdown("### E-COMMERCE AI EMPIRE")
    o = orch()
    st.caption(f"{o.settings.timezone} · {o.settings.currency} · banco {getattr(o.repo,'backend','')}")
    st.session_state["page"] = st.radio(
        "Navegação", [label for label, _ in PAGES],
        index=[label for label, _ in PAGES].index(st.session_state["page"]),
        label_visibility="collapsed",
    )
    st.divider()
    pending = o.tasks.pending_approvals_count()
    if pending:
        notice("warn", f"{pending} aprovação(ões) pendente(s)")
    if not o.ai.has_remote_provider:
        st.caption("IA em modo offline (sem chave). Cálculos locais.")
    if st.button("Atualizar dados", width="stretch"):
        st.rerun()

if login_gate():
    renderer = dict(PAGES)[st.session_state["page"]]
    try:
        renderer()
    except Exception as exc:  # noqa: BLE001 - o painel nunca deve "sumir" com erro
        page_header(st.session_state["page"], "Falha ao renderizar")
        st.error(f"{type(exc).__name__}: {exc}")
        st.exception(exc)
else:
    st.stop()
