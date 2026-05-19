"""Render a one-page lead report PDF from a view dict.

The view dict is the contract — see tests/fixtures/sample_lead_data.json
for the canonical shape. Truth-first: every value the caller hands us is
passed through to the template; missing values stay missing and render as
"Unavailable" rather than zero/placeholder.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

from api.services.chart_renderer import render_dimensions_bar

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
_TEMPLATE_NAME = "lead_report.html"

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
    keep_trailing_newline=False,
)


def render_pdf(view: dict[str, Any], *, installer: dict[str, Any] | None = None) -> bytes:
    """Render the view dict to PDF bytes using WeasyPrint.

    `installer` overrides white-label fields: {name, logo_data_uri}.
    Pass logo as a data URI so the PDF is self-contained (no outbound
    fetch during render).
    """
    installer = installer or {}
    chart_b64 = render_dimensions_bar(view.get("dimensions", []))
    context = {
        **view,
        "chart_png_b64": chart_b64,
        "installer_name": installer.get("name") or view.get("installer_name") or "Solar Installer",
        "installer_logo_data_uri": installer.get("logo_data_uri") or view.get("installer_logo_data_uri"),
        "map_data_uri": view.get("map_data_uri"),
        "generated_at": view.get("generated_at") or dt.date.today().isoformat(),
        "roof": view.get("roof") or {},
        "financial": view.get("financial") or {},
        "data_sources": view.get("data_sources") or [],
    }
    html_str = _env.get_template(_TEMPLATE_NAME).render(**context)
    return HTML(string=html_str, base_url=str(_TEMPLATE_DIR)).write_pdf()


def render_html(view: dict[str, Any], *, installer: dict[str, Any] | None = None) -> str:
    """Same as render_pdf but returns the HTML string — used by tests that
    assert against the pre-PDF render (e.g. logo swap)."""
    installer = installer or {}
    chart_b64 = render_dimensions_bar(view.get("dimensions", []))
    context = {
        **view,
        "chart_png_b64": chart_b64,
        "installer_name": installer.get("name") or view.get("installer_name") or "Solar Installer",
        "installer_logo_data_uri": installer.get("logo_data_uri") or view.get("installer_logo_data_uri"),
        "map_data_uri": view.get("map_data_uri"),
        "generated_at": view.get("generated_at") or dt.date.today().isoformat(),
        "roof": view.get("roof") or {},
        "financial": view.get("financial") or {},
        "data_sources": view.get("data_sources") or [],
    }
    return _env.get_template(_TEMPLATE_NAME).render(**context)
