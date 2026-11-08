"""Gerenciamento de tarefas: estados, tentativas, deduplicação e histórico."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from core.config import Settings, get_settings
from core.utils import new_id, now_iso
from database.models import TaskStatus


class TaskManager:
    """Ciclo de vida completo de uma tarefa.

    Estados: pendente -> em_execucao -> concluida | falhou
                                  \\-> aguardando_aprovacao -> em_execucao | cancelada
    """

    def __init__(self, repo, settings: Settings | None = None):
        self.repo = repo
        self.settings = settings or get_settings()

    # ---------------------------------------------------------------- criação --
    def create(
        self,
        agent: str,
        task_type: str,
        title: str,
        payload: dict[str, Any] | None = None,
        parent_id: str = "",
        dedupe_key: str = "",
        priority: int = 3,
        is_demo: bool = False,
        requested_by: str = "proprietario",
    ) -> dict[str, Any]:
        """Cria a tarefa; se já houver uma igual em andamento, devolve a existente."""
        if dedupe_key:
            existing = self._find_duplicate(dedupe_key)
            if existing:
                self.repo.insert(
                    "task_events",
                    {
                        "task_id": existing["id"],
                        "event": "duplicada",
                        "message": f"Criação evitada: tarefa {title} já em andamento",
                    },
                )
                return {**existing, "_duplicate": True}

        task = self.repo.insert(
            "tasks",
            {
                "id": new_id("task"),
                "parent_id": parent_id or None,
                "agent": agent,
                "task_type": task_type,
                "title": title,
                "status": TaskStatus.PENDENTE.value,
                "priority": priority,
                "payload": payload or {},
                "attempts": 0,
                "max_attempts": self.settings.task_max_attempts,
                "dedupe_key": dedupe_key or None,
                "timeout_seconds": self.settings.task_timeout_seconds,
                "requested_by": requested_by,
                "is_demo": is_demo,
                "created_at": now_iso(),
            },
        )
        self._event(task["id"], "criada", title)
        return {**task, "_duplicate": False}

    def _find_duplicate(self, dedupe_key: str) -> dict | None:
        window = timedelta(minutes=self.settings.task_dedupe_window_minutes)
        cutoff = (datetime.now(timezone.utc) - window).isoformat(timespec="seconds")
        candidates = self.repo.find(
            "tasks",
            {"dedupe_key": dedupe_key, "created_at": {"$gte": cutoff}},
            order_by="-created_at",
            limit=5,
        )
        for task in candidates:
            if task["status"] in {
                TaskStatus.PENDENTE.value,
                TaskStatus.EM_EXECUCAO.value,
                TaskStatus.AGUARDANDO_APROVACAO.value,
            }:
                return task
        return None

    # -------------------------------------------------------------- transições --
    def start(self, task_id: str) -> dict | None:
        task = self.repo.get("tasks", task_id)
        if not task:
            return None
        attempts = int(task.get("attempts") or 0) + 1
        updated = self.repo.update(
            "tasks",
            task_id,
            {"status": TaskStatus.EM_EXECUCAO.value, "started_at": now_iso(), "attempts": attempts},
        )
        self._event(task_id, "iniciada", f"tentativa {attempts}")
        return updated

    def complete(self, task_id: str, result: dict[str, Any]) -> dict | None:
        updated = self.repo.update(
            "tasks",
            task_id,
            {"status": TaskStatus.CONCLUIDA.value, "result": result or {}, "finished_at": now_iso()},
        )
        self._event(task_id, "concluida", (result or {}).get("summary", "")[:400])
        return updated

    def fail(self, task_id: str, error: str) -> dict | None:
        task = self.repo.get("tasks", task_id)
        if not task:
            return None
        attempts = int(task.get("attempts") or 0)
        max_attempts = int(task.get("max_attempts") or self.settings.task_max_attempts)
        status = (
            TaskStatus.PENDENTE.value if attempts < max_attempts else TaskStatus.FALHOU.value
        )
        updated = self.repo.update(
            "tasks",
            task_id,
            {
                "status": status,
                "error": error[:2000],
                "finished_at": now_iso() if status == TaskStatus.FALHOU.value else None,
            },
        )
        self._event(task_id, "erro", f"{error[:300]} (tentativa {attempts}/{max_attempts})")
        return updated

    def await_approval(self, task_id: str, approval_id: str) -> dict | None:
        updated = self.repo.update(
            "tasks", task_id, {"status": TaskStatus.AGUARDANDO_APROVACAO.value}
        )
        self._event(task_id, "aguardando_aprovacao", f"aprovação {approval_id}")
        return updated

    def resume(self, task_id: str) -> dict | None:
        updated = self.repo.update("tasks", task_id, {"status": TaskStatus.EM_EXECUCAO.value})
        self._event(task_id, "retomada", "aprovação concedida")
        return updated

    def cancel(self, task_id: str, reason: str = "") -> dict | None:
        updated = self.repo.update(
            "tasks",
            task_id,
            {"status": TaskStatus.CANCELADA.value, "finished_at": now_iso(), "error": reason or None},
        )
        self._event(task_id, "cancelada", reason)
        return updated

    # ------------------------------------------------------------------ leitura --
    def _event(self, task_id: str, event: str, message: str = "") -> None:
        self.repo.insert(
            "task_events",
            {"id": new_id("evt"), "task_id": task_id, "event": event, "message": message},
        )

    def get(self, task_id: str) -> dict | None:
        return self.repo.get("tasks", task_id)

    def list_tasks(self, status: str | None = None, limit: int = 50) -> list[dict]:
        filters = {"status": status} if status else {}
        return self.repo.find("tasks", filters, order_by="-created_at", limit=limit)

    def events(self, task_id: str) -> list[dict]:
        return self.repo.find("task_events", {"task_id": task_id}, order_by="created_at")

    def stats(self) -> dict[str, int]:
        result = {status.value: 0 for status in TaskStatus}
        for status in TaskStatus:
            result[status.value] = self.repo.count("tasks", {"status": status.value})
        result["total"] = sum(v for k, v in result.items() if k != "total")
        return result

    def pending_approvals_count(self) -> int:
        return self.repo.count("approvals", {"status": "pendente"})
