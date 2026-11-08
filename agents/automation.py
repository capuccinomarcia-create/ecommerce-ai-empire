"""AGENTE 11 - AUTOMATION AI: rotinas, histórico e relatórios."""

from __future__ import annotations

from typing import Any

from agents.base import AgentContext, AgentResult, BaseAgent
from core.utils import local_now

DEFAULT_AUTOMATIONS = [
    {
        "name": "daily_product_research",
        "schedule_cron": "0 8 * * *",
        "job": "product_research",
        "description": "Pesquisa e pontuação de produtos (diário, 08:00 America/Sao_Paulo).",
    },
    {
        "name": "daily_performance_report",
        "schedule_cron": "30 19 * * *",
        "job": "daily_report",
        "description": "Relatório diário de desempenho e alertas (19:30).",
    },
    {
        "name": "weekly_competitor_review",
        "schedule_cron": "0 9 * * 1",
        "job": "weekly_report",
        "description": "Análise de concorrentes, margens e relatório financeiro (segunda, 09:00).",
    },
    {
        "name": "weekly_content_planning",
        "schedule_cron": "0 10 * * 1",
        "job": "content_planning",
        "description": "Planejamento de conteúdo da semana (segunda, 10:00).",
    },
]


class AutomationAgent(BaseAgent):
    name = "automation"
    role = "Automation AI"
    description = (
        "Gerencia rotinas programadas, evita duplicação de tarefas, checa falhas e gera "
        "relatórios. Liga e desliga automações com registro de auditoria."
    )
    capabilities = ["listar_automacoes", "ativar_desativar", "gerar_relatorio",
                    "detectar_falhas", "evitar_duplicidade"]
    tools = [
        {"name": "overview", "description": "Painel de automações, execuções e falhas."},
        {"name": "register_defaults", "description": "Cadastra as rotinas diárias e semanais."},
        {"name": "toggle", "description": "Ativa ou desativa uma rotina."},
        {"name": "report", "description": "Gera relatório diário ou semanal."},
    ]

    def execute(self) -> AgentResult:
        mode = self.ctx.payload().get("mode", "overview")
        if mode == "register_defaults":
            return self._register_defaults()
        if mode == "toggle":
            return self._toggle(self.ctx.payload())
        if mode == "report":
            return self._report(self.ctx.payload())
        return self._overview()

    # ------------------------------------------------------------- cadastro --
    def _register_defaults(self) -> AgentResult:
        created = []
        for item in DEFAULT_AUTOMATIONS:
            existing = self.ctx.repo.find_one("automations", {"name": item["name"]})
            if existing:
                continue
            created.append(
                self.ctx.repo.insert(
                    "automations",
                    {
                        "name": item["name"],
                        "schedule_cron": item["schedule_cron"],
                        "job": item["job"],
                        "enabled": True,
                        "config": {"description": item["description"],
                                   "timezone": self.ctx.settings.timezone},
                    },
                )
            )
        return AgentResult(
            summary=f"{len(created)} rotinas cadastradas (as existentes foram preservadas).",
            data={"created": created, "total": self.ctx.repo.count("automations")},
            findings=[f"{c['name']}: {c['schedule_cron']}" for c in created]
                     or ["Todas as rotinas padrão já estavam cadastradas."],
            next_actions=["Configurar os secrets do GitHub Actions para as rotinas rodarem sem servidor."],
        )

    # ---------------------------------------------------------------- toggle --
    def _toggle(self, payload: dict[str, Any]) -> AgentResult:
        name = payload.get("name")
        enabled = bool(payload.get("enabled", True))
        row = self.ctx.repo.find_one("automations", {"name": name})
        if not row:
            return AgentResult(
                summary=f"Automação {name} não encontrada.",
                data_gaps=[f"Cadastre a automação {name} antes de ativar/desativar."],
            )
        updated = self.ctx.repo.update("automations", row["id"], {"enabled": enabled})
        self.ctx.permissions.audit(
            "proprietario", "automation_toggle", "automation", row["id"],
            {"name": name, "enabled": enabled},
        )
        return AgentResult(
            summary=f"Automação {name} {'ativada' if enabled else 'desativada'}.",
            data={"automation": updated},
            findings=[f"{name}: {'ativa' if enabled else 'pausada'}"],
        )

    # ------------------------------------------------------------- visão geral --
    def _overview(self) -> AgentResult:
        automations = self.ctx.repo.find("automations", {}, order_by="name")
        if not automations:
            return AgentResult(
                summary="Nenhuma automação cadastrada ainda.",
                data={"automations": [], "can_register": True},
                data_gaps=["Rode 'Cadastrar rotinas padrão' para criar as automações diárias e semanais."],
                next_actions=["Cadastrar as rotinas padrão."],
            )
        tasks = self.ctx.tasks.list_tasks(limit=200)
        failures = [t for t in tasks if t["status"] == "falhou"]
        pending = [t for t in tasks if t["status"] in {"pendente", "em_execucao"}]
        waiting = [t for t in tasks if t["status"] == "aguardando_aprovacao"]
        stats = self.ctx.tasks.stats()
        duplicates = self.ctx.repo.find(
            "task_events", {"event": "duplicada"}, order_by="-created_at", limit=20
        )
        findings = [
            f"{len(automations)} rotinas cadastradas, "
            f"{sum(1 for a in automations if a.get('enabled'))} ativas.",
            f"Tarefas: {stats['total']} no total, {len(pending)} em andamento, "
            f"{stats['concluida']} concluídas, {len(failures)} falharam.",
            f"{len(duplicates)} execuções duplicadas evitadas no período.",
        ]
        alerts = [f"Falha em {t['title']}: {(t.get('error') or '')[:120]}" for t in failures[:5]]
        if waiting:
            alerts.append(f"{len(waiting)} tarefa(s) aguardando sua aprovação.")
        return AgentResult(
            summary=f"{len(automations)} rotinas monitoradas, {stats['total']} tarefas registradas.",
            data={
                "automations": automations,
                "task_stats": stats,
                "failures": failures[:10],
                "pending": pending[:10],
                "awaiting_approval": waiting[:10],
                "duplicates_avoided": len(duplicates),
            },
            findings=findings,
            warnings=alerts,
            next_actions=[
                "Revisar a tela de aprovações." if waiting else "Nada pendente de aprovação.",
                "Investigar falhas recorrentes no histórico de tarefas." if failures else
                "Manter as rotinas ativas.",
            ],
        )

    # -------------------------------------------------------------- relatório --
    def _report(self, payload: dict[str, Any]) -> AgentResult:
        from analytics.reports import daily_report, save_report, weekly_report

        kind = payload.get("kind", "daily")
        if kind == "weekly":
            market_rows = payload.get("financial_rows") or []
            body = weekly_report(
                {
                    "financial_rows": market_rows,
                    "channels": payload.get("channels", []),
                    "recommendations": payload.get("recommendations", []),
                    "demo_mode": payload.get("demo_mode", False),
                }
            )
            title = "Relatório semanal"
        else:
            body = daily_report(
                {
                    "products": payload.get("products", []),
                    "alerts": payload.get("alerts", []),
                    "tasks": self.ctx.tasks.list_tasks(limit=15),
                    "opportunities": payload.get("opportunities", []),
                    "demo_mode": payload.get("demo_mode", False),
                }
            )
            title = "Relatório diário"
        saved = save_report(
            self.ctx.repo, kind=kind, title=f"{title} - {local_now().strftime('%d/%m/%Y')}",
            body=body, is_demo=bool(payload.get("demo_mode")),
        )
        return AgentResult(
            summary=f"{title} gerado e salvo no histórico.",
            data={"report_id": saved["id"], "kind": kind, "body": body},
            findings=[f"Relatório {kind} salvo em {saved['created_at']}"],
            next_actions=["Abrir a página Relatórios para ler o conteúdo completo."],
        )
