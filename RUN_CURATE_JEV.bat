@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (set "PYTHON=.venv\Scripts\python.exe") else (set "PYTHON=python")
%PYTHON% --version >nul 2>&1
if errorlevel 1 (echo ERROR: Python not available & pause & exit /b 1)
if not defined OPENROUTER_API_KEY (echo ERROR: OPENROUTER_API_KEY missing & exit /b 1)
echo MeAJOR v4: CURATE_JEV
%PYTHON% "scripts/curate_meajor.py" ^
  --label 1 ^
  --input ^
  "data/meajor_cleaned_preprocessed.csv" ^
  --output-dir ^
  "outputs/quality_jev_label1" ^
  --provider ^
  openrouter ^
  --model ^
  "typesafe/jev-1.14"
set "CODE=%ERRORLEVEL%"
if not "%CODE%"=="0" echo ERROR: operation failed; retry with unchanged arguments to resume
pause
exit /b %CODE%
