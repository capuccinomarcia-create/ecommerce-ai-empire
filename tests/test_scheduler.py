"""Testes do agendador: cron, vencimento, execução e registro."""

from __future__ import annotations

from datetime import datetime

import pytest

from core import jobs
from core.scheduler import Agendador, FUSO, _casa, proximo_disparo


def dt(texto: str) -> datetime:
    return datetime.fromisoformat(texto).replace(tzinfo=FUSO)


# ------------------------------------------------------------------- cron --
def test_cron_diario():
    assert _casa("30 7 * * *", dt("2026-11-09T07:30:00"))
    assert not _casa("30 7 * * *", dt("2026-11-09T07:31:00"))


def test_cron_lista_de_horarios():
    assert _casa("0 12,18 * * *", dt("2026-11-09T12:00:00"))
    assert _casa("0 12,18 * * *", dt("2026-11-09T18:00:00"))
    assert not _casa("0 12,18 * * *", dt("2026-11-09T13:00:00"))


def test_cron_passo():
    assert _casa("*/15 * * * *", dt("2026-11-09T10:45:00"))
    assert not _casa("*/15 * * * *", dt("2026-11-09T10:46:00"))


def test_cron_domingo_zero_e_sete():
    domingo = dt("2026-11-08T09:00:00")   # 08/11/2026 é domingo
    assert _casa("0 9 * * 0", domingo)
    assert _casa("0 9 * * 7", domingo)
    assert not _casa("0 9 * * 1", domingo)


def test_proximo_disparo_hoje():
    agora = dt("2026-11-08T18:51:00")
    assert proximo_disparo("0 20 * * *", agora) == dt("2026-11-08T20:00:00")


def test_proximo_disparo_amanha():
    agora = dt("2026-11-08T21:00:00")
    assert proximo_disparo("30 7 * * *", agora) == dt("2026-11-09T07:30:00")


def test_proximo_disparo_semanal_pula_para_segunda():
    agora = dt("2026-11-08T12:00:00")   # domingo
    assert proximo_disparo("0 10 * * 1", agora) == dt("2026-11-09T10:00:00")


def test_cron_invalido_avisa():
    with pytest.raises(ValueError):
        proximo_disparo("todo dia as 7", dt("2026-11-08T12:00:00"))


# -------------------------------------------------------------- agendador --
@pytest.fixture()
def rotina(repo):
    repo.insert("marketplaces", {"slug": "shopee", "name": "Shopee",
                                "commission_pct": 14.0, "fixed_fee": 4.0})
    repo.insert("products", {"name": "Livro de Colorir", "purchase_price": 18.5,
                             "sale_price": 39.9, "marketplace": "shopee",
                             "status": "ativo", "category": "livros",
                             "description": "x" * 150})
    return repo.insert("automations", {"name": "plano_de_venda", "job": "sales_plan",
                                       "schedule_cron": "30 7 * * *", "enabled": True,
                                       "next_run_at": "2026-11-09T07:30:00-03:00",
                                       "config": {}})


def test_tick_executa_rotina_vencida(repo, rotina):
    agora = lambda: dt("2026-11-09T07:30:05")
    resultados = Agendador(repo, agora_fn=agora).tick()
    assert len(resultados) == 1
    assert resultados[0]["status"] == "ok"
    assert "prontos" in resultados[0]["summary"]
    atualizada = repo.find_one("automations", {"id": rotina["id"]})
    assert atualizada["last_run_at"].startswith("2026-11-09T07:30:05")
    assert atualizada["next_run_at"].startswith("2026-11-10T07:30")


def test_tick_nao_repete_a_mesma_rotina(repo, rotina):
    agendador = Agendador(repo, agora_fn=lambda: dt("2026-11-09T07:30:05"))
    assert len(agendador.tick()) == 1
    assert agendador.tick() == []      # ainda não venceu de novo


def test_rotina_desativada_nao_roda(repo, rotina):
    repo.update("automations", rotina["id"], {"enabled": False})
    assert Agendador(repo, agora_fn=lambda: dt("2026-11-09T07:31:00")).tick() == []


def test_forcar_roda_mesmo_fora_do_horario(repo, rotina):
    agora = lambda: dt("2026-11-09T03:00:00")
    resultados = Agendador(repo, agora_fn=agora).tick(forcar=["plano_de_venda"])
    assert len(resultados) == 1 and resultados[0]["forced"] is True


def test_job_desconhecido_nao_derruba_o_agendador(repo):
    repo.insert("automations", {"name": "quebrada", "job": "nao_existe",
                                "schedule_cron": "0 8 * * *", "enabled": True})
    resultados = Agendador(repo, agora_fn=lambda: dt("2026-11-09T08:00:00")).tick()
    assert resultados[0]["status"] == "erro"
    assert "job desconhecido" in resultados[0]["summary"]


def test_rotina_sem_horario_nunca_roda(repo):
    repo.insert("automations", {"name": "sem_cron", "job": "sales_plan",
                                "schedule_cron": None, "enabled": True})
    assert Agendador(repo, agora_fn=lambda: dt("2026-11-09T08:00:00")).tick() == []


def test_primeira_execucao_marca_proxima(repo):
    repo.insert("automations", {"name": "alerta", "job": "stock_alert",
                                "schedule_cron": "0 12,18 * * *", "enabled": True})
    agendador = Agendador(repo, agora_fn=lambda: dt("2026-11-09T12:00:00"))
    resultados = agendador.tick()
    assert resultados[0]["status"] == "ok"
    assert resultados[0]["next_run_at"].startswith("2026-11-09T18:00")


# -------------------------------------------------------------------- jobs --
def test_job_sales_plan_salva_relatorio(repo, rotina):
    resultado = jobs.sales_plan(repo)
    assert "prontos" in resultado["summary"]
    relatorios = repo.find("reports", {"kind": "vendas"})
    assert relatorios and "Prontos para publicar" in relatorios[0]["body"]


def test_job_stock_alert_sem_estoque_sugere_reposicao(repo, rotina):
    from datetime import datetime as dtp

    produto = repo.find_one("products", {})
    for _ in range(30):
        repo.insert("sales", {"product_id": produto["id"], "quantity": 1,
                              "sold_at": dtp.now().isoformat()})
    resultado = jobs.stock_alert(repo)
    assert "precisam de reposição" in resultado["summary"]
    assert "Livro de Colorir" in resultado["findings"][0]


def test_job_stock_alert_sem_venda_nao_pede_nada(repo, rotina):
    assert jobs.stock_alert(repo)["summary"] == "nada a repor agora"


def test_job_price_review_aponta_margem_baixa(repo, rotina):
    produto = repo.find_one("products", {})
    repo.update("products", produto["id"], {"sale_price": 22.0})
    resultado = jobs.price_review(repo)
    assert "abaixo da meta" in resultado["summary"]
    assert "sugerido" in resultado["findings"][0]


def test_job_listing_check_aprova_catalogo_completo(repo, rotina):
    assert jobs.listing_check(repo)["summary"] == "todos os anúncios estão prontos"


def test_job_daily_report_conta_aprovacoes(repo, rotina):
    repo.insert("approvals", {"status": "pendente", "action": "publicar",
                              "requested_by": "agente"})
    resultado = jobs.daily_report(repo)
    assert "1 aprovações pendentes" in resultado["summary"]
    assert repo.find("reports", {"kind": "diario"})
