# E-COMMERCE AI EMPIRE - inicializador para Windows (PowerShell)
# Uso: clique com o botao direito > "Executar com PowerShell"
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

if (-not (Test-Path ".venv")) {
    Write-Host "Criando ambiente virtual..." -ForegroundColor Cyan
    python -m venv .venv
}

Write-Host "Ativando ambiente e instalando dependencias..." -ForegroundColor Cyan
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet

Write-Host "Abrindo o painel em http://localhost:8501" -ForegroundColor Green
& ".\.venv\Scripts\python.exe" -m streamlit run dashboard/streamlit_app.py
