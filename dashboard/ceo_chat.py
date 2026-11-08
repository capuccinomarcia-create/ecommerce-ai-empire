"""Página 2 - CEO AI: chat principal que dispara o orquestrador."""

from __future__ import annotations

import streamlit as st

from dashboard.common import demo_badge, notice, orch, page_header, table

EXAMPLES = [
    "CEO, encontre 10 produtos com potencial de venda na Shopee, Mercado Livre e TikTok Shop. "
    "Analise concorrência, preços, custos, tendências e lucro. Depois me apresente as cinco "
    "melhores oportunidades.",
    "Analise meus anúncios e identifique quais precisam de melhorias para conseguir mais "
    "visualizações e vendas sem aumentar meus gastos com anúncios.",
    "Compare fornecedores e diga qual tem o melhor custo total de aquisição.",
    "Monte o calendário de conteúdo da próxima semana com roteiros de vídeo.",
]


def render() -> None:
    o = orch()
    page_header(
        "CEO AI",
        "Escreva o objetivo. O CEO distribui a tarefa entre os especialistas e devolve o relatório.",
    )

    if "ceo_history" not in st.session_state:
        st.session_state["ceo_history"] = []

    with st.expander("Exemplos de comando", expanded=not st.session_state["ceo_history"]):
        for example in EXAMPLES:
            if st.button(example[:90] + "...", key=f"ex_{hash(example)}", width="stretch"):
                st.session_state["ceo_prompt"] = example

    command = st.text_area(
        "Comando para o CEO AI",
        value=st.session_state.get("ceo_prompt", ""),
        height=120,
        placeholder="Ex.: encontre produtos com margem acima de 20% para vender na Shopee",
    )

    col_run, col_clear = st.columns([1, 3])
    with col_run:
        run = st.button("Executar", type="primary", width="stretch")
    with col_clear:
        if st.button("Limpar conversa"):
            st.session_state["ceo_history"] = []
            st.rerun()

    if run and command.strip():
        with st.spinner("Distribuindo tarefas entre os agentes..."):
            outcome = o.handle(command)
        st.session_state["ceo_history"].insert(0, outcome)

    if not st.session_state["ceo_history"]:
        st.info("Nenhuma execução ainda. Rode um comando para ver o plano, os agentes e o relatório.")
        return

    outcome = st.session_state["ceo_history"][0]
    if not outcome.get("ok"):
        notice("bad", outcome.get("error", "falha na execução"))
        return

    intent = outcome["intent"]
    notice(
        "info",
        f"<b>Intenção:</b> {intent['label']} (confiança {intent['confidence']:.0%}) · "
        f"{len(outcome['steps'])} etapas · {outcome['duration_s']}s · "
        f"dados DEMO: {demo_badge(outcome['demo_mode'])}",
    )

    st.subheader("Plano executado")
    table(
        [{"Etapa": s["title"], "Agente": s["agent"], "Status": s["status"],
          "Resumo": (s.get("summary") or "")[:120]} for s in outcome["steps"]],
        key="ceo_steps",
    )

    if outcome.get("consistency_issues"):
        with st.expander(f"Validação de consistência ({len(outcome['consistency_issues'])})"):
            for issue in outcome["consistency_issues"]:
                st.markdown(f"- {issue}")

    st.subheader("Relatório consolidado")
    st.markdown(outcome["report"])

    col_a, col_b = st.columns(2)
    with col_a:
        st.download_button(
            "Baixar relatório (.md)", outcome["report"],
            file_name=f"relatorio_ceo_{outcome['run_id']}.md", mime="text/markdown",
            width="stretch",
        )
    with col_b:
        if st.button("Ver tarefas geradas", width="stretch"):
            st.session_state["_show_tasks"] = outcome["root_task_id"]
    if st.session_state.get("_show_tasks"):
        root_id = st.session_state["_show_tasks"]
        children = o.repo.find("tasks", {"parent_id": root_id}, order_by="created_at")
        table([{"Tarefa": t["title"], "Agente": t["agent"], "Status": t["status"],
                "Tentativas": t["attempts"], "Erro": (t.get("error") or "")[:60]} for t in children],
              key="ceo_children")

    if len(st.session_state["ceo_history"]) > 1:
        with st.expander(f"Execuções anteriores ({len(st.session_state['ceo_history']) - 1})"):
            for past in st.session_state["ceo_history"][1:]:
                st.markdown(f"- {past['command'][:100]} · {past['intent']['label']}")
