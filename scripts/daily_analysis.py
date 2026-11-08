"""Rotina DIÁRIA: pesquisa de produtos, análise e relatório de desempenho.

    python -m scripts.daily_analysis

Feito para rodar no GitHub Actions (cron diário) ou em qualquer máquina.
Sem credenciais externas funciona em modo offline + CSV.
"""

from __future__ import annotations

import json
import sys

from core.orchestrator import Orchestrator


def main() -> int:
    orchestrator = Orchestrator()
    outcome = orchestrator.handle(
        "Rotina diária: pesquise produtos com potencial, atualize a análise de oportunidades, "
        "verifique anúncios que precisam de atenção e gere o relatório de desempenho.",
        requested_by="automacao_diaria",
    )
    if not outcome.get("ok"):
        print(f"FALHA: {outcome.get('error')}", file=sys.stderr)
        return 1

    print(outcome["report"])
    print("\n--- resumo ---")
    print(json.dumps({
        "run_id": outcome["run_id"],
        "intent": outcome["intent"]["code"],
        "steps": [{"agent": s["agent"], "status": s["status"]} for s in outcome["steps"]],
        "duration_s": outcome["duration_s"],
        "report_id": outcome["report_id"],
        "pending_approvals": orchestrator.tasks.pending_approvals_count(),
    }, ensure_ascii=False, indent=2))

    failed = [s for s in outcome["steps"] if s["status"] == "falhou"]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
