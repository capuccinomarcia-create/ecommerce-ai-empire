"""Recalcula a margem do ranking com o preço REAL de mercado.

O ranking original usava venda = 3x o custo, que é uma régua de planejamento.
Aqui cada produto recebe o preço observado em anúncios públicos e a margem é
recalculada nas taxas de cada canal. Fonte e data ficam no próprio arquivo.
"""

from __future__ import annotations

import json
from pathlib import Path

from analytics import fees

RAIZ = Path(__file__).resolve().parent.parent
RANKING = RAIZ / "data" / "ranking_fornecedor.json"
MERCADO = RAIZ / "data" / "precos_mercado.json"
APP_RANKING = RAIZ / "docs" / "app" / "ranking.json"


def casar(produto: str, precos: list[dict]) -> dict | None:
    for item in precos:
        if item["chave"].lower() in produto.lower():
            return item
    return None


def recalcular(ranking: dict, mercado: dict) -> dict:
    itens = mercado["itens"]
    for linha in ranking["itens"]:
        preco = casar(linha["produto"], itens)
        if not preco:
            linha["preco_mercado"] = None
            linha["margem_mercado"] = None
            continue
        valor = preco["preco_mercado"]
        linha["preco_mercado"] = valor
        linha["faixa_mercado"] = preco["faixa"]
        linha["fontes_mercado"] = preco["fontes"]
        margens = {}
        for canal in fees.CANAIS:
            r = fees.margem(canal, valor, linha["custo"])
            margens[canal] = {"margem_pct": round(r["margem_pct"], 1), "lucro": round(r["lucro_liquido"], 2)}
        linha["margem_mercado"] = margens
        melhor = max(margens.values(), key=lambda m: m["lucro"])
        linha["veredito"] = "vale" if melhor["margem_pct"] >= 25 else (
            "apertado" if melhor["margem_pct"] >= 10 else "inviável"
        )
    ranking["mercado_coletado_em"] = mercado["coletado_em"]
    ranking["mercado_metodo"] = mercado["metodo"]
    ranking["mercado_aviso"] = mercado["aviso"]
    return ranking


def main() -> None:
    ranking = json.loads(RANKING.read_text(encoding="utf-8"))
    mercado = json.loads(MERCADO.read_text(encoding="utf-8"))
    atualizado = recalcular(ranking, mercado)
    texto = json.dumps(atualizado, ensure_ascii=False, indent=1)
    RANKING.write_text(texto, encoding="utf-8")
    APP_RANKING.write_text(texto, encoding="utf-8")

    com_preco = [l for l in atualizado["itens"] if l.get("preco_mercado")]
    com_preco.sort(key=lambda l: -max(m["margem_pct"] for m in l["margem_mercado"].values()))
    print(f"{'produto':44} {'custo':>8} {'mercado':>8} {'margem real':>12} {'veredito':>10}")
    for l in com_preco:
        melhor = max(l["margem_mercado"].values(), key=lambda m: m["lucro"])
        canal = max(l["margem_mercado"], key=lambda c: l["margem_mercado"][c]["lucro"])
        print(f"{l['produto'][:44]:44} {l['custo']:8.2f} {l['preco_mercado']:8.2f} "
              f"{melhor['margem_pct']:11.1f}% {l['veredito']:>10}  {canal}")


if __name__ == "__main__":
    main()
