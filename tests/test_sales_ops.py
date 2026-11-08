"""Testes do operador de vendas: preço, estoque e prontidão do anúncio."""

from __future__ import annotations

import pytest

from core.sales_ops import (
    VEREDITO_AJUSTAR,
    VEREDITO_BLOQUEADO,
    VEREDITO_PRONTO,
    SalesOperator,
    estoque_minimo,
    preco_para_margem,
    resumo_texto,
)


def criar_produto(repo, **campos):
    base = {"name": "Livro de Colorir", "purchase_price": 18.5, "sale_price": 39.9,
            "marketplace": "shopee", "status": "ativo",
            "description": "x" * 150, "category": "livros"}
    base.update(campos)
    return repo.insert("products", base)


@pytest.fixture()
def canal(repo):
    repo.insert("marketplaces", {"slug": "shopee", "name": "Shopee",
                                "commission_pct": 14.0, "fixed_fee": 4.0})
    return repo


def test_preco_para_margem_matematica():
    # custo 18,50 + fixo 4,00 / (1 - 0,14 - 0,30) = 40,18
    assert preco_para_margem(18.5, 14.0, 4.0, 30.0) == pytest.approx(40.18, abs=0.01)


def test_preco_para_margem_impossivel():
    assert preco_para_margem(10, 80, 0, 30) is None   # comissão + alvo > 100%
    assert preco_para_margem(0, 14, 0, 30) is None    # sem custo não há conta


def test_estoque_minimo_cobre_prazo_mais_seguranca():
    assert estoque_minimo(0) == 0
    assert estoque_minimo(1, 7, 2) == 9
    assert estoque_minimo(0.5, 7, 2) == 5


def test_produto_completo_fica_pronto(repo, canal):
    produto = criar_produto(repo)
    plano = SalesOperator(repo).planejar(produto)
    assert plano.veredito == VEREDITO_PRONTO, plano.bloqueios
    assert plano.margem_pct is not None and plano.margem_pct > 10
    assert plano.preco_sugerido == pytest.approx(40.18, abs=0.01)


def test_sem_custo_fica_bloqueado(repo, canal):
    produto = criar_produto(repo, purchase_price=0)
    plano = SalesOperator(repo).planejar(produto)
    assert plano.veredito == VEREDITO_BLOQUEADO
    assert any("custo" in b for b in plano.bloqueios)


def test_descricao_curta_pede_ajuste(repo, canal):
    produto = criar_produto(repo, description="curta")
    plano = SalesOperator(repo).planejar(produto)
    assert plano.veredito == VEREDITO_AJUSTAR
    assert any("120 caracteres" in b for b in plano.bloqueios)


def test_comissao_zerada_pede_ajuste(repo):
    produto = criar_produto(repo)   # sem registro de marketplace
    plano = SalesOperator(repo).planejar(produto)
    assert any("comissão real" in b for b in plano.bloqueios)


def test_margem_baixa_avisa_com_preco_sugerido(repo, canal):
    produto = criar_produto(repo, sale_price=22.0)
    plano = SalesOperator(repo).planejar(produto)
    assert plano.veredito == VEREDITO_AJUSTAR
    assert any("margem" in b and "sugerido" in b for b in plano.bloqueios)


def test_reposicao_usa_vendas_dos_ultimos_30_dias(repo, canal):
    produto = criar_produto(repo)
    from datetime import datetime

    for _ in range(30):   # 1 venda por dia = 30 em 30 dias
        repo.insert("sales", {"product_id": produto["id"], "marketplace": "shopee",
                              "quantity": 1, "unit_price": 39.9, "total": 39.9,
                              "sold_at": datetime.now().isoformat()})
    plano = SalesOperator(repo, prazo_fornecedor_dias=7).planejar(produto)
    assert plano.vendas_30d == 30
    assert plano.estoque_minimo == 9        # 1/dia * (7 + 2)
    assert plano.repor == 9                 # sem estoque registrado


def test_estoque_existente_reduz_reposicao(repo, canal):
    produto = criar_produto(repo)
    from datetime import datetime

    for _ in range(30):
        repo.insert("sales", {"product_id": produto["id"], "quantity": 1,
                              "sold_at": datetime.now().isoformat()})
    repo.insert("stock_movements", {"product_id": produto["id"], "kind": "entrada",
                                    "quantity": 6})
    plano = SalesOperator(repo).planejar(produto)
    assert plano.estoque_atual == 6
    assert plano.repor == 3


def test_venda_antiga_nao_conta(repo, canal):
    produto = criar_produto(repo)
    repo.insert("sales", {"product_id": produto["id"], "quantity": 40,
                          "sold_at": "2025-01-01T10:00:00"})
    plano = SalesOperator(repo).planejar(produto)
    assert plano.vendas_30d == 0


def test_plano_vazio_orienta(repo):
    plano = SalesOperator(repo).plano()
    assert plano["sem_produtos"] is True
    assert "custo e preço" in resumo_texto(plano)


def test_resumo_separa_prontos_e_travados(repo, canal):
    criar_produto(repo)
    criar_produto(repo, name="Caderno", purchase_price=0)
    plano = SalesOperator(repo).plano()
    texto = resumo_texto(plano)
    assert "Prontos para publicar: 1" in texto
    assert "Bloqueados por dado faltante: 1" in texto


def test_produto_inativo_nao_entra(repo, canal):
    criar_produto(repo, status="pausado")
    assert SalesOperator(repo).plano()["sem_produtos"] is True
