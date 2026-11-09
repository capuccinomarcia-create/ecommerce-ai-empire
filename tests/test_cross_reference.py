"""Testes do cruzamento marketplace × fornecedor (sem rede)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from analytics import cross_reference as cr


@pytest.fixture()
def acervo() -> list[cr.ItemFornecedor]:
    return [
        cr.ItemFornecedor(
            nome="Lousa Magica Tablet Lcd 8.5 Polegadas Escrever Pintar e Desenhar",
            link="https://fornecedor/lousa",
            preco_1un=9.99,
            vendidos=2400,
            nota=4.9,
        ),
        cr.ItemFornecedor(
            nome="Squishy Cubo De Queijo Macio Alivio Antiestresse De Apertar",
            link="https://fornecedor/squishy",
            preco_1un=17.50,
        ),
        cr.ItemFornecedor(
            nome="Mochila Escolar Infantil Estampada Com Lancheira",
            link="https://fornecedor/mochila",
            preco_1un=86.90,
        ),
    ]


def test_tokens_ignoram_palavras_vazias():
    t = cr.tokens("Kit Brinquedo Educativo de Montar 52 Blocos")
    assert "brinquedo" not in t
    assert "educativo" not in t
    assert {"blocos", "montar"}.issubset(t)


def test_aderencia_alta_para_mesmo_produto():
    nota = cr.aderencia(
        "Lousa Magica Infantil Digital Lcd Tablet 8.5",
        "Lousa Magica Tablet Lcd 8.5 Polegadas Escrever Pintar e Desenhar",
    )
    assert nota >= 0.6


def test_cruzar_encontra_fornecedor_com_link_e_custo(acervo):
    anuncios = [
        cr.AnuncioMarketplace(
            canal="Mercado Livre",
            titulo="Lousa Magica Tablet Lcd 8.5 Escrever",
            preco=148.88,
            vendidos=10000,
        )
    ]
    resultado = cr.cruzar(anuncios, acervo)[0]
    assert resultado.encontrado
    assert resultado.fornecedor.link == "https://fornecedor/lousa"
    assert resultado.fornecedor.preco_1un == pytest.approx(9.99)
    assert resultado.aderencia >= 0.6


def test_cruzar_admite_quando_fornecedor_nao_tem(acervo):
    anuncios = [cr.AnuncioMarketplace(canal="Shopee", titulo="Fritadeira Air Fryer 5L Digital")]
    resultado = cr.cruzar(anuncios, acervo)[0]
    assert not resultado.encontrado
    assert resultado.fornecedor is None
    assert "nenhum produto do fornecedor" in resultado.motivo


def test_preco_desconhecido_nao_vira_zero(acervo):
    anuncios = [cr.AnuncioMarketplace(canal="Shopee", titulo="Lousa Magica Infanti Digital Lcd Tablet 8.5")]
    d = cr.cruzar(anuncios, acervo)[0].to_dict()
    assert d["preco"] is None
    assert d["fornecedor_link"] == "https://fornecedor/lousa"


def test_carregar_fornecedor_le_arquivo_real(tmp_path: Path):
    arquivo = tmp_path / "forn.json"
    arquivo.write_text(
        json.dumps(
            {
                "itens": [
                    {
                        "produto": "Lousa Magica Tablet Lcd",
                        "url": "https://fornecedor/lousa",
                        "preco_1un": 9.99,
                        "vendidos": 2400,
                        "nota": 4.9,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    itens = cr.carregar_fornecedor(arquivo)
    assert len(itens) == 1
    assert itens[0].link == "https://fornecedor/lousa"
    assert itens[0].vendidos == 2400


def test_relatorio_markdown_marca_dados_ausentes(acervo):
    anuncios = [cr.AnuncioMarketplace(canal="Shopee", titulo="Lousa Magica Tablet Lcd 8.5")]
    texto = cr.relatorio_markdown(cr.cruzar(anuncios, acervo))
    assert "não informado" in texto
    assert "https://fornecedor/lousa" in texto
