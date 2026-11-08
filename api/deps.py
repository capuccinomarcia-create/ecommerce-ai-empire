"""Dependências compartilhadas da API e do painel."""

from __future__ import annotations

from functools import lru_cache

from core.ai_provider import AIService
from core.config import get_settings
from core.orchestrator import Orchestrator
from database.repository import get_repository


@lru_cache(maxsize=1)
def get_orchestrator() -> Orchestrator:
    repo = get_repository()
    settings = get_settings()
    return Orchestrator(repo=repo, settings=settings, ai=AIService(settings, repo))


def reset_orchestrator() -> None:
    """Usado pelos testes e após trocar configuração de banco."""
    get_orchestrator.cache_clear()
