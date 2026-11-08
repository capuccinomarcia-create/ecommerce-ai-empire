"""Chat no terminal: converse com o super agente.

    python -m core.chat

Digite em português normal. "ajuda" lista os comandos, "sair" encerra.
"""

from __future__ import annotations

import sys

from core.chat_agent import ChatAgent

BANNER = """E-COMMERCE AI EMPIRE — agente conversacional
Escreva o comando em português. "ajuda" mostra o que eu faço, "sair" encerra.
"""


def main() -> int:
    agente = ChatAgent()
    print(BANNER)
    try:
        while True:
            try:
                texto = input("você › ").strip()
            except EOFError:
                print()
                break
            if not texto:
                continue
            if texto.lower() in {"sair", "exit", "quit", "/sair"}:
                break
            resposta = agente.handle_message(texto)
            print(f"\nagente › {resposta.reply}\n")
    except KeyboardInterrupt:
        print("\nAté mais.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
