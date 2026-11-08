"""Planejador: transforma o pedido do proprietário em tarefas para os agentes.

A classificação de intenção é determinística (regras + palavras-chave), portanto
funciona sem IA e sem custo. A IA, quando existe, só narra o resultado.
"""

from __future__ import annotations

import re
from typing import Any

from core.utils import normalize_text

INTENT_RULES: list[dict[str, Any]] = [
    {
        "code": "product_research",
        "label": "Pesquisa e priorização de produtos",
        "patterns": ["produto", "produtos", "oportunidade", "oportunidades", "encontre",
                     "pesquis", "potencial de venda", "lucrativ", "analise concorrência",
                     "melhores oportunidades", "catalogo", "fornecedor de produto"],
    },
    {
        "code": "listing_audit",
        "label": "Auditoria de anúncios e melhorias",
        "patterns": ["anuncio", "anúncio", "anuncios", "visualiza", "vendas sem aumentar",
                     "melhorar", "melhoria", "otimizar anuncio", "impressao", "clique"],
    },
    {
        "code": "financial",
        "label": "Análise financeira e margem",
        "patterns": ["margem", "lucro", "preco", "preço", "custo", "taxa", "comissao",
                     "comissão", "imposto", "roi", "ponto de equilibrio", "equilíbrio",
                     "calculadora"],
    },
    {
        "code": "competitor",
        "label": "Análise de concorrentes",
        "patterns": ["concorrente", "concorrentes", "concorrencia", "concorrência",
                     "posicionamento", "comparar precos", "comparar preços"],
    },
    {
        "code": "marketing",
        "label": "Marketing e campanhas",
        "patterns": ["marketing", "campanha", "divulga", "publico", "público", "anuncio pago",
                     "trafego pago", "estrategia de venda", "promocao", "promoção"],
    },
    {
        "code": "video_content",
        "label": "Conteúdo e vídeos",
        "patterns": ["video", "vídeo", "roteiro", "reels", "shorts", "tiktok", "legenda",
                     "conteudo", "conteúdo", "calendario editorial", "criador de video"],
    },
    {
        "code": "supplier",
        "label": "Fornecedores e custo de aquisição",
        "patterns": ["fornecedor", "fornecedores", "atacado", "quantidade minima",
                     "custo de aquisicao", "comprar de quem"],
    },
    {
        "code": "customer",
        "label": "Atendimento e pós-venda",
        "patterns": ["cliente", "clientes", "atendimento", "pos-venda", "pós-venda", "faq",
                     "duvida", "dúvida", "mensagem", "resposta"],
    },
    {
        "code": "seo",
        "label": "SEO e palavras-chave",
        "patterns": ["seo", "palavra-chave", "palavras-chave", "titulo", "título",
                     "descricao", "descrição", "busca"],
    },
    {
        "code": "automation",
        "label": "Automações e rotinas",
        "patterns": ["automacao", "automação", "automacoes", "rotina", "agendamento",
                     "toda semana", "todos os dias", "diariamente", "semanalmente"],
    },
    {
        "code": "report",
        "label": "Relatórios",
        "patterns": ["relatorio", "relatório", "resumo do dia", "desempenho", "panorama"],
    },
]


def detect_intent(command: str) -> dict[str, Any]:
    """Classifica a intenção com confiança proporcional à quantidade de sinais."""
    text = normalize_text(command)
    best: dict[str, Any] | None = None
    for rule in INTENT_RULES:
        matched = [p for p in rule["patterns"] if p in text]
        if not matched:
            continue
        score = len(set(matched))
        if best is None or score > best["score"]:
            best = {"rule": rule, "score": score, "matched": matched}

    if best is None:
        return {
            "code": "general",
            "label": "Análise geral da operação",
            "confidence": 0.4,
            "matched": [],
        }
    confidence = min(0.95, 0.55 + 0.1 * best["score"])
    return {
        "code": best["rule"]["code"],
        "label": best["rule"]["label"],
        "confidence": round(confidence, 2),
        "matched": best["matched"][:6],
    }


def _step(agent: str, task_type: str, title: str, payload: dict | None = None,
          priority: int = 3, depends_on: list[str] | None = None) -> dict[str, Any]:
    return {
        "id": f"{agent}.{task_type}",
        "agent": agent,
        "task_type": task_type,
        "title": title,
        "payload": payload or {},
        "priority": priority,
        "depends_on": depends_on or [],
    }


FEATURED_PRODUCT = re.compile(r"\b(\d+)\s*(?:produtos|oportunidades)\b", re.IGNORECASE)


