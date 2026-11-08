"""Orquestrador: recebe o comando, distribui tarefas e consolida o resultado."""

from __future__ import annotations

import time
from typing import Any

from agents import build_agents
from agents.base import AgentContext
from analytics.reports import orchestration_report, save_report
from core.ai_provider import AIService
from core.config import Settings, get_settings
from core.memory import MemoryStore
from core.permissions import PermissionGate
from core.planner import build_plan, detect_intent
from core.task_manager import TaskManager
from core.utils import fingerprint, new_id
from database.models import MARKETPLACE_LABELS
from database.repository import get_repository

DEFAULT_MARKETPLACES = [
    ("shopee", "Shopee"),
    ("mercadolivre", "Mercado Livre"),
    ("tiktok_shop", "TikTok Shop"),
    ("instagram", "Instagram"),
    ("loja_propria", "Loja própria"),
    ("woocommerce", "WooCommerce"),
]


class Orchestrator:
    """Cérebro central: plano -> tarefas -> execução -> validação -> relatório."""

    def __init__(self, repo=None, settings: Settings | None = None, ai: AIService | None = None):
        self.settings = settings or get_settings()
        self.repo = repo or get_repository()
        self.ai = ai or AIService(self.settings, self.repo)
        self.memory = MemoryStore(self.repo)
        self.tasks = TaskManager(self.repo, self.settings)
        self.permissions = PermissionGate(self.repo, self.settings)
        self.agents = build_agents()
        self._bootstrap()

    # ---------------------------------------------------------------- bootstrap --
    def _bootstrap(self) -> None:
        self.ensure_marketplace_rules()
        self.register_agents()

    def ensure_marketplace_rules(self) -> None:
        """Cria as linhas de canal com taxa ZERO e fonte explícita.

        Não inventamos taxas: o proprietário informa os valores reais em
        Configurações > Marketplaces.
        """
        for slug, label in DEFAULT_MARKETPLACES:
            exists = self.repo.find_one("marketplaces", {"slug": slug})
            if exists:
                continue
            self.repo.insert(
                "marketplaces",
                {
                    "slug": slug,
                    "name": label,
                    "commission_pct": 0,
                    "fixed_fee": 0,
                    "notes": "Taxa não informada. Preencha com o valor real do seu contrato.",
                    "source": "não informado pelo proprietário",
                },
            )

    def register_agents(self) -> None:
        for key, agent in self.agents.items():
            info = agent.describe()
            self.repo.upsert(
                "agents",
                {
                    "name": key,
                    "role": info["role"],
                    "description": info["description"],
                    "status": "ativo",
                    "capabilities": info["capabilities"],
                    "instructions": "Agente operacional registrado pelo orquestrador.",
                },
                keys=("name",),
            )

    # ------------------------------------------------------------------ execução --
    def handle(self, command: str, requested_by: str = "proprietario") -> dict[str, Any]:
        """Processa um comando do proprietário de ponta a ponta."""
        started = time.perf_counter()
        command = (command or "").strip()
        if not command:
            return {"ok": False, "error": "comando vazio"}

        intent = detect_intent(command)
        plan = build_plan(intent, command)
        run_id = new_id("run")

        root = self.tasks.create(
            agent="ceo",
            task_type="command",
            title=command[:120],
            payload={"command": command, "intent": intent},
            priority=1,
            requested_by=requested_by,
            dedupe_key=fingerprint("command", command, self.settings.task_dedupe_window_minutes),
        )
        root_id = root["id"]
        self.tasks.start(root_id)

        shared: dict[str, Any] = {}
        executed: list[dict[str, Any]] = []
        step_tasks: dict[str, str] = {}
        stop_requested = False
        total_budget = self.settings.task_timeout_seconds * max(2, len(plan))

        for step in plan:
            if stop_requested:
                executed.append({**step, "status": "cancelada",
                                 "summary": "orçamento de tempo do ciclo esgotado"})
                continue

            elapsed = time.perf_counter() - started
            if elapsed > total_budget:
                stop_requested = True
                executed.append({**step, "status": "cancelada",
                                 "summary": "orçamento de tempo do ciclo esgotado"})
                continue

            deps_failed = [
                dep for dep in step["depends_on"]
                if shared.get(dep, {}).get("_failed")
            ]
            if deps_failed:
                executed.append({**step, "status": "cancelada",
                                 "summary": f"dependência falhou: {', '.join(deps_failed)}"})
                continue

            task = self.tasks.create(
                agent=step["agent"],
                task_type=step["task_type"],
                title=step["title"],
                payload=step["payload"],
                parent_id=root_id,
                priority=step["priority"],
                requested_by=requested_by,
                dedupe_key=fingerprint(command, step["agent"], step["task_type"]),
            )
            step_tasks[step["id"]] = task["id"]

            # Tarefa idêntica já concluída: reaproveita o resultado (sem duplicar trabalho)
            if task.get("_duplicate") and task.get("result"):
                shared[step["id"]] = task["result"]
                executed.append({**step, "status": "concluida",
                                 "summary": "resultado reaproveitado (tarefa duplicada)",
                                 "task_id": task["id"], "_reused": True})
                continue

            self.tasks.start(task["id"])
            agent = self.agents.get(step["agent"])
            if agent is None:
                self.tasks.fail(task["id"], f"agente inexistente: {step['agent']}")
                shared[step["id"]] = {"_failed": True, "summary": "agente inexistente"}
                executed.append({**step, "status": "falhou", "summary": "agente inexistente",
                                 "task_id": task["id"]})
                continue

            context = AgentContext(
                repo=self.repo,
                settings=self.settings,
                ai=self.ai,
                memory=self.memory,
                tasks=self.tasks,
                permissions=self.permissions,
                task=task,
                shared=shared,
            )
            step_started = time.perf_counter()
            try:
                result = agent.run(context)
                payload = result.to_dict()
                duration = time.perf_counter() - step_started
                payload["_duration_s"] = round(duration, 2)
                if duration > self.settings.task_timeout_seconds:
                    payload.setdefault("warnings", []).append(
                        f"Etapa levou {duration:.1f}s, acima do limite de "
                        f"{self.settings.task_timeout_seconds}s."
                    )
                self.tasks.complete(task["id"], payload)
                shared[step["id"]] = payload
                executed.append({**step, "status": "concluida", "summary": result.summary,
                                 "task_id": task["id"], "duration_s": round(duration, 2)})
            except Exception as exc:  # noqa: BLE001 - registramos e seguimos
                self.tasks.fail(task["id"], f"{type(exc).__name__}: {exc}")
                shared[step["id"]] = {"_failed": True, "summary": f"erro: {exc}"}
                executed.append({**step, "status": "falhou", "summary": f"erro: {exc}",
                                 "task_id": task["id"]})

        # ---------------------------------------------------------- consolidação --
        ceo_step = next((id_ for id_ in shared if id_.startswith("ceo.")), None)
        ceo_data = shared.get(ceo_step or "", {}) or {}
        data = ceo_data.get("data", {}) or {}
        summary_points = data.get("summary_points") or ceo_data.get("findings") or []
        data_gaps = list(dict.fromkeys(ceo_data.get("data_gaps") or []))
        next_actions = list(dict.fromkeys(ceo_data.get("next_actions") or []))
        demo_mode = bool(data.get("demo_mode"))

        consistency = self._validate(shared)
        if consistency:
            data_gaps.extend(consistency)

        report_body = orchestration_report(
            command=command,
            steps=executed,
            summary_points=summary_points,
            data_gaps=data_gaps,
            next_actions=next_actions,
            demo_mode=demo_mode,
        )
        report = save_report(
            self.repo, kind="orchestration",
            title=f"CEO AI: {intent['label']}", body=report_body, is_demo=demo_mode,
        )

        total_duration = round(time.perf_counter() - started, 2)
        self.memory.log_decision(
            subject="command",
            decision=f"Executado: {intent['label']}",
            rationale=f"Confiança {intent['confidence']:.0%}; {len(executed)} etapas.",
            data={"command": command, "run_id": run_id, "report_id": report["id"]},
        )
        self.permissions.audit(
            requested_by, "orchestration_run", "run", run_id,
            {"command": command, "intent": intent["code"], "steps": len(executed),
             "duration_s": total_duration},
        )

        self.tasks.complete(root_id, {
            "run_id": run_id, "report_id": report["id"],
            "steps": len(executed), "duration_s": total_duration,
        })

        return {
            "ok": True,
            "run_id": run_id,
            "command": command,
            "intent": intent,
            "plan": [{k: v for k, v in step.items() if k != "payload"} for step in plan],
            "steps": executed,
            "task_ids": step_tasks,
            "root_task_id": root_id,
            "report_id": report["id"],
            "report": report_body,
            "summary_points": summary_points,
            "data_gaps": data_gaps,
            "next_actions": next_actions,
            "demo_mode": demo_mode,
            "consistency_issues": consistency,
            "duration_s": total_duration,
            "ai": {
                "provider_last": ceo_data.get("ai_provider", "deterministico"),
                "status": self.ai.status(),
            },
        }

    # --------------------------------------------------------------- validação --
    @staticmethod
    def _validate(shared: dict[str, Any]) -> list[str]:
        """Confere consistência numérica dos resultados antes de entregar."""
        issues: list[str] = []
        financial = shared.get("financial.evaluate", {}).get("data", {}) or {}
        for row in financial.get("rows", [])[:25]:
            revenue = float(row.get("revenue") or 0)
            total_cost = float(row.get("total_cost") or 0)
            net = float(row.get("net_profit") or 0)
            if abs((revenue - total_cost) - net) > 0.05:
                issues.append(
                    f"Inconsistência no cálculo de {row.get('product_name')}: "
                    f"receita - custo != lucro líquido."
                )
            margin = float(row.get("margin_pct") or 0)
            if revenue > 0 and abs(margin - (net / revenue * 100)) > 0.05:
                issues.append(f"Margem inconsistente em {row.get('product_name')}.")

        hunter = shared.get("product_hunter.research", {}).get("data", {}) or {}
        for row in hunter.get("opportunities", [])[:25]:
            score = float(row.get("score") or 0)
            if not 0 <= score <= 100:
                issues.append(f"Score fora da faixa em {row.get('name')}: {score}")
        return issues

    # ------------------------------------------------------------------ utilitário --
    def status(self) -> dict[str, Any]:
        return {
            "app": self.settings.app_name,
            "version": self.settings.version,
            "timezone": self.settings.timezone,
            "currency": self.settings.currency,
            "database": getattr(self.repo, "backend", "desconhecido"),
            "ai": self.ai.status(),
            "ai_usage": self.ai.usage_summary(),
            "agents": len(self.agents),
            "tasks": self.tasks.stats(),
            "pending_approvals": self.repo.count("approvals", {"status": "pendente"}),
            "channels": self.repo.find("marketplaces", {}, order_by="name"),
        }
