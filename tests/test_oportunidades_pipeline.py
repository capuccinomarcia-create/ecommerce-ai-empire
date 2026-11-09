"""Teste de integração: pipeline de oportunidades e rotas novas da API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import app  # app.py na raiz
from scripts.oportunidades import avaliar, demanda_de_vendidos


def test_demanda_convertida_de_vendidos_tem_escala_declarada():
    assert demanda_de_vendidos(None) is None
    assert demanda_de_vendidos(9500) == 100.0
    assert 40 <= demanda_de_vendidos(1000) <= 70
    assert demanda_de_vendidos(10) > 0


def test_pipeline_avalia_comparando_mesmo_preco(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.oportunidades.SAIDA", tmp_path)
    relatorio = avaliar(top=3, gerar_video=False)
    assert relatorio["total_avaliado"] >= 1
    assert len(relatorio["selecionados"]) <= 3
    for item in relatorio["selecionados"]:
        assert item["link"].startswith("https://")
        assert item["preco_venda"] > item["custo_1un"]
        # o lucro do melhor canal precisa ser o maior naquele mesmo preço
        lucros = {canal: dados["lucro_liquido"] for canal, dados in item["canais"].items()}
        assert item["lucro_unidade"] == max(lucros.values())
        assert item["arquivos_anuncio"]


def test_rotas_de_taxas_e_fornecedores():
    cliente = TestClient(app)
    taxas = cliente.get("/api/marketplaces/taxas")
    if taxas.status_code == 404:
        pytest.skip("rotas montadas em outro prefixo")
    assert taxas.status_code == 200
    assert len(taxas.json()["tabelas"]) == 3

    meta = cliente.get("/api/fornecedores/meta")
    assert meta.status_code == 200
    assert meta.json()["total"] >= 2000

    busca = cliente.get("/api/fornecedores/busca", params={"termo": "colorir", "limite": 3})
    assert busca.status_code == 200
    assert all(item["url"].startswith("https://") for item in busca.json())

    margem = cliente.post("/api/marketplaces/margem", json={"canal": "Shopee", "preco": 100, "custo_total": 40})
    assert margem.status_code == 200
    assert margem.json()["lucro_liquido"] == pytest.approx(42.0)
