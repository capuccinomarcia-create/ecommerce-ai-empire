"""Plano de venda do dia: preço, estoque e o que falta no anúncio.

    python -m scripts.sales_plan
    python -m scripts.sales_plan --json
"""

from __future__ import annotations

import argparse
import json
import sys

from core.sales_ops import SalesOperator, resumo_texto
from database.repository import get_repository


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plano de venda dos produtos ativos")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--margem", type=float, default=30.0, help="margem alvo em %%")
    parser.add_argument("--prazo", type=int, default=7, help="prazo do fornecedor em dias")
    args = parser.parse_args(argv)

    operador = SalesOperator(get_repository(), margem_alvo_pct=args.margem,
                             prazo_fornecedor_dias=args.prazo)
    plano = operador.plano()
    if args.json:
        print(json.dumps(plano, ensure_ascii=False, indent=2))
    else:
        print(resumo_texto(plano))
    return 0


if __name__ == "__main__":
    sys.exit(main())
