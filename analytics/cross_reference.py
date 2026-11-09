"""Cruza anúncios campeões de venda dos marketplaces com o catálogo do fornecedor.

REGRA DO PROJETO: nada é inventado. Se o item do marketplace não tem preço
capturado, o campo fica ``None`` e o texto diz "não informado". Se o fornecedor
não tem equivalente, o resultado é ``encontrado=False`` com o motivo.

A entrada é uma lista de anúncios capturados (busca do Google, colagem manual ou
API oficial quando existir), cada um com a fonte e a data da coleta.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

CATALOGO_PADRAO = Path("data/fornecedores_fmsp.json")

# palavras que aparecem em quase todo anúncio e não ajudam a identificar o produto
VAZIAS = {
    "de", "da", "do", "para", "com", "e", "em", "no", "na", "por", "the", "kit",
    "unidade", "unidades", "pecas", "peca", "pcs", "infantil", "infantis", "novo",
    "nova", "original", "promocao", "envio", "rapido", "gratis", "pronta",
    "entrega", "pronto", "estoque", "grande", "pequeno", "colorido", "sortido",
    # palavras de categoria que aparecem em milhares de anúncios e criam falso positivo
    "brinquedo", "brinquedos", "educativo", "educativa", "educacional",
    "educacionais", "criativo", "criativa", "didatico", "didatica", "montagem",
    "sortida", "sortidas", "pronta",
}


def _sem_acento(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )


def tokens(texto: str) -> set[str]:
    """Palavras significativas do título, normalizadas."""
    limpo = _sem_acento(str(texto)).lower()
    palavras = re.findall(r"[a-z0-9]+", limpo)
    return {p for p in palavras if len(p) >= 4 and p not in VAZIAS}


@dataclass
class ItemFornecedor:
    nome: str
    link: str
    preco_1un: float | None = None
    categoria: str | None = None
    vendidos: int | None = None
    nota: float | None = None
    referencia: float | None = None


@dataclass
class AnuncioMarketplace:
    canal: str
    titulo: str
    preco: float | None = None
    vendidos: int | None = None
    avaliacoes: int | None = None
    link: str | None = None
    fonte: str = ""
    coletado_em: str = ""


@dataclass
class Cruzamento:
    anuncio: AnuncioMarketplace
    fornecedor: ItemFornecedor | None
    aderencia: float
    motivo: str
    alternativas: list[tuple[ItemFornecedor, float]] = field(default_factory=list)

    @property
    def encontrado(self) -> bool:
        return self.fornecedor is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "canal": self.anuncio.canal,
            "titulo": self.anuncio.titulo,
            "preco": self.anuncio.preco,
            "vendidos": self.anuncio.vendidos,
            "avaliacoes": self.anuncio.avaliacoes,
            "link_marketplace": self.anuncio.link,
            "encontrado_no_fornecedor": self.encontrado,
            "fornecedor_produto": self.fornecedor.nome if self.fornecedor else None,
            "fornecedor_link": self.fornecedor.link if self.fornecedor else None,
            "fornecedor_custo": self.fornecedor.preco_1un if self.fornecedor else None,
            "fornecedor_vendidos": self.fornecedor.vendidos if self.fornecedor else None,
            "fornecedor_nota": self.fornecedor.nota if self.fornecedor else None,
            "aderencia": round(self.aderencia, 2),
            "motivo": self.motivo,
            "alternativas": [
                {"nome": item.nome, "link": item.link, "aderencia": round(nota, 2)}
                for item, nota in self.alternativas
            ],
            "fonte": self.anuncio.fonte,
            "coletado_em": self.anuncio.coletado_em,
        }


def carregar_fornecedor(caminho: str | Path | None = None) -> list[ItemFornecedor]:
    arquivo = Path(caminho or CATALOGO_PADRAO)
    acervo = json.loads(arquivo.read_text(encoding="utf-8"))
    itens: list[ItemFornecedor] = []
    for bruto in acervo.get("itens", []):
        if not (bruto.get("url") or bruto.get("link")):
            continue
        itens.append(
            ItemFornecedor(
                nome=bruto.get("produto") or bruto.get("nome") or "",
                link=bruto.get("url") or bruto.get("link") or "",
                preco_1un=bruto.get("preco_1un"),
                categoria=bruto.get("categoria"),
                vendidos=bruto.get("vendidos"),
                nota=bruto.get("nota"),
                referencia=bruto.get("preco_referencia_varejo"),
            )
        )
    return itens


def aderencia(titulo_marketplace: str, titulo_fornecedor: str) -> float:
    """Quanto do produto do marketplace está coberto pelo título do fornecedor.

    Usa cobertura (interseção sobre os tokens do marketplace), não Jaccard: o
    título do fornecedor costuma trazer mais palavras que o do anúncio.
    """
    alvo = tokens(titulo_marketplace)
    if not alvo:
        return 0.0
    return len(alvo & tokens(titulo_fornecedor)) / len(alvo)


def cruzar(
    anuncios: Iterable[AnuncioMarketplace],
    acervo: list[ItemFornecedor],
    minimo: float = 0.5,
    alternativas: int = 2,
) -> list[Cruzamento]:
    """Para cada anúncio, acha o produto equivalente no fornecedor."""
    resultado: list[Cruzamento] = []
    for anuncio in anuncios:
        notas = sorted(
            ((item, aderencia(anuncio.titulo, item.nome)) for item in acervo),
            key=lambda par: par[1],
            reverse=True,
        )
        boas = [(item, nota) for item, nota in notas[: alternativas + 1] if nota >= minimo]
        if boas:
            melhor, nota = boas[0]
            motivo = (
                f"{nota:.0%} das palavras do anúncio aparecem no produto do fornecedor"
            )
            resultado.append(
                Cruzamento(
                    anuncio=anuncio,
                    fornecedor=melhor,
                    aderencia=nota,
                    motivo=motivo,
                    alternativas=boas[1:],
                )
            )
        else:
            topo = notas[0][1] if notas else 0.0
            resultado.append(
                Cruzamento(
                    anuncio=anuncio,
                    fornecedor=None,
                    aderencia=topo,
                    motivo=(
                        "nenhum produto do fornecedor bate com o anúncio"
                        f" (melhor semelhança {topo:.0%}, mínimo {minimo:.0%})"
                    ),
                )
            )
    return resultado


def carregar_anuncios(caminho: str | Path) -> list[AnuncioMarketplace]:
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    saida: list[AnuncioMarketplace] = []
    for bruto in dados.get("anuncios", []):
        saida.append(
            AnuncioMarketplace(
                canal=bruto["canal"],
                titulo=bruto["titulo"],
                preco=bruto.get("preco"),
                vendidos=bruto.get("vendidos"),
                avaliacoes=bruto.get("avaliacoes"),
                link=bruto.get("link"),
                fonte=bruto.get("fonte") or dados.get("fonte", ""),
                coletado_em=bruto.get("coletado_em") or dados.get("coletado_em", ""),
            )
        )
    return saida


def relatorio_markdown(resultados: list[Cruzamento]) -> str:
    linhas = [
        "# Mais vendidos × fornecedor",
        "",
        "| Plataforma | Anúncio | Preço | Sinal | Fornecedor tem? | Custo | Link |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in resultados:
        sinal = []
        if r.anuncio.vendidos:
            sinal.append(f"{r.anuncio.vendidos} vendidos")
        if r.anuncio.avaliacoes:
            sinal.append(f"{r.anuncio.avaliacoes} avaliações")
        preco = f"R$ {r.anuncio.preco:.2f}" if r.anuncio.preco is not None else "não informado"
        if r.fornecedor:
            tem = f"SIM ({r.aderencia:.0%})"
            nome = r.fornecedor.nome[:48]
            custo = (
                f"R$ {r.fornecedor.preco_1un:.2f}"
                if r.fornecedor.preco_1un is not None
                else "não informado"
            )
            link = r.fornecedor.link
        else:
            tem, nome, custo, link = "NÃO", "—", "—", "—"
        linhas.append(
            f"| {r.anuncio.canal} | {r.anuncio.titulo[:44]} | {preco} | "
            f"{', '.join(sinal) or 'não informado'} | {tem} | {custo} | {link} |"
        )
    return "\n".join(linhas)
