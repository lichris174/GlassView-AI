$ErrorActionPreference = "Stop"

# dev.ps1 - run the GlassView AI backend (FastAPI) on http://127.0.0.1:8765.
# Run setup.ps1 once first. Requires Ollama running with a vision model.

$root = $PSScriptRoot
Set-Location $root

& ".\.venv\Scripts\python.exe" -m uvicorn glassview_ai.main:app `
    --host 127.0.0.1 --port 8765 --reload
