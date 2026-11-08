"""Testes do orquestrador: plano, execução, consolidação e consistência."""

from __future__ import annotations

from core.planner import build_plan, detect_intent


def test_intencao_pesquisa_de_produtos():
    intent = detect_intent(
        "CEO, encontre 10 produtos com potencial de venda na Shopee e no Mercado Livre"
    )
    assert intent["code"] == "product_research"
    assert intent["confidence"] >= 0.6


def test_intencao_auditoria_de_anuncios():
    intent = detect_intent(
        "Analise meus anúncios e identifique quais precisam de melhorias sem aumentar gastos"
    )
    assert intent["code"] == "listing_audit"


def test_intencao_generica():
    intent = detect_intent("bom dia, tudo bem?")
    assert intent["code"] == "general"


def test_plano_tem_dependencias_validas():
    intent = detect_intent("encontre produtos com potencial de venda")
    plan = build_plan(intent, "encontre 10 produtos")
    ids = {step["id"] for step in plan}
    for step in plan:
        for dependency in step["depends_on"]:
            assert dependency in ids
    assert plan[-1]["agent"] == "ceo"


def test_execucao_completa_com_demo(demo_orchestrator):
    outcome = demo_orchestrator.handle(
        "CEO, encontre 10 produtos com potencial de venda na Shopee, Mercado Livre e TikTok Shop. "
        "Analise concorrência, preços, custos, tendências e lucro. Depois me apresente as cinco "
        "melhores oportunidades."
    )
    assert outcome["ok"] is True
    assert outcome["intent"]["code"] == "product_research"
    assert all(step["status"] == "concluida" for step in outcome["steps"])
    assert outcome["report_id"]
    assert "Relatório do CEO AI" in outcome["report"]
    assert outcome["demo_mode"] is True
    assert outcome["consistency_issues"] == []


def test_pesquisa_retorna_cinco_melhores(demo_orchestrator):
    outcome = demo_orchestrator.handle("encontre 10 produtos com potencial de venda")
    hunter = next(step for step in outcome["steps"] if step["agent"] == "product_hunter")
    assert hunter["status"] == "concluida"
    task = demo_orchestrator.tasks.get(hunter["task_id"])
    opportunities = task["result"]["data"]["top"]
    assert len(opportunities) == 5
    scores = [o["score"] for o in opportunities]
    assert scores == sorted(scores, reverse=True)


def test_sem_dados_nao_inventa(orchestrator):
    outcome = orchestrator.handle("encontre produtos com potencial de venda")
    assert outcome["ok"] is True
    assert outcome["data_gaps"], "deve declarar o que falta em vez de inventar dados"
    assert any("Importe um CSV" in gap or "Catálogo vazio" in gap for gap in outcome["data_gaps"])


def test_relatorio_persistido(orchestrator):
    outcome = orchestrator.handle("gere um relatório do dia")
    report = orchestrator.repo.get("reports", outcome["report_id"])
    assert report is not None
    assert report["kind"] == "orchestration"


def test_registra_auditoria_e_decisao(demo_orchestrator):
    demo_orchestrator.handle("compare fornecedores e diga o melhor custo total")
    assert demo_orchestrator.repo.count("audit_logs") >= 1
    decisions = demo_orchestrator.memory.recent(scope="decisions")
    assert decisions


def test_regras_de_marketplace_criadas(orchestrator):
    rows = orchestrator.repo.find("marketplaces")
    assert len(rows) >= 6
    assert all(float(row["commission_pct"]) == 0 for row in rows)
    assert all(row["source"] for row in rows)


def test_agentes_registrados(orchestrator):
    agents = orchestrator.repo.find("agents")
    assert len(agents) == 12
    names = {agent["name"] for agent in agents}
    assert {"ceo", "product_hunter", "financial", "video_creator"} <= names


def test_tarefas_registradas_com_pai(demo_orchestrator):
    outcome = demo_orchestrator.handle("analise meus anúncios")
    children = demo_orchestrator.repo.find("tasks", {"parent_id": outcome["root_task_id"]})
    assert len(children) == len(outcome["steps"])


def test_validacao_detecta_inconsistencia():
    from core.orchestrator import Orchestrator

    issues = Orchestrator._validate({
        "financial.evaluate": {"data": {"rows": [
            {"product_name": "X", "revenue": 100, "total_cost": 40, "net_profit": 10,
             "margin_pct": 10}
        ]}}
    })
    assert issues, "receita - custo != lucro deve ser sinalizado"


def test_validacao_ok():
    from core.orchestrator import Orchestrator

    issues = Orchestrator._validate({
        "financial.evaluate": {"data": {"rows": [
            {"product_name": "X", "revenue": 100, "total_cost": 40, "net_profit": 60,
             "margin_pct": 60}
        ]}}
    })
    assert issues == []
