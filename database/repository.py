"""Repositório de dados.

Backend padrão: SQLite local (gratuito, zero configuração, persistente).
Backend opcional: Supabase/PostgREST (ver database/supabase_repository.py),
ativado por DATABASE_BACKEND=supabase no .env.

Todo acesso passa por aqui: nenhuma consulta SQL é montada com dados do
usuário sem validação (nomes de tabela/coluna são validados por regex e
whitelist).
"""

from __future__ import annotations

import json
import re
import sqlite3
import tempfile
import threading
from pathlib import Path
from typing import Any, Iterable

from core.config import get_settings
from core.utils import new_id, now_iso, to_json

_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")

TABLES: tuple[str, ...] = (
    "users", "agents", "tasks", "task_events", "memories", "approvals",
    "audit_logs", "categories", "suppliers", "products", "competitors",
    "listings", "marketplaces", "costs", "sales", "opportunities", "reports",
    "automations", "ai_usage", "settings_kv",
)

JSON_COLUMNS: dict[str, set[str]] = {
    "tasks": {"payload", "result"},
    "memories": {"value", "tags"},
    "approvals": {"payload"},
    "audit_logs": {"details"},
    "agents": {"capabilities"},
    "opportunities": {"breakdown"},
    "automations": {"config"},
    "settings_kv": {"value"},
}

BOOL_COLUMNS: set[str] = {"is_demo", "enabled", "ok", "pickup_available", "same_day_pickup"}

SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, full_name TEXT,
  role TEXT NOT NULL DEFAULT 'owner', password_hash TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agents (
  id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL, role TEXT NOT NULL,
  description TEXT, status TEXT NOT NULL DEFAULT 'ativo',
  capabilities TEXT NOT NULL DEFAULT '[]', instructions TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY,
  parent_id TEXT REFERENCES tasks(id) ON DELETE SET NULL,
  agent TEXT NOT NULL, task_type TEXT NOT NULL, title TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pendente', priority INTEGER NOT NULL DEFAULT 3,
  payload TEXT NOT NULL DEFAULT '{}', result TEXT, error TEXT,
  attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 3,
  dedupe_key TEXT, timeout_seconds INTEGER NOT NULL DEFAULT 300,
  requested_by TEXT, is_demo INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_dedupe ON tasks(dedupe_key);
CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at);

