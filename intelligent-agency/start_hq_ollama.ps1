$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

$env:AGENCY_LLM = "router"
$env:AGENCY_LLM_BASE_URL = "http://127.0.0.1:11434/v1"
$env:AGENCY_LLM_API_KEY = "ollama"
$env:AGENCY_OLLAMA_MODEL = "qwen2.5:3b"

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Host "Python virtual environment not found."
    exit 1
}

Write-Host "Starting Polymath HQ with Ollama (qwen2.5:3b)..."

& ".\.venv\Scripts\python.exe" "webapp.py"

