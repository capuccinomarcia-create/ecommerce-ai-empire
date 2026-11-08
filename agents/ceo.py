"""AGENTE 1 - CEO AI: coordena, consolida e apresenta."""

from __future__ import annotations

from typing import Any

from agents.base import AgentContext, AgentResult, BaseAgent


class CEOAgent(BaseAgent):
    name = "ceo"
    role = "CEO AI"
    description = (
        "Coordena a operação: interpreta o pedido do proprietário, distribui tarefas "
        "aos especialistas, confere consistência dos resultados e apresenta a conclusão."
    )
    capabilities = [
        "planejar", "delegar", "consolidar", "priorizar", "pedir_aprovacao",
    ]
    tools = [
        {"name": "plan", "description": "Transforma o pedido em tarefas para os especialistas."},
        {"name": "consolidate", "description": "Reúne e valida os resultados dos especialistas."},
        {"name": "request_approval", "description": "Abre aprovação para ações de risco."},
    ]

    def execute(self) -> AgentResult:
        payload = self.ctx.payload()
        mode = payload.get("mode", "consolidate")
        if mode == "plan":
            return self._plan(payload)
        return self._consolidate(payload)

    # ------------------------------------------------------------------ plano --
    def _plan(self, payload: dict[str, Any]) -> AgentResult:
        from core.planner import detect_intent, build_plan

        command = payload.get("command", "")
        intent = detect_intent(command)
        steps = build_plan(intent, command)
        return AgentResult(
            summary=(
                f"Intenção identificada: {intent['label']}. "
                f"{len(steps)} tarefas distribuídas entre especialistas."
            ),
            data={"intent": intent, "steps": steps},
            findings=[
                f"Intenção: {intent['label']} (confiança {intent['confidence']:.0%})",
                "Especialistas acionados: "
                + ", ".join(dict.fromkeys(step["agent"] for step in steps)),
            ],
            next_actions=["Executar as tarefas na ordem definida pelo plano."],
        )

    # ------------------------------------------------------------ consolidação --
    def _consolidate(self, payload: dict[str, Any]) -> AgentResult:
        results = self.ctx.shared_results()
        findings: list[str] = []
        gaps: list[str] = []
        actions: list[str] = []
        warnings: list[str] = []
        demo_used = False

        for item in results:
            findings.extend((item.get("findings") or [])[:4])
            gaps.extend(item.get("data_gaps") or [])
            actions.extend(item.get("next_actions") or [])
            warnings.extend(item.get("warnings") or [])
            data = item.get("data") or {}
            if data.get("demo_mode") or data.get("is_demo"):
                demo_used = True

        # deduplicar preservando ordem
        def unique(values: list[str]) -> list[str]:
            seen: set[str] = set()
            out: list[str] = []
            for value in values:
                if value and value not in seen:
                    seen.add(value)
                    out.append(value)
            return out

        findings, gaps, actions, warnings = map(unique, (findings, gaps, actions, warnings))

        summary_points = findings[:12]
        if not summary_points:
            summary_points = [
                "Nenhum resultado numérico foi produzido: faltam dados de catálogo/CSV ou "
                "integrações conectadas."
            ]

        intro = (
            f"Consolidação de {len(results)} especialistas para o pedido: "
            f"{payload.get('command', 'análise geral')}"
        )
        narrative, provider = self.narrate(
            intro,
            [f"{item.get('summary','')}" for item in results][:8] + summary_points[:6],
            closing="Ações de risco (compra, preço, publicação) ficam bloqueadas até sua aprovação.",
        )

        return AgentResult(
            summary=f"Resultados de {len(results)} especialistas consolidados.",
            data={"results": results, "demo_mode": demo_used, "summary_points": summary_points},
            findings=summary_points,
            warnings=warnings,
            data_gaps=gaps,
            next_actions=actions or ["Revisar as oportunidades e aprovar os próximos passos."],
            narrative=narrative,
            ai_provider=provider,
        )
