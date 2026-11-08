"""AGENTE 8 - SEO SPECIALIST: palavras-chave, títulos e descrições."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from agents.base import AgentContext, AgentResult, BaseAgent, MarketContext
from core.utils import normalize_text

STOPWORDS = {
    "de", "da", "do", "das", "dos", "para", "com", "sem", "e", "o", "a", "os", "as",
    "um", "uma", "no", "na", "em", "por", "que", "kit", "the", "and",
}


class SEOAgent(BaseAgent):
    name = "seo"
    role = "SEO Specialist"
    description = (
        "Extrai palavras-chave dos seus próprios dados (títulos, descrições, concorrentes), "
        "monta títulos dentro do limite de cada canal e aponta repetição artificial."
    )
    capabilities = ["extrair_palavras_chave", "otimizar_titulo", "otimizar_descricao",
                    "detectar_excesso_de_palavras_chave"]
    tools = [
        {"name": "keywords", "description": "Extrai termos recorrentes de fontes reais."},
        {"name": "title", "description": "Monta título otimizado por canal."},
        {"name": "audit", "description": "Aponta problemas de SEO no anúncio."},
    ]

    def execute(self) -> AgentResult:
        payload = self.ctx.payload()
        market = MarketContext(self.ctx)
        products = market.products()
        if payload.get("product"):
            products = [p for p in products if p.get("name") == payload["product"]] or products[:1]
        if not products:
            return AgentResult(
                summary="Sem produtos para otimizar.",
                data_gaps=["Cadastre produtos para gerar palavras-chave e títulos."],
            )

        rows: list[dict[str, Any]] = []
        gaps = ["Volume de busca real exige ferramenta externa (Google Keyword Planner, etc.). "
                "Aqui os termos vêm dos seus dados e dos concorrentes coletados."]
        for product in products[:10]:
            channel = product.get("marketplace") or "shopee"
            corpus = [product.get("name", ""), product.get("description", ""),
                      product.get("category", "")]
            competitors = self.ctx.repo.find("competitors", {"product_id": product["id"]}, limit=50)
            corpus += [c.get("name", "") for c in competitors]
            keywords = self._keywords(corpus, limit=10)
            from integrations import build_connector

            connector = build_connector(channel, self.ctx.settings, self.ctx.repo)
            limits = connector.listing_limits()
            title = self._build_title(product, keywords, limits["title_max_chars"])
            description = self._build_description(product, keywords)
            audit = self._audit(product, title, description, limits)
            rows.append(
                {
                    "product": product.get("name"),
                    "channel": channel,
                    "keywords": keywords,
                    "title": title,
                    "title_chars": len(title),
                    "title_limit": limits["title_max_chars"],
                    "description": description,
                    "issues": audit,
                    "is_demo": bool(product.get("is_demo")),
                }
            )

        findings = []
        for row in rows:
            findings.append(
                f"{row['product']}: título com {row['title_chars']}/{row['title_limit']} caracteres; "
                f"termos: {', '.join(k['termo'] for k in row['keywords'][:5])}"
            )
        issues = [i for row in rows for i in row["issues"]]
        narrative, provider = self.narrate(
            f"Otimização de SEO em {len(rows)} anúncios.",
            findings[:8], closing="Nenhum volume de busca foi estimado sem fonte."
        )
        return AgentResult(
            summary=f"{len(rows)} anúncios com título e palavras-chave otimizados.",
            data={"rows": rows, "demo_mode": any(r["is_demo"] for r in rows)},
            findings=findings,
            warnings=issues[:10],
            data_gaps=gaps,
            next_actions=[
                "Aplicar os títulos sugeridos nos anúncios (com aprovação).",
                "Coletar 10 títulos de concorrentes para ampliar o vocabulário real do nicho.",
            ],
            narrative=narrative,
            ai_provider=provider,
        )

    # ------------------------------------------------------------- extração --
    def _keywords(self, corpus: list[str], limit: int = 10) -> list[dict[str, Any]]:
        counter: Counter[str] = Counter()
        for text in corpus:
            tokens = [
                token for token in re.split(r"[^a-z0-9à-ÿ]+", normalize_text(text))
                if token and token not in STOPWORDS and len(token) > 2
            ]
            for size in (1, 2):
                for index in range(len(tokens) - size + 1):
                    term = " ".join(tokens[index:index + size])
                    counter[term] += 1
        return [{"termo": term, "ocorrencias": count} for term, count in counter.most_common(limit)]

    def _build_title(self, product: dict, keywords: list[dict], limit: int) -> str:
        base = product.get("name", "Produto").strip()
        extra: list[str] = []
        if product.get("category"):
            extra.append(str(product["category"]))
        for item in keywords:
            term = item["termo"]
            if term.lower() not in normalize_text(base) and term not in extra:
                extra.append(term)
        title = base
        for term in extra:
            candidate = f"{title} {term}".strip()
            if len(candidate) <= limit:
                title = candidate
            else:
                break
        return title[:limit]

    def _build_description(self, product: dict, keywords: list[dict]) -> str:
        name = product.get("name", "Produto")
        terms = ", ".join(k["termo"] for k in keywords[:6])
        return (
            f"{name}\n\n"
            f"O que você recebe: 1 unidade de {name}.\n"
            f"Ideal para: {product.get('category') or 'uso diário'}.\n"
            f"Palavras que descrevem este produto: {terms}.\n\n"
            "Envio rápido, produto conferido antes do despacho.\n"
            "Dúvidas? Responda pelo chat do anúncio antes de comprar.\n"
        )

    def _audit(self, product: dict, title: str, description: str, limits: dict) -> list[str]:
        issues: list[str] = []
        if len(title) < 25:
            issues.append("Título curto: perde espaço de busca.")
        if len(title) > limits["title_max_chars"]:
            issues.append("Título acima do limite do canal.")
        words = normalize_text(title).split()
        if len(words) >= 4 and len(set(words)) / len(words) < 0.6:
            issues.append("Possível repetição artificial de palavras no título.")
        if not description.strip():
            issues.append("Descrição vazia.")
        if not product.get("category"):
            issues.append("Categoria não informada: piora o posicionamento nas buscas.")
        return issues
