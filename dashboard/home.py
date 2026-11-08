"""Página 1 - Dashboard: visão geral real da operação."""

from __future__ import annotations

import streamlit as st

from analytics.profitability import calculate
from dashboard.common import (demo_badge, kpis, money_brl, notice, orch, page_header,
                              pct_br, run_agent, table)
from integrations import connector_statuses


def render() -> None:
    o = orch()
    page_header("Visão geral da operação", "Tudo calculado a partir do banco local. Nada é estimado sem fonte.")

    products = o.repo.find("products", {}, limit=500)
    opportunities = o.repo.find("opportunities", {}, order_by="-created_at", limit=500)
    tasks = o.tasks.stats()
    pending = o.repo.count("approvals", {"status": "pendente"})
    statuses = connector_statuses(o.settings, o.repo)
    connected = sum(1 for s in statuses if s["connected"])

    margins: list[dict] = []
    for product in products:
        rule = o.repo.find_one("marketplaces", {"slug": product.get("marketplace") or "shopee"})
        result = calculate(
            {
                "product_name": product.get("name"),
                "marketplace": product.get("marketplace") or "shopee",
                "costs": {"purchase_price": float(product.get("purchase_price") or 0),
                          "other_costs": float(product.get("extra_cost") or 0)},
                "terms": {"sale_price": float(product.get("sale_price") or 1),
                          "commission_pct": float((rule or {}).get("commission_pct") or 0),
                          "fixed_fee": float((rule or {}).get("fixed_fee") or 0)},
            }
        )
        margins.append({"name": product.get("name"), "margin_pct": result.margin_pct,
                        "net_profit": result.net_profit, "health": result.health,
                        "is_demo": product.get("is_demo")})

    avg_score = (
        round(sum(float(o_row.get("score") or 0) for o_row in opportunities) / len(opportunities), 1)
        if opportunities else 0
    )
    estimated_profit = round(sum(m["net_profit"] for m in margins), 2) if margins else 0

    kpis([
        ("Produtos", len(products), "catálogo analisado"),
        ("Oportunidades", len(opportunities), f"score médio {avg_score}"),
        ("Lucro est./un", money_brl(estimated_profit), "soma por unidade vendida"),
        ("Aprovações", pending, "aguardando você"),
    ])
    st.write("")
    kpis([
        ("Tarefas", tasks.get("total", 0), f"{tasks.get('em_execucao',0)} em execução"),
        ("Concluídas", tasks.get("concluida", 0), f"{tasks.get('falhou',0)} falharam"),
        ("Canais conectados", f"{connected}/{len(statuses)}", "restante via CSV"),
        ("IA", "offline" if not o.ai.has_remote_provider else "provedor ativo",
         "cálculo é sempre local"),
    ])

    st.divider()
    left, right = st.columns([3, 2])

    with left:
        st.subheader("Produtos mais promissores")
        ranked = sorted(margins, key=lambda m: m["net_profit"], reverse=True)[:8]
        table(
            [{"Produto": m["name"], "Margem": pct_br(m["margin_pct"]),
              "Lucro/un": money_brl(m["net_profit"]), "Saúde": m["health"],
              "Origem": demo_badge(m["is_demo"])} for m in ranked],
            key="home_products",
        )

    with right:
        st.subheader("Alertas")
        alerts = []
        low = [m for m in margins if m["margin_pct"] < 8]
        if low:
            alerts.append(f"{len(low)} produto(s) com margem abaixo de 8%.")
        if pending:
            alerts.append(f"{pending} aprovação(ões) pendente(s) — ações de risco bloqueadas.")
        if tasks.get("falhou"):
            alerts.append(f"{tasks['falhou']} tarefa(s) falharam: veja Automações.")
        if not products:
            alerts.append("Catálogo vazio: carregue os dados DEMO ou importe um CSV.")
        if not any(s["connected"] for s in statuses):
            alerts.append("Nenhum canal conectado: operação em modo CSV.")
        if not alerts:
            alerts.append("Nenhum alerta no momento.")
        for alert_text in alerts:
            notice("warn" if "Nenhum" not in alert_text else "ok", alert_text)

        st.subheader("Ações rápidas")
        if st.button("Carregar dados DEMO", width="stretch"):
            from scripts.seed_demo import seed_demo

            report = seed_demo(o.repo)
            notice("ok", "DEMO carregado: " + ", ".join(f"{k}={v.get('imported',0)}" for k, v in report.items()))
            st.rerun()
        if st.button("Cadastrar rotinas padrão", width="stretch"):
            result = run_agent("automation", "register_defaults", "Cadastrar rotinas padrão", {})
            notice("ok" if result["ok"] else "bad",
                   result["result"]["summary"] if result["ok"] else result["error"])
        if st.button("Gerar relatório diário", width="stretch"):
            result = run_agent("automation", "report", "Relatório diário",
                               {"products": margins, "alerts": alerts, "kind": "daily"})
            if result["ok"]:
                notice("ok", "Relatório salvo. Abra a página Relatórios.")
            else:
                notice("bad", result["error"])

    st.divider()
    st.subheader("Últimas execuções")
    table(
        [{"Quando": t["created_at"][:19], "Agente": t["agent"], "Tarefa": t["title"][:60],
          "Status": t["status"]} for t in o.tasks.list_tasks(limit=10)],
        key="home_tasks",
    )
