from scripts.scan_completo import pagina

HTML = '''
<article class="product-miniature product-miniature-default">
<div class="product-description">
<div class="product-category-name text-muted">Mochilas no Atacado</div>
<h3 class="h3 product-title">
<a href="https://www.feiradamadrugadasp.com.br/mochila-teste/p#/1-cor-preto">Mochila Teste - PRETO</a>
</h3>
<div class="rating-value">4.9</div>
</div>
<img data-srcset="https://cdn.feiradamadrugadasp.com.br/img/p/1/9/2/192885-small_default.jpg 127w,
 https://cdn.feiradamadrugadasp.com.br/img/p/1/9/2/192885-home_default.jpg 305w">
<div class="product-price-and-shipping">
<span class="regular-price text-muted">R$&#160;64,00</span>
<span class="price current-price-discount"><span class="starting-text-price"> A partir de </span> R$&#160;53,91</span>
</div>
</article>
<article class="product-miniature product-miniature-default">
<div class="product-description">
<h3 class="h3 product-title"><a href="https://www.feiradamadrugadasp.com.br/sem-preco/p">Sem preço</a></h3>
</div>
</article>
'''


def test_pagina_le_preco_desconto_e_posicao():
    itens = pagina(HTML, 1)
    assert len(itens) == 1  # bloco sem preço é descartado, não inventado
    item = itens[0]
    assert item["nome"] == "Mochila Teste - PRETO"
    assert item["preco"] == 53.91
    assert item["preco_de"] == 64.0
    assert item["desconto"] == 15.8
    assert item["nota"] == 4.9
    assert item["categoria"] == "Mochilas no Atacado"
    assert item["url"].endswith("/mochila-teste/p")
    assert item["imagem"].endswith("192885-home_default.jpg")
    assert item["posicao"] == 1


def test_pagina_calcula_minimo_para_30_nos_tres_canais():
    item = pagina(HTML, 1)[0]
    assert set(item["minimo_30"]) == {"Mercado Livre", "Shopee", "TikTok Shop"}
    for canal, preco in item["minimo_30"].items():
        assert preco > item["preco"], f"{canal} deveria exigir preço maior que o custo"
    assert item["minimo_30"]["TikTok Shop"] < item["minimo_30"]["Shopee"]


def test_posicao_respeita_inicio_da_pagina():
    itens = pagina(HTML, 121)
    assert itens[0]["posicao"] == 121
