@echo off
chcp 65001 > nul
set /p PORT="Enter port number (default 8000): "
if "%PORT%"=="" set PORT=8000

echo Starting FastAPI server on port %PORT%...
python -u -m uvicorn app:app --reload --port %PORT%
pause
