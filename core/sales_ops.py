"""Operador de vendas: o que precisa estar pronto para o anúncio vender.

O que este módulo faz (tudo determinístico, nada estimado por IA):
  * calcula o preço que entrega a margem alvo, com comissão e taxa fixa reais;
  * calcula estoque mínimo e quanto repor, a partir do prazo do fornecedor
    (7 dias, conforme informado) e de 2 dias de segurança;
  * diz o que falta no anúncio para poder publicar (título, descrição, preço,
    custo, categoria), item por item;
  * monta a lista de tarefas do dia, separando o que já vende do que está travado.

O que ele NÃO faz: publicar, comprar ou pagar sozinho. O conector monta o rascunho
e o envio depende da sua aprovação explícita. Isso é decisão de projeto, não falta
de recurso: sem isso o sistema poderia gastar seu dinheiro sem você mandar.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

VEREDITO_PRONTO = "pronto para publicar"
VEREDITO_AJUSTAR = "faltam ajustes"
VEREDITO_BLOQUEADO = "bloqueado por dado faltante"


@dataclass
class Checagem:
    item: str
    ok: bool
    detalhe: str

    def to_dict(self) -> dict[str, Any]:
        return {"item": self.item, "ok": self.ok, "detalhe": self.detalhe}


@dataclass
class PlanoProduto:
    product_id: str
    nome: str
    canal: str
    veredito: str
    preco_atual: float
    preco_sugerido: float | None
    margem_pct: float | None
    lucro_unidade: float | None
    vendas_30d: int
    estoque_atual: int
    estoque_minimo: int
    repor: int
    checagens: list[Checagem] = field(default_factory=list)

    @property
    def bloqueios(self) -> list[str]:
        return [c.detalhe for c in self.checagens if not c.ok]

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "produto": self.nome,
            "canal": self.canal,
            "veredito": self.veredito,
            "preco_atual": round(self.preco_atual, 2),
            "preco_sugerido": None if self.preco_sugerido is None else round(self.preco_sugerido, 2),
            "margem_pct": None if self.margem_pct is None else round(self.margem_pct, 2),
            "lucro_unidade": None if self.lucro_unidade is None else round(self.lucro_unidade, 2),
            "vendas_30d": self.vendas_30d,
            "estoque_atual": self.estoque_atual,
            "estoque_minimo": self.estoque_minimo,
            "repor": self.repor,
            "bloqueios": self.bloqueios,
        }


def preco_para_margem(custo: float, comissao_pct: float, taxa_fixa: float,
                      margem_alvo_pct: float) -> float | None:
    """Preço que entrega a margem alvo sobre a receita.

    margem = (preco*(1-comissao) - fixo - custo) / preco
    => preco = (custo + fixo) / (1 - comissao - alvo)

    Devolve None quando a matemática não fecha (comissão + alvo >= 100%).
    """
    comissao = comissao_pct / 100.0
    alvo = margem_alvo_pct / 100.0
    denominador = 1 - comissao - alvo
    if custo <= 0 or denominador <= 0.01:
        return None
    return round((custo + taxa_fixa) / denominador, 2)


def estoque_minimo(vendas_por_dia: float, prazo_fornecedor_dias: int = 7,
                   seguranca_dias: int = 2) -> int:
    """Estoque que cobre o prazo do fornecedor mais a folga de segurança."""
    if vendas_por_dia <= 0:
        return 0
    return math.ceil(vendas_por_dia * (prazo_fornecedor_dias + seguranca_dias))


class SalesOperator:
    def __init__(self, repo, settings: Any = None, prazo_fornecedor_dias: int = 7,
                 margem_alvo_pct: float = 30.0) -> None:
        self.repo = repo
        self.settings = settings
        self.prazo_fornecedor_dias = prazo_fornecedor_dias
        self.margem_alvo_pct = margem_alvo_pct

    # ------------------------------------------------------------------ dados --
    def _produtos(self) -> list[dict[str, Any]]:
        return self.repo.find("products", {"status": "ativo"}, limit=500) or []

    def _regra_canal(self, canal: str) -> dict[str, Any]:
        return self.repo.find_one("marketplaces", {"slug": canal or "shopee"}) or {}

    def _vendas_30d(self, product_id: str) -> int:
        corte = (datetime.now() - timedelta(days=30)).isoformat()
        vendas = self.repo.find("sales", {"product_id": product_id}, limit=1000) or []
        total = 0
        for venda in vendas:
            if str(venda.get("sold_at") or "") >= corte:
                total += int(venda.get("quantity") or 1)
        return total

    def _estoque(self, product_id: str) -> int:
        movimentos = self.repo.find("stock_movements", {"product_id": product_id}, limit=500) or []
        saldo = 0
        for mov in movimentos:
            quantidade = int(mov.get("quantity") or 0)
            saldo += quantidade if str(mov.get("kind") or "entrada") == "entrada" else -quantidade
        return max(saldo, 0)

    # ------------------------------------------------------------------ plano --
    def planejar(self, produto: dict[str, Any]) -> PlanoProduto:
        from analytics.profitability import calculate

        canal = str(produto.get("marketplace") or "shopee")
        regra = self._regra_canal(canal)
        comissao = float(regra.get("commission_pct") or 0)
        fixa = float(regra.get("fixed_fee") or 0)
        custo = float(produto.get("purchase_price") or 0)
        preco = float(produto.get("sale_price") or 0)

        sugestao = preco_para_margem(custo, comissao, fixa, self.margem_alvo_pct)
        margem = lucro = None
        if custo > 0 and preco > 0:
            resultado = calculate({
                "product_name": produto.get("name"),
                "marketplace": canal,
                "costs": {"purchase_price": custo,
                          "other_costs": float(produto.get("extra_cost") or 0)},
                "terms": {"sale_price": preco, "commission_pct": comissao,
                          "fixed_fee": fixa},
            })
            margem = resultado.margin_pct
            lucro = resultado.net_profit

        vendas_30d = self._vendas_30d(produto["id"])
        por_dia = vendas_30d / 30 if vendas_30d else 0
        minimo = estoque_minimo(por_dia, self.prazo_fornecedor_dias)
        atual = self._estoque(produto["id"])
        repor = max(minimo - atual, 0)

        checagens = [
            Checagem("nome do produto", bool((produto.get("name") or "").strip()),
                     "sem nome" if not (produto.get("name") or "").strip() else
                     f"{produto.get('name')}"),
            Checagem("custo de compra", custo > 0,
                     "custo de compra ausente: informe quanto você paga na unidade" if custo <= 0 else
                     f"R$ {custo:.2f}"),
            Checagem("preço de venda", preco > 0,
                     "defina o preço de venda" if preco <= 0 else f"R$ {preco:.2f}"),
            Checagem("descrição", len((produto.get("description") or "").strip()) >= 120,
                     "escreva ao menos 120 caracteres" if
                     len((produto.get("description") or "").strip()) < 120 else "ok"),
            Checagem("categoria", bool((produto.get("category") or "").strip()),
                     "sem categoria o anúncio perde busca" if
                     not (produto.get("category") or "").strip() else produto.get("category")),
            Checagem("taxa do canal", comissao > 0,
                     f"informe a comissão real da {canal}" if comissao <= 0 else
                     f"{comissao:.1f}% + R$ {fixa:.2f}"),
            Checagem("prazo de entrega do fornecedor", self.prazo_fornecedor_dias > 0,
                     "informe o prazo do fornecedor" if self.prazo_fornecedor_dias <= 0 else
                     f"{self.prazo_fornecedor_dias} dias"),
        ]
        if margem is not None and margem < 10:
            checagens.append(Checagem(
                "margem mínima", False,
                f"margem {margem:.1f}% abaixo do mínimo aceitável (10%)"
                + (f"; sugerido R$ {sugestao:.2f}" if sugestao else "")))

        falhas = [c for c in checagens if not c.ok]
        if any(c.item in {"custo de compra", "preço de venda"} and not c.ok for c in checagens):
            veredito = VEREDITO_BLOQUEADO
        elif falhas:
            veredito = VEREDITO_AJUSTAR
        else:
            veredito = VEREDITO_PRONTO

        return PlanoProduto(
            product_id=produto["id"], nome=produto.get("name") or "(sem nome)", canal=canal,
            veredito=veredito, preco_atual=preco, preco_sugerido=sugestao,
            margem_pct=margem, lucro_unidade=lucro, vendas_30d=vendas_30d,
            estoque_atual=atual, estoque_minimo=minimo, repor=repor, checagens=checagens,
        )

    def plano(self) -> dict[str, Any]:
        produtos = self._produtos()
        planos = [self.planejar(p) for p in produtos]
        prontos = [p for p in planos if p.veredito == VEREDITO_PRONTO]
        ajustar = [p for p in planos if p.veredito == VEREDITO_AJUSTAR]
        bloqueados = [p for p in planos if p.veredito == VEREDITO_BLOQUEADO]
        repor = [p for p in planos if p.repor > 0]
        return {
            "produtos": len(planos),
            "prontos": [p.to_dict() for p in prontos],
            "ajustar": [p.to_dict() for p in ajustar],
            "bloqueados": [p.to_dict() for p in bloqueados],
            "repor": [p.to_dict() for p in repor],
            "sem_produtos": not planos,
            "margem_alvo_pct": self.margem_alvo_pct,
            "prazo_fornecedor_dias": self.prazo_fornecedor_dias,
        }


def resumo_texto(plano: dict[str, Any]) -> str:
    """Versão para chat: direta, sem enfeite, e honesta quando falta dado."""
    if plano["sem_produtos"]:
        return ("Ainda não há produto ativo para vender. Me manda nome, custo e preço "
                "que eu monto o plano de venda (preço, estoque e anúncio).")

    linhas = [f"*Plano de venda* · meta de margem {plano['margem_alvo_pct']:.0f}% "
              f"· fornecedor {plano['prazo_fornecedor_dias']} dias", ""]
    linhas.append(f"Prontos para publicar: {len(plano['prontos'])}")
    for item in plano["prontos"]:
        linhas.append(f"• {item['produto']} — R$ {item['preco_atual']:.2f} "
                      f"· margem {item['margem_pct']:.1f}% · lucro R$ {item['lucro_unidade']:.2f}")
    if plano["ajustar"]:
        linhas.append("")
        linhas.append(f"Faltam ajustes: {len(plano['ajustar'])}")
        for item in plano["ajustar"]:
            linhas.append(f"• {item['produto']}: " + "; ".join(item["bloqueios"]))
    if plano["bloqueados"]:
        linhas.append("")
        linhas.append(f"Bloqueados por dado faltante: {len(plano['bloqueados'])}")
        for item in plano["bloqueados"]:
            linhas.append(f"• {item['produto']}: " + "; ".join(item["bloqueios"]))
    if plano["repor"]:
        linhas.append("")
        linhas.append("Reposição sugerida")
        for item in plano["repor"]:
            linhas.append(f"• {item['produto']}: repor {item['repor']} un "
                          f"(mínimo {item['estoque_minimo']}, tem {item['estoque_atual']})")
    return "\n".join(linhas)
