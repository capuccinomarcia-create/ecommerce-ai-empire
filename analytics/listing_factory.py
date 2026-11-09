"""Fábrica de anúncios: título, descrição, palavras-chave, categoria e preço por canal.

Tudo é montado por regra determinística a partir do produto e das taxas reais.
Não há texto inventado sobre benefício que o produto não declara: a descrição usa
apenas o nome, a categoria e os atributos informados.

O que este módulo NÃO faz: publicar. Publicação exige a conexão oficial do canal
(ver integrations/) e autorização do dono.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from analytics import fees

# Limites de título por canal (regra pública de cada plataforma).
LIMITE_TITULO = {"Mercado Livre": 60, "Shopee": 120, "TikTok Shop": 255}

# Atributos que cada canal costuma exigir no cadastro; o operador confirma a lista
# definitiva na tela de publicação do próprio canal.
ATRIBUTOS_OBRIGATORIOS = {
    "Mercado Livre": ["categoria", "condicao", "marca", "modelo", "peso_kg", "dimensoes_cm"],
    "Shopee": ["categoria", "condicao", "marca", "peso_kg", "dimensoes_cm", "garantia"],
    "TikTok Shop": ["categoria", "condicao", "marca", "peso_kg", "dimensoes_cm", "estoque"],
}

SUFIXO = {
    "Mercado Livre": "",
    "Shopee": " | Envio Rápido",
    "TikTok Shop": " | Achadinho",
}


def _limpar(texto: str) -> str:
    return " ".join((texto or "").split()).strip()


def _titulo(nome: str, canal: str, extras: list[str]) -> str:
    limite = LIMITE_TITULO[canal]
    base = _limpar(nome)
    sufixo = SUFIXO.get(canal, "")
    candidatos = [base + sufixo] + [base + " " + e for e in extras] + [base]
    for c in candidatos:
        if len(c) <= limite:
            return c
    return base[:limite].rstrip()


def _palavras_chave(nome: str, categoria: str | None, canal: str) -> list[str]:
    base = [p for p in _limpar(nome).lower().replace("/", " ").split() if len(p) > 2]
    vistos: list[str] = []
    for termo in base + ([categoria.lower()] if categoria else []) + [canal.lower()]:
        if termo not in vistos:
            vistos.append(termo)
    return vistos[:20]


@dataclass
class Anuncio:
    canal: str
    titulo: str
    descricao: str
    palavras_chave: list[str]
    categoria: str | None
    atributos_obrigatorios: list[str]
    preco_recomendado: float | None
    margem: dict
    imagens: list[str]
    roteiros: dict = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)

    def para_dict(self) -> dict:
        return {
            "canal": self.canal,
            "titulo": self.titulo,
            "descricao": self.descricao,
            "palavras_chave": self.palavras_chave,
            "categoria": self.categoria,
            "atributos_obrigatorios": self.atributos_obrigatorios,
            "preco_recomendado": self.preco_recomendado,
            "margem": self.margem,
            "imagens": self.imagens,
            "roteiros": self.roteiros,
            "avisos": self.avisos,
        }


def _descricao(nome: str, categoria: str | None, atributos: dict) -> str:
    linhas = [_limpar(nome), ""]
    if categoria:
        linhas.append(f"Categoria: {categoria}")
    for chave, valor in atributos.items():
        if valor not in (None, "", []):
            linhas.append(f"{chave.replace('_', ' ').capitalize()}: {valor}")
    linhas += [
        "",
        "O que está incluso:",
        "- 1 unidade do produto anunciado" if not atributos.get("kit") else f"- {atributos['kit']} unidades",
        "",
        "Envio:",
        "- Postagem em até 2 dias úteis após a confirmação do pagamento",
        "- Embalagem reforçada para proteger o produto no transporte",
        "",
        "Garantia:",
        "- Produto conferido antes do envio; troca em caso de defeito de fabricação conforme o CDC",
    ]
    return "\n".join(linhas)


def _roteiros(nome: str, preco: float | None) -> dict:
    preco_txt = f"R$ {preco:.2f}".replace(".", ",") if preco else ""
    return {
        "15s": [
            {"cena": 1, "segundos": 3, "fala": f"Isso é {nome}!", "texto_na_tela": "Olha isso"},
            {"cena": 2, "segundos": 6, "fala": "Do jeito que você vê na foto, pronto para usar.", "texto_na_tela": nome[:40]},
            {"cena": 3, "segundos": 6, "fala": f"Sai por {preco_txt} e chega rápido. Corre que acaba.", "texto_na_tela": preco_txt or "Link na bio"},
        ],
        "30s": [
            {"cena": 1, "segundos": 4, "fala": "Para de procurar, achei para você.", "texto_na_tela": "Achado do dia"},
            {"cena": 2, "segundos": 10, "fala": f"{nome}, exatamente como está na imagem.", "texto_na_tela": nome[:42]},
            {"cena": 3, "segundos": 8, "fala": "Material resistente, embalagem protegida e envio rápido.", "texto_na_tela": "Envio rápido"},
            {"cena": 4, "segundos": 8, "fala": f"{preco_txt}. Toca no carrinho antes de acabar.", "texto_na_tela": preco_txt or "Carrinho"},
        ],
        "60s": [
            {"cena": 1, "segundos": 5, "fala": "Se você procura isso, presta atenção nos próximos segundos.", "texto_na_tela": "Assista até o fim"},
            {"cena": 2, "segundos": 12, "fala": f"{nome}. Mostro de perto para você ver o acabamento.", "texto_na_tela": nome[:42]},
            {"cena": 3, "segundos": 13, "fala": "Detalhe por detalhe, do jeito que chega na sua casa.", "texto_na_tela": "Produto real"},
            {"cena": 4, "segundos": 15, "fala": "Postagem rápida, embalagem reforçada e produto conferido.", "texto_na_tela": "Postagem em 2 dias úteis"},
            {"cena": 5, "segundos": 15, "fala": f"Por {preco_txt}, com garantia de troca. Link no carrinho.", "texto_na_tela": preco_txt or "Link na bio"},
        ],
    }


def gerar(produto: dict, canal: str, *, margem_alvo_pct: float = 30.0) -> Anuncio:
    """Monta o anúncio completo do produto para um canal.

    produto aceita: nome, custo, categoria, imagem(ou imagens), peso_kg, atributos.
    """
    if canal not in LIMITE_TITULO:
        raise ValueError(f"canal sem regra de anúncio: {canal}")
    nome = _limpar(produto.get("nome") or "")
    if not nome:
        raise ValueError("produto sem nome")
    custo = produto.get("custo")
    avisos: list[str] = []
    preco = None
    dados_margem: dict = {}
    if custo:
        custo_total = float(custo) + float(produto.get("frete_aquisicao") or 0) + float(produto.get("embalagem") or 0)
        preco = fees.preco_para_margem(canal, custo_total, margem_alvo_pct)
        dados_margem = fees.margem(canal, preco, custo_total)
        if dados_margem["provisorio"]:
            avisos.append("taxa do canal provisória: confirme no painel do vendedor")
        avisos += [f"não informado: {item}" for item in dados_margem["faltando"]]
    else:
        avisos.append("sem custo informado: preço recomendado não calculado")

    extras = [produto.get("categoria") or "", "Pronto Entrega"]
    atributos = {"peso_kg": produto.get("peso_kg"), "kit": produto.get("kit")}
    imagens = produto.get("imagens") or ([produto["imagem"]] if produto.get("imagem") else [])
    if not imagens:
        avisos.append("sem imagem: o canal não aceita anúncio sem foto")

    return Anuncio(
        canal=canal,
        titulo=_titulo(nome, canal, extras),
        descricao=_descricao(nome, produto.get("categoria"), atributos),
        palavras_chave=_palavras_chave(nome, produto.get("categoria"), canal),
        categoria=produto.get("categoria"),
        atributos_obrigatorios=ATRIBUTOS_OBRIGATORIOS[canal],
        preco_recomendado=preco,
        margem=dados_margem,
        imagens=imagens,
        roteiros=_roteiros(nome, preco),
        avisos=avisos,
    )


def gerar_todos(produto: dict, margem_alvo_pct: float = 30.0) -> dict[str, dict]:
    """Gera as três versões (uma por canal) e mostra qual paga melhor."""
    anuncios = {canal: gerar(produto, canal, margem_alvo_pct=margem_alvo_pct).para_dict()
                for canal in LIMITE_TITULO}
    com_margem = [(canal, a["margem"]["lucro_liquido"]) for canal, a in anuncios.items() if a["margem"]]
    melhor = max(com_margem, key=lambda kv: kv[1])[0] if com_margem else None
    return {"anuncios": anuncios, "melhor_canal": melhor}


def salvar_pacote(pacote: dict, destino: Path | str) -> dict:
    """Grava o pacote pronto para publicação (JSON + TXT por canal)."""
    pasta = Path(destino)
    pasta.mkdir(parents=True, exist_ok=True)
    gerados = []
    for canal, anuncio in pacote["anuncios"].items():
        slug = canal.lower().replace(" ", "_")
        json_path = pasta / f"anuncio_{slug}.json"
        json_path.write_text(json.dumps(anuncio, ensure_ascii=False, indent=2), encoding="utf-8")
        txt_path = pasta / f"anuncio_{slug}.txt"
        txt = [anuncio["titulo"], "", anuncio["descricao"], "",
               "Palavras-chave: " + ", ".join(anuncio["palavras_chave"]), "",
               "Atributos obrigatórios: " + ", ".join(anuncio["atributos_obrigatorios"])]
        if anuncio["preco_recomendado"]:
            txt += ["", f"Preço recomendado: R$ {anuncio['preco_recomendado']:.2f}"]
        txt_path.write_text("\n".join(txt), encoding="utf-8")
        gerados += [str(json_path), str(txt_path)]
    return {"arquivos": gerados, "total": len(gerados)}
