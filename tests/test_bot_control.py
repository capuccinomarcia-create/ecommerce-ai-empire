"""Testes do botão que liga/desliga o bot: processo real, estado e limpeza."""

from __future__ import annotations

import os
import sys
import time

import pytest

from scripts import bot_control


@pytest.fixture()
def dir_dados(tmp_path, monkeypatch):
    monkeypatch.setattr(bot_control, "DIR_DADOS", tmp_path)
    monkeypatch.setattr(bot_control, "PID_FILE", tmp_path / ".bot.pid")
    monkeypatch.setattr(bot_control, "LOG_FILE", tmp_path / "bot.log")
    monkeypatch.setattr(
        bot_control, "COMANDO", [sys.executable, "-c", "import time; time.sleep(120)"]
    )
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:ABC")
    return tmp_path


def test_estado_inicial_desligado(dir_dados):
    estado = bot_control.status()
    assert estado.rodando is False
    assert estado.rotulo == "desligado"
    assert estado.token_configurado is True


def test_sem_token_nao_liga(dir_dados, monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    ok, mensagem = bot_control.start()
    assert ok is False
    assert "TELEGRAM_BOT_TOKEN" in mensagem
    assert bot_control.status().rodando is False


def test_liga_e_desliga_de_verdade(dir_dados):
    ok, mensagem = bot_control.start()
    assert ok is True, mensagem
    tempo_limite = time.time() + 5
    estado = bot_control.status()
    while estado.rodando is False and time.time() < tempo_limite:
        time.sleep(0.1)
        estado = bot_control.status()
    assert estado.rodando is True
    assert estado.pid and estado.pid > 0
    assert "iniciado" in bot_control.ultimas_linhas()

    ok, mensagem = bot_control.parar()
    assert ok is True, mensagem
    assert bot_control.status().rodando is False


def test_nao_liga_duas_vezes(dir_dados):
    bot_control.start()
    try:
        ok, mensagem = bot_control.start()
        assert ok is False
        assert "já está ligado" in mensagem
    finally:
        bot_control.parar()


def test_reiniciar_troca_o_processo(dir_dados):
    bot_control.start()
    primeiro = bot_control.status().pid
    bot_control.parar()
    ok, _ = bot_control.start()
    assert ok is True
    segundo = bot_control.status().pid
    assert segundo != primeiro
    bot_control.parar()


def test_pid_orfao_e_limpo(dir_dados):
    (dir_dados / ".bot.pid").write_text('{"pid": 999999, "started_at": "2026-01-01"}')
    estado = bot_control.status()
    assert estado.rodando is False
    assert "caído" in estado.detalhe or "parado" in estado.detalhe
    assert not (dir_dados / ".bot.pid").exists()


def test_processo_que_morre_ao_subir_avisa(dir_dados, monkeypatch):
    monkeypatch.setattr(bot_control, "COMANDO",
                        [sys.executable, "-c", "raise SystemExit('falhou de proposito')"])
    ok, mensagem = bot_control.start()
    assert ok is False
    assert "morreu" in mensagem


def test_desligar_quando_ja_parado(dir_dados):
    ok, mensagem = bot_control.parar()
    assert ok is False
    assert "já estava parado" in mensagem


def test_cli_status_e_json(dir_dados, capsys):
    assert bot_control.main(["status"]) == 0
    assert "desligado" in capsys.readouterr().out
    assert bot_control.main(["status", "--json"]) == 0
    assert '"rodando"' in capsys.readouterr().out


def test_cli_log_sem_arquivo(dir_dados, capsys):
    assert bot_control.main(["log"]) == 0
    assert "sem log" in capsys.readouterr().out
