"""Testes da central de fornecedores, com os dados reais da Feira da Madrugada."""

from __future__ import annotations

import pytest

from analytics import suppliers


@pytest.fixture(scope="module")
def base():
    return suppliers.carregar()


def test_base_tem_catalogo_real_e_meta(base):
    info = suppliers.meta()
    assert info["total"] >= 2000
    assert info["com_preco_confirmado"] >= 1
    assert info["coletado_em"]
    assert len(base) == info["total"]


def test_todo_item_tem_link_direto_e_fonte(base):
    for item in base[:200]:
        assert item.url.startswith("https://")
        assert item.fornecedor
        assert item.fonte
        assert item.coletado_em


def test_busca_ignora_acento_e_maiuscula():
    achados = suppliers.buscar("livro de colorir", limite=5)
    assert achados
    assert all("colorir" in a.produto.lower() for a in achados)


def test_item_sem_preco_confirma_lacuna_em_vez_de_inventar(base):
    sem_preco = [i for i in base if not i.preco_confirmado][:5]
    assert sem_preco
    for item in sem_preco:
        dados = item.para_dict()
        assert dados["preco_1un"] is None
        assert dados["estoque"] is None
        assert "estoque não informado" in dados["avisos"]


def test_melhor_oferta_usa_preco_confirmado_e_devolve_link():
    resultado = suppliers.melhor_oferta("caixa de som bluetooth com microfone", quantidade=10)
    assert resultado is not None
    oferta = resultado["oferta"]
    assert oferta is not None
    assert oferta["url"].startswith("https://")
    assert oferta["preco_unitario"] == pytest.approx(123.29)
    assert "frete não informado" in oferta["avisos"]


def test_preco_por_faixa_respeita_quantidade():
    item = suppliers.buscar("caixa de som bluetooth com microfone", limite=1)[0]
    assert item.preco_para(1) == pytest.approx(136.99)
    assert item.preco_para(4) == pytest.approx(132.88)
    assert item.preco_para(10) == pytest.approx(123.29)
    assert item.preco_para(50) == pytest.approx(123.29)


def test_melhor_oferta_sem_preco_confirmado_nao_chuta():
    acervo = suppliers.carregar()
    sem_preco = next(i for i in acervo if not i.preco_confirmado)
    resultado = suppliers.melhor_oferta(sem_preco.produto, quantidade=1)
    assert resultado is not None
    assert resultado["oferta"] is None
    assert "preço confirmado" in resultado["motivo"]


def test_abrir_fornecedor_valida_link():
    assert suppliers.abrir_fornecedor("https://www.feiradamadrugadasp.com.br/x/p")["link_direto"]
    with pytest.raises(ValueError):
        suppliers.abrir_fornecedor("ftp://invalido")


def test_arquivo_inexistente_falha_alto():
    with pytest.raises(suppliers.FornecedorIndisponivel):
        suppliers.carregar("/tmp/nao_existe_fornecedores.json")
