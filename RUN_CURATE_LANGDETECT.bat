@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (set "PYTHON=.venv\Scripts\python.exe") else (set "PYTHON=python")
%PYTHON% --version >nul 2>&1
if errorlevel 1 (echo ERROR: Python not available & pause & exit /b 1)
echo MeAJOR v4: CURATE_LANGDETECT
%PYTHON% "scripts/curate_meajor.py" ^
  --label 1 ^
  --input ^
  "data/meajor_cleaned_preprocessed.csv" ^
  --output-dir ^
  "outputs/quality_langdetect_label1" ^
  --provider ^
  langdetect
set "CODE=%ERRORLEVEL%"
if not "%CODE%"=="0" echo ERROR: operation failed; retry with unchanged arguments to resume
pause
exit /b %CODE%
