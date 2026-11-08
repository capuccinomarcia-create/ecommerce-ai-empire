"""Utilidades pequenas e sem dependências externas."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from typing import Any

try:  # pragma: no cover - depende do ambiente
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]


def new_id(prefix: str = "") -> str:
    value = uuid.uuid4().hex
    return f"{prefix}_{value}" if prefix else value


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return utcnow().isoformat(timespec="seconds")


def local_now(tz_name: str = "America/Sao_Paulo") -> datetime:
    if ZoneInfo is None:
        return datetime.now()
    return datetime.now(ZoneInfo(tz_name))


def to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def from_json(value: Any, default: Any = None) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text).strip("-").lower()
    return slug or "item"


def normalize_text(text: str) -> str:
    """Minúsculas e sem acento, para comparação de intenção/palavras-chave."""
    normalized = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in normalized if not unicodedata.combining(c))


def fingerprint(*parts: Any) -> str:
    payload = "|".join(str(p) for p in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def money(value: float, currency: str = "BRL") -> str:
    symbol = "R$" if currency == "BRL" else currency
    formatted = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{symbol} {formatted}"


def pct(value: float) -> str:
    return f"{value:.1f}%".replace(".", ",")


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0
