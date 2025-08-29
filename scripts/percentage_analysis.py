"""
Percentage Analysis Report Generator

This script analyzes the generated leave assignments and compares actual percentages 
to target percentages from the configuration file.
"""

import pandas as pd
import yaml
from datetime import datetime
from dateutil.relativedelta import relativedelta

def load_config(config_file: str = "config/PUconfig.yaml") -> dict:
    """Load configuration from YAML file."""
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)
    return config

def calculate_period_months(start_date: str, end_date: str) -> int:
    """Calculate number of months in simulation period."""
    start = pd.to_datetime(start_date + "-01")
    end = pd.to_datetime(end_date + "-01")
    months = pd.date_range(start=start, end=end, freq="MS")
    return len(months)

def generate_percentage_report(config_file: str = "config/PUconfig.yaml"):
    """Generate percentage analysis report using config file settings."""
    
    # Load configuration
    config = load_config(config_file)
    
    # Load assignments from config-specified file
    assignments_file = config['output']['assignments_file']
    try:
        assignments_df = pd.read_excel(assignments_file)
    except FileNotFoundError:
        print(f"❌ Error: Assignment file '{assignments_file}' not found!")
        print("   Make sure to run inactivity_simulator_cleaned.py first.")
        return None
    
    # Get simulation parameters
    crew_size = config['crew'].get('actual_size', 495)  # Fallback to 495 if not set
    start_date = config['simulation']['start_date']
    end_date = config['simulation']['end_date']
    period_months = calculate_period_months(start_date, end_date)
    
    # Calculate total heads for the period
    total_heads = crew_size
    
    print("=" * 80)
    print("LEAVE PERCENTAGE ANALYSIS REPORT")
    print("=" * 80)
    print(f"Simulation Period: {start_date} to {end_date} ({period_months} months)")
    print(f"Crew Size: {crew_size}")
    print(f"Total Heads: {total_heads:,}")
    print()
    
    # Prepare results for output file
    results = []
    
    print("LEAVE TYPE ANALYSIS (Time-weighted Coverage):")
    print("-" * 80)
    print(f"{'Leave Type':<20} {'Target%':<8} {'Actual%':<8} {'Difference':<10} {'People':<6} {'Status':<8}")
    print("-" * 80)
    
    for leave_type, config_params in config['leave_parameters'].items():
        # Get target percentage from config
        target_percent = config_params['rate_percent']
        
        # Get assignments for this leave type
        leave_assignments = assignments_df[assignments_df['leave_type'] == leave_type]
        
        # Calculate TIME-WEIGHTED coverage (your method)
        total_leave_days = 0
        
        for _, assignment in leave_assignments.iterrows():
            start_date = pd.to_datetime(assignment['start_date'])
            end_date = pd.to_datetime(assignment['end_date'])
            leave_days = (end_date - start_date).days
            total_leave_days += leave_days
        
        # Calculate total available crew-days over the period
        total_crew_days = crew_size * period_months * 30.44  # Average days per month
        
        # Time-weighted percentage: total leave-days / total crew-days * 100
        actual_percent = (total_leave_days / total_crew_days) * 100 if total_crew_days > 0 else 0
        
        # Calculate difference
        difference = actual_percent - target_percent
        
        # Determine status
        if abs(difference) <= 0.1:  # Within 0.1% (more reasonable tolerance)
            status = "✅ Good"
        elif difference > 0:
            status = "⬆️ High"
        else:
            status = "⬇️ Low"
        
        # Count unique people for reference
        unique_heads = leave_assignments['person_id'].nunique()
        total_assignments = len(leave_assignments)
        
        # Print row
        print(f"{leave_type:<20} {target_percent:<8.2f} {actual_percent:<8.2f} {difference:<+10.2f} {unique_heads:<6} {status:<8}")
        
        # Store for output file
        results.append({
            'Leave Type': leave_type,
            'Target Percentage': target_percent,
            'Actual Percentage (Time-weighted)': round(actual_percent, 3),
            'Difference': round(difference, 3),
            'Unique People': unique_heads,
            'Total Assignments': total_assignments,
            'Total Leave-Days': int(total_leave_days),
            'Average Days per Assignment': round(total_leave_days / total_assignments, 1) if total_assignments > 0 else 0,
            'Status': status.replace('✅ ', '').replace('⬆️ ', '').replace('⬇️ ', '')
        })
    
    print("-" * 80)
    
    # Calculate overall statistics using TIME-WEIGHTED method
    total_assignments = len(assignments_df)
    total_unique_heads_on_leave = assignments_df['person_id'].nunique()
    
    # Calculate total time-weighted coverage across all leave types
    total_leave_days_all_types = 0
    for _, assignment in assignments_df.iterrows():
        start_date = pd.to_datetime(assignment['start_date'])
        end_date = pd.to_datetime(assignment['end_date'])
        leave_days = (end_date - start_date).days
        total_leave_days_all_types += leave_days
    
    total_crew_days = crew_size * period_months * 30.44
    overall_actual_percent = (total_leave_days_all_types / total_crew_days) * 100
    overall_target_percent = sum(config['leave_parameters'][lt]['rate_percent'] for lt in config['leave_parameters'].keys())
    
    print()
    print("OVERALL SUMMARY (Time-weighted Analysis):")
    print(f"Total Assignments: {total_assignments}")
    print(f"Total Unique People on Leave: {total_unique_heads_on_leave}")
    print(f"Total Leave-Days: {int(total_leave_days_all_types):,}")
    print(f"Total Crew-Days Available: {int(total_crew_days):,}")
    print(f"Overall Target Percentage: {overall_target_percent:.2f}%")
    print(f"Overall Actual Percentage: {overall_actual_percent:.2f}%")
    print(f"Overall Difference: {overall_actual_percent - overall_target_percent:+.2f}%")
    
    # Add overall summary to results
    results.append({
        'Leave Type': 'TOTAL',
        'Target Percentage': overall_target_percent,
        'Actual Percentage (Time-weighted)': round(overall_actual_percent, 3),
        'Difference': round(overall_actual_percent - overall_target_percent, 3),
        'Unique People': total_unique_heads_on_leave,
        'Total Assignments': total_assignments,
        'Total Leave-Days': int(total_leave_days_all_types),
        'Average Days per Assignment': round(total_leave_days_all_types / total_assignments, 1) if total_assignments > 0 else 0,
        'Status': 'Summary'
    })
    
    print()
    print("=" * 80)
    
    # Export to Excel
    results_df = pd.DataFrame(results)
    output_file = "outputs/percentage_analysis_report.xlsx"
    
    # Create a detailed Excel report with multiple sheets
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        # Summary sheet
        results_df.to_excel(writer, sheet_name='Summary', index=False)
        
        # Detailed assignments sheet
        assignments_with_duration = assignments_df.copy()
        assignments_with_duration['start_date'] = pd.to_datetime(assignments_with_duration['start_date'])
        assignments_with_duration['end_date'] = pd.to_datetime(assignments_with_duration['end_date'])
        assignments_with_duration['duration_days'] = (assignments_with_duration['end_date'] - assignments_with_duration['start_date']).dt.days
        assignments_with_duration['duration_months'] = assignments_with_duration['duration_days'] / 30.44
        
        assignments_with_duration.to_excel(writer, sheet_name='Detailed_Assignments', index=False)
        
        # Configuration parameters sheet
        config_df = pd.DataFrame([
            {'Parameter': 'Simulation Start', 'Value': start_date},
            {'Parameter': 'Simulation End', 'Value': end_date},
            {'Parameter': 'Period (months)', 'Value': period_months},
            {'Parameter': 'Crew Size', 'Value': crew_size},
            {'Parameter': 'Total Heads', 'Value': total_heads},
            {'Parameter': 'Rank', 'Value': config['crew']['rank_name']},
            {'Parameter': 'CDB File', 'Value': config['cdb_file']},
        ])
        config_df.to_excel(writer, sheet_name='Configuration', index=False)
    
    print(f"📊 Detailed report exported to: {output_file}")
    
    return results_df

if __name__ == "__main__":
    import sys
    
    # Allow config file to be specified as command line argument
    config_file = sys.argv[1] if len(sys.argv) > 1 else "config/PUconfig.yaml"
    generate_percentage_report(config_file)