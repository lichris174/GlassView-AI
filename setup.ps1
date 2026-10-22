param(
    # Also install the ML pipeline extras (requirements-ml.txt) and Playwright's Chromium.
    [switch]$ML
)

$ErrorActionPreference = "Stop"

# setup.ps1 - one-time dependency install for GlassView.
#
#   ./setup.ps1        backend + dev tools (pytest, ruff, mypy)
#   ./setup.ps1 -ML    also the ml/ pipeline extras (capture, synth, Playwright)
#
# Prerequisites:
#   - Python 3.11+
#   - Optional: Ollama (https://ollama.com) with a vision model for local answers:
#       ollama pull qwen3-vl:8b
#     Without it the backend still starts (health = degraded) and cloud providers work.

$root = $PSScriptRoot
Set-Location $root

$py = ".\.venv\Scripts\python.exe"

Write-Host "==> Creating Python venv + installing backend deps..." -ForegroundColor Cyan
if (-not (Test-Path ".venv")) { python -m venv .venv }
& $py -m pip install --upgrade pip
& $py -m pip install -r requirements-dev.txt

if ($ML) {
    Write-Host "==> Installing ML extras + Playwright Chromium..." -ForegroundColor Cyan
    & $py -m pip install -r requirements-ml.txt
    & $py -m playwright install chromium
}

Write-Host "==> Done. Start the API with:  .\dev.ps1" -ForegroundColor Green
Write-Host "    Desktop app:  cd apps\desktop; npm ci; npm run tauri dev" -ForegroundColor Green
