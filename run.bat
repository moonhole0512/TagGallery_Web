@echo off
set /p PORT="Enter port number (default 8000): "
if "%PORT%"=="" set PORT=8000

echo Starting FastAPI server on port %PORT%...
uvicorn app:app --reload --port %PORT%
pause
