"""Teste de ponta a ponta: mensagem entra, comando executa, resposta volta.

Usa o processo real do supervisor (scripts.run_agent) e um Telegram falso, para
provar que a cadeia inteira funciona sem depender de rede nem de token real.
"""

from __future__ import annotations

import time

import pytest

from core.chat_agent import ChatAgent
from scripts import run_agent
from scripts import telegram_bot as bot


class TelegramFalso:
    def __init__(self, mensagens: list[str]) -> None:
        self.fila = [{"update_id": i + 1,
                      "message": {"chat": {"id": 42}, "text": texto}}
                     for i, texto in enumerate(mensagens)]
        self.enviados: list[str] = []

    def __call__(self, token, method, payload=None, timeout=30):
        if method == "getUpdates":
            lote, self.fila = self.fila, []
            return {"ok": True, "result": lote}
        if method == "sendMessage":
            self.enviados.append(payload["text"])
            return {"ok": True, "result": {"message_id": len(self.enviados)}}
        return {"ok": True, "result": []}


def test_mensagem_do_telegram_executa_comando(repo):
    telegram = TelegramFalso(["status", "ajuda", "vendas"])
    agente = ChatAgent(orchestrator=_Orquestrador(repo))

    def bot_falso(token, parar=None, agente=None):
        return bot.rodar("token", allowlist={"42"}, uma_vez=True,
                         agente=agente, chamar=telegram)

    supervisor = run_agent.Supervisor(
        rodar_bot_fn=bot_falso, agente_factory=lambda: agente, token="123:ABC"
    )
    supervisor.start()
    limite = time.time() + 10
    while not telegram.enviados and time.time() < limite:
        time.sleep(0.05)
    supervisor.stop(timeout=5)

    texto = "\n".join(telegram.enviados)
    assert "Operação agora" in texto          # status
    assert "Comandos que eu executo" in texto  # ajuda
    assert "produto ativo" in texto.lower()    # vendas sem catálogo: orienta
    assert supervisor.erros == []


def test_bloqueia_remetente_desconhecido(repo):
    telegram = TelegramFalso(["status"])
    agente = ChatAgent(orchestrator=_Orquestrador(repo))
    bot.rodar("token", allowlist={"777"}, uma_vez=True, agente=agente, chamar=telegram)
    assert telegram.enviados and "privado" in telegram.enviados[0]
    assert "Operação agora" not in " ".join(telegram.enviados)


def test_comando_de_venda_executa_o_motor(repo):
    telegram = TelegramFalso(["cadastre o livro de colorir por 39,90"])
    agente = ChatAgent(orchestrator=_Orquestrador(repo))
    bot.rodar("token", allowlist=set(), uma_vez=True, agente=agente, chamar=telegram)
    texto = " ".join(telegram.enviados)
    assert "Intenção" in texto or "relatório" in texto.lower()


class _Orquestrador:
    def __init__(self, repo) -> None:
        self.repo = repo
        self.permissions = None

        class _T:
            def pending_approvals_count(self) -> int:
                return 0

        self.tasks = _T()

    def handle(self, command: str, requested_by: str = "proprietario") -> dict:
        return {"ok": True, "intent": {"label": "Cadastro de produto"},
                "report": "Produto cadastrado e margem calculada.",
                "steps": [{"agent": "ceo", "status": "concluida"}],
                "pending_approvals": []}


def test_comando_rotinas_responde_no_chat(repo):
    from scripts.setup_rotinas import sincronizar

    sincronizar(repo)
    telegram = TelegramFalso(["rotinas"])
    agente = ChatAgent(orchestrator=_Orquestrador(repo))
    bot.rodar("token", allowlist={"42"}, uma_vez=True, agente=agente, chamar=telegram)
    texto = " ".join(telegram.enviados)
    assert "Rotinas automáticas" in texto
    assert "plano_de_venda" in texto


def test_cadastrar_rotinas_pelo_chat(repo):
    telegram = TelegramFalso(["cadastrar rotinas"])
    agente = ChatAgent(orchestrator=_Orquestrador(repo))
    bot.rodar("token", allowlist={"42"}, uma_vez=True, agente=agente, chamar=telegram)
    texto = " ".join(telegram.enviados)
    assert "Rotinas de venda prontas" in texto
    assert repo.count("automations") == 5
