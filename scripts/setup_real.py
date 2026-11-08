"""Coloca o sistema em modo REAL: apaga dados DEMO, cria planilhas de entrada.

    python -m scripts.setup_real --checklist      # o que falta para operar de verdade
    python -m scripts.setup_real --templates      # cria templates/*.csv
    python -m scripts.setup_real --aplicar        # modo real + apaga registros DEMO
    python -m scripts.setup_real --importar pasta # importa seus CSVs reais

Nada aqui busca dado na internet nem inventa número: ou vem de você, ou não existe.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core import data_mode
from core.config import get_settings
from database.repository import get_repository
from integrations.generic_csv import import_csv
from scripts.seed_demo import clear_demo

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

CABECALHOS: dict[str, str] = {
    "produtos.csv": (
        "name;sku;category;description;purchase_price;extra_cost;sale_price;marketplace;"
        "status;supplier\n"
        "COLOQUE_SEU_PRODUTO_AQUI;SKU-001;categoria;descrição curta;0,00;0,00;0,00;"
        "shopee;ativo;nome do fornecedor\n"
    ),
    "fornecedores.csv": (
        "name;contact;url;min_qty;unit_price;lead_time_days;shipping_cost;"
        "pickup_available;same_day_pickup;city;state;notes\n"
        "COLOQUE_SEU_FORNECEDOR_AQUI;telefone ou email;https://...;10;0,00;7;0,00;"
        "nao;nao;cidade;UF;condições comerciais\n"
    ),
    "concorrentes.csv": (
        "name;product_name;marketplace;price;url;rating;reviews;differentials\n"
        "anúncio do concorrente;seu produto equivalente;shopee;0,00;https://...;0;0;o que ele faz melhor\n"
    ),
    "vendas.csv": (
        "product_name;marketplace;quantity;unit_price;fees;shipping;taxes;sold_at\n"
        "COLOQUE_SEU_PRODUTO_AQUI;shopee;1;0,00;0,00;0,00;0,00;2026-11-01\n"
    ),
}


def criar_templates(forcar: bool = False) -> list[str]:
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    criados: list[str] = []
    for nome, conteudo in CABECALHOS.items():
        caminho = TEMPLATES_DIR / nome
        if caminho.exists() and not forcar:
            continue
        caminho.write_text(conteudo, encoding="utf-8")
        criados.append(str(caminho.relative_to(TEMPLATES_DIR.parent)))
    return criados


def aplicar_modo_real(repo) -> dict:
    """Apaga DEMO de verdade e marca o sistema como real."""
    removidos = clear_demo(repo)
    # prazos DEMO deixam de valer: melhor "não informado" do que número inventado
    for regra in repo.find("marketplaces", {}, limit=50):
        if "DEMO" in str(regra.get("sla_source") or ""):
            repo.update("marketplaces", regra["id"], {
                "handling_days": 0, "delivery_days": 0,
                "sla_source": "não informado pelo proprietário",
            })
    data_mode.set_mode(repo, data_mode.REAL)
    return {"registros_demo_removidos": removidos, "modo": data_mode.REAL}


def importar_pasta(repo, pasta: Path) -> dict:
    mapa = {
        "produtos.csv": "products", "products.csv": "products",
        "fornecedores.csv": "suppliers", "suppliers.csv": "suppliers",
        "concorrentes.csv": "competitors", "competitors.csv": "competitors",
        "vendas.csv": "sales", "sales.csv": "sales",
        "oportunidades.csv": "opportunities", "opportunities.csv": "opportunities",
    }
    relatorio: dict[str, dict] = {}
    for arquivo in sorted(pasta.glob("*.csv")):
        entidade = mapa.get(arquivo.name.lower())
        if not entidade:
            relatorio[arquivo.name] = {"error": "nome de arquivo não reconhecido"}
            continue
        resultado = import_csv(arquivo, entidade, repo, is_demo=False, source="proprietário")
        relatorio[arquivo.name] = {
            k: v for k, v in resultado.items() if k not in ("rows",)
        }
    return relatorio


def imprimir_checklist(repo) -> int:
    situacao = data_mode.resumo(repo, get_settings())
    print(f"Modo atual: {situacao['mode'].upper()}  "
          f"({situacao['prontos']}/{situacao['total']} itens prontos)\n")
    for item in situacao["itens"]:
        marca = "[ok]" if item["ok"] else "[  ]"
        print(f"{marca} {item['item']}: {item['detalhe']}")
        if not item["ok"]:
            print(f"      como resolver: {item['como']}")
    return situacao["prontos"] == situacao["total"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Modo real do E-COMMERCE AI EMPIRE")
    parser.add_argument("--checklist", action="store_true", help="mostra o que falta")
    parser.add_argument("--templates", action="store_true", help="cria templates/*.csv")
    parser.add_argument("--aplicar", action="store_true", help="modo real e apaga DEMO")
    parser.add_argument("--importar", metavar="PASTA", help="importa CSVs reais da pasta")
    parser.add_argument("--forcar", action="store_true", help="sobrescreve templates existentes")
    args = parser.parse_args()

    repo = get_repository()

    if args.templates:
        for caminho in criar_templates(args.forcar):
            print(f"criado: {caminho}")
    if args.aplicar:
        print(f"DEMO removido: {aplicar_modo_real(repo)}")
    if args.importar:
        pasta = Path(args.importar)
        if not pasta.is_dir():
            print(f"pasta inexistente: {pasta}", file=sys.stderr)
            return 2
        for arquivo, resultado in importar_pasta(repo, pasta).items():
            print(f"{arquivo}: {resultado}")
    if args.checklist or not (args.templates or args.aplicar or args.importar):
        completo = imprimir_checklist(repo)
        return 0 if completo else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
