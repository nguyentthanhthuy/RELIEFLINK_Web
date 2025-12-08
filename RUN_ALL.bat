@echo off
echo ========================================================
echo         RELIEFLINK CHATBOT SYSTEM LAUNCHER
echo ========================================================
echo.

echo 1. Starting AI Service (Port 8000)...
start "AI Service (FastAPI)" cmd /k "cd ai-service && if not exist venv (py -3.10 -m venv venv) && call venv\Scripts\activate && pip install -r requirements.txt >nul 2>&1 && python main.py"

timeout /t 5 /nobreak >nul

echo 2. Starting Rasa Action Server (Port 5055)...
start "Rasa Action Server" cmd /k "cd chatbot && call venv\Scripts\activate && rasa run actions"

timeout /t 5 /nobreak >nul

echo 3. Starting Rasa Chat Interface...
echo.
echo    System is ready! You can chat below.
echo    To stop, just close these windows.
echo.
cd chatbot
call venv\Scripts\activate
rasa shell
