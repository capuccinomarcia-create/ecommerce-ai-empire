#!/usr/bin/env bash
# E-COMMERCE AI EMPIRE - inicializador para Linux/macOS
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt --quiet
exec ./.venv/bin/python -m streamlit run dashboard/streamlit_app.py
