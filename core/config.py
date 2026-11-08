"""Configuração central do E-COMMERCE AI EMPIRE.

Regras de projeto:
- Nenhuma credencial é escrita no código. Tudo vem de variáveis de ambiente
  ou do arquivo .env (que está no .gitignore).
- Nenhuma integração é "fingida": se as credenciais não existem, o status é
  "Não conectado" e o sistema cai para importação/exportação de CSV.
- O sistema funciona 100% sem nenhum serviço pago. O banco padrão é SQLite
  local; Supabase é opcional.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- #
# .env mínimo (sem dependência externa)
# --------------------------------------------------------------------------- #
def load_dotenv(path: str | Path | None = None) -> None:
    """Carrega o .env sem sobrescrever variáveis já definidas no ambiente."""
    env_path = Path(path) if path else PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _str(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "sim"}


def _int(name: str, default: int) -> int:
    try:
        return int(float(os.environ.get(name, "")))
    except (TypeError, ValueError):
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, ""))
    except (TypeError, ValueError):
        return default


def _list(name: str, default: list[str] | None = None) -> list[str]:
    raw = os.environ.get(name)
    if not raw:
        return list(default or [])
    return [p.strip() for p in raw.split(",") if p.strip()]


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Settings:
    """Configuração imutável da aplicação."""

    app_name: str = "E-COMMERCE AI EMPIRE"
    version: str = "0.1.0"
    env: str = "development"
    debug: bool = False

    # Localização
    timezone: str = "America/Sao_Paulo"
    currency: str = "BRL"
    locale: str = "pt-BR"

    # Banco
    database_backend: str = "sqlite"          # sqlite | supabase
    sqlite_path: Path = PROJECT_ROOT / "data" / "empire.db"
    supabase_url: str = ""
    supabase_key: str = ""
    supabase_schema: str = "public"

    # IA
    ai_providers: list[str] = field(default_factory=lambda: ["gemini", "openai_compatible", "offline"])
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    openai_compatible_key: str = ""
    openai_compatible_base_url: str = ""
    openai_compatible_model: str = ""
    ai_timeout_seconds: int = 45
    ai_max_tokens: int = 2048
    ai_max_calls_per_task: int = 4
    ai_monthly_budget_usd: float = 0.0        # 0 = sem provedor pago habilitado
    ai_temperature: float = 0.4

    # Execução de tarefas
    task_timeout_seconds: int = 300
    task_max_attempts: int = 3
    task_dedupe_window_minutes: int = 30

    # Operação
    posts_per_day: int = 3
    min_hours_between_posts: int = 4
    enabled_channels: list[str] = field(
        default_factory=lambda: ["shopee", "mercadolivre", "tiktok_shop", "instagram", "woocommerce"]
    )
    require_approval: bool = True
    require_login: bool = False

    # Credenciais por marketplace (todas opcionais)
    shopee_partner_id: str = ""
    shopee_partner_key: str = ""
    shopee_shop_id: str = ""
    shopee_base_url: str = "https://partner.shopeemobile.com"

    ml_client_id: str = ""
    ml_client_secret: str = ""
    ml_redirect_uri: str = ""
    ml_refresh_token: str = ""
    ml_access_token: str = ""
    ml_base_url: str = "https://api.mercadolibre.com"

    tiktok_app_key: str = ""
    tiktok_app_secret: str = ""
    tiktok_shop_cipher: str = ""
    tiktok_access_token: str = ""
    tiktok_base_url: str = "https://open-api.tiktokglobalshop.com"

    instagram_access_token: str = ""
    instagram_business_id: str = ""
    instagram_base_url: str = "https://graph.facebook.com/v21.0"

    woocommerce_url: str = ""
    woocommerce_consumer_key: str = ""
    woocommerce_consumer_secret: str = ""

    @property
    def is_production(self) -> bool:
        return self.env.lower() == "production"

    def credential_report(self) -> dict[str, dict[str, Any]]:
        """Quais credenciais existem e quais faltam, por canal.

        Usado pelos conectores e pelo painel. Nunca expõe o valor do segredo,
        somente se está configurado ou não.
        """
        requirements: dict[str, list[tuple[str, str]]] = {
            "shopee": [
                ("SHOPEE_PARTNER_ID", self.shopee_partner_id),
                ("SHOPEE_PARTNER_KEY", self.shopee_partner_key),
                ("SHOPEE_SHOP_ID", self.shopee_shop_id),
            ],
            "mercadolivre": [
                ("ML_CLIENT_ID", self.ml_client_id),
                ("ML_CLIENT_SECRET", self.ml_client_secret),
                ("ML_REFRESH_TOKEN|ML_ACCESS_TOKEN", self.ml_refresh_token or self.ml_access_token),
            ],
            "tiktok_shop": [
                ("TIKTOK_APP_KEY", self.tiktok_app_key),
                ("TIKTOK_APP_SECRET", self.tiktok_app_secret),
                ("TIKTOK_ACCESS_TOKEN", self.tiktok_access_token),
            ],
            "instagram": [
                ("INSTAGRAM_ACCESS_TOKEN", self.instagram_access_token),
                ("INSTAGRAM_BUSINESS_ID", self.instagram_business_id),
            ],
            "woocommerce": [
                ("WOOCOMMERCE_URL", self.woocommerce_url),
                ("WOOCOMMERCE_CONSUMER_KEY", self.woocommerce_consumer_key),
                ("WOOCOMMERCE_CONSUMER_SECRET", self.woocommerce_consumer_secret),
            ],
            "ai_gemini": [("GEMINI_API_KEY", self.gemini_api_key)],
            "ai_openai_compatible": [
                ("OPENAI_COMPATIBLE_BASE_URL", self.openai_compatible_base_url),
                ("OPENAI_COMPATIBLE_MODEL", self.openai_compatible_model),
            ],
        }
        report: dict[str, dict[str, Any]] = {}
        for channel, items in requirements.items():
            missing = [name for name, value in items if not value]
            report[channel] = {
                "configured": not missing,
                "missing": missing,
                "present": [name for name, value in items if value],
            }
        return report


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retorna a configuração (carregando o .env uma única vez)."""
    load_dotenv()
    return Settings(
        env=_str("APP_ENV", "development"),
        debug=_bool("APP_DEBUG", False),
        timezone=_str("APP_TIMEZONE", "America/Sao_Paulo"),
        currency=_str("APP_CURRENCY", "BRL"),
        locale=_str("APP_LOCALE", "pt-BR"),
        database_backend=_str("DATABASE_BACKEND", "sqlite").lower(),
        sqlite_path=Path(_str("SQLITE_PATH", str(PROJECT_ROOT / "data" / "empire.db"))),
        supabase_url=_str("SUPABASE_URL"),
        supabase_key=_str("SUPABASE_KEY"),
        supabase_schema=_str("SUPABASE_SCHEMA", "public"),
        ai_providers=_list("AI_PROVIDERS", ["gemini", "openai_compatible", "offline"]),
        gemini_api_key=_str("GEMINI_API_KEY"),
        gemini_model=_str("GEMINI_MODEL", "gemini-2.0-flash"),
        openai_compatible_key=_str("OPENAI_COMPATIBLE_API_KEY"),
        openai_compatible_base_url=_str("OPENAI_COMPATIBLE_BASE_URL"),
        openai_compatible_model=_str("OPENAI_COMPATIBLE_MODEL"),
        ai_timeout_seconds=_int("AI_TIMEOUT_SECONDS", 45),
        ai_max_tokens=_int("AI_MAX_TOKENS", 2048),
        ai_max_calls_per_task=_int("AI_MAX_CALLS_PER_TASK", 4),
        ai_monthly_budget_usd=_float("AI_MONTHLY_BUDGET_USD", 0.0),
        ai_temperature=_float("AI_TEMPERATURE", 0.4),
        task_timeout_seconds=_int("TASK_TIMEOUT_SECONDS", 300),
        task_max_attempts=_int("TASK_MAX_ATTEMPTS", 3),
        task_dedupe_window_minutes=_int("TASK_DEDUPE_WINDOW_MINUTES", 30),
        posts_per_day=_int("POSTS_PER_DAY", 3),
        min_hours_between_posts=_int("MIN_HOURS_BETWEEN_POSTS", 4),
        enabled_channels=_list(
            "ENABLED_CHANNELS",
            ["shopee", "mercadolivre", "tiktok_shop", "instagram", "woocommerce"],
        ),
        require_approval=_bool("REQUIRE_APPROVAL", True),
        require_login=_bool("APP_REQUIRE_LOGIN", False),
        shopee_partner_id=_str("SHOPEE_PARTNER_ID"),
        shopee_partner_key=_str("SHOPEE_PARTNER_KEY"),
        shopee_shop_id=_str("SHOPEE_SHOP_ID"),
        shopee_base_url=_str("SHOPEE_BASE_URL", "https://partner.shopeemobile.com"),
        ml_client_id=_str("ML_CLIENT_ID"),
        ml_client_secret=_str("ML_CLIENT_SECRET"),
        ml_redirect_uri=_str("ML_REDIRECT_URI"),
        ml_refresh_token=_str("ML_REFRESH_TOKEN"),
        ml_access_token=_str("ML_ACCESS_TOKEN"),
        ml_base_url=_str("ML_BASE_URL", "https://api.mercadolibre.com"),
        tiktok_app_key=_str("TIKTOK_APP_KEY"),
        tiktok_app_secret=_str("TIKTOK_APP_SECRET"),
        tiktok_shop_cipher=_str("TIKTOK_SHOP_CIPHER"),
        tiktok_access_token=_str("TIKTOK_ACCESS_TOKEN"),
        tiktok_base_url=_str("TIKTOK_BASE_URL", "https://open-api.tiktokglobalshop.com"),
        instagram_access_token=_str("INSTAGRAM_ACCESS_TOKEN"),
        instagram_business_id=_str("INSTAGRAM_BUSINESS_ID"),
        instagram_base_url=_str("INSTAGRAM_BASE_URL", "https://graph.facebook.com/v21.0"),
        woocommerce_url=_str("WOOCOMMERCE_URL"),
        woocommerce_consumer_key=_str("WOOCOMMERCE_CONSUMER_KEY"),
        woocommerce_consumer_secret=_str("WOOCOMMERCE_CONSUMER_SECRET"),
    )
