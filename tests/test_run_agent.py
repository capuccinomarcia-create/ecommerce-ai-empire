"""Testes do processo que mantém o agente vivo sozinho."""

from __future__ import annotations

import threading
import time

import pytest

from scripts import run_agent


def test_check_ambiente_sem_token():
    problemas = run_agent.check_ambiente({})
    assert any("TELEGRAM_BOT_TOKEN" in p for p in problemas)


def test_check_ambiente_token_mal_formado():
    problemas = run_agent.check_ambiente({"TELEGRAM_BOT_TOKEN": "abc"})
    assert any("inválido" in p for p in problemas)


def test_check_ambiente_ok():
    assert run_agent.check_ambiente({"TELEGRAM_BOT_TOKEN": "123:ABC"}) == []


def test_check_ambiente_supabase_incompleto():
    problemas = run_agent.check_ambiente({"TELEGRAM_BOT_TOKEN": "123:ABC",
                                          "SUPABASE_URL": "https://x.supabase.co"})
    assert any("SUPABASE_KEY" in p for p in problemas)


def test_check_dados_lista_pendencias(repo, monkeypatch):
    monkeypatch.setattr(run_agent, "get_repository", lambda: repo)
    avisos = run_agent.check_dados()
    assert isinstance(avisos, list)


def test_supervisor_sobe_bot_e_para():
    chamadas: list[str] = []
    parou = threading.Event()

    def fake_bot(token, parar=None, agente=None):
        chamadas.append(token)
        while parar and not parar.is_set():
            time.sleep(0.01)
        parou.set()
        return 0

    supervisor = run_agent.Supervisor(rodar_bot_fn=fake_bot,
                                      agente_factory=lambda: object(),
                                      token="123:ABC")
    supervisor.start()
    time.sleep(0.1)
    assert chamadas == ["123:ABC"]
    assert supervisor.vivo() is True
    supervisor.stop(timeout=5)
    assert parou.is_set()
    assert supervisor.vivo() is False


def test_supervisor_nao_morre_se_bot_falhar():
    def bot_quebrado(token, parar=None, agente=None):
        raise RuntimeError("telegram fora do ar")

    supervisor = run_agent.Supervisor(rodar_bot_fn=bot_quebrado,
                                      agente_factory=lambda: object(),
                                      token="123:ABC")
    supervisor.start()
    time.sleep(0.1)
    supervisor.stop(timeout=5)
    assert any("telegram fora do ar" in erro for erro in supervisor.erros)


def test_supervisor_autonomia_roda_ciclos(monkeypatch):
    monkeypatch.setattr(run_agent, "INTERVALO_CICLO", 0.01)
    ciclos: list[str] = []

    class FakeAgente:
        def run_cycle(self, force: bool = False):
            ciclos.append("ciclo")
            return {"status": "ok"}

    def fake_bot(token, parar=None, agente=None):
        while parar and not parar.is_set():
            time.sleep(0.01)
        return 0

    supervisor = run_agent.Supervisor(rodar_bot_fn=fake_bot,
                                      agente_factory=lambda: object(),
                                      autonomia_factory=FakeAgente,
                                      token="123:ABC", autonomy=True)
    supervisor.start()
    time.sleep(0.2)
    supervisor.stop(timeout=5)
    assert len(ciclos) >= 2


def test_main_check_falha_sem_token(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert run_agent.main(["--check"]) == 1


def test_main_recusa_subir_sem_token(monkeypatch, capsys):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert run_agent.main([]) == 2
    assert "TELEGRAM_BOT_TOKEN" in capsys.readouterr().err


def test_supervisor_roda_o_agendador(monkeypatch):
    monkeypatch.setattr(run_agent, "INTERVALO_AGENDA", 0.01)
    ticks: list[str] = []

    class FakeAgendador:
        def tick(self, agora=None, forcar=None):
            ticks.append("tick")
            return [{"name": "plano_de_venda", "status": "ok", "summary": "ok"}]

    def fake_bot(token, parar=None, agente=None):
        while parar and not parar.is_set():
            time.sleep(0.01)
        return 0

    supervisor = run_agent.Supervisor(rodar_bot_fn=fake_bot,
                                      agente_factory=lambda: object(),
                                      agendador_factory=FakeAgendador,
                                      token="123:ABC", scheduler=True)
    supervisor.start()
    time.sleep(0.2)
    supervisor.stop(timeout=5)
    assert len(ticks) >= 2


def test_supervisor_pode_ficar_sem_agendador():
    supervisor = run_agent.Supervisor(rodar_bot_fn=lambda *a, **k: 0,
                                      agente_factory=lambda: object(),
                                      token="123:ABC", scheduler=False)
    supervisor.start()
    supervisor.stop(timeout=5)
    assert [t.name for t in supervisor.threads] == ["bot"]
