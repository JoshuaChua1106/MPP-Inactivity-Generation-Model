#!/bin/bash

# WePlan Inactivity Simulator - Complete Pipeline
# This script runs the full simulation and analysis pipeline

echo "========================================"
echo "WePlan Inactivity Simulator Pipeline"
echo "========================================"
echo

# Set default config file (now in config folder)
CONFIG_FILE=${1:-"config/PUconfig.yaml"}

echo "Using config file: $CONFIG_FILE"
echo "Working directory: $(pwd)"

# Check if config file exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo "❌ Error: Config file '$CONFIG_FILE' not found!"
    echo "Available config files:"
    ls config/*.yaml 2>/dev/null || echo "No .yaml files found in config/"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "❌ Error: Virtual environment 'venv' not found!"
    echo "Please create it with: python -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# Activate virtual environment
echo "📦 Activating virtual environment..."
source venv/bin/activate

# Check if required files exist
echo "🔍 Checking required files..."
python -c "
import yaml
config = yaml.safe_load(open('$CONFIG_FILE'))
import os
cdb_file = config['cdb_file']
if not os.path.exists(cdb_file):
    print(f'❌ Error: CDB file {cdb_file} not found!')
    exit(1)
print(f'✅ CDB file found: {cdb_file}')
"

if [ $? -ne 0 ]; then
    exit 1
fi

echo

# Run the simulation
echo "🚀 Running inactivity simulation..."
python scripts/inactivity_simulator_cleaned.py

if [ $? -ne 0 ]; then
    echo "❌ Simulation failed!"
    exit 1
fi

echo
echo "📊 Running percentage analysis..."
python scripts/percentage_analysis.py "$CONFIG_FILE"

if [ $? -ne 0 ]; then
    echo "❌ Analysis failed!"
    exit 1
fi

echo
echo "========================================"
echo "✅ Pipeline completed successfully!"
echo "========================================"
echo
echo "Generated files:"
python -c "
import yaml
config = yaml.safe_load(open('$CONFIG_FILE'))
assignments_file = config['output']['assignments_file']
summary_file = config['output']['summary_file']
print(f'📋 Assignments: {assignments_file}')
print(f'📈 Monthly Summary: {summary_file}')
print(f'📊 Analysis Report: outputs/percentage_analysis_report.xlsx')
"
echo
echo "Usage for different configs:"
echo "  ./run_simulation.sh                           # Uses config/PUconfig.yaml (default)"
echo "  ./run_simulation.sh config/FAconfig.yaml     # Uses FAconfig.yaml"
echo "  ./run_simulation.sh config/myconfig.yaml     # Uses custom config"