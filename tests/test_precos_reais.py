from scripts.precos_reais import casar, recalcular


MERCADO = {
    "coletado_em": "2026-11-09",
    "metodo": "teste",
    "aviso": "teste",
    "itens": [
        {"chave": "Mochila Escolar", "preco_mercado": 149.90, "faixa": [134.90, 199.99], "fontes": ["ML"]},
        {"chave": "Caixa De Som Com Microfone", "preco_mercado": 80.00, "faixa": [76.53, 114.31], "fontes": ["ML"]},
    ],
}


def _linha(produto, custo):
    return {"produto": produto, "custo": custo, "venda": custo * 3, "vendidos": 100, "margens": {}}


def test_casar_encontra_chave_no_nome():
    assert casar("Mochila Escolar Infantil Estampada", MERCADO["itens"])["preco_mercado"] == 149.90
    assert casar("Produto Sem Preco", MERCADO["itens"]) is None


def test_veredito_vale_quando_margem_real_passa_de_25():
    r = recalcular({"itens": [_linha("Mochila Escolar X", 86.90)]}, MERCADO)
    linha = r["itens"][0]
    assert linha["veredito"] == "vale"
    assert linha["margem_mercado"]["TikTok Shop"]["margem_pct"] > 25


def test_veredito_inviavel_quando_custo_fica_acima_do_mercado():
    r = recalcular({"itens": [_linha("Caixa De Som Com Microfone Y", 136.99)]}, MERCADO)
    linha = r["itens"][0]
    assert linha["veredito"] == "inviável"
    assert linha["margem_mercado"]["Shopee"]["margem_pct"] < 0


def test_produto_sem_preco_de_mercado_fica_none_e_nao_inventa_veredito():
    r = recalcular({"itens": [_linha("Produto Desconhecido", 10.0)]}, MERCADO)
    linha = r["itens"][0]
    assert linha["preco_mercado"] is None
    assert linha["margem_mercado"] is None
    assert "veredito" not in linha
