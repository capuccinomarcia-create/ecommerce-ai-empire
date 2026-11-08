"""Página 17 - Automações."""

from __future__ import annotations

import streamlit as st

from dashboard.common import notice, orch, page_header, render_result, run_agent, table


def render() -> None:
    o = orch()
    page_header("Automações", "Rotinas diárias e semanais, execuções recentes e falhas.")

    if st.button("Cadastrar rotinas padrão", type="primary"):
        st.session_state["auto"] = run_agent("automation", "register_defaults",
                                             "Cadastrar rotinas padrão", {})
    if st.button("Verificar estado das automações"):
        st.session_state["auto"] = run_agent("automation", "overview",
                                             "Verificar rotinas e execuções", {})

    automations = o.repo.find("automations", {}, order_by="name")
    for automation in automations:
        with st.container(border=True):
            col1, col2, col3 = st.columns([3, 2, 1])
            with col1:
                st.markdown(f"**{automation['name']}**")
                st.caption((automation.get("config") or {}).get("description", ""))
            with col2:
                st.caption(f"cron: `{automation.get('schedule_cron')}` · "
                           f"job: `{automation.get('job')}`")
            with col3:
                enabled = st.toggle("ativa", value=bool(automation.get("enabled")),
                                    key=f"t_{automation['id']}")
                if enabled != bool(automation.get("enabled")):
                    o.repo.update("automations", automation["id"], {"enabled": enabled})
                    o.permissions.audit("proprietario", "automation_toggle", "automation",
                                        automation["id"], {"enabled": enabled})
                    st.rerun()

    if st.session_state.get("auto"):
        render_result(st.session_state["auto"])

    st.divider()
    st.subheader("Histórico de tarefas")
    tasks = o.repo.find("tasks", {}, order_by="-created_at", limit=40)
    table([{"Quando": t["created_at"][:19], "Agente": t["agent"], "Tarefa": t["title"][:50],
            "Status": t["status"], "Tentativas": t["attempts"],
            "Erro": (t.get("error") or "")[:50]} for t in tasks], key="auto_tasks")

    st.subheader("Cancelar uma tarefa pendente")
    pending = [t for t in tasks if t["status"] in {"pendente", "em_execucao", "aguardando_aprovacao"}]
    if not pending:
        st.caption("Nenhuma tarefa pendente.")
    else:
        options = {f"{t['title'][:50]} ({t['status']})": t for t in pending}
        chosen = st.selectbox("Tarefa", list(options))
        if st.button("Cancelar tarefa"):
            o.tasks.cancel(options[chosen]["id"], "cancelada pelo proprietário no painel")
            o.permissions.audit("proprietario", "task_cancel", "task",
                                options[chosen]["id"], {})
            notice("ok", "Tarefa cancelada.")
            st.rerun()

    notice("info", "Para rodar sem servidor: ative os workflows em .github/workflows "
                   "(GitHub Actions, dentro das cotas gratuitas).")
