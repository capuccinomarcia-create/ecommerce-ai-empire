"""Testes do bot do Telegram: parsing, permissão e fatiamento (sem rede)."""

from __future__ import annotations

import pytest

from scripts import telegram_bot as bot


class FakeChamar:
    """Simula a API do Telegram e registra o que foi enviado."""

    def __init__(self, updates: list[dict] | None = None) -> None:
        self.updates = updates or []
        self.enviados: list[tuple[str, str]] = []
        self.chamadas: list[str] = []

    def __call__(self, token: str, method: str, payload: dict | None = None, timeout: int = 30):
        self.chamadas.append(method)
        if method == "getUpdates":
            lote, self.updates = self.updates, []
            return {"ok": True, "result": lote}
        if method == "sendMessage":
            self.enviados.append((payload["chat_id"], payload["text"]))
            return {"ok": True, "result": {"message_id": 1}}
        return {"ok": True, "result": []}


def update_de_texto(chat_id: int, texto: str, update_id: int = 1) -> dict:
    return {"update_id": update_id,
            "message": {"chat": {"id": chat_id}, "text": texto}}


def test_parse_update_aceita_texto():
    assert bot.parse_update(update_de_texto(42, "status")) == ("42", "status")


def test_parse_update_ignora_sem_texto():
    assert bot.parse_update({"update_id": 1, "message": {"chat": {"id": 1}}}) is None
    assert bot.parse_update({"update_id": 2}) is None
    assert bot.parse_update(update_de_texto(1, "   ")) is None


def test_allowlist_bloqueia_estranho():
    assert bot.permitido("99", {"42"}) is False
    assert bot.permitido("42", {"42"}) is True
    assert bot.permitido("99", set()) is True   # lista vazia = aberto


def test_responder_fatia_mensagem_longa(repo, monkeypatch):
    agente = bot.ChatAgent(orchestrator=_FakeOrch(repo))
    enviados: list[tuple[str, str]] = []
    n = bot.responder(agente, "42", "ajuda", lambda c, t: enviados.append((c, t)))
    assert n == len(enviados) >= 1
    assert all(c == "42" for c, _ in enviados)


def test_loop_once_processa_e_responde(repo):
    fake = FakeChamar([update_de_texto(42, "status"), update_de_texto(42, "ajuda", 2)])
    agente = bot.ChatAgent(orchestrator=_FakeOrch(repo))
    codigo = bot.rodar("token", allowlist=set(), uma_vez=True, agente=agente, chamar=fake)
    assert codigo == 0
    assert "getUpdates" in fake.chamadas
    assert len(fake.enviados) >= 2
    assert any("Operação agora" in texto for _, texto in fake.enviados)


def test_loop_avisa_quem_nao_tem_permissao(repo):
    fake = FakeChamar([update_de_texto(99, "status")])
    agente = bot.ChatAgent(orchestrator=_FakeOrch(repo))
    bot.rodar("token", allowlist={"42"}, uma_vez=True, agente=agente, chamar=fake)
    assert fake.enviados and "privado" in fake.enviados[0][1]


def test_env_allowlist(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", " 42, 77 ,, ")
    assert bot.autorizados_do_env() == {"42", "77"}


def test_sem_token_avisa(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setattr("sys.argv", ["telegram_bot"])
    assert bot.main() == 2


class _FakeTasks:
    def pending_approvals_count(self) -> int:
        return 0


class _FakeOrch:
    def __init__(self, repo) -> None:
        self.repo = repo
        self.tasks = _FakeTasks()
        self.permissions = None

    def handle(self, command: str, requested_by: str = "proprietario") -> dict:
        return {"ok": True, "intent": {"label": "Análise"}, "report": "ok",
                "steps": [], "pending_approvals": []}
