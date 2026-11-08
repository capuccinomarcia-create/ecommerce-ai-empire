"""Testes da viabilidade de entrega (prazo do canal x prazo do fornecedor)."""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from analytics.fulfillment import (MODO_RETIRADA_MESMO_DIA, VEREDITO_FORA, VEREDITO_INDEFINIDO,
                                   VEREDITO_LIMITE, VEREDITO_OK, ChannelDeadline,
                                   add_business_days, best_option, evaluate_supplier,
                                   rank_suppliers)

SEGUNDA = date(2026, 11, 9)   # segunda-feira
SEXTA = date(2026, 11, 13)


def fornecedor(**kwargs):
    base = {
        "name": "Fornecedor Teste",
        "unit_price": 10.0,
        "shipping_cost": 20.0,
        "min_qty": 1,
        "lead_time_days": 0,
        "pickup_available": False,
        "same_day_pickup": False,
    }
    base.update(kwargs)
    return base


def test_add_business_days_pula_fim_de_semana():
    assert add_business_days(SEXTA, 1) == date(2026, 11, 16)  # sexta + 1 = segunda
    assert add_business_days(SEGUNDA, 5) == date(2026, 11, 16)  # uma semana útil
    assert add_business_days(SEGUNDA, 0) == SEGUNDA


def test_entrega_folgado_quando_prazo_maior_que_lead_time():
    prazo = ChannelDeadline("shopee", "Shopee", handling_days=3)
    v = evaluate_supplier(fornecedor(lead_time_days=1), prazo, today=SEGUNDA)
    assert v.on_time is True
    assert v.slack_days == 2
    assert v.verdict == VEREDITO_OK
    assert v.dispatch_date == date(2026, 11, 10)


def test_no_limite_do_prazo_avisa_falta_de_folga():
    prazo = ChannelDeadline("shopee", "Shopee", handling_days=3)
    v = evaluate_supplier(fornecedor(lead_time_days=3), prazo, today=SEGUNDA)
    assert v.on_time is True
    assert v.verdict == VEREDITO_LIMITE
    assert any("folga" in r.lower() for r in v.risks)


def test_perde_o_prazo_quando_lead_time_estoura():
    prazo = ChannelDeadline("shopee", "Shopee", handling_days=3)
    v = evaluate_supplier(fornecedor(lead_time_days=5), prazo, today=SEGUNDA)
    assert v.on_time is False
    assert v.verdict == VEREDITO_FORA
    assert v.slack_days == -2


def test_retirada_no_mesmo_dia_despacha_hoje():
    prazo = ChannelDeadline("shopee", "Shopee", handling_days=1)
    v = evaluate_supplier(
        fornecedor(lead_time_days=10, pickup_available=True, same_day_pickup=True),
        prazo, today=SEGUNDA,
    )
    assert v.mode == MODO_RETIRADA_MESMO_DIA
    assert v.days_to_dispatch == 0
    assert v.dispatch_date == SEGUNDA
    assert v.on_time is True


def test_prazo_nao_informado_nao_vira_chute():
    prazo = ChannelDeadline("shopee", "Shopee", handling_days=0)
    v = evaluate_supplier(fornecedor(lead_time_days=1), prazo, today=SEGUNDA)
    assert v.verdict == VEREDITO_INDEFINIDO
    assert v.on_time is None
    assert any("não informado" in r.lower() for r in v.risks)


def test_ranking_coloca_quem_entrega_primeiro_e_mais_barato():
    prazo = ChannelDeadline("shopee", "Shopee", handling_days=3)
    lista = [
        fornecedor(name="Caro e rapido", unit_price=30, lead_time_days=1),
        fornecedor(name="Barato e lento", unit_price=5, lead_time_days=10),
        fornecedor(name="Barato e rapido", unit_price=12, lead_time_days=2),
    ]
    ranking = rank_suppliers(lista, prazo, quantity=1, today=SEGUNDA)
    assert [v.supplier for v in ranking] == ["Barato e rapido", "Caro e rapido", "Barato e lento"]
    assert best_option(lista, prazo, 1, SEGUNDA).supplier == "Barato e rapido"


def test_custo_por_unidade_usa_quantidade_minima():
    prazo = ChannelDeadline("shopee", "Shopee", handling_days=3)
    v = evaluate_supplier(
        fornecedor(unit_price=10, shipping_cost=30, min_qty=10), prazo, quantity=2, today=SEGUNDA
    )
    assert v.quantity == 10            # quantidade mínima manda
    assert v.total_cost == pytest.approx(130.0)
    assert v.landed_unit_cost == pytest.approx(13.0)


def test_migracao_adiciona_colunas_novo_em_banco_antigo(tmp_path):
    """Banco criado antes da versão nova precisa ganhar as colunas, sem perder dados."""
    caminho = tmp_path / "antigo.db"
    conn = sqlite3.connect(caminho)
    conn.executescript(
        """
        CREATE TABLE suppliers (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, contact TEXT, url TEXT,
          min_qty INTEGER NOT NULL DEFAULT 1, unit_price REAL NOT NULL DEFAULT 0,
          lead_time_days INTEGER NOT NULL DEFAULT 0,
          shipping_cost REAL NOT NULL DEFAULT 0, notes TEXT, risk_notes TEXT,
          is_demo INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
        );
        INSERT INTO suppliers (id, name, unit_price, created_at)
        VALUES ('s1', 'Fornecedor antigo', 9.9, '2026-01-01');
        """
    )
    conn.commit()
    conn.close()

    from database.repository import SQLiteRepository

    repo = SQLiteRepository(caminho)
    colunas = repo.columns("suppliers")
    assert {"pickup_available", "same_day_pickup", "city", "state"} <= colunas
    antigo = repo.find_one("suppliers", {"id": "s1"})
    assert antigo["name"] == "Fornecedor antigo"
    assert antigo["pickup_available"] in (0, False)
    assert {"handling_days", "delivery_days", "sla_source"} <= repo.columns("marketplaces")
    repo.close()
