"""Processo único que mantém o super agente vivo sem ninguém abrir painel.

    python -m scripts.run_agent --check      # diz o que falta antes de subir
    python -m scripts.run_agent              # bot + comando no celular
    python -m scripts.run_agent --autonomy   # bot + ciclos autônomos

É isso que roda dentro do Dockerfile: um processo, dois trabalhadores.

• bot: responde no Telegram (long polling, sem porta aberta)
• autonomia: roda ciclo de análise no horário permitido (opcional)

Segurança: compra, pagamento e publicação continuam dependendo da sua aprovação.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
import time
from typing import Any, Callable

from core.autonomy import AutonomousSuperAgent
from core.scheduler import Agendador
from core.chat_agent import ChatAgent
from database.repository import get_repository
from scripts.telegram_bot import TelegramError, rodar as rodar_bot

INTERVALO_CICLO = 300  # segundos entre checagens de "posso rodar um ciclo?"
INTERVALO_AGENDA = 60  # segundos entre checagens de rotinas vencidas


def check_ambiente(env: dict[str, str] | None = None) -> list[str]:
    """Problemas que impedem o agente de rodar sozinho. Vazio = pronto."""
    env = dict(os.environ if env is None else env)
    problemas: list[str] = []
    token = (env.get("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        problemas.append("TELEGRAM_BOT_TOKEN ausente: crie o bot com @BotFather e cole o token")
    elif ":" not in token:
        problemas.append("TELEGRAM_BOT_TOKEN inválido: o formato é 123456:ABC-DEF...")
    if env.get("SUPABASE_URL") and not env.get("SUPABASE_KEY"):
        problemas.append("SUPABASE_URL definido sem SUPABASE_KEY")
    return problemas


def check_dados() -> list[str]:
    """Avisos (não bloqueiam): o agente roda, mas responde que falta dado."""
    from core import data_mode

    repo = get_repository()
    config = data_mode.resumo(repo)
    return [f"{item['item']}: {item['detalhe']}" for item in config["itens"] if not item["ok"]]


class Supervisor:
    """Sobe bot e autonomia em threads e desliga os dois com um pedido de parada."""

    def __init__(self, rodar_bot_fn: Callable[..., int] | None = None,
                 agente_factory: Callable[[], ChatAgent] | None = None,
                 autonomia_factory: Callable[[], AutonomousSuperAgent] | None = None,
                 token: str | None = None, autonomy: bool = False,
                 scheduler: bool = True,
                 agendador_factory: Callable[[], Agendador] | None = None) -> None:
        self.parar = threading.Event()
        self.threads: list[threading.Thread] = []
        self.rodar_bot_fn = rodar_bot_fn or rodar_bot
        self.agente_factory = agente_factory or ChatAgent
        self.autonomia_factory = autonomia_factory or AutonomousSuperAgent
        self.token = token if token is not None else os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.autonomy = autonomy
        self.scheduler = scheduler
        self.agendador_factory = agendador_factory or Agendador
        self.erros: list[str] = []

    def _bot(self) -> None:
        try:
            self.rodar_bot_fn(self.token, parar=self.parar, agente=self.agente_factory())
        except TelegramError as exc:
            self.erros.append(f"bot: {exc}")
        except Exception as exc:  # nunca derruba o processo inteiro por causa do bot
            self.erros.append(f"bot: {exc}")

    def _autonomia(self) -> None:
        try:
            agente = self.autonomia_factory()
            while not self.parar.is_set():
                ciclo = agente.run_cycle()
                if self.parar.wait(INTERVALO_CICLO):
                    break
                if ciclo.get("status") == "erro":
                    self.erros.append(f"autonomia: {ciclo.get('reason')}")
        except Exception as exc:
            self.erros.append(f"autonomia: {exc}")

    def _agenda(self) -> None:
        try:
            agendador = self.agendador_factory()
            while not self.parar.is_set():
                for item in agendador.tick():
                    if item.get("status") != "ok":
                        self.erros.append(f"rotina {item.get('name')}: {item.get('summary')}")
                if self.parar.wait(INTERVALO_AGENDA):
                    break
        except Exception as exc:
            self.erros.append(f"agendador: {exc}")

    def start(self) -> None:
        alvos = [("bot", self._bot)]
        if self.autonomy:
            alvos.append(("autonomia", self._autonomia))
        if self.scheduler:
            alvos.append(("agenda", self._agenda))
        for nome, alvo in alvos:
            thread = threading.Thread(target=alvo, name=nome, daemon=True)
            thread.start()
            self.threads.append(thread)

    def stop(self, timeout: float = 10.0) -> None:
        self.parar.set()
        for thread in self.threads:
            thread.join(timeout)

    def vivo(self) -> bool:
        return any(t.is_alive() for t in self.threads)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mantém o super agente rodando sozinho")
    parser.add_argument("--check", action="store_true", help="só valida o ambiente e sai")
    parser.add_argument("--autonomy", action="store_true", help="liga também os ciclos autônomos")
    parser.add_argument("--no-scheduler", action="store_true",
                        help="não executa as rotinas automáticas de venda")
    args = parser.parse_args(argv)

    problemas = check_ambiente()
    if args.check:
        if problemas:
            print("Não está pronto para rodar sozinho:")
            for problema in problemas:
                print(f"  - {problema}")
        else:
            print("Ambiente ok: token do Telegram presente.")
        avisos = check_dados()
        if avisos:
            print("\nDados que faltam (o agente roda, mas avisa que falta):")
            for aviso in avisos:
                print(f"  - {aviso}")
        return 1 if problemas else 0

    if problemas:
        for problema in problemas:
            print(f"erro: {problema}", file=sys.stderr)
        return 2

    supervisor = Supervisor(autonomy=args.autonomy, scheduler=not args.no_scheduler)

    def encerrar(*_args: Any) -> None:
        print("encerrando...", flush=True)
        supervisor.stop()

    signal.signal(signal.SIGTERM, encerrar)
    signal.signal(signal.SIGINT, encerrar)

    supervisor.start()
    print("agente no ar: mande mensagem no Telegram. Ctrl+C para encerrar.", flush=True)
    try:
        while supervisor.vivo():
            time.sleep(1)
    finally:
        supervisor.stop()
    for erro in supervisor.erros:
        print(f"aviso: {erro}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
