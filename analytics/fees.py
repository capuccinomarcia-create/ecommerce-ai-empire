"""Tabelas de taxas de marketplace — versionadas, com fonte, data e confiança.

REGRA: nenhum valor aqui é "estimativa da IA". Cada tabela declara a fonte e a data
de coleta, e todo número que ainda depende de confirmação no painel do vendedor
carrega `provisorio=True`. O restante do sistema deve mostrar esse aviso em vez de
tratar a margem como definitiva.

Uso:
    from analytics.fees import tarifa, preco_para_margem, resumo_tabelas

    t = tarifa("Shopee", 89.90)
    t.comissao_valor, t.fixo, t.total, t.provisorio
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

COLETADO_EM = "2026-11-09"


@dataclass(frozen=True)
class Faixa:
    """Faixa de preço do item com a taxa correspondente."""

    minimo: float
    maximo: float  # float("inf") = sem teto
    comissao_pct: float
    fixo: float

    def contem(self, preco: float) -> bool:
        return self.minimo <= preco < self.maximo


@dataclass(frozen=True)
class TabelaCanal:
    canal: str
    fonte: str
    coletado_em: str
    confianca: str  # "alta" | "media" | "baixa"
    provisorio: bool
    faixas: tuple[Faixa, ...]
    observacao: str = ""
    faltando: tuple[str, ...] = ()

    def faixa_para(self, preco: float) -> Faixa:
        for faixa in self.faixas:
            if faixa.contem(preco):
                return faixa
        return self.faixas[-1]


TABELAS: dict[str, TabelaCanal] = {
    "Shopee": TabelaCanal(
        canal="Shopee",
        fonte="Central do Vendedor Shopee Brasil — política de comissão e tarifa fixa por item",
        coletado_em=COLETADO_EM,
        confianca="media",
        provisorio=True,
        faixas=(Faixa(0, float("inf"), 14.0, 4.0),),
        observacao="Comissão padrão + tarifa fixa por item vendido; programas e faixas de preço podem alterar.",
        faltando=("frete subsidiado por região", "taxa de programa de frete grátis", "impostos"),
    ),
    "Mercado Livre": TabelaCanal(
        canal="Mercado Livre",
        fonte="Mercado Livre Brasil — custos de vender (clássico) e custo fixo para itens de baixo valor",
        coletado_em=COLETADO_EM,
        confianca="media",
        provisorio=True,
        faixas=(
            Faixa(0, 79.0, 13.0, 6.0),
            Faixa(79.0, float("inf"), 13.0, 0.0),
        ),
        observacao="Comissão por categoria varia de 11% a 16%; aqui usamos o clássico de 13%.",
        faltando=("comissão exata da categoria", "custo de envio com Mercado Envios", "impostos"),
    ),
    "TikTok Shop": TabelaCanal(
        canal="TikTok Shop",
        fonte="TikTok Shop Brasil — taxa de comissão por faixa de preço do item",
        coletado_em=COLETADO_EM,
        confianca="baixa",
        provisorio=True,
        faixas=(
            Faixa(0, 50.0, 10.0, 4.0),
            Faixa(50.0, float("inf"), 6.0, 6.0),
        ),
        observacao="Regras divulgadas para o programa do Brasil; precisa confirmação no Seller Center.",
        faltando=("taxa por categoria", "taxa de afiliado", "impostos"),
    ),
}

CANAIS = tuple(TABELAS)


@dataclass(frozen=True)
class Tarifa:
    canal: str
    preco: float
    comissao_pct: float
    comissao_valor: float
    fixo: float
    total: float
    provisorio: bool
    fonte: str
    coletado_em: str
    faltando: tuple[str, ...]


def tarifa(canal: str, preco: float) -> Tarifa:
    """Calcula a tarifa do canal para um preço. Não inventa taxa ausente."""
    if canal not in TABELAS:
        raise ValueError(f"canal sem tabela de taxas: {canal}")
    if preco <= 0:
        raise ValueError("preço precisa ser maior que zero")
    tabela = TABELAS[canal]
    faixa = tabela.faixa_para(preco)
    comissao = round(preco * faixa.comissao_pct / 100, 2)
    total = round(comissao + faixa.fixo, 2)
    return Tarifa(
        canal=canal,
        preco=round(preco, 2),
        comissao_pct=faixa.comissao_pct,
        comissao_valor=comissao,
        fixo=faixa.fixo,
        total=total,
        provisorio=tabela.provisorio,
        fonte=tabela.fonte,
        coletado_em=tabela.coletado_em,
        faltando=tabela.faltando,
    )


def preco_para_margem(canal: str, custo_total: float, margem_pct: float) -> float:
    """Menor preço que entrega a margem líquida desejada no canal.

    Margem = (preco - tarifa(preco) - custo_total) / preco.
    Resolve por busca monotônica, sem chute.
    """
    if custo_total < 0:
        raise ValueError("custo não pode ser negativo")
    alvo = margem_pct / 100
    if alvo >= 0.95:
        raise ValueError("margem alvo irrealista")
    preco = max(custo_total * 1.2, 5.0)
    for _ in range(4000):
        liquido = preco - tarifa(canal, preco).total - custo_total
        if liquido / preco >= alvo - 1e-6:
            return round(preco, 2)
        preco = round(preco + 0.05, 2)
    raise RuntimeError("não foi possível atingir a margem alvo")


def margem(canal: str, preco: float, custo_total: float) -> dict:
    """Margem e ROI do item no canal, com o aviso de provisório propagado."""
    t = tarifa(canal, preco)
    liquido = round(preco - t.total - custo_total, 2)
    return {
        "canal": canal,
        "preco": round(preco, 2),
        "custo_total": round(custo_total, 2),
        "tarifa": t.total,
        "lucro_liquido": liquido,
        "margem_pct": round(liquido / preco * 100, 2),
        "roi_pct": round(liquido / custo_total * 100, 2) if custo_total else None,
        "provisorio": t.provisorio,
        "faltando": list(t.faltando),
        "fonte": t.fonte,
        "coletado_em": t.coletado_em,
    }


def melhor_canal(preco: float, custo_total: float) -> dict:
    """Compara os três canais e devolve o de maior lucro líquido."""
    resultados = [margem(canal, preco, custo_total) for canal in CANAIS]
    melhor = max(resultados, key=lambda r: r["lucro_liquido"])
    return {"melhor": melhor["canal"], "resultados": resultados}


def resumo_tabelas() -> list[dict]:
    """Lista as tabelas vigentes com fonte e data, para exibir no painel."""
    return [
        {
            "canal": t.canal,
            "fonte": t.fonte,
            "coletado_em": t.coletado_em,
            "confianca": t.confianca,
            "provisorio": t.provisorio,
            "observacao": t.observacao,
            "faltando": list(t.faltando),
            "faixas": [
                {
                    "de": f.minimo,
                    "ate": (None if f.maximo == float("inf") else f.maximo),
                    "comissao_pct": f.comissao_pct,
                    "fixo": f.fixo,
                }
                for f in t.faixas
            ],
        }
        for t in TABELAS.values()
    ]


def data_de_referencia() -> str:
    """Data da coleta das tabelas, em ISO."""
    return str(date.fromisoformat(COLETADO_EM))
