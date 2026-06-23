$ErrorActionPreference = "Stop"

# dev.ps1 — launch GlassView in development.
#
# The Tauri shell owns everything: it runs the Vite UI (beforeDevCommand) and
# spawns the Python AI sidecar. So this is a single command. Run setup.ps1 once
# first to install dependencies.

$root = $PSScriptRoot
Set-Location (Join-Path $root "apps/shell")
cargo tauri dev
