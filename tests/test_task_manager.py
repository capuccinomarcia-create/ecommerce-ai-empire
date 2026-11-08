"""Testes do gerenciador de tarefas."""

from __future__ import annotations

from core.task_manager import TaskManager
from database.models import TaskStatus


def test_ciclo_de_vida(repo):
    manager = TaskManager(repo)
    task = manager.create("ceo", "command", "Teste")
    assert task["status"] == TaskStatus.PENDENTE.value

    manager.start(task["id"])
    assert manager.get(task["id"])["status"] == TaskStatus.EM_EXECUCAO.value
    assert manager.get(task["id"])["attempts"] == 1

    manager.complete(task["id"], {"summary": "ok"})
    final = manager.get(task["id"])
    assert final["status"] == TaskStatus.CONCLUIDA.value
    assert final["result"]["summary"] == "ok"
    assert final["finished_at"]


def test_retentativas(repo):
    manager = TaskManager(repo)
    task = manager.create("ceo", "command", "Falha")
    manager.start(task["id"])
    manager.fail(task["id"], "erro 1")
    assert manager.get(task["id"])["status"] == TaskStatus.PENDENTE.value

    manager.start(task["id"])
    manager.fail(task["id"], "erro 2")
    assert manager.get(task["id"])["status"] == TaskStatus.PENDENTE.value

    manager.start(task["id"])
    manager.fail(task["id"], "erro 3")
    assert manager.get(task["id"])["status"] == TaskStatus.FALHOU.value


def test_deduplicacao(repo):
    manager = TaskManager(repo)
    first = manager.create("ceo", "command", "Igual", dedupe_key="abc")
    second = manager.create("ceo", "command", "Igual de novo", dedupe_key="abc")
    assert second["_duplicate"] is True
    assert second["id"] == first["id"]
    assert repo.count("tasks") == 1


def test_deduplicacao_nao_bloqueia_depois_de_concluida(repo):
    manager = TaskManager(repo)
    first = manager.create("ceo", "command", "Igual", dedupe_key="xyz")
    manager.start(first["id"])
    manager.complete(first["id"], {"summary": "ok"})
    second = manager.create("ceo", "command", "Igual", dedupe_key="xyz")
    assert second["_duplicate"] is False
    assert second["id"] != first["id"]


def test_cancelamento_e_eventos(repo):
    manager = TaskManager(repo)
    task = manager.create("ceo", "command", "Cancelar")
    manager.cancel(task["id"], "pedido do proprietário")
    assert manager.get(task["id"])["status"] == TaskStatus.CANCELADA.value
    events = manager.events(task["id"])
    assert [e["event"] for e in events] == ["criada", "cancelada"]


def test_aguardando_aprovacao(repo):
    manager = TaskManager(repo)
    task = manager.create("ceo", "command", "Aprovar")
    manager.await_approval(task["id"], "apr_1")
    assert manager.get(task["id"])["status"] == TaskStatus.AGUARDANDO_APROVACAO.value
    manager.resume(task["id"])
    assert manager.get(task["id"])["status"] == TaskStatus.EM_EXECUCAO.value


def test_stats(repo):
    manager = TaskManager(repo)
    manager.create("ceo", "a", "1")
    manager.create("ceo", "b", "2")
    stats = manager.stats()
    assert stats["total"] == 2
    assert stats[TaskStatus.PENDENTE.value] == 2
