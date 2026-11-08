"""Página 17 - Automações."""

from __future__ import annotations

import streamlit as st

from core.autonomy import AutonomousSuperAgent
from dashboard.common import notice, orch, page_header, render_result, run_agent, table


def render() -> None:
    o = orch()
    page_header("Automações", "Rotinas diárias e semanais, execuções recentes e falhas.")


    # ---------------------------------------------------- super agente autônomo --
    st.subheader("Super agente autônomo")
    st.caption("Ele acorda sozinho, roda o plano do CEO, grava relatório e para "
               "quando erra demais. Comprar, pagar e publicar continuam com você.")
    agente = AutonomousSuperAgent(orchestrator=o)
    estado = agente.status()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ciclos hoje", f"{estado['cycles_today']}/{estado['limites']['ciclos_por_dia']}")
    c2.metric("Ciclos no total", estado["cycles_total"])
    c3.metric("Aprovações pendentes", estado["aprovacoes_pendentes"])
    c4.metric("Último status", estado.get("last_status") or "nunca rodou")
    st.caption(f"Próximo objetivo: {estado['proximo_objetivo']}")
    if estado["pode_rodar_agora"]:
        notice("ok", "Pronto para rodar.")
    else:
        notice("warn", f"Não vai rodar agora: {estado['motivo']}")
    if estado.get("last_summary"):
        with st.expander("Resumo do último ciclo"):
            st.write(estado["last_summary"])

    b1, b2, b3, b4 = st.columns(4)
    if b1.button("Rodar um ciclo agora", type="primary", width="stretch"):
        with st.spinner("Executando o plano do CEO..."):
            ciclo = agente.run_cycle(force=True)
        if ciclo.get("ok"):
            st.success(f"Ciclo concluído em {ciclo.get('duration_s')}s.")
            st.write(ciclo.get("resumo", "")[:1500])
        elif ciclo.get("skipped"):
            notice("warn", f"Não rodou: {ciclo.get('reason')}")
        else:
            st.error(f"Falhou: {ciclo.get('error')}")
        st.rerun()
    rotulo = "Desativar" if estado["enabled"] else "Ativar autonomia"
    if b2.button(rotulo, width="stretch"):
        agente.enable(not estado["enabled"])
        st.rerun()
    if b3.button("Pausar", width="stretch", disabled=estado["paused"]):
        agente.pause("pausado pelo painel")
        st.rerun()
    if b4.button("Retomar", width="stretch", disabled=not estado["paused"]):
        agente.resume()
        st.rerun()

    notice("info", "Para rodar 24 horas sem o painel aberto, use no computador ou servidor: "
                   "`python -m core.autonomy --loop`. Sem esse processo, o agente só roda "
                   "no botão acima.")

    st.divider()
    if st.button("Cadastrar rotinas padrão", type="primary"):
        st.session_state["auto"] = run_agent("automation", "register_defaults",
                                             "Cadastrar rotinas padrão", {})
    if st.button("Verificar estado das automações"):
        st.session_state["auto"] = run_agent("automation", "overview",
                                             "Verificar rotinas e execuções", {})
    if st.button("Executar rotinas vencidas agora"):
        from core.scheduler import Agendador

        resultados = Agendador(o.repo).tick()
        if not resultados:
            notice("warn", "Nada vencido neste minuto.")
        for item in resultados:
            st.success(f"{item['name']}: {item['summary']} ({item['duration_s']}s)")
        st.rerun()

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
