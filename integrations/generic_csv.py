"""Importação/exportação em CSV - o caminho que funciona sem nenhuma API."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterable

from core.utils import new_id, now_iso

# Colunas aceitas por template. Sinônimos são normalizados.
TEMPLATES: dict[str, dict[str, list[str]]] = {
    "products": {
        "required": ["name"],
        "optional": ["sku", "category", "description", "purchase_price", "extra_cost",
                      "sale_price", "marketplace", "status", "supplier"],
        "aliases": {
            "nome": "name", "produto": "name", "titulo": "name",
            "categoria": "category", "descricao": "description",
            "preco_compra": "purchase_price", "custo": "purchase_price",
            "custo_extra": "extra_cost", "preco_venda": "sale_price", "preco": "sale_price",
            "canal": "marketplace",
        },
    },
    "competitors": {
        "required": ["name", "price"],
        "optional": ["product_name", "marketplace", "url", "rating", "reviews", "differentials"],
        "aliases": {
            "nome": "name", "concorrente": "name", "produto": "product_name",
            "preco": "price", "canal": "marketplace", "link": "url",
            "avaliacao": "rating", "avaliacoes": "reviews", "diferenciais": "differentials",
        },
    },
    "suppliers": {
        "required": ["name", "unit_price"],
        "optional": ["contact", "url", "min_qty", "lead_time_days", "shipping_cost", "notes"],
        "aliases": {
            "fornecedor": "name", "nome": "name", "contato": "contact", "link": "url",
            "quantidade_minima": "min_qty", "prazo_dias": "lead_time_days",
            "frete": "shipping_cost", "preco_unitario": "unit_price", "observacoes": "notes",
        },
    },
    "sales": {
        "required": ["quantity", "unit_price"],
        "optional": ["product_name", "marketplace", "fees", "shipping", "taxes", "sold_at"],
        "aliases": {
            "quantidade": "quantity", "preco_unitario": "unit_price", "produto": "product_name",
            "canal": "marketplace", "taxas": "fees", "frete": "shipping", "impostos": "taxes",
            "data": "sold_at",
        },
    },
    "opportunities": {
        "required": ["name"],
        "optional": ["category", "marketplace", "price_found", "cost_estimate", "source",
                      "demanda", "concorrencia", "tendencia", "logistica", "trafego"],
        "aliases": {
            "produto": "name", "nome": "name", "categoria": "category", "canal": "marketplace",
            "preco_encontrado": "price_found", "custo_estimado": "cost_estimate",
            "fonte": "source", "procura": "demanda", "concorrentes": "concorrencia",
            "tendencia": "tendencia", "logistica": "logistica", "trafego": "trafego",
        },
    },
}

NUMERIC_FIELDS = {
    "purchase_price", "extra_cost", "sale_price", "price", "rating", "reviews",
    "unit_price", "min_qty", "lead_time_days", "shipping_cost", "quantity", "fees",
    "taxes", "price_found", "cost_estimate", "demanda", "concorrencia", "tendencia",
    "logistica", "trafego",
}


def _normalize_header(header: str) -> str:
    from core.utils import normalize_text

    key = normalize_text(header).strip().replace(" ", "_")
    return key


def _parse_number(value: str) -> float | None:
    raw = (value or "").strip()
    if not raw:
        return None
    raw = raw.replace("R$", "").replace("%", "").strip()
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        raw = raw.replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def read_csv(path: str | Path) -> tuple[list[str], list[dict[str, str]]]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"arquivo não encontrado: {path}")
    raw = path.read_text(encoding="utf-8-sig")
    delimiter = ";" if raw.count(";") > raw.count(",") else ","
    reader = csv.DictReader(raw.splitlines(), delimiter=delimiter)
    rows = [dict(row) for row in reader]
    return list(reader.fieldnames or []), rows


def map_row(row: dict[str, str], entity: str) -> dict[str, Any]:
    template = TEMPLATES[entity]
    aliases = template.get("aliases", {})
    mapped: dict[str, Any] = {}
    for header, value in row.items():
        if header is None:
            continue
        key = _normalize_header(header)
        key = aliases.get(key, key)
        if value is None:
            continue
        value = str(value).strip()
        if value == "":
            continue
        if key in NUMERIC_FIELDS:
            number = _parse_number(value)
            if number is not None:
                mapped[key] = number
            continue
        mapped[key] = value
    return mapped


def import_csv(
    path: str | Path,
    entity: str,
    repo,
    is_demo: bool = False,
    source: str = "csv",
) -> dict[str, Any]:
    """Importa um CSV para a entidade correspondente.

    Retorna um relatório honesto: quantos entraram, quantos foram rejeitados
    e por quê. Nada é "consertado" silenciosamente.
    """
    if entity not in TEMPLATES:
        raise ValueError(f"entidade não suportada: {entity}. Use: {', '.join(TEMPLATES)}")

    template = TEMPLATES[entity]
    headers, rows = read_csv(path)
    imported: list[dict] = []
    errors: list[dict] = []

    if not rows:
        return {"entity": entity, "imported": 0, "skipped": 0, "errors": [
            {"line": 0, "error": "arquivo vazio"}], "rows": []}

    for index, row in enumerate(rows, start=2):  # linha 1 = cabeçalho
        mapped = map_row(row, entity)
        missing = [field for field in template["required"] if not mapped.get(field)]
        if missing:
            errors.append({"line": index, "error": f"campos obrigatórios ausentes: {', '.join(missing)}"})
            continue
        mapped.setdefault("id", new_id(entity[:3]))
        if "created_at" in repo.columns(entity):
            mapped.setdefault("created_at", now_iso())
        if entity == "products" and "supplier" in mapped and "supplier_id" not in mapped:
            mapped.pop("supplier")
        if "is_demo" in repo.columns(entity):
            mapped["is_demo"] = is_demo
        if "source" in repo.columns(entity):
            mapped.setdefault("source", source)
        if entity == "opportunities":
            mapped.setdefault("consulted_at", now_iso())
            # critérios de mercado vão para o JSON 'breakdown', não para colunas fixas
            criteria = {}
            for key in ("demanda", "concorrencia", "tendencia", "logistica", "trafego"):
                if key in mapped:
                    criteria[key] = mapped.pop(key)
            if criteria:
                mapped["breakdown"] = {
                    "criteria": criteria,
                    "sources": {key: f"CSV ({source})" for key in criteria},
                }
        if entity == "competitors":
            mapped.setdefault("collected_at", now_iso())
            mapped.setdefault("source", source)
            product_name = mapped.pop("product_name", "")
            if product_name and not mapped.get("product_id"):
                product = repo.find_one("products", {"name": product_name})
                if not product:
                    errors.append(
                        {"line": index, "error": f"produto não encontrado no catálogo: {product_name}"}
                    )
                    continue
                mapped["product_id"] = product["id"]
        if entity == "sales":
            mapped.setdefault("sold_at", now_iso())
            mapped.setdefault("total",
                              float(mapped.get("quantity", 1)) * float(mapped.get("unit_price", 0)))
        try:
            imported.append(repo.insert(entity, mapped))
        except Exception as exc:  # noqa: BLE001 - reportar, não esconder
            errors.append({"line": index, "error": f"falha ao inserir: {exc}"})

    return {
        "entity": entity,
        "headers": headers,
        "imported": len(imported),
        "skipped": len(errors),
        "errors": errors,
        "rows": imported,
        "is_demo": is_demo,
    }


def export_csv(rows: Iterable[dict], path: str | Path, fields: list[str] | None = None) -> Path:
    rows = list(rows)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return path
    columns = fields or [c for c in rows[0].keys()]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore", delimiter=";")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def template_csv(entity: str, path: str | Path) -> Path:
    """Cria um CSV de exemplo (vazio) com o cabeçalho correto."""
    template = TEMPLATES[entity]
    header = template["required"] + template["optional"]
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(";".join(header) + "\n", encoding="utf-8")
    return path
