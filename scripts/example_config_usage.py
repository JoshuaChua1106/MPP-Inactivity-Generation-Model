"""
Example showing how to modify config for different scenarios
"""
import yaml

# Load current config
with open('config.yaml', 'r') as f:
    config = yaml.safe_load(f)

print("=== CURRENT CONFIGURATION ===")
print(f"Rank: {config['crew']['rank_name']}")
print(f"Period: {config['simulation']['start_date']} to {config['simulation']['end_date']}")
print(f"CDB File: {config['cdb_file']}")
print()

print("Leave Rates:")
for leave_type, params in config['leave_parameters'].items():
    print(f"  {leave_type}: {params['rate_percent']}% ({params['duration_months']} months)")

print()
print("=== EXAMPLE MODIFICATIONS ===")

# Example 1: Change to FA crew
print("1. To simulate FA crew instead of PU:")
print("   crew:")
print("     rank_name: 'FA'")
print()

# Example 2: Increase maternity leave rate
print("2. To increase maternity leave to 6%:")
print("   leave_parameters:")
print("     'Maternity Leave':")
print("       rate_percent: 6.0")
print()

# Example 3: Change simulation period
print("3. To simulate just 2025:")
print("   simulation:")
print("     start_date: '2025-01'")
print("     end_date: '2025-12'")
print()

# Example 4: Change output files
print("4. To change output filenames:")
print("   output:")
print("     assignments_file: 'my_leaves.xlsx'")
print("     summary_file: 'my_summary.xlsx'")
print()

print("=== HOW TO APPLY CHANGES ===")
print("1. Edit config.yaml file")
print("2. Run: python inactivity_simulator_cleaned.py")
print("3. The script will automatically use your new settings!")