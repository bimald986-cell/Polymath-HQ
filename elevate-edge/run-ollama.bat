@echo off
cd /d "%~dp0"

echo Elevate Edge — starting with Ollama (gemma2:2b)
set AGENCY_LLM=openai
set AGENCY_LLM_BASE_URL=http://127.0.0.1:11434/v1
set AGENCY_LLM_API_KEY=ollama
set AGENCY_LLM_MODEL=gemma2:2b
set ELEVATE_PORT=8088

python -m pip install -q -r requirements.txt
echo.
echo Open in browser: http://127.0.0.1:8088
echo (Port 5060 is blocked by Chrome — we use 8088)
echo Keep this window open. Ctrl+C to stop.
echo.
python app.py
pause
