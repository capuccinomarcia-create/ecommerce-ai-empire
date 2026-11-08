"""Modelos e enumerações do domínio.

Os modelos são deliberadamente leves (dataclasses). A validação de entrada
fica nos módulos de analytics/core, com Pydantic onde há risco numérico.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskStatus(str, Enum):
    PENDENTE = "pendente"
    EM_EXECUCAO = "em_execucao"
    CONCLUIDA = "concluida"
    FALHOU = "falhou"
    AGUARDANDO_APROVACAO = "aguardando_aprovacao"
    CANCELADA = "cancelada"

    @property
    def terminal(self) -> bool:
        return self in {TaskStatus.CONCLUIDA, TaskStatus.FALHOU, TaskStatus.CANCELADA}


class ApprovalStatus(str, Enum):
    PENDENTE = "pendente"
    APROVADO = "aprovado"
    REJEITADO = "rejeitado"
    CANCELADO = "cancelado"
    EXPIRADO = "expirado"


class RiskLevel(str, Enum):
    BAIXO = "baixo"
    MEDIO = "medio"
    ALTO = "alto"
    CRITICO = "critico"


class Marketplace(str, Enum):
    SHOPEE = "shopee"
    MERCADO_LIVRE = "mercadolivre"
    TIKTOK_SHOP = "tiktok_shop"
    INSTAGRAM = "instagram"
    LOJA_PROPRIA = "loja_propria"
    WOOCOMMERCE = "woocommerce"

    @property
    def label(self) -> str:
        return MARKETPLACE_LABELS[self]


MARKETPLACE_LABELS: dict[str, str] = {
    "shopee": "Shopee",
    "mercadolivre": "Mercado Livre",
    "tiktok_shop": "TikTok Shop",
    "instagram": "Instagram",
    "loja_propria": "Loja própria",
    "woocommerce": "WooCommerce",
}


@dataclass
class Agent:
    name: str
    role: str
    description: str = ""
    status: str = "ativo"
    capabilities: list[str] = field(default_factory=list)
    instructions: str = ""
    id: str = ""

    def to_row(self) -> dict[str, Any]:
        import json

        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "description": self.description,
            "status": self.status,
            "capabilities": json.dumps(self.capabilities, ensure_ascii=False),
            "instructions": self.instructions,
        }


@dataclass
class Product:
    name: str
    sku: str = ""
    category: str = ""
    description: str = ""
    purchase_price: float = 0.0
    extra_cost: float = 0.0
    sale_price: float = 0.0
    supplier_id: str = ""
    marketplace: str = ""
    status: str = "ativo"
    source: str = "manual"
    is_demo: bool = False
    id: str = ""


@dataclass
class Approval:
    action: str
    risk_level: str
    resource_type: str = ""
    resource_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    status: str = ApprovalStatus.PENDENTE.value
    requested_by_agent: str = ""
    requested_by: str = ""
    decided_by: str = ""
    decided_at: str = ""
    note: str = ""
    id: str = ""


@dataclass
class Task:
    agent: str
    task_type: str
    title: str
    status: str = TaskStatus.PENDENTE.value
    priority: int = 3
    payload: dict[str, Any] = field(default_factory=dict)
    parent_id: str = ""
    id: str = ""
    attempts: int = 0
    dedupe_key: str = ""
