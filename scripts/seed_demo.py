"""Carrega dados DEMO, claramente identificados.

Uso:
    python -m scripts.seed_demo            # insere os dados de demonstração
    python -m scripts.seed_demo --clear    # remove somente registros DEMO

Os registros DEMO ficam com is_demo=True e source='DEMO'. Nunca se misturam
com dados reais nas telas nem nos relatórios: o filtro é explícito.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from database.repository import get_repository
from integrations.generic_csv import import_csv

DEMO_DIR = Path(__file__).resolve().parent.parent / "demo"
SOURCES = [
    ("opportunities.csv", "opportunities"),
    ("products.csv", "products"),
    ("competitors.csv", "competitors"),
    ("suppliers.csv", "suppliers"),
]


def clear_demo(repo) -> int:
    removed = 0
    for table in ("opportunities", "products", "competitors", "suppliers", "listings", "sales"):
        removed += repo.delete_where(table, {"is_demo": True})
    return removed


def seed_demo(repo, clear_first: bool = False) -> dict:
    if clear_first:
        clear_demo(repo)
    report = {}
    for filename, entity in SOURCES:
        path = DEMO_DIR / filename
        if not path.exists():
            report[entity] = {"error": f"arquivo ausente: {path}"}
            continue
        result = import_csv(path, entity, repo, is_demo=True, source="DEMO")
        report[entity] = {k: v for k, v in result.items() if k != "rows"}
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Dados DEMO do E-COMMERCE AI EMPIRE")
    parser.add_argument("--clear", action="store_true", help="remove registros DEMO antes de inserir")
    args = parser.parse_args()

    repo = get_repository()
    if args.clear:
        removed = clear_demo(repo)
        print(f"Registros DEMO removidos: {removed}")
        return
    report = seed_demo(repo)
    for entity, result in report.items():
        print(f"{entity}: {result.get('imported', 0)} importados, "
              f"{result.get('skipped', 0)} ignorados")
    print("Dados DEMO carregados. Todos identificados com is_demo=True.")


if __name__ == "__main__":
    main()
