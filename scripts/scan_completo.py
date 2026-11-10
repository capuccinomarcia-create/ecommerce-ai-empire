"""Varre a vitrine de mais vendidos do fornecedor e guarda preço, desconto e nota.

Cada página da vitrine traz 30 produtos com preço no HTML, então 75 páginas
cobrem mais de 2 mil itens com uma leitura por página (não uma por produto).
A posição na lista é o sinal de venda do próprio fornecedor.
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from analytics import fees

RAIZ = Path(__file__).resolve().parent.parent
SAIDA_DADOS = RAIZ / "data" / "scan_completo.json"
SAIDA_APP = RAIZ / "docs" / "app" / "scan_completo.json"
BASE = "https://www.feiradamadrugadasp.com.br/mais-vendidos"
LEITOR = "https://r.jina.ai/"
PAUSA = 3.4


def ler(url: str, tentativas: int = 3) -> str:
    for n in range(tentativas):
        req = urllib.request.Request(LEITOR + url, headers={"x-return-format": "html"})
        try:
            return urllib.request.urlopen(req, timeout=90).read().decode("utf-8", "replace")
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            if n == tentativas - 1:
                raise
            print(f"  retry {n + 1} ({exc})", flush=True)
            time.sleep(6 * (n + 1))
    return ""


def numero(txt: str) -> float:
    return float(txt.replace(".", "").replace(",", ".").replace("\u00a0", ""))


def pagina(html: str, posicao_inicial: int) -> list[dict]:
    itens: list[dict] = []
    blocos = html.split('<article class="product-miniature')[1:]
    for i, bloco in enumerate(blocos):
        b = re.sub(r"\s+", " ", bloco)
        url = re.search(r'href="(https://www\.feiradamadrugadasp\.com\.br/[^"#]+/p)', b)
        nome = re.search(r'product-title">\s*<a[^>]*>(.*?)</a>', b)
        if not url or not nome:
            continue
        atual = re.search(r'current-price[^>]*>.*?R\$&#160;([\d\.,]+)', b)
        regular = re.search(r'regular-price[^>]*>R\$&#160;([\d\.,]+)', b)
        nota = re.search(r'rating-value">([\d\.]+)<', b)
        cat = re.search(r'product-category-name[^>]*>([^<]+)<', b)
        img = re.search(r'(https://cdn\.feiradamadrugadasp\.com\.br/img/[^" ]+-home_default\.jpg)', b)
        if not atual:
            continue
        preco = numero(atual.group(1))
        de = numero(regular.group(1)) if regular else None
        item = {
            "posicao": posicao_inicial + i,
            "nome": re.sub(r"\s+", " ", nome.group(1)).strip(),
            "url": url.group(1),
            "categoria": (cat.group(1).strip() if cat else ""),
            "nota": float(nota.group(1)) if nota else None,
            "preco": preco,
            "preco_de": de,
            "desconto": round((1 - preco / de) * 100, 1) if de and de > preco else None,
            "imagem": img.group(1) if img else None,
        }
        item["minimo_30"] = {
            canal: round(fees.preco_para_margem(canal, preco, 30.0), 2) for canal in fees.CANAIS
        }
        itens.append(item)
    return itens


def main(paginas: int = 75, inicio: int = 1) -> None:
    existente: dict[str, dict] = {}
    if SAIDA_DADOS.exists() and inicio > 1:
        for i in json.loads(SAIDA_DADOS.read_text(encoding="utf-8"))["itens"]:
            existente[i["url"]] = i
    itens = list(existente.values())
    vistos = set(existente)

    for p in range(inicio, inicio + paginas):
        try:
            html = ler(f"{BASE}?page={p}")
        except Exception as exc:  # noqa: BLE001
            print(f"página {p}: falhou ({exc})", flush=True)
            break
        novos = pagina(html, (p - 1) * 30 + 1)
        if not novos:
            print(f"página {p}: sem produtos, encerrando", flush=True)
            break
        add = 0
        for item in novos:
            if item["url"] in vistos:
                continue
            vistos.add(item["url"])
            itens.append(item)
            add += 1
        print(f"página {p}: {len(novos)} lidos, {add} novos, total {len(itens)}", flush=True)
        pacote = {
            "gerado_em": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "fonte": BASE,
            "metodo": "vitrine com preço no HTML, lida via r.jina.ai (1 leitura por página de 30 itens)",
            "observacao": "posição = ordem de mais vendidos do fornecedor; vendidos exatos só nos itens da aba Ranking",
            "total": len(itens),
            "itens": itens,
        }
        SAIDA_DADOS.parent.mkdir(parents=True, exist_ok=True)
        SAIDA_DADOS.write_text(json.dumps(pacote, ensure_ascii=False), encoding="utf-8")
        SAIDA_APP.parent.mkdir(parents=True, exist_ok=True)
        SAIDA_APP.write_text(json.dumps(pacote, ensure_ascii=False), encoding="utf-8")
        time.sleep(PAUSA)

    print(f"FIM: {len(itens)} produtos salvos", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 75,
         int(sys.argv[2]) if len(sys.argv) > 2 else 1)
