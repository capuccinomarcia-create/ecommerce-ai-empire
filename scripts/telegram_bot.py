"""Leva o super agente para o Telegram: você manda mensagem, ele executa.

Não precisa de servidor público nem de domínio: usa long polling, então funciona
atrás de qualquer roteador. Requer só o token do bot.

Passo a passo (2 minutos):
  1. No Telegram, fale com @BotFather e envie /newbot. Ele devolve um token.
  2. Coloque o token no arquivo .env:  TELEGRAM_BOT_TOKEN=123456:ABC...
  3. Opcional, por segurança: TELEGRAM_ALLOWED_CHAT_IDS=seu_id
     (sem isso, qualquer pessoa que achar o bot conversa com ele)
  4. Rode:  python -m scripts.telegram_bot

O bot responde em texto puro (sem Markdown) para não quebrar com caracteres
especiais dos relatórios. Mensagens longas são fatiadas.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

from core.chat_agent import ChatAgent, chunk_text

API = "https://api.telegram.org/bot{token}/{method}"
TIMEOUT = 30


class TelegramError(RuntimeError):
    pass


def _chamar(token: str, method: str, payload: dict[str, Any] | None = None,
            timeout: int = TIMEOUT) -> dict[str, Any]:
    url = API.format(token=token, method=method)
    dados = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(url, data=dados,
                                headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout + 10) as resposta:
            corpo = json.loads(resposta.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detalhe = exc.read().decode("utf-8", "replace")[:300]
        raise TelegramError(f"HTTP {exc.code}: {detalhe}") from exc
    except urllib.error.URLError as exc:
        raise TelegramError(f"sem conexão com o Telegram: {exc.reason}") from exc
    if not corpo.get("ok"):
        raise TelegramError(str(corpo.get("description") or corpo)[:300])
    return corpo


def parse_update(update: dict[str, Any]) -> tuple[str, str] | None:
    """Extrai (chat_id, texto) de um update. Ignora o que não é mensagem de texto."""
    mensagem = update.get("message") or update.get("edited_message") or {}
    chat = mensagem.get("chat") or {}
    texto = mensagem.get("text")
    chat_id = chat.get("id")
    if not chat_id or not isinstance(texto, str) or not texto.strip():
        return None
    return str(chat_id), texto.strip()


def permitido(chat_id: str, allowlist: set[str]) -> bool:
    return not allowlist or str(chat_id) in allowlist


def autorizados_do_env() -> set[str]:
    bruto = os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "")
    return {p.strip() for p in bruto.split(",") if p.strip()}


def responder(agente: ChatAgent, chat_id: str, texto: str,
              enviar: Callable[[str, str], None]) -> int:
    """Executa o comando e responde em pedaços. Devolve quantas mensagens enviou."""
    resposta = agente.handle_message(texto)
    pedacos = chunk_text(resposta.reply or "(sem resposta)")
    for pedaco in pedacos:
        enviar(chat_id, pedaco)
    return len(pedacos)


def rodar(token: str, allowlist: set[str] | None = None, uma_vez: bool = False,
          intervalo: float = 1.0, agente: ChatAgent | None = None,
          chamar: Callable[..., dict] | None = None,
          parar: Any = None) -> int:
    allowlist = allowlist if allowlist is not None else autorizados_do_env()
    agente = agente or ChatAgent()
    chamar = chamar or _chamar
    processados = 0
    offset = 0

    def enviar(chat_id: str, texto: str) -> None:
        chamar(token, "sendMessage", {"chat_id": chat_id, "text": texto})

    while True:
        if parar is not None and parar.is_set():
            break
        try:
            corpo = chamar(token, "getUpdates", {"offset": offset, "timeout": TIMEOUT})
        except TelegramError as exc:
            print(f"[telegram] erro: {exc}", flush=True)
            if uma_vez:
                return 1
            time.sleep(5)
            continue

        updates = corpo.get("result") or []
        if not updates and uma_vez:
            break
        for update in updates:
            offset = max(offset, int(update.get("update_id", 0)) + 1)
            extraido = parse_update(update)
            if not extraido:
                continue
            chat_id, texto = extraido
            if not permitido(chat_id, allowlist):
                enviar(chat_id, "Este bot é privado. Peça acesso ao proprietário.")
                continue
            try:
                responder(agente, chat_id, texto, enviar)
            except Exception as exc:  # um erro não pode derrubar o bot
                try:
                    enviar(chat_id, f"Deu erro ao executar: {exc}"[:600])
                except Exception:
                    pass
            processados += 1
        if uma_vez:
            break
        time.sleep(intervalo)
    return 0 if processados >= 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Bot do super agente no Telegram")
    parser.add_argument("--once", action="store_true", help="processa o que chegou e sai")
    parser.add_argument("--token", default=os.getenv("TELEGRAM_BOT_TOKEN", ""))
    args = parser.parse_args()

    token = (args.token or "").strip()
    if not token:
        print("Falta o token. Crie um bot com @BotFather e coloque TELEGRAM_BOT_TOKEN no .env",
              flush=True)
        return 2
    return rodar(token, uma_vez=args.once)


if __name__ == "__main__":
    raise SystemExit(main())
