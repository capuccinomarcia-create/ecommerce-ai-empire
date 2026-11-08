"""Página 3 - Central de agentes."""

from __future__ import annotations

import streamlit as st

from dashboard.common import notice, orch, page_header, render_result, run_agent, table

# ação principal de cada agente, para execução manual pelo painel
AGENT_ACTIONS = {
    "ceo": ("consolidate", "Consolidar resultados", {"mode": "consolidate"}),
    "product_hunter": ("research", "Pesquisar produtos", {"limit": 10, "top": 5}),
    "market_analyst": ("competitor_scan", "Analisar concorrência", {}),
    "marketplace_manager": ("audit", "Auditar anúncios", {}),
    "financial": ("evaluate", "Calcular margem", {}),
    "marketing": ("plan", "Criar campanha", {}),
    "video_creator": ("scripts", "Escrever roteiros", {}),
    "seo": ("audit", "Otimizar SEO", {}),
    "supplier_hunter": ("compare", "Comparar fornecedores", {}),
    "customer": ("faq", "Preparar FAQ", {}),
    "automation": ("overview", "Verificar automações", {}),
    "content_intelligence": ("plan", "Planejar conteúdo", {"days": 14}),
}


def render() -> None:
    o = orch()
    page_header("Central de agentes", "12 especialistas com responsabilidades e ferramentas distintas.")

    agents = o.repo.find("agents", {}, order_by="name")
    counts: dict[str, int] = {}
    for task in o.repo.find("tasks", {}, limit=500):
        counts[task["agent"]] = counts.get(task["agent"], 0) + 1

    table(
        [{"Agente": a["role"], "Chave": a["name"], "Status": a["status"],
          "Ferramentas": len((o.agents.get(a["name"]) or type("x", (), {"tools": []})).tools),
          "Tarefas": counts.get(a["name"], 0),
          "Capacidades": ", ".join((a.get("capabilities") or [])[:4])} for a in agents],
        key="agents_table",
    )

    st.divider()
    st.subheader("Executar um agente manualmente")
    keys = [a["name"] for a in agents if a["name"] in AGENT_ACTIONS]
    labels = {a["name"]: a["role"] for a in agents}
    selected = st.selectbox("Agente", keys, format_func=lambda k: labels.get(k, k))
    task_type, title, payload = AGENT_ACTIONS[selected]
    st.caption(f"Tarefa: {task_type} · {title}")

    if selected == "product_hunter":
        payload = {
            "limit": st.number_input("Candidatos a analisar", 3, 50, 10),
            "top": st.number_input("Quantos priorizar", 1, 10, 5),
        }
    if selected == "content_intelligence":
        payload = {"days": st.slider("Dias de calendário", 7, 30, 14)}

    if st.button("Executar agente", type="primary"):
        with st.spinner(f"Executando {labels.get(selected, selected)}..."):
            result = run_agent(selected, task_type, title, payload)
        st.session_state["agent_result"] = result

    if st.session_state.get("agent_result"):
        render_result(st.session_state["agent_result"])

    st.divider()
    st.subheader("Histórico recente")
    table(
        [{"Quando": t["created_at"][:19], "Agente": t["agent"], "Tarefa": t["title"][:50],
          "Status": t["status"], "Tentativas": t["attempts"]}
         for t in o.tasks.list_tasks(limit=20)],
        key="agents_history",
    )
    if o.tasks.pending_approvals_count():
        notice("warn", f"{o.tasks.pending_approvals_count()} aprovação(ões) aguardando você "
                        "na página Configurações > Aprovações.")
