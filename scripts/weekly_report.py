"""Rotina SEMANAL: concorrência, margens, relatório financeiro e plano de conteúdo.

    python -m scripts.weekly_report
"""

from __future__ import annotations

import json
import sys

from core.orchestrator import Orchestrator


def main() -> int:
    orchestrator = Orchestrator()

    finance = orchestrator.handle(
        "Rotina semanal: revise as margens de todos os produtos, compare canais de venda "
        "e gere o relatório financeiro da semana.",
        requested_by="automacao_semanal",
    )
    content = orchestrator.handle(
        "Rotina semanal: planeje o conteúdo da próxima semana com pautas e roteiros.",
        requested_by="automacao_semanal",
    )

    for label, outcome in (("financeiro", finance), ("conteúdo", content)):
        print(f"\n===== relatório {label} =====")
        if outcome.get("ok"):
            print(outcome["report"])
        else:
            print(f"FALHA: {outcome.get('error')}", file=sys.stderr)

    print("\n--- resumo ---")
    print(json.dumps({
        "financeiro": {"ok": finance.get("ok"), "steps": len(finance.get("steps", []))},
        "conteudo": {"ok": content.get("ok"), "steps": len(content.get("steps", []))},
        "pending_approvals": orchestrator.tasks.pending_approvals_count(),
    }, ensure_ascii=False, indent=2))

    return 0 if finance.get("ok") and content.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
