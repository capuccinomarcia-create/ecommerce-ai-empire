"""Página - Mercado Livre."""

from __future__ import annotations

from dashboard.channels import render_channel


def render() -> None:
    render_channel("mercadolivre")
