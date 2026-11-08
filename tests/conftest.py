"""Fixtures dos testes. Nenhum teste toca a rede."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def repo(tmp_path):
    from database.repository import SQLiteRepository

    repository = SQLiteRepository(tmp_path / "test.db")
    yield repository
    repository.close()


@pytest.fixture()
def orchestrator(repo):
    from core.orchestrator import Orchestrator

    return Orchestrator(repo=repo)


@pytest.fixture()
def demo_orchestrator(orchestrator):
    from scripts.seed_demo import seed_demo

    seed_demo(orchestrator.repo)
    return orchestrator
