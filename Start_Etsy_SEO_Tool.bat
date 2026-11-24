@echo off
REM Etsy SEO Tool — double-click launcher (Windows).
REM Creates a virtual environment, installs requirements, runs Streamlit.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv .venv
)
call .venv\Scripts\activate.bat
echo Installing requirements...
pip install -q -r requirements.txt
if not exist ".env" (
    echo.
    echo NOTE: copy .env.example to .env and paste your Etsy Keystring
    echo and Shared Secret there before connecting to Etsy.
    echo.
)
echo Starting Etsy SEO Tool at http://localhost:8501 ...
streamlit run app.py
pause
