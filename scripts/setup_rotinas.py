"""Cadastra (ou atualiza) as rotinas automáticas de venda no banco.

    python -m scripts.setup_rotinas            # cria o que falta, calcula a próxima
    python -m scripts.setup_rotinas --listar   # só mostra
    python -m scripts.setup_rotinas --ativar   # garante todas ativas
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

from agents.automation import DEFAULT_AUTOMATIONS
from core.scheduler import FUSO, Agendador, proximo_disparo
from database.repository import get_repository


def sincronizar(repo, ativar: bool = False) -> dict:
    criadas, atualizadas = [], []
    agora = datetime.now(FUSO)
    for item in DEFAULT_AUTOMATIONS:
        existente = repo.find_one("automations", {"name": item["name"]})
        proxima = proximo_disparo(item["schedule_cron"], agora).isoformat(timespec="seconds")
        dados = {"job": item["job"], "schedule_cron": item["schedule_cron"],
                 "config": {"description": item["description"], "timezone": str(FUSO)}}
        if existente:
            if ativar:
                dados["enabled"] = True
            if not existente.get("next_run_at"):
                dados["next_run_at"] = proxima
            repo.update("automations", existente["id"], dados)
            atualizadas.append(item["name"])
        else:
            repo.insert("automations", {**dados, "name": item["name"], "enabled": True,
                                        "next_run_at": proxima})
            criadas.append(item["name"])
    return {"criadas": criadas, "atualizadas": atualizadas,
            "total": repo.count("automations")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rotinas automáticas de venda")
    parser.add_argument("--listar", action="store_true")
    parser.add_argument("--ativar", action="store_true")
    args = parser.parse_args(argv)

    repo = get_repository()
    if args.listar:
        rotinas = Agendador(repo).rotinas()
        if not rotinas:
            print("Nenhuma rotina cadastrada.")
            return 0
        for r in rotinas:
            print(f"{r.get('name'):<24} {r.get('schedule_cron'):<14} "
                  f"{'ativa' if r.get('enabled') else 'pausada':<8} "
                  f"próxima: {r.get('next_run_at') or '—'}")
        return 0

    resultado = sincronizar(repo, ativar=args.ativar)
    print(f"rotinas: {len(resultado['criadas'])} criadas, "
          f"{len(resultado['atualizadas'])} atualizadas, {resultado['total']} no total")
    for nome in resultado["criadas"]:
        print(f"  + {nome}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