def build_plan(intent: dict[str, Any], command: str) -> list[dict[str, Any]]:
    """Monta o plano (lista ordenada de tarefas) para a intenção detectada."""
    code = intent.get("code", "general")
    top_match = FEATURED_PRODUCT.search(normalize_text(command))
    requested_products = int(top_match.group(1)) if top_match else 10
    limit = max(3, min(50, requested_products))
    top = min(5, limit)
    base = {"command": command}

    if code == "product_research":
        return [
            _step("product_hunter", "research", "Pesquisar e pontuar produtos",
                  {**base, "limit": limit, "top": top}, priority=1),
            _step("market_analyst", "competitor_scan", "Analisar concorrência e preços",
                  {**base}, priority=2, depends_on=["product_hunter.research"]),
            _step("financial", "evaluate", "Calcular custos, margem e lucro",
                  {**base}, priority=2, depends_on=["product_hunter.research"]),
            _step("seo", "keywords", "Preparar palavras-chave dos finalistas",
                  {**base}, priority=3, depends_on=["product_hunter.research"]),
            _step("ceo", "consolidate", "Consolidar as melhores oportunidades",
                  {**base}, priority=1,
                  depends_on=["market_analyst.competitor_scan", "financial.evaluate",
                              "seo.keywords"]),
        ]

    if code == "listing_audit":
        return [
            _step("marketplace_manager", "audit", "Auditar anúncios por canal", {**base}, priority=1),
            _step("seo", "audit", "Revisar títulos e descrições", {**base}, priority=2,
                  depends_on=["marketplace_manager.audit"]),
            _step("financial", "evaluate", "Checar margem dos anúncios", {**base}, priority=2),
            _step("marketing", "plan", "Propor melhorias de conversão", {**base}, priority=3,
                  depends_on=["marketplace_manager.audit"]),
            _step("ceo", "consolidate", "Consolidar plano de melhorias", {**base}, priority=1,
                  depends_on=["seo.audit", "financial.evaluate", "marketing.plan"]),
        ]

    if code == "financial":
        return [
            _step("financial", "evaluate", "Calcular margem, ROI e ponto de equilíbrio",
                  {**base}, priority=1),
            _step("marketplace_manager", "status", "Checar disponibilidade dos canais",
                  {**base, "mode": "status"}, priority=3),
            _step("ceo", "consolidate", "Consolidar o quadro financeiro", {**base}, priority=1,
                  depends_on=["financial.evaluate", "marketplace_manager.status"]),
        ]

    if code == "competitor":
        return [
            _step("market_analyst", "competitor_scan", "Comparar concorrentes e preços",
                  {**base}, priority=1),
            _step("seo", "keywords", "Extrair termos usados pelos concorrentes", {**base},
                  priority=2, depends_on=["market_analyst.competitor_scan"]),
            _step("ceo", "consolidate", "Consolidar posicionamento", {**base}, priority=1,
                  depends_on=["market_analyst.competitor_scan", "seo.keywords"]),
        ]

    if code == "marketing":
        return [
            _step("marketing", "plan", "Criar campanhas orgânicas", {**base}, priority=1),
            _step("video_creator", "scripts", "Escrever roteiros de vídeo", {**base}, priority=2,
                  depends_on=["marketing.plan"]),
            _step("content_intelligence", "plan", "Montar calendário de conteúdo", {**base},
                  priority=2),
            _step("ceo", "consolidate", "Consolidar o plano de marketing", {**base}, priority=1,
                  depends_on=["marketing.plan", "video_creator.scripts",
                              "content_intelligence.plan"]),
        ]

    if code == "video_content":
        return [
            _step("video_creator", "scripts", "Escrever roteiros de 15, 30 e 60s", {**base},
                  priority=1),
            _step("content_intelligence", "plan", "Planejar calendário de publicações", {**base},
                  priority=2),
            _step("marketing", "plan", "Definir distribuição orgânica", {**base}, priority=3),
            _step("ceo", "consolidate", "Consolidar plano de conteúdo", {**base}, priority=1,
                  depends_on=["video_creator.scripts", "content_intelligence.plan",
                              "marketing.plan"]),
        ]

    if code == "supplier":
        return [
            _step("supplier_hunter", "compare", "Comparar fornecedores por custo total",
                  {**base}, priority=1),
            _step("financial", "evaluate", "Validar margem com o custo do fornecedor",
                  {**base}, priority=2, depends_on=["supplier_hunter.compare"]),
            _step("ceo", "consolidate", "Consolidar recomendação de compra", {**base}, priority=1,
                  depends_on=["supplier_hunter.compare", "financial.evaluate"]),
        ]

    if code == "customer":
        return [
            _step("customer", "faq", "Preparar FAQ e modelos de resposta", {**base}, priority=1),
            _step("ceo", "consolidate", "Consolidar padrão de atendimento", {**base}, priority=1,
                  depends_on=["customer.faq"]),
        ]

    if code == "seo":
        return [
            _step("seo", "audit", "Otimizar títulos, descrições e palavras-chave", {**base},
                  priority=1),
            _step("marketplace_manager", "audit", "Checar limites de cada canal", {**base},
                  priority=2),
            _step("ceo", "consolidate", "Consolidar plano de SEO", {**base}, priority=1,
                  depends_on=["seo.audit", "marketplace_manager.audit"]),
        ]

    if code == "automation":
        return [
            _step("automation", "overview", "Verificar rotinas e execuções", {**base}, priority=1),
            _step("ceo", "consolidate", "Consolidar estado das automações", {**base}, priority=1,
                  depends_on=["automation.overview"]),
        ]

    if code == "report":
        return [
            _step("financial", "evaluate", "Recalcular margens do período", {**base}, priority=1),
            _step("product_hunter", "research", "Reavaliar oportunidades", {**base}, priority=2),
            _step("automation", "report", "Gerar relatório", {**base, "kind": "daily"}, priority=3,
                  depends_on=["financial.evaluate"]),
            _step("ceo", "consolidate", "Consolidar relatório", {**base}, priority=1,
                  depends_on=["automation.report", "product_hunter.research"]),
        ]

    return [
        _step("product_hunter", "research", "Levantar oportunidades", {**base}, priority=1),
        _step("market_analyst", "competitor_scan", "Analisar concorrência", {**base}, priority=2),
        _step("financial", "evaluate", "Calcular margem e lucro", {**base}, priority=2),
        _step("ceo", "consolidate", "Consolidar visão geral", {**base}, priority=1,
              depends_on=["product_hunter.research", "market_analyst.competitor_scan",
                          "financial.evaluate"]),
    ]
