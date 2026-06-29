@echo off
title AgriTwin — Start All Services
echo.
echo  Starting AgriTwin Services...
echo  ================================
echo.

:: Backend FastAPI — port 8000
echo  [1/3] Starting FastAPI Backend  ^(port 8000^)...
start "AgriTwin Backend" cmd /k "cd /d D:\BOT\AGRICULTURE && python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000"

timeout /t 2 /nobreak >nul

:: Frontend Next.js — port 3000
echo  [2/3] Starting Next.js Frontend ^(port 3000^)...
start "AgriTwin Frontend" cmd /k "cd /d D:\BOT\AGRICULTURE\frontend && npm run dev"

timeout /t 2 /nobreak >nul

:: Streamlit Legacy — port 8501
echo  [3/3] Starting Streamlit Legacy ^(port 8501^)...
start "AgriTwin Streamlit" cmd /k "cd /d D:\BOT\AGRICULTURE && streamlit run tumbal.py --server.port 8501"

echo.
echo  ================================
echo  Services started! Open browser:
echo.
echo    Dashboard  : http://localhost:3000
echo    API Docs   : http://localhost:8000/docs
echo    Streamlit  : http://localhost:8501
echo.
echo  Close this window anytime.
pause
