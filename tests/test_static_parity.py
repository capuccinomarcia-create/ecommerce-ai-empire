"""Garante que a calculadora do painel estático (JavaScript) dá exatamente os
mesmos números que o motor Python.

Se alguém mudar a fórmula em analytics/profitability.py e esquecer o painel,
este teste quebra. Roda `node` de verdade, sem reimplementar nada no teste.
"""

from __future__ import annotations

import json
import random
import shutil
import subprocess
from pathlib import Path

import pytest

from analytics.profitability import CostStructure, FinancialInput, SaleTerms, calculate

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "docs" / "index.html"
NODE = shutil.which("node")


def _extrair_funcao_js() -> str:
    html = HTML.read_text(encoding="utf-8")
    begin = html.index("function calcular(i){")
    end = html.index("if (typeof module", begin)
    # o helper r2 vem do próprio arquivo publicado, não é recriado no teste
    linha_r2 = next(
        l for l in html.splitlines() if l.strip().startswith("const r2 = ")
    )
    return linha_r2 + "\n" + html[begin:end] + "\nmodule.exports = {calcular};\n"


def _rodar_js(casos: list[dict]) -> list[dict]:
    script = _extrair_funcao_js()
    script += "const casos = JSON.parse(process.argv[1]);\n"
    script += "console.log(JSON.stringify(casos.map(calcular)));\n"
    out = subprocess.run(
        [NODE, "-e", script, json.dumps(casos)],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return json.loads(out.stdout)


def _casos(n: int = 6) -> list[dict]:
    rnd = random.Random(7)
    casos = []
    for _ in range(n):
        preco = round(rnd.uniform(15, 300), 2)
        casos.append(
            {
                "quantity": rnd.randint(1, 12),
                "purchasePrice": round(rnd.uniform(3, preco * 0.8), 2),
                "acquisitionShipping": round(rnd.uniform(0, 25), 2),
                "packaging": round(rnd.uniform(0, 6), 2),
                "otherCosts": round(rnd.uniform(0, 10), 2),
                "salePrice": preco,
                "commissionPct": round(rnd.uniform(0, 20), 2),
                "fixedFee": round(rnd.uniform(0, 8), 2),
                "subsidizedShipping": round(rnd.uniform(0, 20), 2),
                "taxPct": round(rnd.uniform(0, 12), 2),
                "discount": round(rnd.uniform(0, preco * 0.1), 2),
                "adCost": round(rnd.uniform(0, 15), 2),
                "fixedMonthlyCosts": round(rnd.uniform(0, 3000), 2),
                "targetMarginPct": round(rnd.uniform(5, 45), 1),
            }
        )
    return casos


CAMPIOS = [
    ("net_profit", "netProfit"),
    ("margin_pct", "marginPct"),
    ("roi_pct", "roiPct"),
    ("revenue", "revenue"),
    ("total_cost", "totalCost"),
    ("min_price_breakeven", "minBreakeven"),
    ("min_price_target_margin", "minTarget"),
]


@pytest.mark.skipif(NODE is None, reason="node não instalado")
def test_calculadora_js_igual_ao_python() -> None:
    assert HTML.exists(), "rode python -m scripts.build_static_panel antes"
    casos = _casos()
    js = _rodar_js(casos)

    for entrada, saida_js in zip(casos, js):
        py = calculate(
            FinancialInput(
                costs=CostStructure(
                    purchase_price=entrada["purchasePrice"],
                    acquisition_shipping=entrada["acquisitionShipping"],
                    packaging=entrada["packaging"],
                    other_costs=entrada["otherCosts"],
                ),
                terms=SaleTerms(
                    sale_price=entrada["salePrice"],
                    commission_pct=entrada["commissionPct"],
                    fixed_fee=entrada["fixedFee"],
                    subsidized_shipping=entrada["subsidizedShipping"],
                    tax_pct=entrada["taxPct"],
                    discount=entrada["discount"],
                    ad_cost=entrada["adCost"],
                ),
                quantity=entrada["quantity"],
                fixed_monthly_costs=entrada["fixedMonthlyCosts"],
                target_margin_pct=entrada["targetMarginPct"],
            )
        ).to_dict()

        for campo_py, campo_js in CAMPIOS:
            esperado = py[campo_py]
            obtido = saida_js[campo_js]
            if esperado is None:
                assert obtido is None, f"{campo_py}: python=None js={obtido}"
                continue
            assert obtido is not None, f"{campo_py}: python={esperado} js=None"
            assert abs(float(esperado) - float(obtido)) <= 0.02, (
                f"{campo_py}: python={esperado} js={obtido} entrada={entrada}"
            )

        # ponto de equilíbrio é inteiro (ceil)
        assert py["breakeven_units"] == saida_js["breakevenUnits"]


@pytest.mark.skipif(NODE is None, reason="node não instalado")
def test_painel_nao_tem_botao_morto() -> None:
    """Todo onclick aponta para função definida no próprio arquivo."""
    html = HTML.read_text(encoding="utf-8")
    import re

    chamadas = set(re.findall(r'onclick="(\w+)\(', html))
    for nome in chamadas:
        assert f"function {nome}(" in html, f"onclick={nome} sem função"
