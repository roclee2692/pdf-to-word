@echo off
REM Windows one-click GUI launcher for PDF-to-Word
cd /d "%~dp0"

if exist ".env" (
  for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    if not "%%A"=="" if not "%%A:~0,1%"=="#" set "%%A=%%B"
  )
)

if not defined PDF2WORD_SOFFICE (
  if exist "C:\Program Files\LibreOffice\program\soffice.exe" set "PDF2WORD_SOFFICE=C:\Program Files\LibreOffice\program\soffice.exe"
  if exist "C:\Program Files (x86)\LibreOffice\program\soffice.exe" set "PDF2WORD_SOFFICE=C:\Program Files (x86)\LibreOffice\program\soffice.exe"
)

if not exist ".venv\Scripts\python.exe" (
  echo .venv not found. Run: python -m venv .venv ^& .venv\Scripts\pip install -r requirements.txt -r requirements-gui.txt ^& .venv\Scripts\pip install -e .
  pause
  exit /b 1
)

set PYTHONPATH=src
if not exist logs mkdir logs
echo ==== %DATE% %TIME% start.bat ====>> logs\start.log
.venv\Scripts\python.exe -m pdf2word gui 2>> logs\start.log
if errorlevel 1 (
  echo GUI failed. See logs\start.log
  pause
  exit /b 1
)
