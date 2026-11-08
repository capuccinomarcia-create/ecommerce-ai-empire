"""Executa UM comando e imprime a resposta. Feito para ser chamado de fora.

É a ponte mais curta entre "mensagem que você manda" e "código que roda":

    python -m scripts.ask status
    python -m scripts.ask "analise o livro de colorir na shopee e calcule a margem"
    python -m scripts.ask produtos --json

Qualquer pessoa ou serviço que consiga rodar um comando neste projeto (Telegram,
WhatsApp, cron, atalho no celular) usa este arquivo como porta de entrada.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from core.chat_agent import ChatAgent


def executar(texto: str, user: str = "proprietario", agente: ChatAgent | None = None) -> dict[str, Any]:
    """Roda o comando no mesmo motor do chat e devolve a resposta estruturada."""
    agente = agente or ChatAgent(user=user)
    resposta = agente.handle_message(texto)
    return {
        "ok": resposta.kind != "erro",
        "reply": resposta.reply,
        "kind": resposta.kind,
        "wait_for_approval": resposta.wait_for_approval,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Um comando, uma resposta")
    parser.add_argument("comando", nargs="+", help="o que você quer que o agente faça")
    parser.add_argument("--json", action="store_true", help="saída em JSON")
    parser.add_argument("--user", default="proprietario")
    args = parser.parse_args(argv)

    texto = " ".join(args.comando).strip()
    resultado = executar(texto, user=args.user)

    if args.json:
        print(json.dumps(resultado, ensure_ascii=False))
    else:
        print(resultado["reply"])
    return 0 if resultado["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
