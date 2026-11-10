from scripts.ranking_fornecedor import _linha, faixas, detalhe


def test_faixas_descarta_linha_que_encarece():
    md = (
        "| 1 - 3 | -37% | R$136,99 |\n"
        "| 4 - 7 | -39% | R$132,88 |\n"
        "| 10 + | -43% | R$123,29 |\n"
        "| 24 + | -0% | R$136,99 |\n"
    )
    assert faixas(md) == [(1, 136.99), (4, 132.88), (10, 123.29)]


def test_detalhe_le_vendidos_e_nota():
    md = "4.3+ de 3800 vendidos\nR$216,24-36%\nR$136,99"
    d = detalhe(md)
    assert d["vendidos"] == 3800
    assert d["nota"] == 4.3
    assert d["preco_referencia"] == 216.24


def test_linha_calcula_margem_nos_tres_canais_e_usa_3x():
    linha = _linha({"produto": "Lousa", "url": "https://x/p", "imagem": None}, [(1, 10.0)], 2400, 4.9)
    assert linha["venda"] == 30.0
    assert set(linha["margens"]) == {"Mercado Livre", "Shopee", "TikTok Shop"}
    assert linha["margens"]["TikTok Shop"] > linha["margens"]["Shopee"]
    assert linha["vendidos"] == 2400


def test_linha_sem_vendidos_nao_inventa_numero():
    linha = _linha({"produto": "X", "url": "https://x/p"}, [(1, 10.0)], None, None)
    assert linha["vendidos"] is None
    assert linha["nota"] is None
