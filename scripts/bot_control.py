"""Liga, desliga e mostra o estado do bot — o que o botão do painel aciona.

O painel publicado no GitHub Pages é HTML estático: um botão lá não consegue iniciar
processo nenhum. Quem liga o bot de verdade é este módulo, chamado pelo painel
Streamlit (que roda na sua máquina/VM) ou pelo terminal:

    python -m scripts.bot_control start
    python -m scripts.bot_control status
    python -m scripts.bot_control log --lines 40
    python -m scripts.bot_control stop

Guardas:
  * só sobe com TELEGRAM_BOT_TOKEN configurado;
  * um bot por vez (arquivo .pid em data/);
  * processo órfão é detectado e limpo sozinho.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
DIR_DADOS = Path(os.getenv("DATA_DIR") or (RAIZ / "data"))
PID_FILE = DIR_DADOS / ".bot.pid"
LOG_FILE = DIR_DADOS / "bot.log"
COMANDO = [sys.executable, "-m", "scripts.run_agent"]


@dataclass
class EstadoBot:
    rodando: bool
    pid: int | None = None
    desde: str | None = None
    token_configurado: bool = False
    detalhe: str = ""
    log_recente: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "rodando": self.rodando,
            "pid": self.pid,
            "desde": self.desde,
            "token_configurado": self.token_configurado,
            "detalhe": self.detalhe,
        }

    @property
    def rotulo(self) -> str:
        if self.rodando:
            return "ligado"
        return "desligado"


def _pid_vivo(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":  # Windows: sem sinal, consulta o processo
        try:
            saida = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"],
                                   capture_output=True, text=True, timeout=10).stdout
            return str(pid) in saida
        except Exception:
            return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def ler_pid() -> tuple[int | None, str | None]:
    if not PID_FILE.exists():
        return None, None
    try:
        dados = json.loads(PID_FILE.read_text(encoding="utf-8"))
        return int(dados.get("pid")), dados.get("started_at")
    except Exception:
        return None, None


def _token_ok() -> bool:
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    return bool(token) and ":" in token


def ultimas_linhas(limite: int = 20) -> str:
    if not LOG_FILE.exists():
        return ""
    try:
        linhas = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return ""
    return "\n".join(linhas[-limite:])


def status() -> EstadoBot:
    pid, desde = ler_pid()
    if pid and _pid_vivo(pid):
        return EstadoBot(True, pid, desde, _token_ok(), "bot em execução",
                         ultimas_linhas())
    if pid:
        # arquivo sobrou de um processo que morreu
        PID_FILE.unlink(missing_ok=True)
        return EstadoBot(False, None, None, _token_ok(),
                         "o bot havia caído; estado limpo", ultimas_linhas())
    return EstadoBot(False, None, None, _token_ok(), "bot parado", ultimas_linhas())


def start(forcar: bool = False) -> tuple[bool, str]:
    atual = status()
    if atual.rodando and not forcar:
        return False, f"o bot já está ligado (pid {atual.pid})"
    if atual.rodando and forcar:
        parar()
    if not _token_ok():
        return False, ("falta TELEGRAM_BOT_TOKEN. Crie o bot com @BotFather e coloque "
                       "o token no .env")
    DIR_DADOS.mkdir(parents=True, exist_ok=True)
    log = open(LOG_FILE, "a", encoding="utf-8")
    log.write(f"\n--- iniciado em {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
    log.flush()
    processo = subprocess.Popen(
        COMANDO, cwd=str(RAIZ), stdout=log, stderr=subprocess.STDOUT,
        start_new_session=(os.name != "nt"),
    )
    PID_FILE.write_text(json.dumps({
        "pid": processo.pid,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }), encoding="utf-8")
    time.sleep(1.5)
    if processo.poll() is not None:
        PID_FILE.unlink(missing_ok=True)
        return False, "o processo morreu ao subir. Veja o log:\n" + ultimas_linhas(15)
    return True, f"bot ligado (pid {processo.pid}). Já pode mandar mensagem no Telegram."


def parar(timeout: float = 10.0) -> tuple[bool, str]:
    pid, _ = ler_pid()
    if not pid:
        return False, "o bot já estava parado"
    if not _pid_vivo(pid):
        PID_FILE.unlink(missing_ok=True)
        return False, "o bot já estava parado (estado limpo)"
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           capture_output=True, timeout=timeout)
        else:
            os.kill(pid, signal.SIGTERM)
            limite = time.time() + timeout
            while time.time() < limite and _pid_vivo(pid):
                time.sleep(0.2)
            if _pid_vivo(pid):
                os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except Exception as exc:
        return False, f"não consegui encerrar: {exc}"
    finally:
        PID_FILE.unlink(missing_ok=True)
    return True, f"bot desligado (pid {pid})"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Controle do bot")
    parser.add_argument("acao", choices=["start", "stop", "restart", "status", "log"])
    parser.add_argument("--lines", type=int, default=30)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.acao == "start":
        ok, msg = start()
    elif args.acao == "stop":
        ok, msg = parar()
    elif args.acao == "restart":
        parar()
        ok, msg = start()
    elif args.acao == "log":
        print(ultimas_linhas(args.lines) or "(sem log ainda)")
        return 0
    else:
        estado = status()
        if args.json:
            print(json.dumps(estado.to_dict(), ensure_ascii=False))
        else:
            print(f"bot: {estado.rotulo} · {estado.detalhe}")
            if estado.log_recente:
                print("\n--- últimas linhas do log ---")
                print(estado.log_recente)
        return 0

    print(msg)
    return 0 if ok else 1



if __name__ == "__main__":
    raise SystemExit(main())
