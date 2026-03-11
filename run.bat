@echo off
cd /d "%~dp0"

if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

call venv\Scripts\activate.bat
pip install -r requirements.txt -q
echo.
echo System Health Monitor starting at http://127.0.0.1:5000
echo Press Ctrl+C to stop.
echo.
python app.py
pause
