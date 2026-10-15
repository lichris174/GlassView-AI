$ErrorActionPreference = "Stop"

# setup.ps1 - one-time dependency install for the GlassView AI backend.
#
# Prerequisites:
#   - Python 3.11+
#   - Ollama (https://ollama.com) running, with a vision model pulled:
#       ollama pull qwen3-vl:8b

$root = $PSScriptRoot
Set-Location $root

Write-Host "==> Creating Python venv + installing backend deps..." -ForegroundColor Cyan
if (-not (Test-Path ".venv")) { python -m venv .venv }
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r requirements-dev.txt

Write-Host "==> Done. Start the API with:  .\dev.ps1" -ForegroundColor Green
