"""Product Hunter: descoberta de produtos a partir de fontes reais e autorizadas.

Fontes suportadas hoje:
  - sitemap de catálogo de fornecedor (XML): nome, link exato e imagem.
  - CSV/planilha exportada: nome, custo, preço, categoria, peso, dimensões.
  - lista de URLs fornecida pelo usuário (viram itens para análise, sem inventar dado).

REGRA: o módulo nunca inventa preço, estoque, vendas ou procura. O que não vier da
fonte fica None e vai para `lacunas`. Nada de "estimativa" dentro do cálculo.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable

# cabeçalhos aceitos, em português e inglês
MAPA_CABECALHOS = {
    "nome": ("nome", "produto", "title", "titulo", "descricao", "description", "name"),
    "custo": ("custo", "preco_custo", "preco de compra", "cost", "purchase_price", "preco_compra"),
    "preco": ("preco", "preço", "preco_venda", "price", "sale_price", "valor"),
    "categoria": ("categoria", "category", "secao", "setor"),
    "url": ("url", "link", "produto_url", "product_url", "site"),
    "peso_kg": ("peso", "peso_kg", "weight", "weight_kg"),
    "altura_cm": ("altura", "altura_cm", "height"),
    "largura_cm": ("largura", "largura_cm", "width"),
    "comprimento_cm": ("comprimento", "comprimento_cm", "length", "profundidade"),
    "estoque": ("estoque", "stock", "quantidade", "qtd", "quantity"),
    "fornecedor": ("fornecedor", "supplier", "loja", "vendor"),
}


def _sem_acento(texto: str) -> str:
    normal = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in normal if unicodedata.category(c) != "Mn").lower().strip()


def _chave(cabecalho: str) -> str | None:
    alvo = _sem_acento(cabecalho).replace("-", "_").replace(" ", "_")
    for campo, variantes in MAPA_CABECALHOS.items():
        if alvo in {_sem_acento(v).replace(" ", "_") for v in variantes}:
            return campo
    return None


def _numero(valor: Any) -> float | None:
    if valor is None or valor == "":
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip().replace("R$", "").replace(" ", "")
    if not texto:
        return None
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return None


@dataclass
class Produto:
    """Produto descoberto, com a origem do dado registrada."""

    nome: str
    fonte: str
    url: str | None = None
    imagem: str | None = None
    custo: float | None = None
    preco: float | None = None
    categoria: str | None = None
    peso_kg: float | None = None
    altura_cm: float | None = None
    largura_cm: float | None = None
    comprimento_cm: float | None = None
    estoque: int | None = None
    fornecedor: str | None = None
    coletado_em: str | None = None
    lacunas: list[str] = field(default_factory=list)

    def para_dict(self) -> dict:
        dados = {k: getattr(self, k) for k in (
            "nome", "fonte", "url", "imagem", "custo", "preco", "categoria", "peso_kg",
            "altura_cm", "largura_cm", "comprimento_cm", "estoque", "fornecedor", "coletado_em",
        )}
        dados["lacunas"] = sorted(set(self.lacunas + [
            campo for campo in ("custo", "preco", "peso_kg", "estoque") if getattr(self, campo) is None
        ]))
        return dados


def importar_sitemap(xml: str, fonte: str = "", coletado_em: str | None = None) -> list[Produto]:
    """Lê o sitemap de produtos de um fornecedor (PrestaShop/Google) e monta a lista."""
    produtos: list[Produto] = []
    for bloco in re.findall(r"<url>(.*?)</url>", xml, flags=re.S):
        loc = re.search(r"<loc><!\[CDATA\[(.*?)\]\]></loc>", bloco) or re.search(r"<loc>(.*?)</loc>", bloco)
        if not loc:
            continue
        url = loc.group(1).strip()
        if not re.search(r"/p/?$", url):
            continue
        titulo = re.search(r"<image:title><!\[CDATA\[(.*?)\]\]></image:title>", bloco)
        imagem = re.search(r"<image:loc><!\[CDATA\[(.*?)\]\]></image:loc>", bloco)
        atualizado = re.search(r"<lastmod>(.*?)</lastmod>", bloco)
        nome = titulo.group(1).strip() if titulo else _nome_pela_url(url)
        produtos.append(Produto(
            nome=nome,
            fonte=fonte or url.split("/")[2],
            url=url,
            imagem=imagem.group(1).strip() if imagem else None,
            coletado_em=coletado_em or (atualizado.group(1)[:10] if atualizado else None),
            lacunas=["custo", "preco", "estoque", "peso_kg"],
        ))
    return produtos


def _nome_pela_url(url: str) -> str:
    pedaco = url.rstrip("/").split("/")[-2] if url.endswith("/p") else url.rstrip("/").split("/")[-1]
    return pedaco.replace("-", " ").title()


def importar_csv(conteudo: str, fonte: str = "csv") -> list[Produto]:
    """Importa produtos de CSV/TSV colado ou lido de arquivo. Cabeçalho é flexível."""
    texto = conteudo.strip()
    if not texto:
        return []
    delimitador = "\t" if "\t" in texto.splitlines()[0] else (";" if ";" in texto.splitlines()[0] else ",")
    leitor = csv.DictReader(io.StringIO(texto), delimiter=delimitador)
    produtos: list[Produto] = []
    for linha in leitor:
        dados: dict[str, Any] = {}
        for chave, valor in linha.items():
            campo = _chave(chave or "")
            if campo:
                dados[campo] = valor
        nome = (dados.get("nome") or "").strip()
        if not nome:
            continue
        produtos.append(Produto(
            nome=nome,
            fonte=fonte,
            url=dados.get("url"),
            custo=_numero(dados.get("custo")),
            preco=_numero(dados.get("preco")),
            categoria=dados.get("categoria"),
            peso_kg=_numero(dados.get("peso_kg")),
            altura_cm=_numero(dados.get("altura_cm")),
            largura_cm=_numero(dados.get("largura_cm")),
            comprimento_cm=_numero(dados.get("comprimento_cm")),
            estoque=int(_numero(dados.get("estoque")) or 0) if dados.get("estoque") else None,
            fornecedor=dados.get("fornecedor"),
        ))
    return produtos


def importar_urls(urls: Iterable[str], fonte: str = "url informada") -> list[Produto]:
    """Transforma URLs fornecidas pelo usuário em itens de análise."""
    produtos = []
    for url in urls:
        limpa = (url or "").strip()
        if not limpa.startswith("http"):
            continue
        produtos.append(Produto(nome=_nome_pela_url(limpa), fonte=fonte, url=limpa,
                                lacunas=["custo", "preco", "estoque", "peso_kg"]))
    return produtos


def deduplicar(produtos: Iterable[Produto]) -> list[Produto]:
    """Remove repetidos por URL e, sem URL, por nome."""
    vistos: set[str] = set()
    saida: list[Produto] = []
    for p in produtos:
        chave = p.url or _sem_acento(p.nome)
        if chave in vistos:
            continue
        vistos.add(chave)
        saida.append(p)
    return saida


def filtrar(produtos: Iterable[Produto], *,
            categoria: str | None = None,
            preco_min: float | None = None,
            preco_max: float | None = None,
            custo_max: float | None = None,
            peso_max_kg: float | None = None,
            apenas_com_preco: bool = False,
            fornecedor: str | None = None) -> list[Produto]:
    """Aplica filtros. Item sem o dado pedido é descartado, não presumido."""
    alvo_cat = _sem_acento(categoria) if categoria else None
    alvo_forn = _sem_acento(fornecedor) if fornecedor else None
    saida = []
    for p in produtos:
        if apenas_com_preco and p.preco is None:
            continue
        if alvo_cat and (not p.categoria or alvo_cat not in _sem_acento(p.categoria)):
            continue
        if alvo_forn and (not p.fornecedor or alvo_forn not in _sem_acento(p.fornecedor)):
            continue
        if preco_min is not None and (p.preco is None or p.preco < preco_min):
            continue
        if preco_max is not None and (p.preco is None or p.preco > preco_max):
            continue
        if custo_max is not None and (p.custo is None or p.custo > custo_max):
            continue
        if peso_max_kg is not None and (p.peso_kg is None or p.peso_kg > peso_max_kg):
            continue
        saida.append(p)
    return saida


def resumo(produtos: Iterable[Produto]) -> dict:
    """Quantos produtos, quantos com preço, e quais dados faltam na base."""
    lista = list(produtos)
    faltando: dict[str, int] = {}
    for p in lista:
        for campo in p.para_dict()["lacunas"]:
            faltando[campo] = faltando.get(campo, 0) + 1
    return {
        "total": len(lista),
        "com_preco": sum(1 for p in lista if p.preco is not None),
        "com_custo": sum(1 for p in lista if p.custo is not None),
        "fontes": sorted({p.fonte for p in lista if p.fonte}),
        "lacunas": dict(sorted(faltando.items(), key=lambda kv: -kv[1])),
    }
