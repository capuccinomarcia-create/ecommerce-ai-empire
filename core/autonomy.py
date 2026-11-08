"""Super agente autônomo: o CEO que roda sozinho, dentro de limites.

O que ele faz sem ninguém pedir:
  * acorda no intervalo definido, escolhe o próximo objetivo da fila,
  * roda o plano do CEO (pesquisa, análise, margem, prazo, conteúdo),
  * grava relatório, histórico e custo,
  * e para sozinho quando erra demais ou quando você manda.

O que ele NUNCA faz sem aprovação: comprar, pagar, publicar anúncio, alterar
preço, mandar mensagem em massa. Essas ações caem na fila de aprovação e
esperam você. Não existe "autonomia" que gaste seu dinheiro sozinha aqui.

Uso:
    python -m core.autonomy --status
    python -m core.autonomy --once            # um ciclo agora
    python -m core.autonomy --loop            # roda até você parar
    python -m core.autonomy --pause --motivo "revisar custos"
    python -m core.autonomy --resume
"""

from __future__ import annotations

import argparse
import json
import time
import traceback
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Callable

from core.config import get_settings
from core.orchestrator import Orchestrator
from core.utils import local_now, now_iso

STATE_KEY = "autonomy_state"

# Objetivos que ele reveza. Cada um é um comando de verdade para o CEO.
OBJETIVOS_PADRAO: tuple[str, ...] = (
    "Rotina autônoma: pesquise produtos com potencial de venda nos canais ativos, "
    "calcule margem e verifique se o fornecedor entrega dentro do prazo do canal.",
    "Rotina autônoma: analise meus anúncios e identifique quais precisam de melhoria "
    "para ganhar visualizações sem aumentar gastos com anúncios.",
    "Rotina autônoma: compare concorrentes e atualize a análise de preços e posicionamento.",
    "Rotina autônoma: planeje o conteúdo orgânico da semana para os produtos de melhor margem.",
)


@dataclass
class AutonomyPolicy:
    """Limites do agente. Tudo aqui é configurável e conservador por padrão."""

    interval_seconds: int = 1800            # 30 min entre ciclos
    daily_cycle_limit: int = 8              # no máximo 8 ciclos por dia
    work_hours: tuple[int, int] = (7, 23)   # só roda nesse intervalo
    max_consecutive_failures: int = 2       # 2 falhas seguidas = pausa automática
    failure_cooldown_seconds: int = 900     # espera 15 min antes de tentar de novo
    max_pending_approvals: int = 25         # fila entupida = para e te chama
    objectives: tuple[str, ...] = OBJETIVOS_PADRAO


def _hoje() -> str:
    return local_now().date().isoformat()


