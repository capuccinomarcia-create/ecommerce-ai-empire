"""Página 18 - Configurações."""

from __future__ import annotations

import streamlit as st

from core.auth import AuthService
from dashboard.common import kpis, notice, orch, page_header, table
from integrations import connector_statuses


def render() -> None:
    o = orch()
    page_header("Configurações", "Taxas, credenciais, IA, aprovações, dados DEMO e segurança.")

    tabs = st.tabs(["Marketplaces", "Conexões", "IA", "Aprovações", "Auditoria",
                    "Dados DEMO", "Segurança"])

    # ---------------------------------------------------------------- taxas --
    with tabs[0]:
        st.markdown("**Comissão e taxa fixa por canal.** Nada é estimado: se você não informar, "
                    "o cálculo usa 0% e o relatório avisa.")
        marketplaces = o.repo.find("marketplaces", {}, order_by="name")
        for row in marketplaces:
            with st.form(f"mp_{row['slug']}"):
                col1, col2, col3 = st.columns([2, 1, 1])
                with col1:
                    st.markdown(f"**{row['name']}**")
                    st.caption(f"fonte atual: {row.get('source')}")
                with col2:
                    commission = st.number_input("Comissão %", 0.0, 100.0,
                                                 value=float(row.get("commission_pct") or 0),
                                                 key=f"c_{row['slug']}")
                with col3:
                    fixed = st.number_input("Taxa fixa R$", 0.0,
                                            value=float(row.get("fixed_fee") or 0),
                                            key=f"f_{row['slug']}")
                source = st.text_input("Fonte do valor",
                                       value=row.get("source") or "informado pelo proprietário",
                                       key=f"s_{row['slug']}")
                if st.form_submit_button("Salvar"):
                    o.repo.update("marketplaces", row["id"], {
                        "commission_pct": commission, "fixed_fee": fixed, "source": source})
                    o.permissions.audit("proprietario", "marketplace_rule_update",
                                        "marketplace", row["slug"],
                                        {"commission_pct": commission, "fixed_fee": fixed})
                    notice("ok", f"Regra de {row['name']} atualizada.")
                    st.rerun()

    # ------------------------------------------------------------ conexões --
    with tabs[1]:
        statuses = connector_statuses(o.settings, o.repo)
        table([{"Canal": s["label"], "Status": s["status"], "Modo": s["mode"],
                "Faltando": ", ".join(s["missing"]) or "-", "Docs": s["docs_url"]}
               for s in statuses], key="conn_table")
        notice("info", "As credenciais ficam no arquivo .env (nunca no repositório). "
                       "Enquanto não existirem, use CSV.")

    # ------------------------------------------------------------------- IA --
    with tabs[2]:
        ai_status = o.ai.status()
        table(ai_status, key="ai_table")
        usage = o.ai.usage_summary()
        kpis([("Chamadas", usage["calls"], "registradas"),
              ("Tokens in", usage["tokens_in"], ""),
              ("Tokens out", usage["tokens_out"], ""),
              ("Custo USD", usage["cost_usd"], "só com preço configurado")])
        st.caption("Sem chave configurada o sistema opera em modo offline: os cálculos continuam "
                   "válidos e a redação é local. Limite por tarefa: "
                   f"{o.settings.ai_max_calls_per_task} chamadas.")

    # ----------------------------------------------------------- aprovações --
    with tabs[3]:
        pending = o.permissions.pending()
        if not pending:
            st.caption("Nenhuma aprovação pendente.")
        for approval in pending:
            with st.container(border=True):
                st.markdown(f"**{approval['action']}** · risco {approval['risk_level']} · "
                            f"agente {approval.get('requested_by_agent') or '-'}")
                st.json(approval.get("payload") or {})
                col1, col2, col3 = st.columns(3)
                if col1.button("Aprovar", key=f"ap_{approval['id']}"):
                    o.permissions.approve(approval["id"], "proprietario")
                    notice("ok", "Aprovação registrada.")
                    st.rerun()
                if col2.button("Rejeitar", key=f"rj_{approval['id']}"):
                    o.permissions.reject(approval["id"], "proprietario")
                    notice("warn", "Solicitação rejeitada.")
                    st.rerun()
                if col3.button("Cancelar", key=f"cn_{approval['id']}"):
                    o.permissions.cancel(approval["id"], "proprietario")
                    notice("warn", "Solicitação cancelada.")
                    st.rerun()
        st.subheader("Histórico de aprovações")
        table([{"Quando": a["created_at"][:19], "Ação": a["action"], "Status": a["status"],
                "Quem decidiu": a.get("decided_by") or "-", "Quando decidiu":
                (a.get("decided_at") or "")[:19]} for a in o.permissions.history(50)],
              key="approval_history")

    # ------------------------------------------------------------ auditoria --
    with tabs[4]:
        table([{"Quando": l["created_at"][:19], "Ator": l["actor"], "Ação": l["action"],
                "Recurso": f"{l.get('resource_type') or ''}:{l.get('resource_id') or ''}"}
               for l in o.permissions.audit_trail(100)], key="audit_table")

    # ----------------------------------------------------------------- demo --
    with tabs[5]:
        products = o.repo.find("products", {}, limit=500)
        demo_count = sum(1 for p in products if p.get("is_demo"))
        real_count = len(products) - demo_count
        kpis([("Produtos DEMO", demo_count, "fictícios"), ("Produtos reais", real_count, "")])
        st.caption("Dados DEMO nunca aparecem escondidos: cada linha do painel leva o selo DEMO.")
        col1, col2 = st.columns(2)
        if col1.button("Carregar DEMO", width="stretch"):
            from scripts.seed_demo import seed_demo

            report = seed_demo(o.repo)
            notice("ok", ", ".join(f"{k}={v.get('imported',0)}" for k, v in report.items()))
            st.rerun()
        if col2.button("Remover somente DEMO", width="stretch"):
            from scripts.seed_demo import clear_demo

            removed = clear_demo(o.repo)
            notice("warn", f"{removed} registros DEMO removidos. Dados reais preservados.")
            st.rerun()

    # ------------------------------------------------------------ segurança --
    with tabs[6]:
        st.markdown(f"**Banco:** `{getattr(o.repo, 'backend', 'desconhecido')}`")
        st.markdown(f"**Fuso:** `{o.settings.timezone}` · **Moeda:** `{o.settings.currency}`")
        auth = AuthService(o.repo)
        st.markdown(f"**Usuários cadastrados:** {o.repo.count('users')}")
        if not auth.has_users():
            with st.form("setup_owner"):
                email = st.text_input("E-mail do proprietário")
                password = st.text_input("Senha (mín. 8 caracteres)", type="password")
                if st.form_submit_button("Criar usuário"):
                    try:
                        auth.create_user(email, password, role="owner")
                        notice("ok", "Usuário criado com senha em hash scrypt.")
                    except ValueError as exc:
                        st.error(str(exc))
        st.caption("Ative APP_REQUIRE_LOGIN=1 no .env para exigir login no painel. "
                   "Nenhuma senha ou token é gravada em texto puro no código ou no repositório.")
