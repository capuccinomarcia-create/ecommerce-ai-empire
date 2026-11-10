"""Garante que todo botão do app aponta para uma função que existe.

O bug real que motivou este teste: o app tinha dois `window.EMF = { ... }` e o
segundo apagava os métodos do primeiro, deixando seis botões mudos.
"""
from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "docs" / "app" / "index.html"


def _js() -> str:
    html = APP.read_text(encoding="utf-8")
    return re.search(r"<script>([\s\S]*)</script>", html).group(1)


def test_todo_handler_emf_existe():
    js = _js()
    usados = set(re.findall(r"EMF\.([A-Za-z0-9_]+)\s*\(", js))
    definidos = set(re.findall(r"^\s{4}([A-Za-z0-9_]+)\s*:\s*function", js, re.M))
    definidos |= set(re.findall(r"EMPIRE\.([A-Za-z0-9_]+)\s*=", js))
    faltando = sorted(usados - definidos)
    assert not faltando, f"botões sem função: {faltando}"


def test_emf_nao_e_sobrescrito():
    js = _js()
    atribuicoes = js.count("window.EMF = {")
    assert atribuicoes <= 1, "use Object.assign para somar métodos ao EMF, não reatribua"
    if "Object.assign(window.EMF" in js:
        assert atribuicoes == 1


def test_abas_tem_tela():
    js = _js()
    bloco = js[js.find("var ABAS"): js.find("var ABAS") + 600]
    abas = re.findall(r'\["([a-z]+)","[^"]+"\]', bloco)
    for aba in abas:
        # a última aba do encadeamento é o else final, sem comparação
        if aba == abas[-1]:
            continue
        assert f'aba==="{aba}" ?' in js, f"aba {aba} sem tela no render"
