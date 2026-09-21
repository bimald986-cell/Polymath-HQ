@echo off
cd /d "%~dp0"

echo Setting Ollama backend (gemma2:2b)...
set AGENCY_LLM=openai
set AGENCY_LLM_BASE_URL=http://127.0.0.1:11434/v1
set AGENCY_LLM_API_KEY=ollama
set AGENCY_LLM_MODEL=gemma2:2b

echo Installing deps if needed...
python -m pip install -q -r requirements.txt

echo.
echo Open in browser: http://127.0.0.1:5000
echo Keep this window open. Press Ctrl+C to stop.
echo.
python webapp.py
pause
