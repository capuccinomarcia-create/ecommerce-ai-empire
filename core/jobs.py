"""O que cada rotina faz de verdade.

Todos os jobs são determinísticos e usam o banco real. Nenhum publica anúncio,
compra ou paga: quando falta autorização, o job registra a pendência e segue.

    sales_plan      preço com margem alvo, estoque mínimo e checklist do anúncio
    stock_alert     só o que precisa repor, com quantidade
    price_review    produtos abaixo da margem alvo, com preço sugerido
    listing_check   anúncios que ainda não podem ser publicados
    daily_report    resumo do dia, salvo no histórico de relatórios
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from analytics.reports import save_report
from core.sales_ops import SalesOperator, resumo_texto


def _plano(repo) -> dict[str, Any]:
    return SalesOperator(repo).plano()


def sales_plan(repo) -> dict[str, Any]:
    plano = _plano(repo)
    texto = resumo_texto(plano)
    save_report(repo, kind="vendas", title="Plano de venda", body=texto, is_demo=False)
    return {"summary": f"{len(plano['prontos'])} prontos, {len(plano['ajustar'])} a ajustar, "
                       f"{len(plano['bloqueados'])} bloqueados",
            "findings": [texto], "plan": plano}


def stock_alert(repo) -> dict[str, Any]:
    plano = _plano(repo)
    repor = plano["repor"]
    if not repor:
        return {"summary": "nada a repor agora", "findings": []}
    linhas = [f"repor {i['repor']} un de {i['produto']} (tem {i['estoque_atual']}, "
              f"mínimo {i['estoque_minimo']})" for i in repor]
    return {"summary": f"{len(repor)} produto(s) precisam de reposição",
            "findings": linhas, "items": repor}


def price_review(repo) -> dict[str, Any]:
    plano = _plano(repo)
    abaixo = [i for i in plano["ajustar"] + plano["bloqueados"]
              if any("margem" in b for b in i["bloqueios"])]
    if not abaixo:
        return {"summary": "nenhum produto abaixo da meta de margem", "findings": []}
    linhas = [f"{i['produto']}: margem {i['margem_pct']}% → sugerido R$ {i['preco_sugerido']}"
              for i in abaixo if i.get("preco_sugerido")]
    return {"summary": f"{len(abaixo)} produto(s) abaixo da meta de {plano['margem_alvo_pct']:.0f}%",
            "findings": linhas, "items": abaixo}


def listing_check(repo) -> dict[str, Any]:
    plano = _plano(repo)
    travados = plano["ajustar"] + plano["bloqueados"]
    if not travados:
        return {"summary": "todos os anúncios estão prontos", "findings": []}
    linhas = [f"{i['produto']}: " + "; ".join(i["bloqueios"]) for i in travados]
    return {"summary": f"{len(travados)} anúncio(s) não podem ser publicados",
            "findings": linhas, "items": travados}


def daily_report(repo) -> dict[str, Any]:
    plano = _plano(repo)
    pendencias = repo.find("approvals", {"status": "pendente"}, limit=50) or []
    total_aprovacoes = len(pendencias)
    corpo = [resumo_texto(plano), "",
             f"Aprovações pendentes: {total_aprovacoes}",
             f"Gerado em {datetime.now():%d/%m/%Y %H:%M}"]
    texto = "\n".join(corpo)
    save_report(repo, kind="diario", title="Relatório diário", body=texto, is_demo=False)
    return {"summary": f"relatório do dia salvo ({plano['produtos']} produtos, "
                       f"{total_aprovacoes} aprovações pendentes)",
            "findings": [texto]}


JOBS = {
    "sales_plan": sales_plan,
    "stock_alert": stock_alert,
    "price_review": price_review,
    "listing_check": listing_check,
    "daily_report": daily_report,
}
