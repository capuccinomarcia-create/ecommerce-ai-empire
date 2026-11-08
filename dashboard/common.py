"""Componentes e utilidades compartilhadas do painel."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from agents.base import AgentContext
from api.deps import get_orchestrator
from core.auth import AuthService
from core.utils import money, pct
from integrations.generic_csv import import_csv, template_csv

C = {
    "bg": "#0f1115",
    "panel": "#161a22",
    "line": "#252b36",
    "text": "#e8eaf0",
    "muted": "#9aa3b2",
    "accent": "#4f8cff",
    "ok": "#2fbf71",
    "warn": "#f5a524",
    "bad": "#f2555a",
}


def orch():
    return get_orchestrator()


def page_header(title: str, subtitle: str = "") -> None:
    st.markdown(
        f"<div style='margin-bottom:18px'><h2 style='margin:0'>{title}</h2>"
        f"<p style='color:{C['muted']};margin:4px 0 0'>{subtitle}</p></div>",
        unsafe_allow_html=True,
    )


def demo_badge(is_demo: bool) -> str:
    return "DEMO" if is_demo else "REAL"


def kpis(items: list[tuple[str, Any, str]]) -> None:
    columns = st.columns(len(items))
    for column, (label, value, hint) in zip(columns, items):
        with column:
            st.markdown(
                f"<div style='background:{C['panel']};border:1px solid {C['line']};"
                "border-radius:10px;padding:14px 16px'>"
                f"<div style='font-size:12px;letter-spacing:.06em;color:{C['muted']};"
                f"text-transform:uppercase'>{label}</div>"
                f"<div style='font-size:26px;font-weight:600;margin-top:6px'>{value}</div>"
                f"<div style='font-size:12px;color:{C['muted']};margin-top:2px'>{hint}</div>"
                "</div>",
                unsafe_allow_html=True,
            )


def table(rows: list[dict], columns: list[str] | None = None, key: str = "") -> None:
    if not rows:
        st.caption("Sem registros.")
        return
    frame = pd.DataFrame(rows)
    if columns:
        frame = frame[[c for c in columns if c in frame.columns]]
    st.dataframe(frame, width="stretch", hide_index=True, key=key or None)


def notice(kind: str, text: str) -> None:
    color = {"ok": C["ok"], "warn": C["warn"], "bad": C["bad"], "info": C["accent"]}[kind]
    st.markdown(
        f"<div style='border-left:3px solid {color};background:{C['panel']};"
        f"padding:10px 14px;border-radius:6px;margin:6px 0;color:{C['text']};"
        f"font-size:14px'>{text}</div>",
        unsafe_allow_html=True,
    )


def money_brl(value: float | None) -> str:
    return money(float(value or 0))


def pct_br(value: float | None) -> str:
    return pct(float(value or 0))


# --------------------------------------------------------------------- execução --
def run_agent(agent_key: str, task_type: str, title: str, payload: dict) -> dict[str, Any]:
    """Executa um agente de verdade, registrando a tarefa no histórico."""
    o = orch()
    task = o.tasks.create(agent_key, task_type, title, payload, requested_by="painel")
    o.tasks.start(task["id"])
    context = AgentContext(
        repo=o.repo, settings=o.settings, ai=o.ai, memory=o.memory,
        tasks=o.tasks, permissions=o.permissions, task=task, shared={},
    )
    try:
        result = o.agents[agent_key].run(context)
        o.tasks.complete(task["id"], result.to_dict())
        return {"ok": True, "result": result.to_dict(), "task_id": task["id"]}
    except Exception as exc:  # noqa: BLE001 - o painel mostra o erro, não esconde
        o.tasks.fail(task["id"], f"{type(exc).__name__}: {exc}")
        return {"ok": False, "error": str(exc), "task_id": task["id"]}


def render_result(result: dict[str, Any]) -> None:
    if not result.get("ok"):
        notice("bad", f"Falha na execução: {result.get('error')}")
        return
    data = result["result"]
    notice("ok", f"<b>{data.get('summary','')}</b>")
    if data.get("findings"):
        st.markdown("**Achados**")
        for item in data["findings"][:12]:
            st.markdown(f"- {item}")
    if data.get("warnings"):
        with st.expander(f"Alertas ({len(data['warnings'])})"):
            for item in data["warnings"][:20]:
                st.markdown(f"- {item}")
    if data.get("data_gaps"):
        with st.expander(f"Dados que faltam ({len(data['data_gaps'])})"):
            for item in data["data_gaps"][:20]:
                st.markdown(f"- {item}")
    if data.get("next_actions"):
        st.markdown("**Próximas ações**")
        for item in data["next_actions"][:8]:
            st.markdown(f"- {item}")


def csv_import_widget(entity: str, label: str = "") -> None:
    """Upload real de CSV, com download do modelo."""
    st.markdown(f"**Importar CSV de {label or entity}**")
    st.caption(
        "Use ponto e vírgula ou vírgula como separador. Os registros importados por aqui "
        "entram como dados reais (is_demo=False)."
    )
    template_path = template_csv(entity, f"exports/modelo_{entity}.csv")
    st.download_button(
        "Baixar modelo CSV", template_path.read_bytes(), file_name=f"modelo_{entity}.csv",
        mime="text/csv", key=f"tpl_{entity}",
    )
    upload = st.file_uploader("Arquivo CSV", type=["csv"], key=f"upload_{entity}")
    if upload is not None:
        suffix = f"_{entity}.csv"
        target = template_path.parent / f"upload{suffix}"
        target.write_bytes(upload.getvalue())
        result = import_csv(target, entity, orch().repo, is_demo=False, source="upload_csv")
        if result["imported"]:
            notice("ok", f"{result['imported']} linhas importadas.")
        if result["errors"]:
            notice("warn", f"{result['skipped']} linhas rejeitadas.")
            st.json(result["errors"][:10])


def login_gate() -> bool:
    """Login opcional (APP_REQUIRE_LOGIN=1) com senha em hash scrypt."""
    if not orch().settings.require_login:
        return True
    if st.session_state.get("user"):
        return True
    auth = AuthService(orch().repo)
    page_header("Entrar", "Acesso restrito ao proprietário")
    if not auth.has_users():
        st.info("Nenhum usuário cadastrado ainda. Crie o proprietário.")
        with st.form("create_owner"):
            email = st.text_input("E-mail")
            password = st.text_input("Senha (mín. 8 caracteres)", type="password")
            if st.form_submit_button("Criar proprietário"):
                try:
                    auth.create_user(email, password, role="owner")
                    st.success("Proprietário criado. Faça login.")
                except ValueError as exc:
                    st.error(str(exc))
        return False
    with st.form("login"):
        email = st.text_input("E-mail")
        password = st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar"):
            user = auth.authenticate(email, password)
            if user:
                st.session_state["user"] = user
                st.rerun()
            else:
                st.error("Credenciais inválidas.")
    return False
