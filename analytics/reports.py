"""Geração de relatórios em Markdown (determinístico, sem IA obrigatória)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.utils import local_now, money, pct


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "_Sem registros._\n"
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        out.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(out) + "\n"


def _header(title: str, subtitle: str = "") -> str:
    stamp = local_now().strftime("%d/%m/%Y %H:%M")
    lines = [f"# {title}", ""]
    if subtitle:
        lines += [f"_{subtitle}_", ""]
    lines += [f"Gerado em {stamp} (America/Sao_Paulo)", ""]
    return "\n".join(lines)


def daily_report(payload: dict[str, Any]) -> str:
    """Relatório diário de operação."""
    products = payload.get("products", [])
    alerts = payload.get("alerts", [])
    tasks = payload.get("tasks", [])
    opportunities = payload.get("opportunities", [])
    demo = payload.get("demo_mode", False)

    body = _header(
        "Relatório diário - E-COMMERCE AI EMPIRE",
        "Dados DEMO incluídos (não são dados reais de mercado)" if demo else "",
    )

    best = sorted(
        [p for p in products if p.get("score") is not None],
        key=lambda p: p["score"],
        reverse=True,
    )[:5]
    body += "## 1. Produtos com melhor pontuação\n\n"
    body += _table(
        ["Produto", "Score", "Classificação", "Margem %", "Canal"],
        [
            [
                p.get("name", "-"),
                p.get("score", "-"),
                p.get("classification_label", "-"),
                p.get("margin_pct", "-"),
                p.get("marketplace", "-"),
            ]
            for p in best
        ],
    )

    body += "\n## 2. Oportunidades registradas\n\n"
    body += _table(
        ["Produto", "Canal", "Preço", "Margem est.", "Score"],
        [
            [
                o.get("name", "-"),
                o.get("marketplace", "-"),
                money(float(o["price_found"])) if o.get("price_found") else "-",
                pct(float(o["margin_estimate"])) if o.get("margin_estimate") is not None else "-",
                o.get("score", "-"),
            ]
            for o in opportunities[:10]
        ],
    )

    body += "\n## 3. Alertas\n\n"
    body += "\n".join(f"- {a}" for a in alerts) if alerts else "_Nenhum alerta._"
    body += "\n\n## 4. Tarefas do dia\n\n"
    body += _table(
        ["Tarefa", "Agente", "Status"],
        [[t.get("title", "-"), t.get("agent", "-"), t.get("status", "-")] for t in tasks[:15]],
    )
    body += (
        "\n## 5. Limitações\n\n"
        "- Nenhuma taxa de marketplace é estimada: só entram valores informados em Configurações.\n"
        "- Indicadores de demanda e concorrência exigem dados importados (CSV) ou APIs autorizadas.\n"
        "- Campos vazios significam ausência de dado, não zero.\n"
    )
    return body


def weekly_report(payload: dict[str, Any]) -> str:
    """Relatório semanal financeiro e estratégico."""
    financial = payload.get("financial_rows", [])
    channel_rows = payload.get("channels", [])
    recommendations = payload.get("recommendations", [])

    body = _header(
        "Relatório semanal - E-COMMERCE AI EMPIRE",
        "Dados DEMO incluídos (não são dados reais de mercado)" if payload.get("demo_mode") else "",
    )
    body += "## 1. Margem por produto\n\n"
    body += _table(
        ["Produto", "Canal", "Receita", "Custo total", "Lucro líquido", "Margem %", "Saúde"],
        [
            [
                r.get("product_name", "-"),
                r.get("marketplace", "-"),
                money(r.get("revenue", 0)),
                money(r.get("total_cost", 0)),
                money(r.get("net_profit", 0)),
                pct(r.get("margin_pct", 0)),
                r.get("health", "-"),
            ]
            for r in financial
        ],
    )
    body += "\n## 2. Comparativo de canais\n\n"
    body += _table(
        ["Canal", "Comissão %", "Lucro líquido", "Margem %", "Recomendação"],
        [
            [
                c.get("marketplace", "-"),
                c.get("commission_pct", "-"),
                money(c.get("net_profit", 0)),
                pct(c.get("margin_pct", 0)),
                "priorizar" if c.get("net_profit", 0) >= 0 else "revisar",
            ]
            for c in channel_rows
        ],
    )
    body += "\n## 3. Recomendações estratégicas\n\n"
    body += ("\n".join(f"- {r}" for r in recommendations) if recommendations else "_Sem recomendações._")
    body += "\n"
    return body


def orchestration_report(
    command: str,
    steps: list[dict[str, Any]],
    summary_points: list[str],
    data_gaps: list[str],
    next_actions: list[str],
    demo_mode: bool = False,
) -> str:
    """Relatório final consolidado de uma solicitação ao CEO AI."""
    body = _header(
        "Relatório do CEO AI",
        "Inclui dados DEMO, claramente identificados" if demo_mode else "",
    )
    body += f"**Solicitação:** {command}\n\n"
    body += "## O que foi executado\n\n"
    body += _table(
        ["Agente", "Tarefa", "Status", "Resumo"],
        [
            [
                s.get("agent", "-"),
                s.get("title", "-"),
                s.get("status", "-"),
                (s.get("summary", "") or "")[:160],
            ]
            for s in steps
        ],
    )
    body += "\n## Resultado consolidado\n\n"
    body += "\n".join(f"- {p}" for p in summary_points) if summary_points else "_Sem conclusões._"
    body += "\n\n## Dados que faltam\n\n"
    body += "\n".join(f"- {g}" for g in data_gaps) if data_gaps else "_Nenhuma lacuna identificada._"
    body += "\n\n## Próximas ações sugeridas\n\n"
    body += "\n".join(f"{i + 1}. {a}" for i, a in enumerate(next_actions)) if next_actions else "- -"
    body += "\n\n---\n\n"
    body += (
        "Este relatório foi montado pelo orquestrador com cálculos determinísticos e, "
        "quando disponível, texto do provedor de IA. Números sem fonte informada são "
        "marcados como ausentes, nunca estimados.\n"
    )
    return body


def save_report(repo, kind: str, title: str, body: str, is_demo: bool = False) -> dict:
    """Persiste o relatório no banco (histórico sobrevive a reinícios)."""
    return repo.insert(
        "reports",
        {
            "kind": kind,
            "title": title,
            "body": body,
            "period_start": datetime.now().isoformat(timespec="seconds"),
            "is_demo": is_demo,
        },
    )
