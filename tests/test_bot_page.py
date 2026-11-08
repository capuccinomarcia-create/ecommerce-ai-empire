"""Teste do painel: o botão "Ligar o bot" existe e reage ao estado do bot."""

from __future__ import annotations

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from scripts import bot_control  # noqa: E402

PAGINA = """
import sys
sys.path.insert(0, ".")
from dashboard import bot_page
bot_page.render()
"""


@pytest.fixture()
def pagina(tmp_path, monkeypatch):
    monkeypatch.setattr(bot_control, "DIR_DADOS", tmp_path)
    monkeypatch.setattr(bot_control, "PID_FILE", tmp_path / ".bot.pid")
    monkeypatch.setattr(bot_control, "LOG_FILE", tmp_path / "bot.log")
    return AppTest.from_string(PAGINA, default_timeout=30)


def test_botao_ligar_existe_e_tem_rotulo(pagina, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:ABC")
    pagina.run()
    assert not pagina.exception
    rotulos = [b.label for b in pagina.button]
    assert "Ligar o bot" in rotulos
    assert "Desligar" in rotulos
    assert "Reiniciar" in rotulos


def test_botao_ligar_fica_desabilitado_sem_token(pagina, monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    pagina.run()
    ligar = next(b for b in pagina.button if b.label == "Ligar o bot")
    assert ligar.disabled is True
    assert any("token" in w.value.lower() for w in pagina.warning)


def test_metricas_mostram_desligado(pagina, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:ABC")
    pagina.run()
    valores = [m.value for m in pagina.metric]
    assert "DESLIGADO" in valores


def test_clicar_ligar_liga_o_bot(pagina, monkeypatch, tmp_path):
    import sys

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:ABC")
    monkeypatch.setattr(bot_control, "COMANDO",
                        [sys.executable, "-c", "import time; time.sleep(60)"])
    pagina.run()
    ligar = next(b for b in pagina.button if b.label == "Ligar o bot")
    ligar.click().run()
    assert not pagina.exception
    assert "LIGADO" in [m.value for m in pagina.metric]
    bot_control.parar()
    assert bot_control.status().rodando is False
