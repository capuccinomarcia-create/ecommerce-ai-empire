"""Fábrica de vídeo: gera arquivo MP4 real com ffmpeg (imagens + texto + música opcional).

Isto produz vídeo de verdade, não roteiro. Se o ffmpeg não estiver instalado, o módulo
levanta erro explicando o que falta em vez de fingir que gerou.

Recursos usados: ffmpeg/ffprobe (open source, gratis). Música só entra se o arquivo
for fornecido pelo usuário e tiver licença livre — o módulo não baixa áudio.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

LARGURA_PADRAO = 1080
ALTURA_PADRAO = 1920  # vertical, formato de Reels/Shorts/TikTok


class FfmpegAusente(RuntimeError):
    """ffmpeg/ffprobe não encontrados no sistema."""


def ffmpeg_disponivel() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def _checar_ffmpeg() -> None:
    if not ffmpeg_disponivel():
        raise FfmpegAusente(
            "ffmpeg/ffprobe não encontrados. Instale com 'apt install ffmpeg' (Linux) "
            "ou 'brew install ffmpeg' (macOS). Sem isso não há MP4 real."
        )


def _escapar_texto(texto: str) -> str:
    """Escapa texto para drawtext do ffmpeg."""
    return (
        texto.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\u2019")
        .replace("%", "\\%")
    )


@dataclass
class VideoGerado:
    caminho: str
    duracao_s: float
    largura: int
    altura: int
    fps: float
    tem_audio: bool
    bytes: int
    imagens_usadas: int

    def para_dict(self) -> dict:
        return {
            "caminho": self.caminho,
            "duracao_s": round(self.duracao_s, 2),
            "largura": self.largura,
            "altura": self.altura,
            "fps": self.fps,
            "tem_audio": self.tem_audio,
            "bytes": self.bytes,
            "imagens_usadas": self.imagens_usadas,
        }


def probe(caminho: Path | str) -> dict:
    """Lê o arquivo gerado com ffprobe para provar que o vídeo existe e tem streams."""
    _checar_ffmpeg()
    saida = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(caminho)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(saida.stdout)


def gerar_video(
    imagens: list[Path | str],
    titulo: str,
    saida: Path | str,
    *,
    preco: str | None = None,
    duracao_total: float = 15.0,
    musica: Path | str | None = None,
    largura: int = LARGURA_PADRAO,
    altura: int = ALTURA_PADRAO,
    fonte: str | None = None,
) -> VideoGerado:
    """Monta um MP4 vertical com as imagens, zoom suave e legenda fixa.

    Cada imagem fica `duracao_total / quantidade` segundos. Se `musica` for passada,
    ela entra como trilha (o arquivo precisa existir e ter licença livre).
    """
    _checar_ffmpeg()
    lista = [Path(i) for i in imagens]
    if not lista:
        raise ValueError("informe pelo menos uma imagem")
    for caminho in lista:
        if not caminho.exists():
            raise FileNotFoundError(f"imagem não encontrada: {caminho}")
    if musica and not Path(musica).exists():
        raise FileNotFoundError(f"música não encontrada: {musica}")

    destino = Path(saida)
    destino.parent.mkdir(parents=True, exist_ok=True)
    por_imagem = max(round(duracao_total / len(lista), 2), 1.0)
    fps = 30

    comandos = ["ffmpeg", "-y", "-loglevel", "error"]
    for caminho in lista:
        comandos += ["-loop", "1", "-t", f"{por_imagem}", "-i", str(caminho)]
    if musica:
        comandos += ["-i", str(musica)]

    filtros = []
    for indice in range(len(lista)):
        # enquadra em vertical, aplica zoom lento e escreve a legenda
        filtros.append(
            f"[{indice}:v]scale={largura}:{altura}:force_original_aspect_ratio=increase,"
            f"crop={largura}:{altura},"
            f"zoompan=z='min(zoom+0.0015,1.12)':d={int(por_imagem * fps)}:s={largura}x{altura}:fps={fps},"
            f"setsar=1[v{indice}]"
        )
    filtros.append("".join(f"[v{i}]" for i in range(len(lista))) + f"concat=n={len(lista)}:v=1:a=0[base]")

    textos = [titulo[:48]]
    if preco:
        textos.append(preco)
    desenho = "".join(
        f",drawtext=text='{_escapar_texto(t)}':fontcolor=white:fontsize={56 if i == 0 else 64}:"
        f"box=1:boxcolor=black@0.55:boxborderw=18:x=(w-text_w)/2:y={'h*0.12' if i == 0 else 'h*0.82'}"
        + (f":fontfile={fonte}" if fonte else "")
        for i, t in enumerate(textos)
    )
    filtros.append(f"[base]{desenho.lstrip(',')}[vout]")

    comandos += ["-filter_complex", ";".join(filtros), "-map", "[vout]"]
    if musica:
        comandos += ["-map", f"{len(lista)}:a", "-shortest", "-c:a", "aac", "-b:a", "128k"]
    comandos += [
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-pix_fmt", "yuv420p", "-r", str(fps), "-t", f"{duracao_total}", str(destino),
    ]

    subprocess.run(comandos, check=True, capture_output=True, text=True)

    info = probe(destino)
    streams = info.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    tem_audio = any(s.get("codec_type") == "audio" for s in streams)
    if not video:
        raise RuntimeError("ffmpeg não produziu trilha de vídeo")
    duracao = float(info.get("format", {}).get("duration") or 0)
    if duracao <= 0:
        raise RuntimeError("vídeo gerado sem duração válida")

    return VideoGerado(
        caminho=str(destino),
        duracao_s=duracao,
        largura=int(video.get("width") or largura),
        altura=int(video.get("height") or altura),
        fps=float(video.get("r_frame_rate", "0/1").split("/")[0] or 0),
        tem_audio=tem_audio,
        bytes=destino.stat().st_size,
        imagens_usadas=len(lista),
    )


def gerar_para_anuncio(pacote: dict, destino: Path | str, *,
                       duracao: float = 15.0, musica: Path | str | None = None) -> dict:
    """Gera o vídeo a partir do pacote da fábrica de anúncios.

    Usa as imagens do anúncio e o título/preço do canal de melhor margem.
    """
    canal = pacote.get("melhor_canal") or next(iter(pacote["anuncios"]))
    anuncio = pacote["anuncios"][canal]
    imagens = [i for i in anuncio.get("imagens", []) if Path(i).exists()]
    if not imagens:
        return {
            "ok": False,
            "motivo": "as imagens do anúncio precisam estar baixadas no disco para virar vídeo",
            "imagens_informadas": anuncio.get("imagens", []),
        }
    preco = anuncio.get("preco_recomendado")
    video = gerar_video(
        imagens, anuncio["titulo"], destino,
        preco=(f"R$ {preco:.2f}".replace(".", ",") if preco else None),
        duracao_total=duracao, musica=musica,
    )
    return {"ok": True, "canal": canal, "video": video.para_dict()}
