"""Testes da porta de entrada de um comando só."""

from __future__ import annotations

import json

from scripts import ask


class FakeAgent:
    def __init__(self, resposta) -> None:
        self.resposta = resposta
        self.recebidos: list[str] = []

    def handle_message(self, texto: str):
        self.recebidos.append(texto)
        return self.resposta


class FakeResposta:
    def __init__(self, reply: str, kind: str = "texto", wait: bool = False) -> None:
        self.reply = reply
        self.kind = kind
        self.wait_for_approval = wait


def test_executar_devolve_estrutura():
    fake = FakeAgent(FakeResposta("Operação agora", wait=True))
    resultado = ask.executar("status", agente=fake)
    assert resultado == {"ok": True, "reply": "Operação agora", "kind": "texto",
                         "wait_for_approval": True}
    assert fake.recebidos == ["status"]


def test_cli_imprime_texto(monkeypatch, capsys):
    monkeypatch.setattr(ask, "ChatAgent", lambda user="proprietario": FakeAgent(
        FakeResposta("Tudo certo")))
    codigo = ask.main(["status"])
    assert codigo == 0
    assert "Tudo certo" in capsys.readouterr().out


def test_cli_json_e_frase_com_espacos(monkeypatch, capsys):
    fake = FakeAgent(FakeResposta("Relatório X"))
    monkeypatch.setattr(ask, "ChatAgent", lambda user="proprietario": fake)
    codigo = ask.main(["analise", "o", "livro", "de", "colorir", "--json"])
    saida = json.loads(capsys.readouterr().out)
    assert codigo == 0
    assert saida["reply"] == "Relatório X"
    assert fake.recebidos == ["analise o livro de colorir"]


def test_cli_erro_retorna_codigo_1(monkeypatch, capsys):
    monkeypatch.setattr(ask, "ChatAgent", lambda user="proprietario": FakeAgent(
        FakeResposta("falhou", kind="erro")))
    assert ask.main(["qualquer coisa"]) == 1