CREATE TABLE IF NOT EXISTS task_events (
  id TEXT PRIMARY KEY, task_id TEXT REFERENCES tasks(id) ON DELETE CASCADE,
  event TEXT NOT NULL, message TEXT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_task_events_task ON task_events(task_id);

CREATE TABLE IF NOT EXISTS memories (
  id TEXT PRIMARY KEY, scope TEXT NOT NULL DEFAULT 'global', key TEXT NOT NULL,
  value TEXT NOT NULL, tags TEXT DEFAULT '[]', importance INTEGER NOT NULL DEFAULT 3,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(scope, key)
);

CREATE TABLE IF NOT EXISTS approvals (
  id TEXT PRIMARY KEY, action TEXT NOT NULL, risk_level TEXT NOT NULL DEFAULT 'alto',
  resource_type TEXT, resource_id TEXT, payload TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'pendente', requested_by_agent TEXT,
  requested_by TEXT, decided_by TEXT, decided_at TEXT, note TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);

CREATE TABLE IF NOT EXISTS audit_logs (
  id TEXT PRIMARY KEY, actor TEXT NOT NULL, action TEXT NOT NULL,
  resource_type TEXT, resource_id TEXT, details TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at);

CREATE TABLE IF NOT EXISTS categories (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, parent_id TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS suppliers (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, contact TEXT, url TEXT,
  min_qty INTEGER NOT NULL DEFAULT 1, unit_price REAL NOT NULL DEFAULT 0,
  lead_time_days INTEGER NOT NULL DEFAULT 0,
  shipping_cost REAL NOT NULL DEFAULT 0, notes TEXT, risk_notes TEXT,
  pickup_available INTEGER NOT NULL DEFAULT 0,
  same_day_pickup INTEGER NOT NULL DEFAULT 0,
  city TEXT, state TEXT,
  is_demo INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
  id TEXT PRIMARY KEY, sku TEXT, name TEXT NOT NULL, category TEXT,
  description TEXT, purchase_price REAL NOT NULL DEFAULT 0,
  extra_cost REAL NOT NULL DEFAULT 0, sale_price REAL NOT NULL DEFAULT 0,
  supplier_id TEXT, marketplace TEXT, status TEXT NOT NULL DEFAULT 'ativo',
  source TEXT DEFAULT 'manual', is_demo INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS competitors (
  id TEXT PRIMARY KEY, product_id TEXT, name TEXT NOT NULL, marketplace TEXT,
  price REAL, url TEXT, rating REAL, reviews INTEGER, differentials TEXT,
  source TEXT, collected_at TEXT NOT NULL, is_demo INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS listings (
  id TEXT PRIMARY KEY, product_id TEXT, marketplace TEXT NOT NULL,
  external_id TEXT, title TEXT, description TEXT, price REAL,
  status TEXT NOT NULL DEFAULT 'rascunho', score REAL, url TEXT,
  is_demo INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS marketplaces (
  id TEXT PRIMARY KEY, slug TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
  commission_pct REAL NOT NULL DEFAULT 0, fixed_fee REAL NOT NULL DEFAULT 0,
  handling_days INTEGER NOT NULL DEFAULT 0,
  delivery_days INTEGER NOT NULL DEFAULT 0,
  notes TEXT, source TEXT, sla_source TEXT, updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS costs (
  id TEXT PRIMARY KEY, product_id TEXT, kind TEXT NOT NULL,
  amount REAL NOT NULL DEFAULT 0, note TEXT, created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sales (
  id TEXT PRIMARY KEY, product_id TEXT, listing_id TEXT, marketplace TEXT,
  quantity INTEGER NOT NULL DEFAULT 1, unit_price REAL NOT NULL DEFAULT 0,
  fees REAL NOT NULL DEFAULT 0, shipping REAL NOT NULL DEFAULT 0,
  taxes REAL NOT NULL DEFAULT 0, total REAL NOT NULL DEFAULT 0,
  sold_at TEXT NOT NULL, is_demo INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS opportunities (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT, marketplace TEXT,
  price_found REAL, source TEXT, consulted_at TEXT NOT NULL,
  cost_estimate REAL, margin_estimate REAL, score REAL,
  recommendation TEXT, breakdown TEXT NOT NULL DEFAULT '{}', risks TEXT,
  is_demo INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reports (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
  period_start TEXT, period_end TEXT, is_demo INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS automations (
  id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL, schedule_cron TEXT,
  job TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, last_run_at TEXT,
  next_run_at TEXT, config TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_usage (
  id TEXT PRIMARY KEY, provider TEXT NOT NULL, model TEXT, task_id TEXT,
  agent TEXT, prompt_tokens INTEGER DEFAULT 0, completion_tokens INTEGER DEFAULT 0,
  cost_usd REAL DEFAULT 0, latency_ms INTEGER DEFAULT 0,
  ok INTEGER NOT NULL DEFAULT 1, error TEXT, created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings_kv (
  key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL
);
"""


def _check_ident(name: str, kind: str = "coluna") -> str:
    if not isinstance(name, str) or not _IDENT.match(name):
        raise ValueError(f"{kind} inválido: {name!r}")
    return name


class SQLiteRepository:
    """Repositório transacional sobre SQLite (mesmo esquema do schema.sql)."""

    backend = "sqlite"

    @staticmethod
    def _resolve_path(path: Path) -> Path:
        """Usa o caminho pedido; se o disco for somente leitura (hospedagem gerenciada),
        cai para um diretório temporário gravável em vez de quebrar a aplicação."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            probe = path.parent / ".write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return path
        except OSError:
            fallback = Path(tempfile.gettempdir()) / path.name
            fallback.parent.mkdir(parents=True, exist_ok=True)
            return fallback

    def __init__(self, path: str | Path):
        self.path = self._resolve_path(Path(path))
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        self._columns: dict[str, set[str]] = {}
        self.init_schema()

    # ---------------------------------------------------------------- infra --
    def init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(SQLITE_SCHEMA)
            self._conn.commit()
        self._columns.clear()
        self._migrate_columns()

    # colunas adicionadas depois da primeira versão do banco. Sem isso, quem já
    # tinha o arquivo .db criado não receberia os campos novos.
    _NEW_COLUMNS: dict[str, dict[str, str]] = {
        "suppliers": {
            "pickup_available": "INTEGER NOT NULL DEFAULT 0",
            "same_day_pickup": "INTEGER NOT NULL DEFAULT 0",
            "city": "TEXT",
            "state": "TEXT",
        },
        "marketplaces": {
            "handling_days": "INTEGER NOT NULL DEFAULT 0",
            "delivery_days": "INTEGER NOT NULL DEFAULT 0",
            "sla_source": "TEXT",
        },
    }

    def _migrate_columns(self) -> None:
        with self._lock:
            for table, cols in self._NEW_COLUMNS.items():
                existentes = self.columns(table)
                for col, ddl in cols.items():
                    if col in existentes:
                        continue
                    self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
                    self._conn.commit()
                    self._columns.pop(table, None)

    def columns(self, table: str) -> set[str]:
        table = self._table(table)
        if table not in self._columns:
            with self._lock:
                rows = self._conn.execute(f"PRAGMA table_info({table})").fetchall()
            self._columns[table] = {r["name"] for r in rows}
        return self._columns[table]

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------- helpers --
    @staticmethod
    def _table(table: str) -> str:
        _check_ident(table, "tabela")
        if table not in TABLES:
            raise ValueError(f"tabela desconhecida: {table}")
        return table

    def _encode(self, table: str, data: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        json_cols = JSON_COLUMNS.get(table, set())
        for key, value in data.items():
            key = _check_ident(key)
            if key in json_cols and value is not None and not isinstance(value, str):
                out[key] = to_json(value)
            elif key in BOOL_COLUMNS and isinstance(value, bool):
                out[key] = 1 if value else 0
            else:
                out[key] = value
        return out

    def _decode(self, table: str, row: sqlite3.Row | dict | None) -> dict | None:
        if row is None:
            return None
        data = dict(row)
        for col in JSON_COLUMNS.get(table, set()):
            if col in data and isinstance(data[col], str):
                try:
                    data[col] = json.loads(data[col])
                except (TypeError, ValueError):
                    # texto simples (não-JSON) é preservado como está
                    continue
        for col in BOOL_COLUMNS:
            if col in data and data[col] is not None:
                data[col] = bool(data[col])
        return data

    def _where(self, filters: dict[str, Any] | None) -> tuple[str, list[Any]]:
        if not filters:
            return "", []
        clauses: list[str] = []
        params: list[Any] = []
        for raw_key, value in filters.items():
            key = _check_ident(str(raw_key).lstrip("-"), "coluna")
            if isinstance(value, dict):
                for op, op_value in value.items():
                    if op == "$gte":
                        clauses.append(f"{key} >= ?"); params.append(op_value)
                    elif op == "$lte":
                        clauses.append(f"{key} <= ?"); params.append(op_value)
                    elif op == "$gt":
                        clauses.append(f"{key} > ?"); params.append(op_value)
                    elif op == "$lt":
                        clauses.append(f"{key} < ?"); params.append(op_value)
                    elif op == "$ne":
                        clauses.append(f"{key} != ?"); params.append(op_value)
                    elif op == "$in":
                        values = list(op_value)
                        if not values:
                            clauses.append("1 = 0")
                        else:
                            placeholders = ",".join("?" for _ in values)
                            clauses.append(f"{key} IN ({placeholders})")
                            params.extend(values)
                    elif op == "$like":
                        clauses.append(f"{key} LIKE ?"); params.append(op_value)
                    elif op == "$isnull":
                        clauses.append(f"{key} IS NULL" if op_value else f"{key} IS NOT NULL")
                    else:
                        raise ValueError(f"operador inválido: {op}")
            elif value is None:
                clauses.append(f"{key} IS NULL")
            else:
                clauses.append(f"{key} = ?"); params.append(value)
        return " WHERE " + " AND ".join(clauses), params

    @staticmethod
    def _order(order_by: str | None) -> str:
        if not order_by:
            return ""
        direction = "ASC"
        field = order_by.strip()
        if field.startswith("-"):
            direction = "DESC"; field = field[1:]
        parts = field.split()
        if len(parts) == 2 and parts[1].lower() in {"asc", "desc"}:
            field, direction = parts[0], parts[1].upper()
        _check_ident(field, "ordenação")
        return f" ORDER BY {field} {direction}"

    # ----------------------------------------------------------------- CRUD --
    def insert(self, table: str, data: dict[str, Any]) -> dict[str, Any]:
        table = self._table(table)
        payload = dict(data)
        payload.setdefault("id", new_id(table[:3]))
        now = now_iso()
        if "created_at" in self.columns(table):
            payload.setdefault("created_at", now)
        if "updated_at" in self.columns(table):
            payload.setdefault("updated_at", now)
        encoded = self._encode(table, payload)
        cols = ", ".join(encoded)
        placeholders = ", ".join("?" for _ in encoded)
        with self._lock:
            self._conn.execute(
                f"INSERT INTO {table} ({cols}) VALUES ({placeholders})",
                list(encoded.values()),
            )
            self._conn.commit()
            row = self._conn.execute(
                f"SELECT * FROM {table} WHERE id = ?", (payload["id"],)
            ).fetchone()
        return self._decode(table, row) or {}

    def insert_many(self, table: str, rows: Iterable[dict[str, Any]]) -> list[dict]:
        return [self.insert(table, row) for row in rows]

    def get(self, table: str, record_id: str) -> dict | None:
        table = self._table(table)
        with self._lock:
            row = self._conn.execute(
                f"SELECT * FROM {table} WHERE id = ?", (record_id,)
            ).fetchone()
        return self._decode(table, row)

    def find(
        self,
        table: str,
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict]:
        table = self._table(table)
        where, params = self._where(filters)
        sql = f"SELECT * FROM {table}{where}{self._order(order_by)}"
        if limit is not None:
            sql += f" LIMIT {int(limit)} OFFSET {int(offset)}"
        elif offset:
            sql += f" LIMIT -1 OFFSET {int(offset)}"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [self._decode(table, row) or {} for row in rows]

    def find_one(self, table: str, filters: dict[str, Any]) -> dict | None:
        rows = self.find(table, filters, limit=1)
        return rows[0] if rows else None

    def count(self, table: str, filters: dict[str, Any] | None = None) -> int:
        table = self._table(table)
        where, params = self._where(filters)
        with self._lock:
            row = self._conn.execute(
                f"SELECT COUNT(*) AS n FROM {table}{where}", params
            ).fetchone()
        return int(row["n"]) if row else 0

    def update(self, table: str, record_id: str, data: dict[str, Any]) -> dict | None:
        table = self._table(table)
        payload = dict(data)
        payload.pop("id", None)
        payload.pop("created_at", None)
        if "updated_at" in self.columns(table):
            payload["updated_at"] = now_iso()
        if not payload:
            return self.get(table, record_id)
        encoded = self._encode(table, payload)
        assignments = ", ".join(f"{col} = ?" for col in encoded)
        with self._lock:
            self._conn.execute(
                f"UPDATE {table} SET {assignments} WHERE id = ?",
                [*encoded.values(), record_id],
            )
            self._conn.commit()
        return self.get(table, record_id)

    def update_where(
        self, table: str, filters: dict[str, Any], data: dict[str, Any]
    ) -> int:
        table = self._table(table)
        payload = dict(data)
        payload.pop("id", None)
        if "updated_at" in self.columns(table):
            payload["updated_at"] = now_iso()
        if not payload:
            return 0
        encoded = self._encode(table, payload)
        assignments = ", ".join(f"{col} = ?" for col in encoded)
        where, params = self._where(filters)
        with self._lock:
            cur = self._conn.execute(
                f"UPDATE {table} SET {assignments}{where}",
                [*encoded.values(), *params],
            )
            self._conn.commit()
        return cur.rowcount

    def upsert(
        self, table: str, data: dict[str, Any], keys: tuple[str, ...]
    ) -> dict[str, Any]:
        filters = {k: data[k] for k in keys if k in data}
        existing = self.find_one(table, filters) if len(filters) == len(keys) else None
        if existing:
            return self.update(table, existing["id"], data) or existing
        return self.insert(table, data)

    def delete(self, table: str, record_id: str) -> bool:
        table = self._table(table)
        with self._lock:
            cur = self._conn.execute(f"DELETE FROM {table} WHERE id = ?", (record_id,))
            self._conn.commit()
        return cur.rowcount > 0

    def delete_where(self, table: str, filters: dict[str, Any]) -> int:
        table = self._table(table)
        where, params = self._where(filters)
        if not where:
            raise ValueError("delete_where exige filtros explícitos")
        with self._lock:
            cur = self._conn.execute(f"DELETE FROM {table}{where}", params)
            self._conn.commit()
        return cur.rowcount

    # -------------------------------------------------------------- settings --
    def set_setting(self, key: str, value: Any) -> None:
        self.upsert("settings_kv", {"key": key, "value": to_json(value)}, keys=("key",))

    def get_setting(self, key: str, default: Any = None) -> Any:
        row = self.find_one("settings_kv", {"key": key})
        if not row:
            return default
        raw = row.get("value")
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except (TypeError, ValueError):
                return default
        return raw if raw is not None else default

    # ----------------------------------------------------------------- raw --
    def raw(self, sql: str, params: Iterable[Any] = ()) -> list[dict]:
        """Consulta SQL livre. Uso interno/administrativo (apenas SQLite)."""
        with self._lock:
            rows = self._conn.execute(sql, tuple(params)).fetchall()
        return [dict(r) for r in rows]


_repository: SQLiteRepository | Any | None = None
_repository_lock = threading.Lock()


def get_repository(force_new: bool = False):
    """Retorna a instância única do repositório conforme a configuração."""
    global _repository
    with _repository_lock:
        if _repository is not None and not force_new:
            return _repository
        settings = get_settings()
        if settings.database_backend == "supabase":
            from database.supabase_repository import SupabaseRepository

            _repository = SupabaseRepository(
                settings.supabase_url, settings.supabase_key, settings.supabase_schema
            )
        else:
            _repository = SQLiteRepository(settings.sqlite_path)
        return _repository


def reset_repository(new: Any | None = None) -> None:
    """Reconfigura o repositório global (usado nos testes)."""
    global _repository
    with _repository_lock:
        if _repository is not None and hasattr(_repository, "close"):
            try:
                _repository.close()
            except Exception:  # pragma: no cover
                pass
        _repository = new
