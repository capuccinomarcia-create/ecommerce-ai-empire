"""Testes da fábrica de anúncios e da fábrica de vídeo (MP4 real com ffmpeg)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from analytics import listing_factory, video_factory

PRODUTO = {
    "nome": "Caixa De Som Bluetooth Com Microfone Grande Led USB Potente",
    "custo": 136.99,
    "categoria": "Eletrônicos",
    "peso_kg": 1.2,
    "imagem": "/tmp/img_teste_1.jpg",
}


def test_titulo_respeita_limite_de_cada_canal():
    for canal, limite in listing_factory.LIMITE_TITULO.items():
        anuncio = listing_factory.gerar(PRODUTO, canal)
        assert len(anuncio.titulo) <= limite
        assert anuncio.titulo


def test_anuncio_traz_campos_obrigatorios_e_preco_calculado():
    anuncio = listing_factory.gerar(PRODUTO, "TikTok Shop").para_dict()
    assert anuncio["descricao"] and "Envio" in anuncio["descricao"]
    assert anuncio["palavras_chave"]
    assert anuncio["atributos_obrigatorios"]
    assert anuncio["preco_recomendado"] > PRODUTO["custo"]
    assert anuncio["margem"]["margem_pct"] == pytest.approx(30.0, abs=0.3)
    assert any("provisória" in a for a in anuncio["avisos"])


def test_anuncio_sem_custo_nao_inventa_preco():
    produto = dict(PRODUTO)
    produto.pop("custo")
    anuncio = listing_factory.gerar(produto, "Shopee").para_dict()
    assert anuncio["preco_recomendado"] is None
    assert any("custo" in a for a in anuncio["avisos"])


def test_gerar_todos_aponta_melhor_canal():
    pacote = listing_factory.gerar_todos(PRODUTO)
    assert set(pacote["anuncios"]) == {"Mercado Livre", "Shopee", "TikTok Shop"}
    lucros = {c: a["margem"]["lucro_liquido"] for c, a in pacote["anuncios"].items()}
    assert pacote["melhor_canal"] == max(lucros, key=lucros.get)


def test_roteiros_existem_nos_tres_formatos():
    anuncio = listing_factory.gerar(PRODUTO, "Shopee").para_dict()
    assert set(anuncio["roteiros"]) == {"15s", "30s", "60s"}
    assert all(len(anuncio["roteiros"][k]) >= 3 for k in anuncio["roteiros"])


def test_salvar_pacote_grava_arquivos(tmp_path):
    pacote = listing_factory.gerar_todos(PRODUTO)
    resultado = listing_factory.salvar_pacote(pacote, tmp_path)
    assert resultado["total"] == 6
    for nome in resultado["arquivos"]:
        assert Path(nome).exists()
    dados = json.loads((tmp_path / "anuncio_shopee.json").read_text(encoding="utf-8"))
    assert dados["canal"] == "Shopee"


def test_canal_invalido_falha():
    with pytest.raises(ValueError):
        listing_factory.gerar(PRODUTO, "Amazon")


# ---------------- vídeo ----------------


def _criar_imagens(pasta: Path, quantidade: int = 2) -> list[Path]:
    caminhos = []
    for indice in range(quantidade):
        caminho = pasta / f"cena_{indice}.jpg"
        imagem = Image.new("RGB", (800, 1200), (20 + indice * 40, 40, 90))
        desenho = ImageDraw.Draw(imagem)
        desenho.rectangle([80, 200, 720, 1000], fill=(240, 240, 250))
        desenho.text((120, 260), f"Cena {indice + 1}", fill=(0, 0, 0))
        imagem.save(caminho, quality=90)
        caminhos.append(caminho)
    return caminhos


@pytest.mark.skipif(not video_factory.ffmpeg_disponivel(), reason="ffmpeg ausente")
def test_gera_mp4_real_com_duracao_e_resolucao(tmp_path):
    imagens = _criar_imagens(tmp_path)
    destino = tmp_path / "anuncio.mp4"
    video = video_factory.gerar_video(
        imagens, "Caixa de Som Bluetooth", destino,
        preco="R$ 216,24", duracao_total=6.0,
    )
    assert destino.exists() and destino.stat().st_size > 10_000
    assert 5.0 <= video.duracao_s <= 7.0
    assert (video.largura, video.altura) == (1080, 1920)
    assert video.tem_audio is False

    info = video_factory.probe(destino)
    codigos = {s["codec_type"] for s in info["streams"]}
    assert "video" in codigos


@pytest.mark.skipif(not video_factory.ffmpeg_disponivel(), reason="ffmpeg ausente")
def test_video_com_musica_ganha_trilha(tmp_path):
    imagens = _criar_imagens(tmp_path, 1)
    musica = tmp_path / "trilha.wav"
    import subprocess

    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", "sine=frequency=440:duration=5", str(musica)], check=True)
    video = video_factory.gerar_video(imagens, "Teste", tmp_path / "com_musica.mp4",
                                      duracao_total=5.0, musica=musica)
    assert video.tem_audio is True


def test_imagem_inexistente_falha_alto(tmp_path):
    with pytest.raises(FileNotFoundError):
        video_factory.gerar_video([tmp_path / "nao_existe.jpg"], "Teste", tmp_path / "x.mp4")


@pytest.mark.skipif(not video_factory.ffmpeg_disponivel(), reason="ffmpeg ausente")
def test_pacote_sem_imagem_em_disco_avisa_em_vez_de_gerar(tmp_path):
    pacote = listing_factory.gerar_todos(PRODUTO)  # imagem aponta para arquivo ausente
    resultado = video_factory.gerar_para_anuncio(pacote, tmp_path / "v.mp4")
    assert resultado["ok"] is False
    assert "disco" in resultado["motivo"]
