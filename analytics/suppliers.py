"""Central de fornecedores: cadastro, busca e comparação com link direto.

REGRA: este módulo não inventa fornecedor, link, preço ou estoque. Cada registro
carrega `fonte`, `coletado_em` e a lista `lacunas` com o que não foi confirmado.
Campo desconhecido é `None` e aparece como "não informado" na saída, nunca como 0.

Fonte dos dados: data/fornecedores_fmsp.json (catálogo real da Feira da Madrugada SP,
com 2.189 produtos; 10 com preço por faixa confirmado na página do produto).
"""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path

ARQUIVO_PADRAO = Path(__file__).resolve().parent.parent / "data" / "fornecedores_fmsp.json"

# campos que, quando ausentes, impedem uma decisão de compra segura
CAMPOS_CRITICOS = ("preco_1un", "estoque", "frete", "prazo_despacho")


class FornecedorIndisponivel(RuntimeError):
    """Quando o arquivo de fornecedores não existe."""


def _sem_acento(texto: str) -> str:
    normal = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in normal if unicodedata.category(c) != "Mn").lower()


@dataclass
class ItemFornecedor:
    fornecedor: str
    produto: str
    url: str
    preco_1un: float | None
    quantidade_minima: int | None
    faixas: list[dict]
    estoque: int | None
    frete: float | None
    prazo_despacho: int | None
    localizacao: str
    fonte: str
    coletado_em: str
    imagem: str | None = None
    vendidos: int | None = None
    nota: float | None = None
    preco_confirmado: bool = False
    lacunas: tuple[str, ...] = ()
    bruto: dict | None = None

    @property
    def preco_por_quantidade(self) -> dict[int, float]:
        return {int(f["minimo"]): float(f["preco_unidade"]) for f in self.faixas}

    def preco_para(self, quantidade: int) -> float | None:
        """Preço unitário na menor faixa que cobre a quantidade pedida."""
        if not self.faixas:
            return self.preco_1un
        aplicavel = [f for f in self.faixas if int(f["minimo"]) <= quantidade]
        if not aplicavel:
            return self.preco_1un
        melhor = max(aplicavel, key=lambda f: int(f["minimo"]))
        return float(melhor["preco_unidade"])

    def pode_comprar(self, quantidade: int) -> bool:
        if self.estoque is not None and quantidade > self.estoque:
            return False
        return True

    def para_dict(self) -> dict:
        dados = {
            "fornecedor": self.fornecedor,
            "produto": self.produto,
            "url": self.url,
            "preco_1un": self.preco_1un,
            "quantidade_minima": self.quantidade_minima,
            "faixas": self.faixas,
            "estoque": self.estoque,
            "frete": self.frete,
            "prazo_despacho": self.prazo_despacho,
            "localizacao": self.localizacao,
            "fonte": self.fonte,
            "coletado_em": self.coletado_em,
            "imagem": self.imagem,
            "vendidos": self.vendidos,
            "nota": self.nota,
            "preco_confirmado": self.preco_confirmado,
            "lacunas": list(self.lacunas),
        }
        dados["avisos"] = [
            f"{campo} não informado" for campo in CAMPOS_CRITICOS if dados.get(campo) is None
        ]
        return dados


def _faixas_monotonica(faixas: list[dict]) -> list[dict]:
    """Descarta faixa cujo preço unitário sobe em relação à faixa anterior.

    A tabela do fornecedor às vezes repete o preço cheio numa linha de quantidade
    maior; aceitar isso faria o comprador pagar mais comprando mais.
    """
    limpas: list[dict] = []
    melhor = float("inf")
    for faixa in sorted(faixas, key=lambda f: int(f["minimo"])):
        preco = float(faixa["preco_unidade"])
        if preco < melhor:
            melhor = preco
            limpas.append(faixa)
    return limpas


