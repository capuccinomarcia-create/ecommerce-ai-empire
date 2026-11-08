"""Gera o painel estático (docs/index.html) a partir do banco real.

Por que existe: o Streamlit Community Cloud exige login do proprietário para
criar o app. Para ter um link que abre em qualquer aparelho sem login, este
script exporta o estado real da operação para um HTML autocontido, publicado
pelo GitHub Pages.

O que é de verdade aqui:
  * todos os números vêm do banco (produtos, oportunidades, scores, margens);
  * a calculadora roda no navegador com a MESMA matemática de
    analytics/profitability.py (verificado por tests/test_static_parity.py).

Uso:
    python -m scripts.build_static_panel            # gera docs/index.html
    python -m scripts.build_static_panel --out DIR
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from core.config import get_settings
from database.repository import SQLiteRepository

TZ = ZoneInfo("America/Sao_Paulo")
ROOT = Path(__file__).resolve().parent.parent

CHANNEL_LABELS = {
    "shopee": "Shopee",
    "mercadolivre": "Mercado Livre",
    "tiktok_shop": "TikTok Shop",
    "instagram": "Instagram",
    "woocommerce": "Loja própria (WooCommerce)",
}


def _r2(value):
    return None if value is None else round(float(value), 2)


def collect_data() -> dict:
    settings = get_settings()
    repo = SQLiteRepository(settings.sqlite_path)

    products = repo.find("products", {})
    opportunities = repo.find("opportunities", {})
    agents = repo.find("agents", {})
    marketplaces = repo.find("marketplaces", {})
    competitors = repo.find("competitors", {})
    suppliers = repo.find("suppliers", {})

    # margens calculadas pelo motor Python, não pela interface
    from analytics.profitability import CostStructure, FinancialInput, SaleTerms, calculate

    rules = {m.get("slug"): m for m in marketplaces}
    product_rows = []
    for p in products:
        rule = rules.get(p.get("marketplace") or "", {})
        try:
            result = calculate(
                FinancialInput(
                    product_name=p.get("name", ""),
                    marketplace=p.get("marketplace") or "loja_propria",
                    costs=CostStructure(
                        purchase_price=float(p.get("purchase_price") or 0),
                        packaging=float(p.get("extra_cost") or 0),
                    ),
                    terms=SaleTerms(
                        sale_price=float(p.get("sale_price") or 0.01),
                        commission_pct=float(rule.get("commission_pct") or 0),
                        fixed_fee=float(rule.get("fixed_fee") or 0),
                    ),
                )
            ).to_dict()
        except Exception as exc:  # preço inválido no cadastro não derruba o build
            result = {"error": str(exc)}
        product_rows.append(
            {
                "name": p.get("name"),
                "category": p.get("category"),
                "marketplace": p.get("marketplace"),
                "purchase_price": _r2(p.get("purchase_price")),
                "sale_price": _r2(p.get("sale_price")),
                "is_demo": bool(p.get("is_demo")),
                "fin": result,
            }
        )

    opportunity_rows = []
    for o in opportunities:
        bd = o.get("breakdown") or {}
        if isinstance(bd, str):
            try:
                bd = json.loads(bd)
            except json.JSONDecodeError:
                bd = {}
        opportunity_rows.append(
            {
                "name": o.get("name"),
                "category": o.get("category"),
                "marketplace": o.get("marketplace"),
                "price_found": _r2(o.get("price_found")),
                "cost_estimate": _r2(o.get("cost_estimate")),
                "margin_estimate": _r2(o.get("margin_estimate")),
                "score": _r2(o.get("score")),
                "recommendation": o.get("recommendation"),
                "sources": bd.get("sources") or {},
                "criteria": bd.get("criteria") or {},
                "explanation": bd.get("explanation") or [],
                "consulted_at": o.get("consulted_at"),
                "is_demo": bool(o.get("is_demo")),
            }
        )
    opportunity_rows.sort(key=lambda r: r["score"] or -1, reverse=True)

    scored = [o for o in opportunity_rows if o["score"] is not None]
    avg_score = round(sum(o["score"] for o in scored) / len(scored), 1) if scored else 0.0

    profit_sum = 0.0
    for row in product_rows:
        fin = row["fin"]
        if "net_profit_per_unit" in fin:
            profit_sum += fin["net_profit_per_unit"] or 0

    # viabilidade de entrega: prazo do canal x prazo de cada fornecedor
    from analytics.fulfillment import deadline_from_marketplace, rank_suppliers

    viability = []
    for m in marketplaces:
        prazo = deadline_from_marketplace(m)
        ranking = rank_suppliers(suppliers, prazo, None)
        viability.append(
            {
                "channel": prazo.slug,
                "channel_name": prazo.name,
                "handling_days": prazo.handling_days,
                "delivery_days": prazo.delivery_days,
                "informed": prazo.informado,
                "source": prazo.source,
                "ranking": [v.to_dict() for v in ranking],
            }
        )
    viability_order = {v["channel"]: i for i, v in enumerate(viability)}
    viability.sort(key=lambda v: (not v["informed"], v["channel_name"]))

    channels = []
    for slug, label in CHANNEL_LABELS.items():
        rule = rules.get(slug, {})
        channels.append(
            {
                "slug": slug,
                "label": label,
                "commission_pct": rule.get("commission_pct"),
                "fixed_fee": rule.get("fixed_fee"),
                "notes": rule.get("notes") or "Taxa não informada pelo proprietário.",
                "connected": False,
            }
        )

    from core import data_mode

    config = data_mode.resumo(repo, get_settings())

    estado_autonomia = repo.get_setting("autonomy_state", {}) or {}
    ultimo_relatorio = repo.find("reports", {}, order_by="-created_at", limit=1)
    autonomia = {
        "enabled": bool(estado_autonomia.get("enabled")),
        "paused": bool(estado_autonomia.get("paused")),
        "pause_reason": estado_autonomia.get("pause_reason"),
        "cycles_today": int(estado_autonomia.get("cycles_today", 0) or 0),
        "cycles_total": int(estado_autonomia.get("cycles_total", 0) or 0),
        "last_status": estado_autonomia.get("last_status"),
        "last_cycle_at": estado_autonomia.get("last_cycle_at"),
        "last_summary": estado_autonomia.get("last_summary"),
        "consecutive_failures": int(estado_autonomia.get("consecutive_failures", 0) or 0),
        "ultimo_relatorio": (
            {"titulo": ultimo_relatorio[0].get("title"),
             "quando": ultimo_relatorio[0].get("created_at")}
            if ultimo_relatorio else None
        ),
    }

    return {
        "generated_at": datetime.now(TZ).strftime("%d/%m/%Y %H:%M"),
        "timezone": settings.timezone,
        "currency": "BRL",
        "kpis": {
            "products": len(products),
            "opportunities": len(opportunities),
            "avg_score": avg_score,
            "profit_per_unit": round(profit_sum, 2),
            "competitors": len(competitors),
            "suppliers": len(suppliers),
            "scored": len(scored),
        },
        "products": product_rows,
        "opportunities": opportunity_rows,
        "agents": [
            {
                "name": a.get("name"),
                "role": a.get("role"),
                "description": a.get("description"),
                "status": a.get("status") or "pronto",
            }
            for a in agents
        ],
        "channels": channels,
        "viability": viability,
        "autonomia": autonomia,
        "config": config,
        "mode": config["mode"],
        "marketplaces": [
            {"slug": m.get("slug"), "name": m.get("name"),
             "commission_pct": m.get("commission_pct"), "fixed_fee": m.get("fixed_fee"),
             "source": m.get("source"), "notes": m.get("notes")}
            for m in marketplaces
        ],
        "has_demo": any(p["is_demo"] for p in product_rows)
        or any(o["is_demo"] for o in opportunity_rows),
    }


TEMPLATE = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>E-COMMERCE AI EMPIRE</title>
<style>
  :root{
    --bg:#0f172a; --bg2:#131f36; --card:#ffffff; --ink:#0f172a; --muted:#64748b;
    --line:#e2e8f0; --brand:#2563eb; --brand2:#1d4ed8; --ok:#059669; --warn:#b45309;
    --bad:#b91c1c; --soft:#f8fafc;
  }
  *{box-sizing:border-box}
  body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
       background:var(--soft);color:var(--ink);font-size:15px;line-height:1.45}
  .app{display:flex;min-height:100vh}
  aside{width:250px;flex:0 0 250px;background:var(--bg);color:#cbd5e1;padding:20px 14px;position:sticky;top:0;height:100vh;overflow:auto}
  aside h1{font-size:15px;color:#fff;margin:0 0 2px;letter-spacing:.02em}
  aside .sub{font-size:11px;color:#7c8db0;margin-bottom:18px}
  nav button{display:block;width:100%;text-align:left;background:none;border:0;color:#cbd5e1;
    padding:9px 11px;border-radius:8px;font-size:13.5px;cursor:pointer;font-family:inherit}
  nav button:hover{background:#1b2a45;color:#fff}
  nav button.on{background:var(--brand);color:#fff;font-weight:600}
  main{flex:1;padding:26px 30px 60px;max-width:1180px}
  h2{font-size:22px;margin:0 0 4px}
  .hint{color:var(--muted);font-size:13px;margin-bottom:20px}
  .grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));margin-bottom:22px}
  .kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
  .kpi .l{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);font-weight:600}
  .kpi .v{font-size:23px;font-weight:700;margin-top:6px}
  .kpi .s{font-size:11.5px;color:var(--muted);margin-top:3px}
  section.panel{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:18px;margin-bottom:18px}
  table{border-collapse:collapse;width:100%;font-size:13.5px}
  th,td{text-align:left;padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top}
  th{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}
  td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
  .tag{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600}
  .tag.demo{background:#fef3c7;color:#92400e}
  .tag.ok{background:#d1fae5;color:#065f46}
  .tag.off{background:#f1f5f9;color:#475569}
  .tag.bad{background:#fee2e2;color:#991b1b}
  .tag.mid{background:#fef3c7;color:#92400e}
  .bar{height:7px;background:#eef2f7;border-radius:4px;overflow:hidden;min-width:70px}
  .bar > i{display:block;height:100%;background:var(--brand)}
  form.calc{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(150px,1fr))}
  label{display:block;font-size:11.5px;color:var(--muted);font-weight:600;margin-bottom:4px}
  input,select{width:100%;padding:8px 9px;border:1px solid #cbd5e1;border-radius:7px;font-size:14px;font-family:inherit;background:#fff;color:var(--ink)}
  input:focus,select:focus{outline:2px solid #bfdbfe;border-color:var(--brand)}
  .row{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}
  button.act{background:var(--brand);color:#fff;border:0;border-radius:8px;padding:10px 16px;font-size:14px;font-weight:600;cursor:pointer;font-family:inherit}
  button.act:hover{background:var(--brand2)}
  button.ghost{background:#fff;color:var(--brand);border:1px solid #bfdbfe}
  .out{display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));margin-top:18px}
  .out div{background:#f8fafc;border:1px solid var(--line);border-radius:8px;padding:10px 12px}
  .out .l{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}
  .out .v{font-size:17px;font-weight:700;margin-top:3px}
  .warn{background:#fffbeb;border:1px solid #fde68a;color:#78350f;border-radius:8px;padding:10px 12px;font-size:13px;margin-top:12px}
  .note{background:#eff6ff;border:1px solid #bfdbfe;color:#1e3a8a;border-radius:8px;padding:10px 12px;font-size:13px;margin-bottom:16px}
  footer{color:var(--muted);font-size:12px;margin-top:26px;border-top:1px solid var(--line);padding-top:14px}
  @media(max-width:820px){
    .app{flex-direction:column}
    aside{width:auto;height:auto;position:static;flex:none}
    nav{display:grid;grid-template-columns:1fr 1fr;gap:2px}
    main{padding:18px 14px 50px}
    table{font-size:12.5px}
    th,td{padding:7px 6px}
  }
</style>
</head>
<body>
<div class="app">
  <aside>
    <h1>E-COMMERCE AI EMPIRE</h1>
    <div class="sub">America/Sao_Paulo · BRL · dados reais do banco</div>
    <nav id="nav"></nav>
  </aside>
  <main id="view"></main>
</div>
<script>
const DATA = /*__DATA__*/;

/* ---------- utilitários ---------- */
const brl = v => (v === null || v === undefined || isNaN(v)) ? "—"
  : v.toLocaleString("pt-BR", {style:"currency", currency:"BRL"});
const pct = v => (v === null || v === undefined || isNaN(v)) ? "—" : v.toFixed(1).replace(".", ",") + "%";
const num = v => (v === null || v === undefined || isNaN(v)) ? "—" : v.toLocaleString("pt-BR", {minimumFractionDigits:2, maximumFractionDigits:2});
const esc = s => String(s === null || s === undefined ? "" : s)
  .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
const r2 = v => Math.round((v + Number.EPSILON) * 100) / 100;

/* ---------- calculadora: espelha analytics/profitability.py ---------- */
function calcular(i){
  const qty = Math.max(1, Math.floor(i.quantity || 1));
  const grossRevenue = i.salePrice * qty;
  const revenue = grossRevenue - i.discount * qty;
  const goodsCost = (i.purchasePrice + i.acquisitionShipping + i.packaging + i.otherCosts) * qty;
  const commission = revenue * (i.commissionPct / 100);
  const fixedFees = i.fixedFee * qty;
  const shipping = i.subsidizedShipping * qty;
  const fees = commission + fixedFees + shipping;
  const taxes = revenue * (i.taxPct / 100);
  const adCost = i.adCost * qty;
  const totalCost = goodsCost + fees + taxes + adCost;
  const grossProfit = revenue - goodsCost;
  const netProfit = revenue - totalCost;
  const netPerUnit = netProfit / qty;
  const marginPct = revenue ? (netProfit / revenue * 100) : 0;
  const invested = goodsCost + adCost;
  const roiPct = invested ? (netProfit / invested * 100) : 0;
  const markupPct = i.purchasePrice ? ((i.salePrice - i.purchasePrice) / i.purchasePrice * 100) : 0;

  const perUnitFixed = i.purchasePrice + i.acquisitionShipping + i.packaging + i.otherCosts
    + i.fixedFee + i.subsidizedShipping + i.adCost + i.discount;
  const rate = (i.commissionPct + i.taxPct) / 100;
  const solve = target => {
    const den = 1 - rate - target;
    return den <= 0 ? null : r2(perUnitFixed / den);
  };
  const minBreakeven = solve(0);
  const minTarget = solve((i.targetMarginPct || 0) / 100);
  const breakevenUnits = (i.fixedMonthlyCosts > 0 && netPerUnit > 0)
    ? Math.ceil(i.fixedMonthlyCosts / netPerUnit) : null;

  const warnings = [];
  if (i.commissionPct === 0 && i.fixedFee === 0)
    warnings.push("Comissão e taxa fixa estão em 0. Se o canal cobra taxas, informe os valores para não superestimar o lucro.");
  if (i.taxPct === 0)
    warnings.push("Impostos em 0%. Informe o percentual aplicável ao seu regime.");
  if (grossProfit > 0 && netProfit <= 0)
    warnings.push("Lucro bruto positivo, mas o lucro líquido é negativo: taxas, frete, impostos ou anúncios consomem toda a margem.");
  if (netProfit < 0) warnings.push("Prejuízo estimado nesta configuração.");
  if (i.salePrice < i.purchasePrice) warnings.push("O preço de venda está abaixo do custo de compra.");
  if (minTarget === null)
    warnings.push("Não é possível atingir a margem desejada: comissão + imposto + margem somam 100% ou mais da receita.");

  const health = marginPct >= 25 ? "saudável" : marginPct >= 12 ? "atenção" : "crítico";
  return {revenue, goodsCost, fees, taxes, adCost, totalCost, grossProfit, netProfit,
          netPerUnit, marginPct, roiPct, markupPct, minBreakeven, minTarget, breakevenUnits,
          warnings, health};
}
if (typeof module !== "undefined") module.exports = {calcular};

/* ---------- páginas ---------- */
const PAGES = [
  ["home", "Visão geral"],
  ["agente", "Super agente"],
  ["products", "Produtos"],
  ["opps", "Oportunidades"],
  ["prazos", "Prazos e fornecedores"],
  ["calc", "Calculadora financeira"],
  ["agents", "Central de agentes"],
  ["channels", "Conexões"],
  ["report", "Relatório"],
  ["about", "Sobre os dados"],
];

function cardKpi(label, value, sub){
  return `<div class="kpi"><div class="l">${esc(label)}</div><div class="v">${value}</div><div class="s">${esc(sub||"")}</div></div>`;
}

function tagFor(score){
  if (score === null || score === undefined) return `<span class="tag off">sem dados</span>`;
  if (score >= 90) return `<span class="tag ok">prioritária</span>`;
  if (score >= 75) return `<span class="tag ok">interessante</span>`;
  if (score >= 60) return `<span class="tag mid">analisar</span>`;
  return `<span class="tag bad">não recomendar</span>`;
}

const VIEWS = {
  modoBanner(){
    const c = DATA.config || {mode:"demo", prontos:0, total:0, itens:[]};
    const real = c.mode === "real";
    const pend = c.itens.filter(i => !i.ok);
    const cor = real ? (pend.length ? "mid" : "ok") : "off";
    return `
      <div class="panel" style="border-left:4px solid ${real ? "#0f766e" : "#94a3b8"}">
        <div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:baseline">
          <div style="font-weight:700;font-size:14px">
            ${real ? "MODO REAL" : "MODO DEMO"} · ${c.prontos}/${c.total} itens de operação prontos
          </div>
          <span class="tag ${cor}">${real ? (pend.length ? "faltam dados seus" : "pronto para operar") : "dados de teste"}</span>
        </div>
        <table style="margin-top:10px"><thead><tr><th style="width:34px"></th><th>Item</th>
          <th>Situação</th><th>Como resolver</th></tr></thead><tbody>
        ${c.itens.map(i => `<tr>
          <td>${i.ok ? "✔" : "—"}</td>
          <td style="font-weight:600">${esc(i.item)}</td>
          <td style="font-size:12.5px">${esc(i.detalhe)}</td>
          <td style="font-size:12px;color:#64748b">${i.ok ? "" : esc(i.como)}</td>
        </tr>`).join("")}
        </tbody></table>
      </div>`;
  },

  home(){
    const k = DATA.kpis;
    const top = DATA.products.filter(p => p.fin && p.fin.netProfit !== undefined)
      .sort((a,b) => (b.fin.marginPct||0) - (a.fin.marginPct||0)).slice(0,5);
    return `
      <h2>Visão geral da operação</h2>
      <div class="hint">Cada número vem do banco do sistema. Margens e lucros são calculados por código, nunca estimados por IA.</div>
      ${VIEWS.modoBanner()}
      ${DATA.has_demo ? `<div class="note">Há registros marcados como <b>DEMO</b>. Eles servem para testar o painel e não devem ser confundidos com dados reais de operação.</div>` : ""}
      <div class="grid">
        ${cardKpi("Produtos", k.products, "catálogo analisado")}
        ${cardKpi("Oportunidades", k.opportunities, `${k.scored} com score · média ${k.avg_score}`)}
        ${cardKpi("Lucro est./un", brl(k.profit_per_unit), "soma por unidade vendida")}
        ${cardKpi("Concorrentes", k.competitors, "mapeados")}
        ${cardKpi("Fornecedores", k.suppliers, "cadastrados")}
        ${cardKpi("Agentes", DATA.agents.length, "especialistas")}
      </div>
      <section class="panel">
        <h3 style="margin:0 0 10px;font-size:16px">Produtos com melhor margem</h3>
        <table><thead><tr><th>Produto</th><th>Canal</th><th class="num">Venda</th><th class="num">Margem</th><th class="num">Lucro/un</th></tr></thead><tbody>
        ${top.map(p => `<tr><td>${esc(p.name)} ${p.is_demo?'<span class="tag demo">DEMO</span>':''}</td>
          <td>${esc(p.marketplace)}</td><td class="num">${brl(p.sale_price)}</td>
          <td class="num">${pct(p.fin.marginPct)}</td><td class="num">${brl(p.fin.netPerUnit)}</td></tr>`).join("")}
        ${top.length ? "" : `<tr><td colspan="5">Nenhum produto cadastrado.</td></tr>`}
        </tbody></table>
      </section>
      <section class="panel">
        <h3 style="margin:0 0 10px;font-size:16px">Cinco melhores oportunidades</h3>
        <table><thead><tr><th>Produto</th><th>Canal</th><th class="num">Score</th><th>Classificação</th><th class="num">Margem est.</th></tr></thead><tbody>
        ${DATA.opportunities.slice(0,5).map(o => `<tr><td>${esc(o.name)}</td><td>${esc(o.marketplace)}</td>
          <td class="num">${o.score === null ? "—" : o.score}</td><td>${tagFor(o.score)}</td>
          <td class="num">${pct(o.margin_estimate)}</td></tr>`).join("")}
        ${DATA.opportunities.length ? "" : `<tr><td colspan="5">Nenhuma oportunidade importada.</td></tr>`}
        </tbody></table>
      </section>`;
  },

  agente(){
    const a = DATA.autonomia || {};
    const ligado = a.enabled && !a.paused;
    return `
      <h2>Super agente autônomo</h2>
      <div class="hint">Modo manual: ele roda o plano do CEO quando você aperta o botão, grava o
      relatório e para. Nada roda sozinho. Comprar, pagar, publicar anúncio e alterar preço
      continuam exigindo sua aprovação.</div>
      <div class="grid">
        ${cardKpi("Estado", a.enabled ? (ligado ? "rodando" : "pausado") : "manual (só no botão)",
                  a.pause_reason || "sem pausa")}
        ${cardKpi("Ciclos hoje", a.cycles_today ?? 0, "limite diário padrão: 8")}
        ${cardKpi("Ciclos no total", a.cycles_total ?? 0, "desde o início")}
        ${cardKpi("Falhas seguidas", a.consecutive_failures ?? 0, "2 pausam sozinho")}
      </div>
      <section class="panel">
        <h3 style="margin:0 0 8px;font-size:16px">Último ciclo</h3>
        <div style="font-size:13px;color:#64748b;margin-bottom:8px">
          ${a.last_cycle_at ? esc(String(a.last_cycle_at).slice(0,16).replace("T"," ")) : "nunca rodou"}
          ${a.last_status ? " · " + esc(a.last_status) : ""}
        </div>
        <pre style="white-space:pre-wrap;font-size:12.5px;background:#f8fafc;border:1px solid var(--line);border-radius:8px;padding:12px;max-height:460px;overflow:auto;margin:0">${esc(a.last_summary || "Nenhum ciclo registrado ainda.")}</pre>
      </section>
      <section class="panel">
        <h3 style="margin:0 0 8px;font-size:16px">O que ele faz sozinho e o que não faz</h3>
        <table><thead><tr><th>Faz sozinho</th><th>Só com sua aprovação</th></tr></thead><tbody>
          <tr><td>Pesquisar produto, calcular margem, checar se o fornecedor entrega no prazo,
                  comparar concorrente, escrever título, descrição e roteiro, montar relatório.</td>
              <td>Comprar, pagar, publicar anúncio, mudar preço, excluir produto,
                  mandar mensagem em massa, mexer em campanha.</td></tr>
        </tbody></table>
        <div class="note" style="margin-top:12px">Você também pode mandar comando em português,
        como faz com um assistente: <code>python -m core.chat</code> no terminal ou
        <code>python -m scripts.telegram_bot</code> para falar com ele pelo Telegram
        (só precisa do token do @BotFather, sem servidor público).</div>
        <div class="note" style="margin-top:12px">Para rodar sem ninguém abrir o painel:
        <code>python -m core.autonomy --loop</code>. Sem esse processo ativo, ele só roda no botão.</div>
      </section>`;
  },

  products(){
    const rows = DATA.products;
    return `
      <h2>Produtos</h2>
      <div class="hint">Lucro e margem calculados com as taxas do canal configuradas no sistema. Taxa em 0 significa "não informada".</div>
      <section class="panel">
        <table><thead><tr><th>Produto</th><th>Categoria</th><th>Canal</th>
          <th class="num">Compra</th><th class="num">Venda</th><th class="num">Lucro/un</th>
          <th class="num">Margem</th><th class="num">ROI</th><th class="num">Preço mín.</th></tr></thead><tbody>
        ${rows.map(p => {
          const f = p.fin || {};
          return `<tr><td>${esc(p.name)} ${p.is_demo?'<span class="tag demo">DEMO</span>':''}</td>
            <td>${esc(p.category)}</td><td>${esc(p.marketplace)}</td>
            <td class="num">${brl(p.purchase_price)}</td><td class="num">${brl(p.sale_price)}</td>
            <td class="num">${brl(f.netPerUnit)}</td><td class="num">${pct(f.marginPct)}</td>
            <td class="num">${pct(f.roiPct)}</td><td class="num">${brl(f.minBreakeven)}</td></tr>`;
        }).join("") || `<tr><td colspan="9">Nenhum produto cadastrado.</td></tr>`}
        </tbody></table>
        <div class="row"><button class="act" onclick="exportCsv('produtos')">Exportar CSV</button></div>
      </section>`;
  },

  opps(){
    return `
      <h2>Oportunidades</h2>
      <div class="hint">Product Opportunity Score de 0 a 100. Pesos: demanda 25, margem 25, concorrência 15, tendência 15, logística 10, tráfego 10.</div>
      <section class="panel">
        <table><thead><tr><th>Produto</th><th>Canal</th><th class="num">Preço visto</th>
          <th class="num">Custo est.</th><th class="num">Margem est.</th><th class="num">Score</th>
          <th>Classificação</th><th>Fonte</th></tr></thead><tbody>
        ${DATA.opportunities.map(o => `<tr>
          <td>${esc(o.name)} ${o.is_demo?'<span class="tag demo">DEMO</span>':''}</td>
          <td>${esc(o.marketplace)}</td><td class="num">${brl(o.price_found)}</td>
          <td class="num">${brl(o.cost_estimate)}</td><td class="num">${pct(o.margin_estimate)}</td>
          <td class="num">${o.score === null ? "—" : o.score}</td><td>${tagFor(o.score)}</td>
          <td style="font-size:12px;color:#64748b">${esc(o.sources && o.sources.demanda ? o.sources.demanda : "—")}</td>
        </tr>`).join("") || `<tr><td colspan="8">Nenhuma oportunidade importada.</td></tr>`}
        </tbody></table>
        <div class="row"><button class="act" onclick="exportCsv('oportunidades')">Exportar CSV</button></div>
      </section>
      <section class="panel">
        <h3 style="margin:0 0 12px;font-size:16px">Composição da nota (por critério e peso)</h3>
        ${DATA.opportunities.slice(0,3).map(o => `
          <div style="margin-bottom:16px">
            <div style="font-weight:600;font-size:14px">${esc(o.name)} — ${o.score === null ? "sem nota" : o.score + " pts"}</div>
            ${["demanda","margem","concorrencia","tendencia","logistica","trafego"].map(k => {
              const names = {demanda:"Demanda e procura",margem:"Margem de lucro",concorrencia:"Concorrência",
                tendencia:"Tendência de crescimento",logistica:"Facilidade logística",trafego:"Potencial de tráfego orgânico"};
              const weights = {demanda:25,margem:25,concorrencia:15,tendencia:15,logistica:10,trafego:10};
              const v = (o.criteria || {})[k];
              return `<div style="display:flex;align-items:center;gap:10px;margin-top:5px;font-size:12.5px">
                <span style="flex:0 0 190px;color:#475569">${names[k]} <span style="color:#94a3b8">(${weights[k]} pts)</span></span>
                <span class="bar" style="flex:1"><i style="width:${v === null || v === undefined ? 0 : v}%"></i></span>
                <span style="flex:0 0 42px;text-align:right;color:#0f172a;font-weight:600">${v === null || v === undefined ? "n/d" : v}</span>
              </div>`;
            }).join("")}
          </div>`).join("") || "<div>Sem oportunidades para detalhar.</div>"}
      </section>`;
  },

  prazos(){
    const v = DATA.viability || [];
    const tagV = t => {
      if (t === "pode vender hoje") return `<span class="tag ok">${esc(t)}</span>`;
      if (t === "vende no limite") return `<span class="tag mid">${esc(t)}</span>`;
      if (t === "vende com risco") return `<span class="tag mid">${esc(t)}</span>`;
      if (t === "perde o prazo") return `<span class="tag bad">${esc(t)}</span>`;
      return `<span class="tag off">${esc(t)}</span>`;
    };
    return `
      <h2>Prazos e fornecedores</h2>
      <div class="hint">Atraso no despacho derruba o anúncio no ranking e queima o tráfego.
      Aqui cada fornecedor é comparado com o prazo de despacho do canal. Os prazos abaixo são
      valores carregados na configuração do sistema (marcados quando são DEMO).</div>
      ${v.length ? "" : `<div class="note">Nenhum canal configurado.</div>`}
      ${v.map(c => `
        <section class="panel">
          <div style="display:flex;justify-content:space-between;align-items:baseline;gap:10px;flex-wrap:wrap">
            <h3 style="margin:0;font-size:16px">${esc(c.channel_name)}</h3>
            <span style="font-size:12.5px;color:#64748b">
              ${c.informed ? `despachar em até <b>${c.handling_days}</b> dia(s) útil(eis) · entrega ${c.delivery_days} dia(s)` : `<span class="tag bad">prazo não informado</span>`}
            </span>
          </div>
          <div style="font-size:12px;color:#94a3b8;margin:4px 0 10px">fonte: ${esc(c.source || "não informado")}</div>
          <table><thead><tr><th>Fornecedor</th><th>Veredito</th><th>Despacha em</th>
            <th class="num">Dias úteis</th><th class="num">Folga</th><th>Modo</th>
            <th class="num">Custo/un</th></tr></thead><tbody>
          ${c.ranking.map(r => `<tr>
            <td style="font-weight:600">${esc(r.supplier)}</td>
            <td>${tagV(r.verdict)}</td>
            <td>${esc((r.dispatch_date||"").split("-").reverse().join("/"))}</td>
            <td class="num">${r.days_to_dispatch}</td>
            <td class="num">${r.slack_days === null ? "—" : r.slack_days}</td>
            <td style="font-size:12.5px">${esc(r.mode)}</td>
            <td class="num">${brl(r.landed_unit_cost)}</td></tr>`).join("") ||
            `<tr><td colspan="7">Nenhum fornecedor cadastrado.</td></tr>`}
          </tbody></table>
        </section>`).join("")}
      <section class="panel">
        <h3 style="margin:0 0 8px;font-size:16px">Como usar isso</h3>
        <div style="font-size:13.5px;color:#334155">
          Só publique um produto cujo fornecedor apareça como <b>pode vender hoje</b>.
          Se o melhor aparecer como <b>vende no limite</b>, tenha estoque já na mão antes de subir
          o anúncio. Se aparecer <b>perde o prazo</b>, ou você acha outro fornecedor, ou usa
          retirada no mesmo dia, ou não vende esse produto nesse canal.
        </div>
      </section>`;
  },

  calc(){
    const presets = DATA.marketplaces.map(m =>
      `<option value="${esc(m.slug)}" data-c="${m.commission_pct||0}" data-f="${m.fixed_fee||0}">${esc(m.name)}</option>`).join("");
    const field = (id, label, value, step) =>
      `<div><label for="${id}">${label}</label><input id="${id}" type="number" step="${step||"0.01"}" min="0" value="${value}"></div>`;
    return `
      <h2>Calculadora financeira</h2>
      <div class="hint">Mesma matemática do motor Python do projeto: receita, custos, taxas, impostos, lucro, margem, ROI, preço mínimo e ponto de equilíbrio.</div>
      <section class="panel">
        <div class="note">As taxas de marketplace não vêm prontas de propósito: o sistema não inventa comissão. Preencha com o valor real do seu contrato.</div>
        <div style="margin-bottom:14px">
          <label for="preset">Canal de venda</label>
          <select id="preset" onchange="aplicarPreset()">
            <option value="" selected>Preencher manualmente</option>
            ${presets}
          </select>
        </div>
        <form class="calc" onsubmit="return false">
          ${field("quantity","Quantidade",1,"1")}
          ${field("purchasePrice","Preço de compra",0)}
          ${field("acquisitionShipping","Frete de aquisição",0)}
          ${field("packaging","Embalagem",0)}
          ${field("otherCosts","Outros custos",0)}
          ${field("salePrice","Preço de venda",0)}
          ${field("commissionPct","Comissão (%)",0,"0.01")}
          ${field("fixedFee","Taxa fixa por item",0)}
          ${field("subsidizedShipping","Frete subsidiado",0)}
          ${field("taxPct","Impostos (%)",0,"0.01")}
          ${field("discount","Desconto por unidade",0)}
          ${field("adCost","Custo de anúncios",0)}
          ${field("fixedMonthlyCosts","Custos fixos mensais",0)}
          ${field("targetMarginPct","Margem desejada (%)",20,"0.1")}
        </form>
        <div class="row">
          <button class="act" onclick="rodarCalculo()">Calcular</button>
          <button class="act ghost" onclick="exportCsv('calculo')">Exportar resultado</button>
        </div>
        <div id="calcOut"></div>
      </section>`;
  },

  agents(){
    return `
      <h2>Central de agentes</h2>
      <div class="hint">São ${DATA.agents.length} especialistas, cada um com responsabilidade e ferramentas próprias. Eles são executados pelo CEO na orquestração.</div>
      <section class="panel">
        <table><thead><tr><th>Agente</th><th>Papel</th><th>Responsabilidade</th><th>Status</th></tr></thead><tbody>
        ${DATA.agents.map(a => `<tr><td style="font-weight:600">${esc(a.name)}</td>
          <td>${esc(a.role)}</td><td style="color:#475569">${esc(a.description)}</td>
          <td><span class="tag ok">${esc(a.status)}</span></td></tr>`).join("") ||
          `<tr><td colspan="4">Agentes ainda não inicializados.</td></tr>`}
        </tbody></table>
      </section>`;
  },

  channels(){
    return `
      <h2>Conexões</h2>
      <div class="hint">Nenhuma integração é simulada. Sem credenciais válidas o status é "não conectado", e a operação usa importação por CSV.</div>
      <section class="panel">
        <table><thead><tr><th>Canal</th><th>Status</th><th class="num">Comissão</th><th class="num">Taxa fixa</th><th>Observação</th></tr></thead><tbody>
        ${DATA.channels.map(c => `<tr><td style="font-weight:600">${esc(c.label)}</td>
          <td><span class="tag ${c.connected ? "ok" : "off"}">${c.connected ? "conectado" : "não conectado"}</span></td>
          <td class="num">${c.commission_pct === null || c.commission_pct === undefined ? "—" : c.commission_pct + "%"}</td>
          <td class="num">${brl(c.fixed_fee)}</td>
          <td style="color:#475569;font-size:12.5px">${esc(c.notes)}</td></tr>`).join("")}
        </tbody></table>
        <div class="row"><button class="act" onclick="exportCsv('canais')">Exportar CSV</button></div>
      </section>
      <section class="panel">
        <h3 style="margin:0 0 8px;font-size:16px">O que falta para conectar</h3>
        <div style="font-size:13.5px;color:#334155">
          Cada canal exige credenciais próprias guardadas em variáveis de ambiente, nunca no código:
          Mercado Livre e Instagram usam OAuth oficial; Shopee e TikTok Shop usam chave de parceiro;
          WooCommerce usa chave REST. Enquanto isso não existe, o caminho é exportar CSV no painel do
          marketplace e importar em <b>Pesquisa de produtos</b>.
        </div>
      </section>`;
  },

  report(){
    const top = DATA.opportunities.slice(0,5);
    const k = DATA.kpis;
    return `
      <h2>Relatório da operação</h2>
      <div class="hint">Gerado em ${esc(DATA.generated_at)} a partir do banco do sistema.</div>
      <section class="panel" style="font-size:14px;color:#1e293b">
        <p><b>Resumo.</b> O catálogo tem ${k.products} produtos e ${k.opportunities} oportunidades mapeadas
        (${k.scored} com score calculado, média ${String(k.avg_score).replace(".",",")}).
        O lucro estimado por unidade vendida somando o catálogo é ${brl(k.profit_per_unit)}.</p>
        <p><b>Cinco melhores oportunidades.</b></p>
        <ol style="padding-left:20px;margin-top:0">
          ${top.map(o => `<li><b>${esc(o.name)}</b> — ${esc(o.marketplace)}, score ${o.score === null ? "n/d" : o.score}
            (${esc(o.recommendation || "sem classificação")}), margem estimada ${pct(o.margin_estimate)}.
            Fonte: ${esc(o.sources && o.sources.demanda ? o.sources.demanda : "não informada")}.</li>`).join("") ||
            "<li>Nenhuma oportunidade importada ainda.</li>"}
        </ol>
        <p><b>O que observar antes de comprar.</b> Comissão e imposto informados mudam a margem
        inteira; com eles em zero o lucro aparece inflado. Antes de repor estoque, confirme prazo e
        custo real do fornecedor e simule na calculadora com o frete que você vai pagar.</p>
      </section>`;
  },

  about(){
    return `
      <h2>Sobre os dados</h2>
      <div class="hint">Transparência sobre o que este painel mostra e o que ele não faz.</div>
      <section class="panel" style="font-size:14px;color:#1e293b">
        <p><b>Origem.</b> Todos os números vêm do banco do sistema
        (${DATA.has_demo ? "que neste momento contém registros de demonstração marcados como DEMO" : "sem registros de demonstração"}).
        Preços e concorrentes só entram por importação de CSV, dados informados por você ou API autorizada.
        O sistema não raspa sites protegidos e não inventa estatística de vendas.</p>
        <p><b>Cálculo.</b> Margem, lucro, ROI, preço mínimo e ponto de equilíbrio são calculados por código
        determinístico. A IA, quando configurada, apenas explica o resultado.</p>
        <p><b>Limite desta página.</b> Ela é uma fotografia do estado em ${esc(DATA.generated_at)}. Os números
        são reais, mas a análise nova (pedir ao CEO, importar CSV, rodar automação) acontece no aplicativo
        Streamlit, que precisa de execução contínua. Aqui, o que é interativo é a calculadora.</p>
        <p><b>Fuso e moeda.</b> ${esc(DATA.timezone)} · ${esc(DATA.currency)}.</p>
      </section>`;
  },
};

/* ---------- navegação ---------- */
let current = "home";
function render(page){
  current = page;
  document.getElementById("view").innerHTML = VIEWS[page]();
  document.querySelectorAll("#nav button").forEach(b =>
    b.classList.toggle("on", b.dataset.p === page));
  if (page === "calc") rodarCalculo();
  window.scrollTo(0,0);
}
document.getElementById("nav").innerHTML = PAGES.map(
  ([id, label]) => `<button data-p="${id}" onclick="render('${id}')">${label}</button>`).join("");

/* ---------- ação: calcular ---------- */
const g = id => {
  const el = document.getElementById(id);
  const v = parseFloat(String(el.value).replace(",", "."));
  return isNaN(v) ? 0 : v;
};
function aplicarPreset(){
  const sel = document.getElementById("preset");
  const opt = sel.options[sel.selectedIndex];
  if (!opt || !opt.dataset.c) return;
  document.getElementById("commissionPct").value = opt.dataset.c;
  document.getElementById("fixedFee").value = opt.dataset.f;
}
function lerFormulario(){
  return {
    quantity: g("quantity") || 1, purchasePrice: g("purchasePrice"),
    acquisitionShipping: g("acquisitionShipping"), packaging: g("packaging"),
    otherCosts: g("otherCosts"), salePrice: g("salePrice"),
    commissionPct: g("commissionPct"), fixedFee: g("fixedFee"),
    subsidizedShipping: g("subsidizedShipping"), taxPct: g("taxPct"),
    discount: g("discount"), adCost: g("adCost"),
    fixedMonthlyCosts: g("fixedMonthlyCosts"), targetMarginPct: g("targetMarginPct"),
  };
}
let ultimoCalculo = null;
function rodarCalculo(){
  const i = lerFormulario();
  const out = document.getElementById("calcOut");
  if (!i.salePrice || i.salePrice <= 0){
    out.innerHTML = `<div class="warn">Informe um preço de venda maior que zero para calcular.</div>`;
    return;
  }
  if (i.discount >= i.salePrice){
    out.innerHTML = `<div class="warn">O desconto não pode ser maior ou igual ao preço de venda.</div>`;
    return;
  }
  const c = calcular(i);
  ultimoCalculo = {i, c};
  const cls = c.health === "saudável" ? "ok" : c.health === "atenção" ? "mid" : "bad";
  out.innerHTML = `
    <div style="margin-top:18px;display:flex;align-items:center;gap:10px">
      <b style="font-size:15px">Resultado</b><span class="tag ${cls}">${c.health}</span>
    </div>
    <div class="out">
      <div><div class="l">Receita</div><div class="v">${brl(c.revenue)}</div></div>
      <div><div class="l">Custo das mercadorias</div><div class="v">${brl(c.goodsCost)}</div></div>
      <div><div class="l">Taxas do canal</div><div class="v">${brl(c.fees)}</div></div>
      <div><div class="l">Impostos</div><div class="v">${brl(c.taxes)}</div></div>
      <div><div class="l">Anúncios</div><div class="v">${brl(c.adCost)}</div></div>
      <div><div class="l">Custo total</div><div class="v">${brl(c.totalCost)}</div></div>
      <div><div class="l">Lucro bruto</div><div class="v">${brl(c.grossProfit)}</div></div>
      <div><div class="l">Lucro líquido</div><div class="v">${brl(c.netProfit)}</div></div>
      <div><div class="l">Margem</div><div class="v">${pct(c.marginPct)}</div></div>
      <div><div class="l">ROI</div><div class="v">${pct(c.roiPct)}</div></div>
      <div><div class="l">Markup</div><div class="v">${pct(c.markupPct)}</div></div>
      <div><div class="l">Lucro por unidade</div><div class="v">${brl(c.netPerUnit)}</div></div>
      <div><div class="l">Preço mínimo (equilíbrio)</div><div class="v">${brl(c.minBreakeven)}</div></div>
      <div><div class="l">Preço p/ margem desejada</div><div class="v">${brl(c.minTarget)}</div></div>
      <div><div class="l">Ponto de equilíbrio</div><div class="v">${c.breakevenUnits === null ? "—" : c.breakevenUnits + " un/mês"}</div></div>
    </div>
    ${c.warnings.length ? `<div class="warn"><b>Atenção:</b><br>${c.warnings.map(esc).join("<br>")}</div>` : ""}`;
}

/* ---------- ação: exportar CSV ---------- */
function baixar(nome, texto){
  const blob = new Blob(["\ufeff" + texto], {type:"text/csv;charset=utf-8;"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = nome;
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(a.href);
}
function exportCsv(tipo){
  const sep = ";";
  if (tipo === "produtos"){
    const head = ["nome","categoria","canal","preco_compra","preco_venda","lucro_unidade","margem_pct","roi_pct","preco_minimo"];
    const lines = DATA.products.map(p => [p.name, p.category, p.marketplace, p.purchase_price, p.sale_price,
      p.fin.netPerUnit, p.fin.marginPct, p.fin.roiPct, p.fin.minBreakeven]);
    baixar("produtos.csv", [head, ...lines].map(r => r.map(v => `"${v ?? ""}"`).join(sep)).join("\n"));
  } else if (tipo === "oportunidades"){
    const head = ["nome","categoria","canal","preco_visto","custo_estimado","margem_estimada","score","classificacao","fonte"];
    const lines = DATA.opportunities.map(o => [o.name, o.category, o.marketplace, o.price_found,
      o.cost_estimate, o.margin_estimate, o.score, o.recommendation,
      o.sources && o.sources.demanda ? o.sources.demanda : ""]);
    baixar("oportunidades.csv", [head, ...lines].map(r => r.map(v => `"${v ?? ""}"`).join(sep)).join("\n"));
  } else if (tipo === "canais"){
    const head = ["canal","status","comissao_pct","taxa_fixa"];
    const lines = DATA.channels.map(c => [c.label, c.connected ? "conectado" : "não conectado", c.commission_pct, c.fixed_fee]);
    baixar("canais.csv", [head, ...lines].map(r => r.map(v => `"${v ?? ""}"`).join(sep)).join("\n"));
  } else if (tipo === "calculo"){
    if (!ultimoCalculo){ alert("Calcule primeiro."); return; }
    const {i, c} = ultimoCalculo;
    const rows = [["campo","valor"],
      ["preco_venda", i.salePrice], ["quantidade", i.quantity], ["receita", c.revenue],
      ["custo_mercadorias", c.goodsCost], ["taxas", c.fees], ["impostos", c.taxes],
      ["anuncios", c.adCost], ["custo_total", c.totalCost], ["lucro_bruto", c.grossProfit],
      ["lucro_liquido", c.netProfit], ["margem_pct", c.marginPct], ["roi_pct", c.roiPct],
      ["preco_minimo", c.minBreakeven], ["preco_margem_desejada", c.minTarget],
      ["ponto_equilibrio_un", c.breakevenUnits]];
    baixar("calculo.csv", rows.map(r => r.join(sep)).join("\n"));
  }
}

render("home");
</script>
<footer style="padding:0 30px 30px">__FOOTER__</footer>
</body>
</html>
"""


def build(out_dir: Path, data: dict | None = None) -> Path:
    data = data or collect_data()
    out_dir.mkdir(parents=True, exist_ok=True)
    html = TEMPLATE.replace("/*__DATA__*/", json.dumps(data, ensure_ascii=False))
    html = html.replace(
        "__FOOTER__",
        f'Fotografia do estado em {data["generated_at"]} \u00b7 {data["timezone"]} '
        f'\u00b7 dados do banco do sistema',
    )
    target = out_dir / "index.html"
    target.write_text(html, encoding="utf-8")
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera o painel estático em docs/")
    parser.add_argument("--out", default=str(ROOT / "docs"))
    args = parser.parse_args()
    target = build(Path(args.out))
    print(f"painel gerado: {target} ({target.stat().st_size/1024:.1f} KB)")


if __name__ == "__main__":
    main()
