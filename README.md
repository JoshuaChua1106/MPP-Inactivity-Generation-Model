# WePlan Inactivity Simulator

A comprehensive simulation tool for generating realistic crew inactivity data (leaves, sick time, etc.) for manpower planning and resource allocation analysis.

## ⚡ Quick Overview

**TL;DR:** This tool simulates crew leave assignments (maternity, parental, sick leave, etc.) that meet realistic constraints and generate accurate coverage percentages for manpower planning.

### 🚀 Quickstart (3 Steps):

1. **Run the simulation:**
   ```bash
   ./run_simulation.sh          # Linux/Mac
   run_simulation.bat           # Windows
   ```

2. **Check results:** All outputs automatically saved to `outputs/` folder

3. **View key files:**
   - `outputs/percentage_analysis_report.xlsx` - Target vs actual coverage analysis
   - `outputs/simulated_cdb_upload.xlsx` - Ready-to-upload leave assignments  
   - `outputs/simulated_monthly_summary.xlsx` - Monthly trends and breakdowns

**That's it!** The tool handles crew data loading, constraint satisfaction, and report generation automatically.

---

## 🎯 Purpose

This simulator generates dummy inactivity data that meets specific constraints:
- **Even temporal distribution** - Leaves spread evenly across time periods, not clumped
- **No individual overlaps** - Each person can only have one leave at a time
- **Fair distribution** - Leaves distributed across crew members, not concentrated on few individuals
- **Realistic percentages** - Maintains target percentage coverage using time-weighted analysis

## 📁 Project Structure

```
Inactivity simulator v2/
├── 📋 cdb_export_2025-07-23_11-00-32.xlsx  # Input crew data (CDB export)
├── 🚀 run_simulation.sh                     # Main Linux/Mac runner
├── 🚀 run_simulation.bat                    # Main Windows runner
├── 📁 config/                               # Configuration files
│   ├── PUconfig.yaml                        # Main configuration
│   └── PUconfig - Copy.yaml                # Backup configuration
├── 📁 scripts/                              # Python simulation scripts
│   ├── inactivity_simulator_cleaned.py     # Core simulation engine
│   ├── percentage_analysis.py              # Analysis & reporting
│   └── example_config_usage.py             # Usage examples
├── 📁 outputs/                              # Generated output files
│   ├── simulated_cdb_upload.xlsx           # Assignments for CDB upload
│   ├── simulated_monthly_summary.xlsx      # Monthly breakdown
│   └── percentage_analysis_report.xlsx     # Detailed analysis report
└── 📁 venv/                                 # Python virtual environment
```

## 🚀 Quick Start

### Prerequisites
- Python 3.7+ with pip
- Required packages: pandas, openpyxl, pyyaml, python-dateutil, numpy

### Setup (First Time)
1. **Create virtual environment:**
   ```bash
   python -m venv venv
   ```

2. **Activate virtual environment:**
   ```bash
   # Linux/Mac
   source venv/bin/activate
   
   # Windows
   venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install pandas openpyxl pyyaml python-dateutil numpy
   ```

### Running the Simulation

**Linux/Mac:**
```bash
./run_simulation.sh                           # Uses config/PUconfig.yaml
./run_simulation.sh config/custom.yaml       # Uses custom config
```

**Windows:**
```bash
run_simulation.bat                            # Uses config\PUconfig.yaml  
run_simulation.bat config\custom.yaml        # Uses custom config
```

The script will:
1. ✅ Validate configuration and input files
2. 🚀 Run the inactivity simulation
3. 📊 Generate percentage analysis report
4. 📋 Export all results to `outputs/` folder

## ⚙️ Configuration

### Main Configuration File: `config/PUconfig.yaml`

#### Simulation Period
```yaml
simulation:
  start_date: "2023-08"    # YYYY-MM format
  end_date: "2026-12"      # YYYY-MM format
```

#### Crew Settings
```yaml
crew:
  rank_name: "PU"          # Rank to simulate (PU, FA, CP, etc.)
  actual_size: 495         # Crew size (auto-detected from CDB)
  max_leaves_per_person: 3 # Max leaves per person over entire period
```

#### Leave Type Parameters
```yaml
leave_parameters:
  "Maternity Leave":
    rate_percent: 5.0      # % of crew on this leave type annually
    duration_months: 3.22  # Average duration in months
    gender: "female"       # Gender restriction (male/female/any)
    max_per_person: 1      # Max occurrences per person
```

### 🎯 Dynamic Parental Leave Configuration

**Simple 4-Parameter Setup** - Only adjust these values:

```yaml
parental_leave_dynamic:
  female_duration_months: 7.5    # Average duration for females
  female_percentage: 60.0         # % of parental leaves taken by females
  male_duration_months: 2.0       # Average duration for males  
  male_percentage: 40.0           # % of parental leaves taken by males
```

