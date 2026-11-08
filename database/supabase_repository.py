"""Repositório Supabase (PostgREST) - opcional.

Ativado somente quando DATABASE_BACKEND=supabase. Requer o esquema de
database/schema.sql aplicado no projeto Supabase do proprietário.
Nenhum dado é enviado sem que o proprietário configure URL e chave.
"""

from __future__ import annotations

from typing import Any, Iterable

import httpx

from core.utils import new_id, now_iso


class SupabaseUnavailable(RuntimeError):
    """Levantado quando o Supabase não está configurado/reachável."""


class SupabaseRepository:
    backend = "supabase"

    def __init__(self, url: str, key: str, schema: str = "public"):
        if not url or not key:
            raise SupabaseUnavailable(
                "SUPABASE_URL e SUPABASE_KEY são obrigatórios para DATABASE_BACKEND=supabase"
            )
        self.url = url.rstrip("/")
        self.key = key
        self.schema = schema
        self._client = httpx.Client(
            base_url=f"{self.url}/rest/v1",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Accept-Profile": schema,
                "Content-Profile": schema,
                "Prefer": "return=representation",
            },
            timeout=20.0,
        )

    # ------------------------------------------------------------------ HTTP --
    def _request(self, method: str, path: str, **kwargs) -> Any:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:  # pragma: no cover - rede
            raise SupabaseUnavailable(f"Falha de rede no Supabase: {exc}") from exc
        if response.status_code >= 400:
            raise SupabaseUnavailable(
                f"Supabase {response.status_code}: {response.text[:300]}"
            )
        if not response.content:
            return None
        return response.json()

    # ------------------------------------------------------------------- CRUD --
    def insert(self, table: str, data: dict[str, Any]) -> dict[str, Any]:
        payload = dict(data)
        payload.setdefault("id", new_id(table[:3]))
        payload.setdefault("created_at", now_iso())
        payload.setdefault("updated_at", now_iso())
        result = self._request("POST", f"/{table}", json=payload)
        return result[0] if isinstance(result, list) and result else payload

    def insert_many(self, table: str, rows: Iterable[dict[str, Any]]) -> list[dict]:
        return [self.insert(table, row) for row in rows]

    def get(self, table: str, record_id: str) -> dict | None:
        rows = self._request("GET", f"/{table}", params={"id": f"eq.{record_id}"})
        return rows[0] if rows else None

    def find(
        self,
        table: str,
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict]:
        params: dict[str, Any] = {}
        for key, value in (filters or {}).items():
            if isinstance(value, dict):
                for op, op_value in value.items():
                    mapped = {"$gte": "gte", "$lte": "lte", "$gt": "gt", "$lt": "lt",
                              "$ne": "neq", "$like": "like"}.get(op)
                    if mapped:
                        params[key] = f"{mapped}.{op_value}"
            elif value is None:
                params[key] = "is.null"
            else:
                params[key] = f"eq.{value}"
        if order_by:
            direction = "desc" if order_by.startswith("-") else "asc"
            field = order_by.lstrip("-")
            params["order"] = f"{field}.{direction}"
        if limit is not None:
            params["limit"] = int(limit)
        if offset:
            params["offset"] = int(offset)
        return self._request("GET", f"/{table}", params=params) or []

    def find_one(self, table: str, filters: dict[str, Any]) -> dict | None:
        rows = self.find(table, filters, limit=1)
        return rows[0] if rows else None

    def count(self, table: str, filters: dict[str, Any] | None = None) -> int:
        return len(self.find(table, filters))

    def update(self, table: str, record_id: str, data: dict[str, Any]) -> dict | None:
        payload = dict(data)
        payload.pop("id", None)
        payload["updated_at"] = now_iso()
        rows = self._request(
            "PATCH", f"/{table}", json=payload, params={"id": f"eq.{record_id}"}
        )
        return rows[0] if rows else None

    def update_where(self, table: str, filters: dict[str, Any], data: dict[str, Any]) -> int:
        rows = self.find(table, filters)
        for row in rows:
            self.update(table, row["id"], data)
        return len(rows)

    def upsert(self, table: str, data: dict[str, Any], keys: tuple[str, ...]) -> dict:
        filters = {k: data[k] for k in keys if k in data}
        existing = self.find_one(table, filters) if len(filters) == len(keys) else None
        if existing:
            return self.update(table, existing["id"], data) or existing
        return self.insert(table, data)

    def delete(self, table: str, record_id: str) -> bool:
        self._request("DELETE", f"/{table}", params={"id": f"eq.{record_id}"})
        return True

    def delete_where(self, table: str, filters: dict[str, Any]) -> int:
        rows = self.find(table, filters)
        for row in rows:
            self.delete(table, row["id"])
        return len(rows)

    def set_setting(self, key: str, value: Any) -> None:
        self.upsert("settings_kv", {"key": key, "value": value}, keys=("key",))

    def get_setting(self, key: str, default: Any = None) -> Any:
        row = self.find_one("settings_kv", {"key": key})
        return row["value"] if row else default
