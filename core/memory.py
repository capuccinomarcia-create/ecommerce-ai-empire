"""Memória persistente: decisões, contexto de longo prazo e histórico."""

from __future__ import annotations

from typing import Any

from core.utils import new_id, now_iso


class MemoryStore:
    """Chave-valor com escopo, persistido na tabela ``memories``.

    Sobrevive a reinícios da aplicação porque vive no banco (SQLite/Supabase),
    não na memória do processo.
    """

    def __init__(self, repo):
        self.repo = repo

    def remember(
        self,
        key: str,
        value: Any,
        scope: str = "global",
        tags: list[str] | None = None,
        importance: int = 3,
    ) -> dict:
        serializable = value
        return self.repo.upsert(
            "memories",
            {
                "scope": scope,
                "key": key,
                "value": serializable,
                "tags": tags or [],
                "importance": importance,
                "updated_at": now_iso(),
            },
            keys=("scope", "key"),
        )

    def recall(self, key: str, default: Any = None, scope: str = "global") -> Any:
        row = self.repo.find_one("memories", {"scope": scope, "key": key})
        if not row:
            return default
        value = row.get("value")
        return value if value is not None else default

    def forget(self, key: str, scope: str = "global") -> bool:
        row = self.repo.find_one("memories", {"scope": scope, "key": key})
        return self.repo.delete("memories", row["id"]) if row else False

    def search(self, term: str, scope: str | None = None, limit: int = 20) -> list[dict]:
        filters: dict[str, Any] = {}
        if scope:
            filters["scope"] = scope
        rows = self.repo.find("memories", filters, order_by="-importance", limit=500)
        needle = (term or "").lower()
        if not needle:
            return rows[:limit]
        found = []
        for row in rows:
            haystack = f"{row.get('key','')} {row.get('value','')} {row.get('tags','')}".lower()
            if needle in haystack:
                found.append(row)
        return found[:limit]

    def recent(self, scope: str | None = None, limit: int = 20) -> list[dict]:
        filters = {"scope": scope} if scope else {}
        return self.repo.find("memories", filters, order_by="-updated_at", limit=limit)

    # -------------------------------------------------------------- decisões --
    def log_decision(self, subject: str, decision: str, rationale: str = "", data: dict | None = None) -> dict:
        key = f"{subject}:{new_id()[:8]}"
        return self.remember(
            key,
            {"decision": decision, "rationale": rationale, "data": data or {}},
            scope="decisions",
            tags=["decisao"],
            importance=4,
        )
