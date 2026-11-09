"""Pipeline real de oportunidades: fornecedor -> margem -> ranking -> anúncio -> vídeo.

Roda de ponta a ponta com dados reais, sem inventar número:

    python -m scripts.oportunidades --top 5 --video

Saídas em saida/oportunidades/:
    relatorio.json          ranking completo com fonte de cada dado
    relatorio.md            versão para leitura
    anuncios/<slug>/        pacote por canal (json + txt)
    video/<slug>.mp4        vídeo real gerado com ffmpeg (quando há imagem baixada)
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from analytics import fees, hunter, listing_factory, suppliers, video_factory
from analytics.product_score import score_from_product

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "saida" / "oportunidades"


def _slug(texto: str) -> str:
    limpo = re.sub(r"[^a-z0-9]+", "-", texto.lower())
    return limpo.strip("-")[:60] or "produto"


def baixar_imagem(url: str, destino: Path) -> Path | None:
    """Baixa a foto do produto no fornecedor. Devolve None se falhar."""
    if not url:
        return None
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists() and destino.stat().st_size > 2000:
        return destino
    pedido = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
        "Referer": "https://www.feiradamadrugadasp.com.br/",
    })
    try:
        with urllib.request.urlopen(pedido, timeout=25) as resposta:
            dados = resposta.read()
        if len(dados) < 2000:
            return None
        destino.write_bytes(dados)
        return destino
    except Exception:
        return None


def demanda_de_vendidos(vendidos: int | None) -> float | None:
    """Converte 'vendidos' do fornecedor em nota de demanda 0-100, com escala declarada."""
    if not vendidos:
        return None
    # escala: 500 vendidos -> 40 ; 2.000 -> 70 ; 8.000+ -> 100
    if vendidos >= 8000:
        return 100.0
    if vendidos >= 2000:
        return 70.0 + (vendidos - 2000) / 6000 * 30
    if vendidos >= 500:
        return 40.0 + (vendidos - 500) / 1500 * 30
    return max(10.0, vendidos / 500 * 40)


def avaliar(top: int, gerar_video: bool) -> dict:
    itens = [i for i in suppliers.carregar() if i.preco_confirmado and i.preco_1un]
    if not itens:
        raise RuntimeError("nenhum fornecedor com preço confirmado na base")

    linhas = []
    for item in itens:
        custo = item.preco_1un
        # comparação justa: mesmo preço de vitrine para os três canais, para saber
        # qual realmente paga melhor (não comparar preços diferentes por canal)
        preco_vitrine = max(fees.preco_para_margem(canal, custo, 30.0) for canal in fees.CANAIS)
        comparativo = {canal: fees.margem(canal, preco_vitrine, custo) for canal in fees.CANAIS}
        melhor = max(comparativo.values(), key=lambda r: r["lucro_liquido"])
        score = score_from_product(
            {"name": item.produto},
            margin_pct=melhor["margem_pct"],
            extra={
                "demanda": demanda_de_vendidos(item.vendidos),
                "logistica": 70.0 if (item.bruto or {}).get("categoria") in {"Papelaria", "Brinquedos"} else None,
                "notes": f"vendidos no fornecedor: {item.vendidos or 'não informado'}",
                "sources": {"demanda": "vendidos na página do fornecedor (Feira da Madrugada)"},
            },
        )
        linhas.append({
            "produto": item.produto,
            "fornecedor": item.fornecedor,
            "link": item.url,
            "imagem": item.imagem,
            "custo_1un": custo,
            "caixas": item.preco_por_quantidade,
            "vendidos": item.vendidos,
            "nota": item.nota,
            "coletado_em": item.coletado_em,
            "canais": comparativo,
            "melhor_canal": melhor["canal"],
            "lucro_unidade": melhor["lucro_liquido"],
            "margem_pct": melhor["margem_pct"],
            "preco_venda": preco_vitrine,
            "precos_por_canal": {c: fees.preco_para_margem(c, custo, 30.0) for c in fees.CANAIS},
            "score": score.score,
            "score_classificacao": score.to_dict().get("classification"),
            "score_sem_dado": score.to_dict().get("missing", []),
            "taxas_provisorias": melhor["provisorio"],
        })

    linhas.sort(key=lambda r: (-r["score"], -r["lucro_unidade"]))
    selecionados = linhas[:top]

    SAIDA.mkdir(parents=True, exist_ok=True)
    for linha in selecionados:
        imagem = baixar_imagem(linha["imagem"], SAIDA / "imagens" / f"{_slug(linha['produto'])}.jpg")
        linha["imagem_local"] = str(imagem) if imagem else None
        produto = {
            "nome": linha["produto"],
            "custo": linha["custo_1un"],
            "categoria": (next((i.bruto for i in itens if i.produto == linha["produto"]), {}) or {}).get("categoria"),
            "imagem": linha["imagem_local"],
            "imagens": [linha["imagem_local"]] if linha["imagem_local"] else [],
        }
        pacote = listing_factory.gerar_todos(produto)
        pasta = SAIDA / "anuncios" / _slug(linha["produto"])
        arquivos = listing_factory.salvar_pacote(pacote, pasta)
        linha["anuncios"] = {c: {"titulo": a["titulo"], "preco": a["preco_recomendado"]}
                             for c, a in pacote["anuncios"].items()}
        linha["arquivos_anuncio"] = arquivos["arquivos"]
        if gerar_video and linha["imagem_local"]:
            destino = SAIDA / "video" / f"{_slug(linha['produto'])}.mp4"
            try:
                resultado = video_factory.gerar_para_anuncio(pacote, destino, duracao=15.0)
                linha["video"] = resultado
            except Exception as erro:  # ffmpeg ausente ou falha de encode
                linha["video"] = {"ok": False, "motivo": str(erro)}

    relatorio = {
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "taxas": fees.resumo_tabelas(),
        "total_avaliado": len(linhas),
        "selecionados": selecionados,
        "avisos": [
            "As taxas de marketplace são provisórias: confirmar no painel do vendedor.",
            "estoque, frete de aquisição e prazo de despacho não vêm no catálogo do fornecedor.",
            "vídeo só é gerado quando a foto do produto foi baixada.",
        ],
    }
    (SAIDA / "relatorio.json").write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
    (SAIDA / "relatorio.md").write_text(_markdown(relatorio), encoding="utf-8")
    return relatorio


def _markdown(relatorio: dict) -> str:
    linhas = [
        "# Oportunidades — E-COMMERCE AI EMPIRE",
        f"Gerado em {relatorio['gerado_em']} · {relatorio['total_avaliado']} produtos avaliados",
        "",
        "| # | Produto | Custo | Venda | Lucro/un | Margem | Canal | Score |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for i, item in enumerate(relatorio["selecionados"], 1):
        linhas.append(
            f"| {i} | {item['produto'][:44]} | R$ {item['custo_1un']:.2f} | R$ {item['preco_venda']:.2f} | "
            f"R$ {item['lucro_unidade']:.2f} | {item['margem_pct']:.1f}% | {item['melhor_canal']} | {item['score']:.0f} |"
        )
    linhas += ["", "## Avisos", ""] + [f"- {a}" for a in relatorio["avisos"]]
    return "\n".join(linhas)


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline de oportunidades com dados reais")
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--video", action="store_true", help="gera MP4 real dos selecionados")
    args = parser.parse_args()

    relatorio = avaliar(args.top, args.video)
    print(f"produtos avaliados: {relatorio['total_avaliado']}")
    print(f"{'produto':44} {'custo':>8} {'venda':>8} {'lucro':>8} {'margem':>7} {'canal':>13} {'score':>5}")
    for item in relatorio["selecionados"]:
        print(f"{item['produto'][:44]:44} {item['custo_1un']:8.2f} {item['preco_venda']:8.2f} "
              f"{item['lucro_unidade']:8.2f} {item['margem_pct']:6.1f}% {item['melhor_canal']:>13} {item['score']:5.0f}")
    for item in relatorio["selecionados"]:
        if item.get("video"):
            print(f"vídeo {item['produto'][:40]}: {item['video'].get('ok')} {item['video'].get('video', {}).get('duracao_s', item['video'].get('motivo'))}")
    print(f"\nrelatório: {SAIDA / 'relatorio.md'}")


if __name__ == "__main__":
    main()
