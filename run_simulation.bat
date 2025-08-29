@echo off
REM WePlan Inactivity Simulator - Complete Pipeline (Windows)

echo ========================================
echo WePlan Inactivity Simulator Pipeline
echo ========================================
echo.

REM Set default config file (now in config folder)
set CONFIG_FILE=%1
if "%CONFIG_FILE%"=="" set CONFIG_FILE=config\PUconfig.yaml

echo Using config file: %CONFIG_FILE%
echo Working directory: %CD%

REM Check if config file exists
if not exist "%CONFIG_FILE%" (
    echo ❌ Error: Config file '%CONFIG_FILE%' not found!
    echo Available config files:
    dir config\*.yaml /B 2>nul
    pause
    exit /b 1
)

REM Check if virtual environment exists
if not exist "venv" (
    echo ❌ Error: Virtual environment 'venv' not found!
    echo Please create it with: python -m venv venv ^&^& venv\Scripts\activate ^&^& pip install pandas openpyxl pyyaml python-dateutil numpy
    pause
    exit /b 1
)

REM Activate virtual environment
echo 📦 Activating virtual environment...
call venv\Scripts\activate

REM Run the simulation
echo.
echo 🚀 Running inactivity simulation...
python scripts\inactivity_simulator_cleaned.py

if %ERRORLEVEL% neq 0 (
    echo ❌ Simulation failed!
    pause
    exit /b 1
)

REM Run analysis
echo.
echo 📊 Running percentage analysis...
python scripts\percentage_analysis.py "%CONFIG_FILE%"

if %ERRORLEVEL% neq 0 (
    echo ❌ Analysis failed!
    pause
    exit /b 1
)

echo.
echo ========================================
echo ✅ Pipeline completed successfully!
echo ========================================
echo.
echo Generated files:
echo 📋 Assignments: outputs\simulated_cdb_upload.xlsx
echo 📈 Monthly Summary: outputs\simulated_monthly_summary.xlsx
echo 📊 Analysis Report: outputs\percentage_analysis_report.xlsx
echo.
echo Usage for different configs:
echo   run_simulation.bat                           # Uses config\PUconfig.yaml (default)
echo   run_simulation.bat config\FAconfig.yaml     # Uses FAconfig.yaml
echo   run_simulation.bat config\myconfig.yaml     # Uses custom config
echo.
pause