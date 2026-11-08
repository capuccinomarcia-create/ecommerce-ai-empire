"""Testes do modo real: templates, checklist e remoção dos dados DEMO."""

from __future__ import annotations

import pytest

from core import data_mode
from scripts import setup_real


def test_modo_padrao_e_demo(repo):
    assert data_mode.get_mode(repo) == data_mode.DEMO
    assert data_mode.is_real(repo) is False


def test_troca_de_modo_valida(repo):
    data_mode.set_mode(repo, data_mode.REAL)
    assert data_mode.is_real(repo) is True
    with pytest.raises(ValueError):
        data_mode.set_mode(repo, "producao")


def test_checklist_aponta_pendencias(repo):
    situacao = data_mode.resumo(repo)
    assert situacao["prontos"] == 0
    itens = {i["item"]: i for i in situacao["itens"]}
    assert itens["Produtos reais cadastrados"]["ok"] is False
    assert "templates" in itens["Fornecedores reais com prazo e frete"]["como"]


def test_aplicar_modo_real_apaga_demo(demo_orchestrator, monkeypatch, tmp_path):
    repo = demo_orchestrator.repo
    assert repo.find("products", {}, limit=10)
    resultado = setup_real.aplicar_modo_real(repo)
    assert resultado["registros_demo_removidos"] > 0
    assert resultado["modo"] == data_mode.REAL
    # nada de produto/oportunidade DEMO sobrou
    assert repo.find("products", {}, limit=10) == []
    assert repo.find("opportunities", {}, limit=10) == []
    # prazo DEMO dos canais também foi limpo, para não virar número inventado
    for regra in repo.find("marketplaces", {}, limit=20):
        assert "DEMO" not in str(regra.get("sla_source") or "")


def test_templates_sao_criados_com_cabecalho(tmp_path, monkeypatch):
    monkeypatch.setattr(setup_real, "TEMPLATES_DIR", tmp_path)
    criados = setup_real.criar_templates()
    assert len(criados) == 4
    texto = (tmp_path / "fornecedores.csv").read_text(encoding="utf-8")
    assert "lead_time_days" in texto and "shipping_cost" in texto
    # não sobrescreve o que o proprietário já editou
    (tmp_path / "produtos.csv").write_text("meus;dados\n", encoding="utf-8")
    assert setup_real.criar_templates() == []
    assert (tmp_path / "produtos.csv").read_text(encoding="utf-8") == "meus;dados\n"


def test_importa_csv_real_sem_marcar_demo(repo, tmp_path):
    (tmp_path / "produtos.csv").write_text(
        "name;purchase_price;sale_price;marketplace\n"
        "Livro de Colorir;18,50;39,90;shopee\n", encoding="utf-8")
    relatorio = setup_real.importar_pasta(repo, tmp_path)
    assert relatorio["produtos.csv"]["imported"] == 1
    produto = repo.find_one("products", {"name": "Livro de Colorir"})
    assert produto["is_demo"] in (0, False)
    assert float(produto["sale_price"]) == pytest.approx(39.9)
