"""Coleta preço por faixa e vendidos no fornecedor e monta o ranking de maior margem.

Fonte: catálogo local (data/fornecedores_fmsp.json) + leitura de cada página de
produto pela rota r.jina.ai, porque o site bloqueia acesso direto (Cloudflare).
Nada de preço inventado: produto sem faixa lida fica fora do ranking.
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

from analytics import fees

LEITOR = "https://r.jina.ai/"
UA = "Mozilla/5.0 (compatible; EmpireBot/1.0)"
PAUSA = 3.6  # respeita o limite de 20 leituras por minuto do leitor


def ler(url: str, tentativas: int = 2) -> str:
    for tentativa in range(tentativas + 1):
        try:
            req = urllib.request.Request(LEITOR + url, headers={"Accept": "text/plain", "User-Agent": UA})
            return urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
        except Exception as erro:  # noqa: BLE001
            if tentativa == tentativas:
                raise
            print(f"  recuo: {erro}", file=sys.stderr)
            time.sleep(6)
    return ""


def faixas(md: str) -> list[tuple[int, float]]:
    out = []
    for m in re.finditer(r"\|\s*(\d+)\s*(?:-\s*(\d+)|\+)\s*\|\s*-?\d+%\s*\|\s*R\$ ?([\d\.]+,\d{2})", md):
        out.append((int(m.group(1)), float(m.group(3).replace(".", "").replace(",", "."))))
    limpas, melhor = [], float("inf")
    for quanto, preco in sorted(out):
        if preco < melhor:
            melhor = preco
            limpas.append((quanto, preco))
    return limpas


def detalhe(md: str) -> dict:
    vend = re.search(r"\+\s*de\s*([\d\.]+)\s*vendidos", md)
    nota = re.search(r"([45]\.\d)\s*\+ de", md)
    ref = re.search(r"R\$ ?([\d\.]+,\d{2})\s*-?\d+%\s*R\$", md)
    return {
        "vendidos": int(vend.group(1).replace(".", "")) if vend else None,
        "nota": float(nota.group(1)) if nota else None,
        "preco_referencia": float(ref.group(1).replace(".", "").replace(",", ".")) if ref else None,
    }


def main(limite: int = 36, saida_web: str = "docs/app/ranking.json") -> None:
    acervo = json.loads(Path("data/fornecedores_fmsp.json").read_text(encoding="utf-8"))["itens"]
    conhecidos = [i for i in acervo if i.get("preco_1un") and i.get("vendidos")]
    fila = conhecidos + [i for i in acervo if not i.get("preco_1un")]
    vistos, linhas = set(), []

    for item in conhecidos:
        if item["url"] in vistos:
            continue
        vistos.add(item["url"])
        linhas.append(_linha(item, [(1, item["preco_1un"])], item.get("vendidos"), item.get("nota")))

    faltam = max(0, limite - len(linhas))
    print(f"lendo {faltam} produtos novos no fornecedor...")
    for item in fila[len(conhecidos):]:
        if faltam <= 0:
            break
        if item["url"] in vistos:
            continue
        vistos.add(item["url"])
        try:
            md = ler(item["url"])
        except Exception as erro:  # noqa: BLE001
            print(f"  falhou {item['produto'][:40]}: {erro}", file=sys.stderr)
            continue
        faixas_lidas = faixas(md)
        if not faixas_lidas:
            print(f"  sem faixa: {item['produto'][:40]}")
            time.sleep(PAUSA)
            continue
        info = detalhe(md)
        linhas.append(_linha(item, faixas_lidas, info["vendidos"], info["nota"], info["preco_referencia"]))
        print(f"  ok {item['produto'][:46]:48} R$ {faixas_lidas[0][1]:7.2f} | vendidos {info['vendidos']}")
        faltam -= 1
        time.sleep(PAUSA)

    validas = [l for l in linhas if l["margens"] and max(l["margens"].values()) >= 20]
    validas.sort(key=lambda l: (-max(l["margens"].values()), -(l["vendidos"] or 0)))
    ranking = {
        "coletado_em": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "fonte": "feiradamadrugadasp.com.br (preço e vendidos lidos na página do produto)",
        "markup": 3.0,
        "avisos": [
            "margem calculada com venda = 3x o custo unitário (faixa de 1 a 3 unidades)",
            "taxas de marketplace ainda provisórias até confirmação no Seller Center",
        ],
        "itens": validas,
    }
    Path("data/ranking_fornecedor.json").write_text(json.dumps(ranking, ensure_ascii=False, indent=1), encoding="utf-8")
    Path(saida_web).parent.mkdir(parents=True, exist_ok=True)
    Path(saida_web).write_text(json.dumps(ranking, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n{len(validas)} produtos com margem >= 20%")
    print(f"{'produto':46} {'custo':>8} {'venda':>8} {'melhor':>13} {'margem':>7} {'vendidos':>9}")
    for l in validas[:15]:
        canal = max(l["margens"], key=l["margens"].get)
        print(f'{l["produto"][:46]:46} {l["custo"]:8.2f} {l["venda"]:8.2f} {canal:>13} {l["margens"][canal]:6.1f}% {str(l["vendidos"] or "-"):>9}')


def _linha(item: dict, faixas_lidas: list[tuple[int, float]], vendidos, nota, referencia=None) -> dict:
    custo = faixas_lidas[0][1]
    venda = round(custo * 3, 2)
    margens = {canal: round(fees.margem(canal, venda, custo)["margem_pct"], 1) for canal in fees.CANAIS}
    return {
        "produto": item["produto"],
        "url": item["url"],
        "imagem": item.get("imagem"),
        "custo": custo,
        "venda": venda,
        "faixas": [{"minimo": q, "preco": p} for q, p in faixas_lidas],
        "vendidos": vendidos,
        "nota": nota,
        "preco_referencia": referencia,
        "margens": margens,
        "lucro": {c: round(fees.margem(c, venda, custo)["lucro_liquido"], 2) for c in fees.CANAIS},
    }


if __name__ == "__main__":
    main(limite=int(sys.argv[1]) if len(sys.argv) > 1 else 36)
