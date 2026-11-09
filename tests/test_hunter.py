"""Testes do Product Hunter: sitemap, CSV, URLs e filtros — sem inventar dado."""

from __future__ import annotations

import pytest

from analytics import hunter

SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">
  <url>
    <loc><![CDATA[https://fornecedor.com.br/livro-de-colorir-100-desenhos/p]]></loc>
    <lastmod>2026-11-05</lastmod>
    <image:image>
      <image:loc><![CDATA[https://cdn.fornecedor.com.br/img/1-large_default.jpg]]></image:loc>
      <image:title><![CDATA[Livro de Colorir 100 Desenhos]]></image:title>
    </image:image>
  </url>
  <url>
    <loc><![CDATA[https://fornecedor.com.br/kit-3-livros-colorir/p]]></loc>
    <image:image>
      <image:loc><![CDATA[https://cdn.fornecedor.com.br/img/2-large_default.jpg]]></image:loc>
      <image:title><![CDATA[Kit 3 Livros Colorir]]></image:title>
    </image:image>
  </url>
  <url>
    <loc><![CDATA[https://fornecedor.com.br/categoria/papelaria]]></loc>
  </url>
</urlset>
"""

CSV = (
    "Nome;Custo;Preço;Categoria;Peso;Estoque\n"
    "Livro de Colorir Adulto;18,50;39,90;Papelaria;0,3;10\n"
    "Kit 3 Livros;42,00;79,90;Papelaria;0,9;6\n"
    "Squishy Queijo;17,50;;Brinquedos;;\n"
)


def test_importar_sitemap_pega_nome_link_e_imagem():
    produtos = hunter.importar_sitemap(SITEMAP, fonte="fornecedor.com.br", coletado_em="2026-11-09")
    assert len(produtos) == 2, "só URLs de produto entram, categoria fica fora"
    primeiro = produtos[0]
    assert primeiro.nome == "Livro de Colorir 100 Desenhos"
    assert primeiro.url.endswith("/p")
    assert primeiro.imagem.endswith("1-large_default.jpg")
    assert primeiro.coletado_em == "2026-11-09"
    assert "custo" in primeiro.lacunas


def test_importar_csv_normaliza_numero_e_cabecalho():
    produtos = hunter.importar_csv(CSV, fonte="planilha.xlsx")
    assert len(produtos) == 3
    livro = produtos[0]
    assert livro.custo == pytest.approx(18.5)
    assert livro.preco == pytest.approx(39.90)
    assert livro.peso_kg == pytest.approx(0.3)
    assert livro.estoque == 10
    vazio = produtos[2]
    assert vazio.preco is None
    assert "preco" in vazio.para_dict()["lacunas"]


def test_importar_urls_descarta_link_invalido():
    produtos = hunter.importar_urls(["https://ok.com.br/produto-a/p", "nao-e-link", ""])
    assert len(produtos) == 1
    assert produtos[0].nome
    assert produtos[0].custo is None


def test_deduplicar_por_url_e_por_nome():
    a = hunter.Produto(nome="Livro A", fonte="x", url="https://a.com/p")
    b = hunter.Produto(nome="Livro A repetido", fonte="x", url="https://a.com/p")
    c = hunter.Produto(nome="Squishy", fonte="x")
    d = hunter.Produto(nome="squishy", fonte="y")
    assert len(hunter.deduplicar([a, b, c, d])) == 2


def test_filtrar_descarta_item_sem_o_dado_pedido():
    produtos = hunter.importar_csv(CSV)
    com_peso = hunter.filtrar(produtos, peso_max_kg=1.0)
    assert [p.nome for p in com_peso] == ["Livro de Colorir Adulto", "Kit 3 Livros"]

    com_preco = hunter.filtrar(produtos, apenas_com_preco=True)
    assert all(p.preco is not None for p in com_preco)
    assert len(com_preco) == 2

    baratos = hunter.filtrar(produtos, preco_max=50)
    assert [p.nome for p in baratos] == ["Livro de Colorir Adulto"]


def test_resumo_mostra_lacunas_da_base():
    produtos = hunter.importar_sitemap(SITEMAP)
    dados = hunter.resumo(produtos)
    assert dados["total"] == 2
    assert dados["com_preco"] == 0
    assert dados["lacunas"]["preco"] == 2
