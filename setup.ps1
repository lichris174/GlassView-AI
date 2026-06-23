$ErrorActionPreference = "Stop"

# setup.ps1 — one-time dependency install for GlassView.
#
# Prerequisites you must have installed:
#   - Ollama (https://ollama.com) running, with a vision model pulled:
#       ollama pull qwen3-vl:8b
#   - Rust + cargo, and the Tauri CLI:  cargo install tauri-cli
#   - Node.js (>= 18) and Python (>= 3.11)

$root = $PSScriptRoot

Write-Host "==> Installing UI dependencies (npm)..." -ForegroundColor Cyan
Set-Location (Join-Path $root "apps/ui")
npm install

Write-Host "==> Creating Python venv + installing backend deps..." -ForegroundColor Cyan
Set-Location (Join-Path $root "apps/server")
if (-not (Test-Path ".venv")) { python -m venv .venv }
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r requirements-dev.txt

Write-Host "==> Done. Start the app with:  .\dev.ps1" -ForegroundColor Green
Set-Location $root
