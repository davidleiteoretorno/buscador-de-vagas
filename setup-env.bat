@echo off
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
    py -m venv venv
    if errorlevel 1 exit /b 1
)
"venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
"venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 exit /b 1
echo Configure o arquivo .env e execute: venv\Scripts\streamlit run painel.py
