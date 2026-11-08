"""Testes de memória persistente."""

from __future__ import annotations

from core.memory import MemoryStore
from database.repository import SQLiteRepository


def test_remember_e_recall(repo):
    memory = MemoryStore(repo)
    memory.remember("meta_mensal", {"valor": 1000}, scope="financeiro")
    assert memory.recall("meta_mensal", scope="financeiro") == {"valor": 1000}
    assert memory.recall("inexistente", default="nada") == "nada"


def test_sobrescreve_mesma_chave(repo):
    memory = MemoryStore(repo)
    memory.remember("preferencia", "A")
    memory.remember("preferencia", "B")
    assert memory.recall("preferencia") == "B"
    assert repo.count("memories") == 1


def test_persistencia_apos_reabrir(tmp_path):
    path = tmp_path / "mem.db"
    first = SQLiteRepository(path)
    MemoryStore(first).remember("decisao", {"acao": "investir"})
    first.close()

    second = SQLiteRepository(path)
    assert MemoryStore(second).recall("decisao") == {"acao": "investir"}
    second.close()


def test_busca_por_termo(repo):
    memory = MemoryStore(repo)
    memory.remember("fornecedor_preferido", "Distribuidora Sul")
    memory.remember("outro", "nada a ver")
    found = memory.search("fornecedor")
    assert len(found) == 1


def test_log_de_decisao(repo):
    memory = MemoryStore(repo)
    memory.log_decision("comando", "priorizar livros", "margem maior")
    decisions = memory.recent(scope="decisions")
    assert decisions and decisions[0]["value"]["decision"] == "priorizar livros"


def test_forget(repo):
    memory = MemoryStore(repo)
    memory.remember("temporario", 1)
    assert memory.forget("temporario") is True
    assert memory.recall("temporario") is None
