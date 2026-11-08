"""Testes da importação CSV (caminho sem API)."""

from __future__ import annotations

from pathlib import Path

import pytest

from integrations.generic_csv import export_csv, import_csv, map_row, read_csv, template_csv


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_mapeia_cabecalhos_em_portugues():
    row = map_row({"Nome": "Livro", "Preço": "R$ 39,90", "Custo": "12,50"}, "products")
    assert row["name"] == "Livro"
    assert row["sale_price"] == 39.90
    assert row["purchase_price"] == 12.50


def test_importa_produtos(tmp_path, repo):
    path = write(tmp_path / "p.csv",
                 "name;purchase_price;sale_price\nLivro A;10;30\nLivro B;12;35\n")
    result = import_csv(path, "products", repo)
    assert result["imported"] == 2
    assert result["skipped"] == 0
    assert repo.count("products") == 2
    assert all(p["is_demo"] is False for p in repo.find("products"))


def test_rejeita_linha_sem_campo_obrigatorio(tmp_path, repo):
    path = write(tmp_path / "p.csv", "name;purchase_price\n;10\nLivro;12\n")
    result = import_csv(path, "products", repo)
    assert result["imported"] == 1
    assert result["skipped"] == 1
    assert "name" in result["errors"][0]["error"]


def test_demo_flag(tmp_path, repo):
    path = write(tmp_path / "p.csv", "name\nProduto demo\n")
    import_csv(path, "products", repo, is_demo=True, source="DEMO")
    product = repo.find("products")[0]
    assert product["is_demo"] is True
    assert product["source"] == "DEMO"


def test_importa_concorrentes_vinculando_produto(tmp_path, repo):
    repo.insert("products", {"name": "Livro X", "purchase_price": 10, "sale_price": 30})
    path = write(tmp_path / "c.csv",
                 "product_name;name;price;rating;reviews\nLivro X;Loja A;28,90;4,5;120\n")
    result = import_csv(path, "competitors", repo)
    assert result["imported"] == 1
    competitor = repo.find("competitors")[0]
    assert competitor["product_id"]


def test_concorrente_de_produto_inexistente_e_rejeitado(tmp_path, repo):
    path = write(tmp_path / "c.csv", "product_name;name;price\nNao Existe;Loja A;28,90\n")
    result = import_csv(path, "competitors", repo)
    assert result["imported"] == 0
    assert "não encontrado" in result["errors"][0]["error"]


def test_importa_oportunidades_com_criterios(tmp_path, repo):
    path = write(tmp_path / "o.csv",
                 "name;marketplace;price_found;cost_estimate;demanda;concorrencia\n"
                 "Livro Y;shopee;40;15;90;60\n")
    import_csv(path, "opportunities", repo)
    opportunity = repo.find("opportunities")[0]
    assert opportunity["breakdown"]["criteria"]["demanda"] == 90


def test_separador_virgula(tmp_path, repo):
    path = write(tmp_path / "p.csv", "name,purchase_price\nLivro,10\n")
    result = import_csv(path, "products", repo)
    assert result["imported"] == 1


def test_arquivo_vazio(tmp_path, repo):
    path = write(tmp_path / "p.csv", "name\n")
    result = import_csv(path, "products", repo)
    assert result["imported"] == 0


def test_exportar_e_modelo(tmp_path, repo):
    repo.insert("products", {"name": "Livro", "purchase_price": 1, "sale_price": 2})
    rows = repo.find("products")
    path = export_csv(rows, tmp_path / "out.csv")
    assert path.exists()
    headers, back = read_csv(path)
    assert back[0]["name"] == "Livro"

    model = template_csv("suppliers", tmp_path / "modelo.csv")
    assert "name" in model.read_text(encoding="utf-8")


def test_entidade_invalida(tmp_path, repo):
    path = write(tmp_path / "x.csv", "name\nA\n")
    with pytest.raises(ValueError):
        import_csv(path, "inexistente", repo)
