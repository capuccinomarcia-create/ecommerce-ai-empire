"""Contrato comum dos conectores de marketplace.

Regras:
- Nenhum conector simula conexão. Sem credenciais, o status é "Não conectado".
- Nada é publicado/alterado sem aprovação do proprietário (core/permissions.py).
- Toda integração tem um caminho alternativo por CSV.
"""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import Any

from core.config import Settings, get_settings
from core.utils import now_iso


class NotConfigured(RuntimeError):
    """Conector sem credenciais válidas."""


class APIError(RuntimeError):
    """Falha retornada pela API externa."""


@dataclass
class ConnectorStatus:
    channel: str
    label: str
    connected: bool
    mode: str
    missing: list[str] = field(default_factory=list)
    detail: str = ""
    docs_url: str = ""
    last_checked: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "label": self.label,
            "connected": self.connected,
            "status": "Conectado" if self.connected else "Não conectado",
            "mode": self.mode,
            "missing": self.missing,
            "detail": self.detail,
            "docs_url": self.docs_url,
            "last_checked": self.last_checked or now_iso(),
        }


class MarketplaceConnector(ABC):
    channel: str = "base"
    label: str = "Base"
    docs_url: str = ""
    required_env: tuple[str, ...] = ()
    title_max_chars: int = 60
    description_max_chars: int = 3000

    def __init__(self, settings: Settings | None = None, repo=None):
        self.settings = settings or get_settings()
        self.repo = repo

    # ----------------------------------------------------------------- status --
    def missing_credentials(self) -> list[str]:
        report = self.settings.credential_report().get(self.channel, {})
        return list(report.get("missing", []))

    def status(self) -> ConnectorStatus:
        report = self.settings.credential_report().get(self.channel, {})
        connected = bool(report.get("configured"))
        return ConnectorStatus(
            channel=self.channel,
            label=self.label,
            connected=connected,
            mode="api" if connected else "csv",
            missing=list(report.get("missing", [])),
            detail=(
                "Credenciais configuradas."
                if connected
                else "Sem credenciais: use importação/exportação de CSV enquanto isso."
            ),
            docs_url=self.docs_url,
        )

    def require(self) -> None:
        status = self.status()
        if not status.connected:
            raise NotConfigured(
                f"{self.label}: credenciais ausentes ({', '.join(status.missing) or 'n/a'}). "
                "Use CSV ou configure o .env."
            )

    # ------------------------------------------------------------------ dados --
    def fetch_products(self, limit: int = 50) -> list[dict[str, Any]]:
        """Lê produtos do canal. Deve ser implementado pelos conectores reais."""
        raise NotImplementedError

    # --------------------------------------------------------------- anúncios --
    def listing_limits(self) -> dict[str, int]:
        return {
            "title_max_chars": self.title_max_chars,
            "description_max_chars": self.description_max_chars,
        }

    def prepare_listing(self, product: dict[str, Any], title: str = "", description: str = "",
                        price: float | None = None) -> dict[str, Any]:
        """Monta o rascunho do anúncio (nunca publica)."""
        title = title or product.get("name", "")
        description = description or product.get("description", "") or ""
        limits = self.listing_limits()
        return {
            "channel": self.channel,
            "channel_label": self.label,
            "product_id": product.get("id"),
            "title": title[: limits["title_max_chars"]],
            "description": description[: limits["description_max_chars"]],
            "price": float(price if price is not None else product.get("sale_price") or 0),
            "status": "rascunho",
            "requires_approval_to_publish": True,
            "generated_at": now_iso(),
        }

    def evaluate_listing(self, listing: dict[str, Any]) -> dict[str, Any]:
        """Checagens objetivas de qualidade do anúncio (sem dados inventados)."""
        title = (listing.get("title") or "").strip()
        description = (listing.get("description") or "").strip()
        limits = self.listing_limits()
        issues: list[str] = []
        if not title:
            issues.append("Título vazio.")
        if len(title) < 25:
            issues.append(f"Título curto ({len(title)} caracteres): perde espaço de busca.")
        if len(title) > limits["title_max_chars"]:
            issues.append(
                f"Título acima do limite do canal ({len(title)}/{limits['title_max_chars']})."
            )
        if len(description) < 150:
            issues.append(f"Descrição curta ({len(description)} caracteres).")
        if not listing.get("price"):
            issues.append("Preço não definido.")
        score = max(0, 100 - len(issues) * 15)
        return {"channel": self.channel, "issues": issues, "score": score, "ok": not issues}