**What Happens Automatically:**
- ✅ Weighted duration calculated: `(60% × 7.5) + (40% × 2.0) = 5.3 months`
- ✅ Gender split ratios updated: `[0.60, 0.40]`
- ✅ Assignment logic updated with dynamic values
- ✅ Percentage analysis uses correct weighted averages

## 📊 Output Files

### 1. `outputs/simulated_cdb_upload.xlsx`
Ready-to-upload assignments with columns:
- `person_id` - Crew member identifier
- `leave_type` - Type of leave/inactivity
- `start_date` - Leave start date
- `end_date` - Leave end date
- Additional metadata fields

### 2. `outputs/simulated_monthly_summary.xlsx`
Monthly breakdown showing:
- Leave counts by type per month
- Crew utilization statistics
- Trend analysis data

### 3. `outputs/percentage_analysis_report.xlsx`
Comprehensive analysis with multiple sheets:
- **Summary** - Target vs actual percentages by leave type
- **Detailed_Assignments** - Full assignment list with durations
- **Configuration** - Simulation parameters used

## 📈 Analysis Method

### Time-Weighted Coverage Calculation
The simulator uses **time-weighted analysis** to measure leave coverage:

```
Actual % = (Total Leave-Days / Total Crew-Days Available) × 100
```

This measures **steady-state coverage** (how many people are on leave at any given time) rather than **lifetime experience** (how many people ever had leave).

### Example
- 495 crew members over 41 months = 617,779 total crew-days
- 55,902 leave-days generated
- Actual coverage: 9.05% (55,902 ÷ 617,779 × 100)

## 🔧 Advanced Usage

### Running Individual Components
```bash
# Activate virtual environment first
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Run just the simulation
python scripts/inactivity_simulator_cleaned.py

# Run just the analysis (after simulation)
python scripts/percentage_analysis.py config/PUconfig.yaml
```

### Custom Configuration
1. Copy `config/PUconfig.yaml` to `config/my_config.yaml`
2. Modify parameters as needed
3. Run: `./run_simulation.sh config/my_config.yaml`

### Multiple Scenarios
Create different config files for different scenarios:
- `config/PU_baseline.yaml` - Current baseline scenario
- `config/PU_high_leave.yaml` - High leave scenario
- `config/FA_config.yaml` - Flight Attendant configuration

## 📋 Leave Types Supported

| Leave Type | Default Rate | Duration | Gender | Description |
|------------|--------------|----------|---------|-------------|
| Maternity Leave | 5.0% | 3.22 months | Female | Maternity leave |
| Parental Leave | 1.0% | Dynamic | Any | Configurable parental leave |
| Unpaid Leave | 0.25% | 1.0 months | Any | Unpaid personal leave |
| Long Term Sick | 2.0% | 2.0 months | Any | Extended sick leave |
| Grounded | 0.1% | 0.5 months | Any | Medical grounding |
| Rehab | 0.2% | 0.46 months | Any | Rehabilitation |
| Special Leave | 0.1% | 0.46 months | Any | Special circumstances |

## 🎛️ Key Features

### ✅ Constraint Satisfaction
- **No Overlaps**: Each person can only have one active leave
- **Even Distribution**: Leaves spread evenly across time periods
- **Fair Assignment**: Uses Monte Carlo approach for realistic distribution
- **Gender Compliance**: Respects gender restrictions for specific leave types

### ✅ Dynamic Configuration
- **Real-time Calculation**: Parameters calculated at startup
- **Input Validation**: Warns about configuration issues
- **Backward Compatibility**: Legacy config sections preserved
- **Flexible Scenarios**: Easy parameter adjustments

### ✅ Professional Output
- **Excel Integration**: Ready-to-import XLSX files
- **Multi-sheet Reports**: Comprehensive analysis breakdowns
- **Time-series Data**: Monthly summaries and trends
- **Audit Trail**: Configuration parameters saved with results

## 🚨 Troubleshooting

### Common Issues

**"Virtual environment 'venv' not found"**
```bash
python -m venv venv && source venv/bin/activate && pip install pandas openpyxl pyyaml python-dateutil numpy
```

**"Config file not found"**
- Ensure config file exists in `config/` folder
- Check file path spelling and extension (.yaml)

**"CDB file not found"**
- Verify CDB export file exists in root directory
- Update `cdb_file` path in configuration

**Low Assignment Success Rates**
- Increase `max_assignment_attempts` in config
- Reduce leave rates if over-constrained
- Check for conflicting constraints

## 📝 Version History

- **v2.0** - Dynamic parental leave configuration, organized file structure
- **v1.5** - Time-weighted percentage analysis, automated pipeline
- **v1.0** - Initial simplified assignment algorithm

## 🤝 Contributing

For modifications or enhancements:
1. Test changes with different configurations
2. Verify percentage analysis accuracy  
3. Ensure cross-platform compatibility (Linux/Windows)
4. Update documentation as needed

## 📄 License

Internal tool for WePlan manpower planning operations.

---

**For support or questions, contact the WePlan development team.**