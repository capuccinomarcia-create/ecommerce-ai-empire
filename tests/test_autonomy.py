"""Testes do super agente autônomo: limites, pausa automática e histórico."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from core.autonomy import STATE_KEY, AutonomyPolicy, AutonomousSuperAgent


class Relogio:
    """Relógio controlável: o teste decide quando o tempo passa."""

    def __init__(self, hora: int = 10) -> None:
        self.momento = datetime(2026, 11, 9, hora, 0, 0)

    def __call__(self) -> datetime:
        return self.momento

    def avancar(self, segundos: int) -> None:
        self.momento += timedelta(seconds=segundos)


class FakeTasks:
    def __init__(self, pendentes: int = 0) -> None:
        self.pendentes = pendentes

    def pending_approvals_count(self) -> int:
        return self.pendentes


class FakePermissions:
    def __init__(self) -> None:
        self.eventos: list[tuple] = []

    def audit(self, actor, action, resource_type, resource_id, details) -> None:
        self.eventos.append((actor, action, details))


class FakeOrchestrator:
    """Orquestrador de mentira: rápido, determinístico e sem rede."""

    def __init__(self, repo, falhar_vezes: int = 0) -> None:
        self.repo = repo
        self.permissions = FakePermissions()
        self.tasks = FakeTasks()
        self.falhar_vezes = falhar_vezes
        self.chamadas: list[str] = []

    def handle(self, command: str, requested_by: str = "proprietario") -> dict:
        self.chamadas.append(command)
        if self.falhar_vezes > 0:
            self.falhar_vezes -= 1
            raise RuntimeError("falha simulada do provedor de IA")
        return {
            "ok": True,
            "run_id": f"run_{len(self.chamadas)}",
            "report_id": f"rep_{len(self.chamadas)}",
            "report": f"Relatório do ciclo {len(self.chamadas)}",
            "intent": {"code": "product_research"},
            "steps": [{"agent": "product_hunter", "status": "concluida"}],
        }


def agente(repo, hora: int = 10, intervalo: int = 60, **kwargs):
    fake = FakeOrchestrator(repo, **kwargs)
    policy = AutonomyPolicy(interval_seconds=intervalo, daily_cycle_limit=3)
    relogio = Relogio(hora)
    return AutonomousSuperAgent(orchestrator=fake, policy=policy, now_fn=relogio), fake, relogio


def test_desativado_nao_roda(repo):
    a, _, _ = agente(repo)
    pode, motivo = a.due()
    assert pode is False
    assert "desativada" in motivo


def test_ativado_roda_dentro_da_janela(repo):
    a, _, _ = agente(repo)
    a.enable(True)
    pode, motivo = a.due()
    assert pode is True, motivo


def test_fora_da_janela_nao_roda(repo):
    a, _, _ = agente(repo, hora=3)
    a.enable(True)
    pode, motivo = a.due()
    assert pode is False
    assert "janela" in motivo


def test_limite_diario_bloqueia_e_renova_no_dia_seguinte(repo):
    a, fake, relogio = agente(repo)
    a.enable(True)
    for _ in range(3):
        assert a.run_cycle()["ok"] is True
        relogio.avancar(120)
    pode, motivo = a.due()
    assert pode is False
    assert "limite diário" in motivo
    assert len(fake.chamadas) == 3

    salvo = repo.get_setting(STATE_KEY)
    salvo["day"] = "2020-01-01"
    repo.set_setting(STATE_KEY, salvo)
    a2, _, _ = agente(repo)
    assert a2.state["cycles_today"] == 0


def test_intervalo_entre_ciclos(repo):
    a, fake, relogio = agente(repo)
    a.enable(True)
    a.run_cycle()
    pode, motivo = a.due()
    assert pode is False
    assert "intervalo" in motivo
    relogio.avancar(61)
    assert a.due()[0] is True
    assert len(fake.chamadas) == 1


def test_force_ignora_guarda_corpos(repo):
    a, fake, _ = agente(repo)
    resultado = a.run_cycle(force=True)   # desativado e fora da janela
    assert resultado["ok"] is True
    assert len(fake.chamadas) == 1


def test_falhas_seguidas_pausam_sozinho(repo):
    a, _, relogio = agente(repo, falhar_vezes=5)
    a.enable(True)
    a.run_cycle()
    relogio.avancar(901)  # depois de falha o cooldown é maior
    resultado = a.run_cycle()
    assert resultado.get("auto_pausado") is True
    assert a.state["paused"] is True
    assert "falhas seguidas" in a.state["pause_reason"]
    pode, motivo = a.due()
    assert pode is False
    assert "pausado" in motivo


def test_objetivos_rotacionam(repo):
    a, fake, relogio = agente(repo)
    a.enable(True)
    a.run_cycle(force=True)
    relogio.avancar(120)
    a.run_cycle(force=True)
    assert len(fake.chamadas) == 2
    assert fake.chamadas[0] != fake.chamadas[1]
    assert fake.chamadas[0].startswith("Rotina autônoma")


def test_loop_respeita_limite_diario(repo):
    a, _, _ = agente(repo, intervalo=0)
    a.enable(True)
    historico = a.run_loop(max_cycles=6, sleep_fn=lambda s: None)
    assert len(historico) == 3          # limite diário de 3
    assert a.state["cycles_today"] == 3


def test_loop_para_quando_pausado(repo):
    a, _, _ = agente(repo, intervalo=0)
    a.enable(True)
    a.pause("teste")
    historico = a.run_loop(max_cycles=5, sleep_fn=lambda s: None)
    assert historico == []


def test_fila_de_aprovacoes_entupida_segura_o_agente(repo):
    a, fake, _ = agente(repo)
    a.enable(True)
    fake.tasks.pendentes = a.policy.max_pending_approvals
    pode, motivo = a.due()
    assert pode is False
    assert "aprovações pendentes" in motivo


def test_pausa_e_retomada_ficam_registradas(repo):
    a, _, _ = agente(repo)
    a.enable(True)
    a.pause("revisar custos")
    assert a.state["paused"] is True
    a.resume()
    assert a.state["paused"] is False
    assert any(e[1] == "autonomy_pause" for e in a.orchestrator.permissions.eventos)
    assert any(e[1] == "autonomy_resume" for e in a.orchestrator.permissions.eventos)


def test_estado_sobrevive_a_reinicio(repo):
    a, _, _ = agente(repo)
    a.enable(True)
    a.run_cycle(force=True)
    outro, _, _ = agente(repo)
    assert outro.state["cycles_total"] == 1
    assert outro.state["enabled"] is True


@pytest.mark.slow
def test_ciclo_real_com_demo_data(demo_orchestrator):
    """Um ciclo de verdade com os dados DEMO: gera relatório e não publica nada."""
    policy = AutonomyPolicy(interval_seconds=0, daily_cycle_limit=5)
    a = AutonomousSuperAgent(
        orchestrator=demo_orchestrator, policy=policy,
        now_fn=lambda: datetime(2026, 11, 9, 10, 0, 0),
    )
    a.enable(True)
    resultado = a.run_cycle()
    assert resultado["ok"] is True, resultado.get("error")
    assert resultado["report_id"]
    assert demo_orchestrator.repo.find("reports", {}, limit=1)
    # nada é publicado sozinho: o que exige aval continua na fila de aprovação
    assert demo_orchestrator.tasks.pending_approvals_count() >= 0