def _item(bruto: dict) -> ItemFornecedor:
    return ItemFornecedor(
        fornecedor=bruto.get("fornecedor", ""),
        produto=bruto.get("produto", ""),
        url=bruto.get("url", ""),
        preco_1un=bruto.get("preco_1un"),
        quantidade_minima=bruto.get("quantidade_minima"),
        faixas=_faixas_monotonica(bruto.get("faixas_quantidade") or []),
        estoque=bruto.get("estoque"),
        frete=bruto.get("frete"),
        prazo_despacho=bruto.get("prazo_despacho"),
        localizacao=bruto.get("localizacao", ""),
        fonte=bruto.get("fonte", ""),
        coletado_em=bruto.get("coletado_em", ""),
        imagem=bruto.get("imagem"),
        vendidos=bruto.get("vendidos"),
        nota=bruto.get("nota"),
        preco_confirmado=bool(bruto.get("preco_confirmado")),
        lacunas=tuple(bruto.get("lacunas") or ()),
        bruto=bruto,
    )


def carregar(caminho: Path | str | None = None) -> list[ItemFornecedor]:
    """Carrega a central de fornecedores do arquivo JSON."""
    arquivo = Path(caminho) if caminho else ARQUIVO_PADRAO
    if not arquivo.exists():
        raise FornecedorIndisponivel(f"arquivo de fornecedores não encontrado: {arquivo}")
    dados = json.loads(arquivo.read_text(encoding="utf-8"))
    return [_item(i) for i in dados.get("itens", [])]


def meta(caminho: Path | str | None = None) -> dict:
    """Resumo do arquivo: total, quantos têm preço confirmado e a data da coleta."""
    arquivo = Path(caminho) if caminho else ARQUIVO_PADRAO
    if not arquivo.exists():
        raise FornecedorIndisponivel(f"arquivo de fornecedores não encontrado: {arquivo}")
    dados = json.loads(arquivo.read_text(encoding="utf-8"))
    return {
        "total": dados.get("total", len(dados.get("itens", []))),
        "com_preco_confirmado": dados.get("com_preco_confirmado"),
        "coletado_em": dados.get("coletado_em"),
        "observacao": dados.get("observacao", ""),
    }


def buscar(termo: str, limite: int = 20, apenas_com_preco: bool = False,
           caminho: Path | str | None = None) -> list[ItemFornecedor]:
    """Busca por nome do produto, ignorando acento e maiúscula."""
    alvo = _sem_acento(termo or "").strip()
    if not alvo:
        return []
    achados = []
    for item in carregar(caminho):
        if apenas_com_preco and not item.preco_confirmado:
            continue
        if alvo in _sem_acento(item.produto):
            achados.append(item)
            if len(achados) >= limite:
                break
    return achados


def melhor_oferta(termo: str, quantidade: int = 1,
                  caminho: Path | str | None = None) -> dict | None:
    """Compara fornecedores para o mesmo termo e devolve a oferta mais barata.

    Só considera itens com preço confirmado; o resto entra como pendência.
    """
    candidatos = buscar(termo, limite=200, caminho=caminho)
    com_preco = [c for c in candidatos if c.preco_confirmado and c.preco_1un]
    sem_preco = [c for c in candidatos if not c.preco_confirmado]
    if not com_preco:
        if not candidatos:
            return None
        return {
            "termo": termo,
            "oferta": None,
            "motivo": "produto encontrado, mas nenhum fornecedor com preço confirmado",
            "pendencias": [c.para_dict() for c in sem_preco[:5]],
        }
    melhor = min(com_preco, key=lambda c: c.preco_para(quantidade) or c.preco_1un)
    return {
        "termo": termo,
        "oferta": {
            "fornecedor": melhor.fornecedor,
            "produto": melhor.produto,
            "url": melhor.url,
            "preco_unitario": melhor.preco_para(quantidade),
            "quantidade": quantidade,
            "coletado_em": melhor.coletado_em,
            "avisos": melhor.para_dict()["avisos"],
        },
        "alternativas": [
            {"fornecedor": c.fornecedor, "preco_unitario": c.preco_para(quantidade), "url": c.url}
            for c in com_preco
            if c is not melhor
        ][:5],
    }


def comparar(termos: list[str], quantidade: int = 1,
             caminho: Path | str | None = None) -> list[dict]:
    """Compara vários produtos de uma vez, para o painel."""
    return [melhor_oferta(t, quantidade, caminho) for t in termos]


def abrir_fornecedor(url: str) -> dict:
    """Devolve o comando de abertura do link direto, sem inventar URL."""
    if not url or not url.startswith("http"):
        raise ValueError("link inválido para abrir fornecedor")
    return {"link_direto": url, "abrir_url": url, "instrucao": "Clique para abrir a página exata do produto no fornecedor"}
