"""Modo REAL vs DEMO: o sistema precisa saber com qual base está falando.

Regra do projeto: dado DEMO nunca entra em número real. Em modo real os registros
DEMO são apagados do banco, não apenas escondidos.
"""

from __future__ import annotations

from typing import Any

MODE_KEY = "data_mode"
REAL = "real"
DEMO = "demo"


def get_mode(repo) -> str:
    modo = str(repo.get_setting(MODE_KEY, DEMO) or DEMO).lower()
    return modo if modo in (REAL, DEMO) else DEMO


def set_mode(repo, mode: str) -> str:
    if mode not in (REAL, DEMO):
        raise ValueError("modo inválido: use 'real' ou 'demo'")
    repo.set_setting(MODE_KEY, mode)
    return mode


def is_real(repo) -> bool:
    return get_mode(repo) == REAL


def checklist(repo, settings: Any = None) -> list[dict]:
    """O que falta para operar de verdade. Cada item diz como resolver."""
    deps = settings
    itens: list[dict] = []

    produtos = [p for p in repo.find("products", {}, limit=500) if not p.get("is_demo")]
    itens.append({
        "item": "Produtos reais cadastrados",
        "ok": bool(produtos),
        "detalhe": f"{len(produtos)} produto(s) real(is)" if produtos else "nenhum ainda",
        "como": "planilha templates/produtos.csv ou página Produtos no painel interativo",
    })

    fornecedores = [s for s in repo.find("suppliers", {}, limit=500) if not s.get("is_demo")]
    itens.append({
        "item": "Fornecedores reais com prazo e frete",
        "ok": bool(fornecedores),
        "detalhe": f"{len(fornecedores)} fornecedor(es)" if fornecedores else "nenhum ainda",
        "como": "templates/fornecedores.csv (lead_time_days, shipping_cost, retirada)",
    })

    tem_taxa = False
    tem_prazo = False
    if hasattr(repo, "find"):
        for regra in repo.find("marketplaces", {}, limit=50):
            if float(regra.get("commission_pct") or 0) > 0 or float(regra.get("fixed_fee") or 0) > 0:
                tem_taxa = True
            if int(regra.get("handling_days") or 0) > 0:
                tem_prazo = True
    itens.append({
        "item": "Taxas reais do marketplace",
        "ok": tem_taxa,
        "detalhe": "comissão e taxa fixa informadas" if tem_taxa else "comissão em 0%",
        "como": "página do canal no painel interativo (Shopee, Mercado Livre...)",
    })
    itens.append({
        "item": "Prazo de despacho do canal",
        "ok": tem_prazo,
        "detalhe": "prazo informado" if tem_prazo else "prazo não informado",
        "como": "página do canal: dias úteis que a plataforma te dá para postar",
    })

    chave_ia = False
    if deps is not None:
        chave_ia = any(
            bool(getattr(deps, atributo, ""))
            for atributo in dir(deps)
            if atributo.endswith("api_key") and not atributo.startswith("_")
        )
    itens.append({
        "item": "Chave de IA (opcional)",
        "ok": chave_ia,
        "detalhe": "configurada" if chave_ia else "sem chave: agentes trabalham só com seus dados",
        "como": "GEMINI_API_KEY no .env (plano gratuito do Google AI Studio)",
    })

    vendas = [v for v in repo.find("sales", {}, limit=500) if not v.get("is_demo")]
    itens.append({
        "item": "Vendas reais para medir resultado",
        "ok": bool(vendas),
        "detalhe": f"{len(vendas)} venda(s)" if vendas else "nenhuma ainda",
        "como": "templates/vendas.csv ou importação do CSV da plataforma",
    })

    return itens


def resumo(repo, settings: Any = None) -> dict:
    itens = checklist(repo, settings)
    prontos = sum(1 for i in itens if i["ok"])
    return {
        "mode": get_mode(repo),
        "prontos": prontos,
        "total": len(itens),
        "itens": itens,
    }