class AutonomousSuperAgent:
    """Loop autônomo com guarda-corpos, estado persistido e histórico."""

    def __init__(
        self,
        orchestrator: Orchestrator | None = None,
        policy: AutonomyPolicy | None = None,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self.orchestrator = orchestrator or Orchestrator()
        self.policy = policy or AutonomyPolicy()
        self.now_fn = now_fn or local_now
        self.state = self._load_state()

    # ------------------------------------------------------------ estado --
    def _load_state(self) -> dict[str, Any]:
        salvo = self.orchestrator.repo.get_setting(STATE_KEY, {}) or {}
        estado = {
            "enabled": bool(salvo.get("enabled", False)),
            "paused": bool(salvo.get("paused", False)),
            "pause_reason": salvo.get("pause_reason"),
            "day": salvo.get("day") or _hoje(),
            "cycles_today": int(salvo.get("cycles_today", 0) or 0),
            "consecutive_failures": int(salvo.get("consecutive_failures", 0) or 0),
            "last_cycle_at": salvo.get("last_cycle_at"),
            "last_status": salvo.get("last_status"),
            "last_summary": salvo.get("last_summary"),
            "last_run_id": salvo.get("last_run_id"),
            "last_error": salvo.get("last_error"),
            "objective_index": int(salvo.get("objective_index", 0) or 0),
            "cycles_total": int(salvo.get("cycles_total", 0) or 0),
        }
        if estado["day"] != _hoje():
            estado.update({"day": _hoje(), "cycles_today": 0})
        return estado

    def _save_state(self) -> None:
        self.orchestrator.repo.set_setting(STATE_KEY, self.state)

    # ---------------------------------------------------------- controles --
    def enable(self, enabled: bool = True) -> dict[str, Any]:
        self.state["enabled"] = enabled
        if not enabled:
            self.state["paused"] = True
            self.state["pause_reason"] = "modo manual: roda só quando você pede"
        self._save_state()
        return self.status()

    def pause(self, reason: str = "pausado pelo proprietário") -> dict[str, Any]:
        self.state["paused"] = True
        self.state["pause_reason"] = reason
        self._save_state()
        self.orchestrator.permissions.audit(
            "proprietario", "autonomy_pause", "autonomy", STATE_KEY, {"motivo": reason}
        )
        return self.status()

    def resume(self) -> dict[str, Any]:
        self.state.update({"paused": False, "pause_reason": None, "consecutive_failures": 0})
        self.state["enabled"] = True
        self._save_state()
        self.orchestrator.permissions.audit(
            "proprietario", "autonomy_resume", "autonomy", STATE_KEY, {}
        )
        return self.status()

    # ---------------------------------------------------------- avaliação --
    def due(self) -> tuple[bool, str]:
        """Pode rodar agora? Devolve (pode, motivo)."""
        agora = self.now_fn()
        if not self.state["enabled"]:
            return False, "autonomia desativada"
        if self.state["paused"]:
            return False, f"pausado: {self.state['pause_reason'] or 'sem motivo informado'}"

        inicio, fim = self.policy.work_hours
        if not (inicio <= agora.hour < fim):
            return False, f"fora da janela de trabalho ({inicio}h-{fim}h)"

        if self.state["cycles_today"] >= self.policy.daily_cycle_limit:
            return False, f"limite diário atingido ({self.policy.daily_cycle_limit} ciclos)"

        pendentes = self.orchestrator.tasks.pending_approvals_count()
        if pendentes >= self.policy.max_pending_approvals:
            return False, f"{pendentes} aprovações pendentes: resolva antes de continuar"

        ultimo = self.state.get("last_cycle_at")
        if ultimo:
            try:
                passado = datetime.fromisoformat(ultimo)
                referencia = agora
                if passado.tzinfo is None:
                    passado = passado.replace(tzinfo=agora.tzinfo)
                elif agora.tzinfo is None:
                    referencia = agora.replace(tzinfo=passado.tzinfo)
                espera = self.policy.interval_seconds
                if self.state.get("last_status") == "falhou":
                    espera = max(espera, self.policy.failure_cooldown_seconds)
                decorrido = referencia - passado
                if decorrido < timedelta(seconds=espera):
                    restante = int(espera - decorrido.total_seconds())
                    return False, f"aguardando intervalo ({max(restante, 1)}s)"
            except ValueError:
                pass

        return True, "pronto"

    def next_objective(self) -> str:
        objetivos = self.policy.objectives
        indice = self.state["objective_index"] % len(objetivos)
        return objetivos[indice]

    def status(self) -> dict[str, Any]:
        pode, motivo = self.due()
        return {
            **self.state,
            "pode_rodar_agora": pode,
            "motivo": motivo,
            "proximo_objetivo": self.next_objective(),
            "limites": {
                "intervalo_s": self.policy.interval_seconds,
                "ciclos_por_dia": self.policy.daily_cycle_limit,
                "janela": f"{self.policy.work_hours[0]}h-{self.policy.work_hours[1]}h",
                "falhas_para_pausar": self.policy.max_consecutive_failures,
            },
            "aprovacoes_pendentes": self.orchestrator.tasks.pending_approvals_count(),
        }

    # ------------------------------------------------------------- ciclo --
    def run_cycle(self, force: bool = False) -> dict[str, Any]:
        """Executa um ciclo. `force` ignora os guarda-corpos (uso manual)."""
        if not force:
            pode, motivo = self.due()
            if not pode:
                return {"ok": False, "skipped": True, "reason": motivo, "status": self.status()}

        objetivo = self.next_objective()
        iniciado = time.time()
        resultado: dict[str, Any] = {"ok": False, "objective": objetivo}

        try:
            outcome = self.orchestrator.handle(objetivo, requested_by="super_agente_autonomo")
            resultado.update(
                {
                    "ok": bool(outcome.get("ok")),
                    "run_id": outcome.get("run_id"),
                    "report_id": outcome.get("report_id"),
                    "intent": (outcome.get("intent") or {}).get("code"),
                    "resumo": (outcome.get("report") or "")[:1200],
                    "etapas": [
                        {"agente": s.get("agent"), "status": s.get("status")}
                        for s in outcome.get("steps", [])
                    ],
                }
            )
            self.state["last_status"] = "concluido" if resultado["ok"] else "falhou"
            self.state["last_summary"] = resultado.get("resumo")
            self.state["last_run_id"] = resultado.get("run_id")
            self.state["last_error"] = None if resultado["ok"] else outcome.get("error")
            if resultado["ok"]:
                self.state["consecutive_failures"] = 0
            else:
                self.state["consecutive_failures"] += 1
        except Exception as exc:  # falha inesperada nunca derruba o loop
            resultado.update({"ok": False, "error": str(exc), "traceback": traceback.format_exc()})
            self.state["last_status"] = "falhou"
            self.state["last_error"] = str(exc)
            self.state["consecutive_failures"] += 1

        self.state["objective_index"] += 1
        self.state["cycles_today"] += 1
        self.state["cycles_total"] += 1
        self.state["last_cycle_at"] = self.now_fn().isoformat()
        resultado["duration_s"] = round(time.time() - iniciado, 2)

        if self.state["consecutive_failures"] >= self.policy.max_consecutive_failures:
            self.state["paused"] = True
            self.state["pause_reason"] = (
                f"{self.state['consecutive_failures']} falhas seguidas: "
                "pausado sozinho para não insistir no erro"
            )
            resultado["auto_pausado"] = True

        self._save_state()
        resultado["status"] = self.status()
        return resultado

    def run_loop(
        self,
        max_cycles: int | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        on_cycle: Callable[[dict[str, Any]], None] | None = None,
        stop_fn: Callable[[], bool] | None = None,
    ) -> list[dict[str, Any]]:
        """Roda continuamente. Para por limite, pausa, falhas ou stop_fn."""
        historico: list[dict[str, Any]] = []
        pulos_seguidos = 0
        while max_cycles is None or len(historico) < max_cycles:
            if stop_fn and stop_fn():
                break
            ciclo = self.run_cycle()
            if ciclo.get("skipped"):
                motivo = str(ciclo.get("reason") or "")
                if any(
                    trava in motivo
                    for trava in ("limite diário", "pausado", "desativada", "aprovações pendentes")
                ):
                    break  # não adianta insistir: precisa de você
                # nada a fazer agora: dorme em fatias curtas para reagir a pausa
                pulos_seguidos += 1
                if pulos_seguidos >= 3:
                    break  # três ciclos seguidos sem poder rodar: não insiste
                for _ in range(6):
                    if stop_fn and stop_fn():
                        return historico
                    sleep_fn(max(self.policy.interval_seconds // 6, 1))
                continue
            pulos_seguidos = 0
            historico.append(ciclo)
            if on_cycle:
                on_cycle(ciclo)
            if self.state["paused"] or not self.state["enabled"]:
                break
            sleep_fn(max(self.policy.interval_seconds, 1))
        return historico


def main() -> int:
    parser = argparse.ArgumentParser(description="Super agente autônomo do E-COMMERCE AI EMPIRE")
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--once", action="store_true", help="roda um ciclo e sai")
    grupo.add_argument("--loop", action="store_true", help="roda continuamente")
    grupo.add_argument("--status", action="store_true", help="mostra o estado")
    grupo.add_argument("--pause", action="store_true", help="pausa a autonomia")
    grupo.add_argument("--resume", action="store_true", help="reativa a autonomia")
    grupo.add_argument("--disable", action="store_true",
                       help="modo manual: só roda quando você pedir")
    parser.add_argument("--force", action="store_true", help="ignora guarda-corpos (manual)")
    parser.add_argument("--interval", type=int, default=1800, help="segundos entre ciclos")
    parser.add_argument("--max-cycles", type=int, default=None)
    parser.add_argument("--motivo", default="pausado pelo proprietário")
    args = parser.parse_args()

    agente = AutonomousSuperAgent(
        policy=AutonomyPolicy(interval_seconds=args.interval)
    )

    if args.status:
        print(json.dumps(agente.status(), ensure_ascii=False, indent=2, default=str))
        return 0
    if args.pause:
        print(json.dumps(agente.pause(args.motivo), ensure_ascii=False, indent=2, default=str))
        return 0
    if args.resume:
        print(json.dumps(agente.resume(), ensure_ascii=False, indent=2, default=str))
        return 0
    if args.disable:
        estado = agente.enable(False)
        print(json.dumps(estado, ensure_ascii=False, indent=2, default=str))
        return 0

    agente.enable(True)
    if args.once:
        ciclo = agente.run_cycle(force=args.force)
        print(json.dumps(ciclo, ensure_ascii=False, indent=2, default=str))
        return 0 if ciclo.get("ok") or ciclo.get("skipped") else 1
    if args.loop:
        def mostrar(ciclo: dict[str, Any]) -> None:
            marca = "ok" if ciclo.get("ok") else ("pulado" if ciclo.get("skipped") else "falhou")
            motivo = ciclo.get("reason") or ciclo.get("error") or ""
            print(f"[{now_iso()}] {marca}: {motivo[:200]}", flush=True)

        historico = agente.run_loop(max_cycles=args.max_cycles, on_cycle=mostrar)
        print(f"ciclos executados: {len(historico)}")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
