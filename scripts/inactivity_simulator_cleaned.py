"""
Inactivity Simulator for Manpower Planning

This script generates dummy inactivity data (leaves, sick time, etc.) for resource planning
simulations, ensuring even distribution across time and personnel while preventing overlaps.

Requirements:
1. Leave must be spread evenly across the year
2. Inactivities cannot overlap for the same person
3. Inactivities must be distributed across crew members
"""

import pandas as pd
import numpy as np
import random
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from typing import Dict, List, Tuple, Optional
import logging
import yaml

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Constants
DAYS_PER_MONTH = 30.44  # Average days per month
MAX_ASSIGNMENT_ATTEMPTS = 300  # Max attempts per month - can be overridden by config
DEFAULT_SEED = 42


def load_config(config_file: str = "config/PUconfig.yaml") -> dict:
    """Load configuration from YAML file."""
    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
        logger.info(f"Loaded configuration from {config_file}")
        return config
    except FileNotFoundError:
        logger.error(f"Configuration file {config_file} not found!")
        raise
    except yaml.YAMLError as e:
        logger.error(f"Error parsing configuration file: {e}")
        raise


class InactivitySimulator:
    """
    Simulates inactivity periods (leaves, sick time) for manpower planning.
    
    Ensures constraints are met:
    - Even temporal distribution
    - No individual overlaps
    - Fair distribution across personnel
    """
    
    def __init__(self, config: dict):
        """
        Initialize the simulator with configuration.
        
        Args:
            config: Configuration dictionary from YAML file
        """
        self.config = config
        self.crew_size = None  # Will be set when loading personnel
        self.start_date = config['simulation']['start_date']
        self.end_date = config['simulation']['end_date']
        self.months = self._generate_months()
        self.inactivity_records = []
        
        # Load leave parameters from config and calculate dynamic values
        self.leave_parameters = config['leave_parameters'].copy()
        self._calculate_dynamic_parental_leave_params()
        
    def _generate_months(self) -> List[datetime]:
        """Generate list of month start dates for the simulation period."""
        start = pd.to_datetime(self.start_date + "-01")
        end = pd.to_datetime(self.end_date + "-01")
        return pd.date_range(start=start, end=end, freq="MS").tolist()
    
    def _calculate_dynamic_parental_leave_params(self):
        """Calculate dynamic parental leave parameters from config."""
        if 'parental_leave_dynamic' not in self.config:
            logger.warning("No parental_leave_dynamic section found, using static values")
            return
            
        dynamic_config = self.config['parental_leave_dynamic']
        
        # Extract the 4 user-configurable parameters
        female_duration = dynamic_config.get('female_duration_months', 7.5)
        female_percentage = dynamic_config.get('female_percentage', 60.0) / 100.0  # Convert to decimal
        male_duration = dynamic_config.get('male_duration_months', 2.0)
        male_percentage = dynamic_config.get('male_percentage', 40.0) / 100.0  # Convert to decimal
        
        # Validate percentages sum to 100%
        if abs((female_percentage + male_percentage) - 1.0) > 0.01:
            logger.warning(f"Female + male percentages = {(female_percentage + male_percentage)*100:.1f}%, should be 100%")
        
        # Calculate weighted average duration
        weighted_duration = (female_percentage * female_duration) + (male_percentage * male_duration)
        
        # Update leave parameters
        if "Parental Leave" in self.leave_parameters:
            self.leave_parameters["Parental Leave"]["duration_months"] = weighted_duration
            logger.info(f"Dynamic parental leave calculation:")
            logger.info(f"  Female: {female_percentage*100:.1f}% @ {female_duration} months")
            logger.info(f"  Male: {male_percentage*100:.1f}% @ {male_duration} months")
            logger.info(f"  Weighted duration: {weighted_duration:.2f} months")
        
        # Update legacy parental_leave section for compatibility
        if 'parental_leave' not in self.config:
            self.config['parental_leave'] = {}
        
        self.config['parental_leave']['split_female_male'] = [female_percentage, male_percentage]
        self.config['parental_leave']['female_avg_duration'] = female_duration
        self.config['parental_leave']['male_avg_duration'] = male_duration
    
    def _get_assignment_priority(self, leave_type: str, required_gender: str, duration_months: float) -> float:
        """Calculate priority for assignment ordering (higher = more constrained)."""
        priority = 0.0
        
        # Gender restrictions increase priority
        if required_gender == 'female':
            priority += 100  # Most constrained
        elif required_gender == 'male':
            priority += 50
        
        # Longer durations increase priority (block more future slots)
        priority += duration_months * 10
        
        # Specific leave type priorities
        if leave_type == 'Maternity Leave':
            priority += 1000  # Highest priority
        elif leave_type == 'Long Term Sick':
            priority += 500   # High priority due to duration
        
        return priority

    def _find_best_candidate(self, request: dict, personnel_df: pd.DataFrame, 
                           existing_records: list, max_leaves_per_person: int, max_attempts: int) -> str:
        """Find best candidate for a leave assignment request."""
        leave_type = request['leave_type']
        start_date = request['start_date']
        end_date = request['end_date']
        required_gender = request['required_gender']
        
        # Filter by gender
        if required_gender == 'female':
            candidate_pool = personnel_df[personnel_df['gender'] == 'female']
        elif required_gender == 'male':
            candidate_pool = personnel_df[personnel_df['gender'] == 'male']
        else:
            candidate_pool = personnel_df
        
        # Sort candidates by current leave count (prefer people with fewer leaves)
        candidate_scores = []
        for _, candidate in candidate_pool.iterrows():
            person_id = candidate['person_id']
            current_leaves = self._count_person_leaves(person_id, existing_records)
            
            # Skip if already at max leaves
            if current_leaves >= max_leaves_per_person:
                continue
                
            # Skip if same-type restriction applies
            if leave_type in ['Maternity Leave'] and self._count_person_leaves_by_type(person_id, leave_type, existing_records) > 0:
                continue
                
            # Skip if overlap exists
            if self._check_overlap(person_id, start_date, end_date, existing_records):
                continue
                
            # Calculate score (lower is better - fewer existing leaves)
            score = current_leaves + random.random() * 0.1  # Small random tiebreaker
            candidate_scores.append((score, person_id))
        
        # Sort by score and try candidates in order
        candidate_scores.sort()
        
        attempts = 0
        for score, person_id in candidate_scores:
            attempts += 1
            if attempts > max_attempts:
                break
                
            # Double-check constraints (they might have changed)
            if (self._count_person_leaves(person_id, existing_records) < max_leaves_per_person and
                not self._check_overlap(person_id, start_date, end_date, existing_records)):
                return person_id
        
        return None  # No suitable candidate found

    def calculate_monthly_starters(self, 
                                 leave_type: str, 
                                 variability: float = 0.1,
                                 seed: Optional[int] = None) -> List[float]:
        """
        Calculate number of people starting leave each month for a given leave type.
        
        Args:
            leave_type: Type of leave
            variability: Random variability factor (0.1 = ±10%)
            seed: Random seed for reproducibility
            
        Returns:
            List of starters per month
        """
        if seed is not None:
            np.random.seed(seed)
            
        params = self.leave_parameters[leave_type]
        rate_percent = params['rate_percent']
        duration_months = params['duration_months']
        
        # Calculate requirement scaled to actual simulation period
        num_months = len(self.months)
        period_years = num_months / 12.0  # Convert months to years
        
        # Calculate steady-state requirement: maintain rate_percent of crew on leave at all times
        people_on_leave_at_any_time = self.crew_size * (rate_percent / 100)  # e.g., 25 people
        total_leave_months_needed = people_on_leave_at_any_time * num_months  # e.g., 25 × 41 = 1,025
        total_people_needed = total_leave_months_needed / duration_months     # e.g., 1,025 ÷ 3.22 = 318
        monthly_base = total_people_needed / num_months                       # e.g., 318 ÷ 41 = 7.8
        
        # Apply variability while maintaining period total
        multipliers = np.random.uniform(1 - variability, 1 + variability, num_months)
        monthly_starters = monthly_base * multipliers
        
        # Normalize to maintain exact period total
        target_total = total_people_needed
        current_total = monthly_starters.sum()
        monthly_starters = monthly_starters * (target_total / current_total)
        
        return monthly_starters.tolist()
    
    def _check_overlap(self, 
                      person_id: str, 
                      start_date: datetime, 
                      end_date: datetime,
                      existing_records: List[Dict]) -> bool:
        """
        Check if proposed leave period overlaps with existing leaves for a person.
        
        Args:
            person_id: Unique identifier for person
            start_date: Proposed start date
            end_date: Proposed end date  
            existing_records: List of existing leave records
            
        Returns:
            True if overlap exists, False otherwise
        """
        for record in existing_records:
            if record['person_id'] != person_id:
                continue
                
            existing_start = pd.to_datetime(record['start_date'])
            existing_end = pd.to_datetime(record['end_date'])
            
            # Check for any overlap
            if start_date < existing_end and end_date > existing_start:
                return True
                
        return False
    
    def _count_person_leaves(self, person_id: str, existing_records: List[Dict]) -> int:
        """Count existing leaves for a person."""
        return sum(1 for record in existing_records if record['person_id'] == person_id)
    
    def _count_person_leaves_by_type(self, person_id: str, leave_type: str, existing_records: List[Dict]) -> int:
        """Count existing leaves of a specific type for a person."""
        return sum(1 for record in existing_records 
                  if record['person_id'] == person_id and record.get('leave_type') == leave_type)
    
    def _assign_parental_leave_after_maternity(self, 
                                             maternity_records: List[Dict],
                                             personnel_df: pd.DataFrame,
                                             all_records: List[Dict],
                                             max_leaves_per_person: int,
                                             participation_rate: float = 0.4) -> List[Dict]:
        """
        Assign parental leave to females after maternity leave (3-12 months duration).
        
        Args:
            maternity_records: List of maternity leave records
            personnel_df: Personnel DataFrame
            all_records: Existing leave records to check for overlaps
            max_leaves_per_person: Maximum leaves per person
            participation_rate: Percentage of maternity leaves that get followed by parental leave
            
        Returns:
            List of new parental leave records
        """
        new_parental_records = []
        
        for maternity_record in maternity_records:
            # Only some percentage choose to take parental leave after maternity
            if random.random() >= participation_rate:  # Fixed: >= instead of >
                continue
                
            person_id = maternity_record['person_id']
            
            # Check if person already has max leaves
            if self._count_person_leaves(person_id, all_records) >= max_leaves_per_person:
                continue
                
            # Calculate parental leave period (immediately after maternity leave ends)
            maternity_end = pd.to_datetime(maternity_record['end_date'])
            parental_start = maternity_end + timedelta(days=1)
            
            # Female parental leave duration from dynamic config
            female_duration = self.config.get('parental_leave', {}).get('female_avg_duration', 7.5)
            # Add some variability (±20%)
            duration_months = np.random.uniform(female_duration * 0.8, female_duration * 1.2)
            parental_end = parental_start + timedelta(days=int(duration_months * DAYS_PER_MONTH))
            
            # Check for overlap with existing records
            if self._check_overlap(person_id, parental_start, parental_end, all_records):
                continue
                
            parental_record = {
                'person_id': person_id,
                'leave_type': 'Parental Leave',
                'start_date': parental_start.strftime('%Y-%m-%d'),
                'end_date': parental_end.strftime('%Y-%m-%d'),
                'duration_months': duration_months
            }
            
            new_parental_records.append(parental_record)
            # Note: all_records will be updated by caller
            
        return new_parental_records
    
    def _assign_male_parental_leave(self,
                                  personnel_df: pd.DataFrame,
                                  all_records: List[Dict],
                                  max_leaves_per_person: int,
                                  target_assignments: int,
                                  seed: Optional[int] = None) -> List[Dict]:
        """
        Assign parental leave to males (1-3 months duration, anytime).
        
        Args:
            personnel_df: Personnel DataFrame
            all_records: Existing leave records
            max_leaves_per_person: Maximum leaves per person
            target_assignments: Number of assignments to make
            seed: Random seed
            
        Returns:
            List of new male parental leave records
        """
        if seed is not None:
            np.random.seed(seed)
            random.seed(seed)
            
        male_pool = personnel_df[personnel_df['gender'] == 'male']
        new_records = []
        assignments_made = 0
        
        for _ in range(target_assignments * 2):  # Try more attempts
            if assignments_made >= target_assignments:
                break
                
            if len(male_pool) == 0:
                break
                
            candidate = male_pool.sample(1).iloc[0]
            person_id = candidate['person_id']
            
            # Check constraints
            if self._count_person_leaves(person_id, all_records) >= max_leaves_per_person:
                continue
                
            # Random month and start day
            month_start = random.choice(self.months)
            start_day = random.randint(1, 10)
            start_date = month_start.replace(day=start_day)
            
            # Male parental leave duration from dynamic config  
            male_duration = self.config.get('parental_leave', {}).get('male_avg_duration', 2.0)
            # Add some variability (±20%)
            duration_months = np.random.uniform(male_duration * 0.8, male_duration * 1.2)
            end_date = start_date + timedelta(days=int(duration_months * DAYS_PER_MONTH))
            
            # Check for overlap
            if self._check_overlap(person_id, start_date, end_date, all_records):
                continue
                
            parental_record = {
                'person_id': person_id,
                'leave_type': 'Parental Leave',
                'start_date': start_date.strftime('%Y-%m-%d'),
                'end_date': end_date.strftime('%Y-%m-%d'),
                'duration_months': duration_months
            }
            
            new_records.append(parental_record)
            # Note: all_records will be updated by caller
            assignments_made += 1
            
        return new_records
    
    def assign_leaves_simple(self, 
                            personnel_df: pd.DataFrame,
                            max_leaves_per_person: int = 3,
                            duration_variability: float = 0.15,
                            existing_inactivity_df: Optional[pd.DataFrame] = None,
                            seed: Optional[int] = None) -> pd.DataFrame:
        """
        SIMPLIFIED assignment approach based on the original working script.
        Uses basic random selection without complex constraints.
        """
        if seed is not None:
            np.random.seed(seed)
            random.seed(seed)

        crew_size = len(personnel_df)
        logger.info(f"Loaded real crew data: {crew_size} members ({personnel_df['gender'].value_counts().to_dict()})")

        # Initialize with existing records
        all_records = []
        if existing_inactivity_df is not None and len(existing_inactivity_df) > 0:
            for _, row in existing_inactivity_df.iterrows():
                if row['Unique ID'] in personnel_df['person_id'].values:
                    existing_record = {
                        'person_id': row['Unique ID'],
                        'leave_type': row['Assignable Name'],
                        'start_date': pd.to_datetime(row['Start']).strftime('%Y-%m-%d'),
                        'end_date': pd.to_datetime(row['End']).strftime('%Y-%m-%d'),
                        'duration_months': (pd.to_datetime(row['End']) - pd.to_datetime(row['Start'])).days / DAYS_PER_MONTH
                    }
                    all_records.append(existing_record)

        logger.info(f"Loaded {len(all_records)} existing inactivity records")

        # Convert to DataFrame for overlap checking
        running_df = pd.DataFrame(all_records) if all_records else pd.DataFrame(columns=['person_id', 'leave_type', 'start_date', 'end_date'])

        assignment_stats = {}
        maternity_records = []

        # Simple processing order - no complex prioritization
        for leave_type in self.leave_parameters.keys():
            if leave_type == 'Parental Leave':
                continue  # Handle separately

            logger.info(f"Assigning {leave_type}...")
            
            monthly_starters = self.calculate_monthly_starters(leave_type, seed=seed)
            params = self.leave_parameters[leave_type]
            base_duration = params['duration_months']
            required_gender = params['gender']

            # Set up candidate pool
            if required_gender == 'female':
                candidate_pool = personnel_df[personnel_df['gender'] == 'female']
            elif required_gender == 'male':
                candidate_pool = personnel_df[personnel_df['gender'] == 'male']
            else:
                candidate_pool = personnel_df

            successful_assignments = 0
            total_target = sum(monthly_starters)

            # SIMPLIFIED monthly assignment loop (like original)
            for month_idx, starters in enumerate(monthly_starters):
                month_start = self.months[month_idx]
                n_starters = int(round(starters))

                for _ in range(n_starters):
                    # Random start day within first 10 days
                    start_day = random.randint(1, 10)
                    start_date = month_start.replace(day=start_day)
                    
                    # Calculate duration with variability
                    duration = base_duration * (1 + np.random.uniform(0, duration_variability))
                    end_date = start_date + timedelta(days=int(duration * DAYS_PER_MONTH))

                    # SIMPLE assignment logic from original script
                    attempts = 0
                    found_candidate = False
                    
                    while attempts < 100:  # Original used 100 attempts
                        if len(candidate_pool) == 0:
                            break
                            
                        candidate = candidate_pool.sample(1).iloc[0]
                        person_id = candidate['person_id']

                        # Count existing leaves for this person
                        person_leaves = len(running_df[running_df['person_id'] == person_id])
                        if person_leaves >= max_leaves_per_person:
                            attempts += 1
                            continue

                        # Check for same-type restrictions
                        if leave_type == 'Maternity Leave':
                            same_type_leaves = len(running_df[
                                (running_df['person_id'] == person_id) & 
                                (running_df['leave_type'] == leave_type)
                            ])
                            if same_type_leaves > 0:
                                attempts += 1
                                continue

                        # SIMPLE overlap check (like original)
                        if not running_df.empty:
                            person_records = running_df[running_df['person_id'] == person_id]
                            overlap_found = False
                            
                            for _, record in person_records.iterrows():
                                existing_start = pd.to_datetime(record['start_date'])
                                existing_end = pd.to_datetime(record['end_date'])
                                
                                if start_date < existing_end and end_date > existing_start:
                                    overlap_found = True
                                    break
                            
                            if overlap_found:
                                attempts += 1
                                continue

                        # Success! Assign the leave
                        found_candidate = True
                        break

                    if found_candidate:
                        # Add to records
                        new_record = {
                            'person_id': person_id,
                            'leave_type': leave_type,
                            'start_date': start_date.strftime('%Y-%m-%d'),
                            'end_date': end_date.strftime('%Y-%m-%d'),
                            'duration_months': duration
                        }
                        
                        all_records.append(new_record)
                        running_df = pd.concat([running_df, pd.DataFrame([new_record])], ignore_index=True)
                        successful_assignments += 1

                        # Track maternity for parental leave
                        if leave_type == 'Maternity Leave':
                            maternity_records.append(new_record)

            # Track statistics
            success_rate = (successful_assignments / total_target * 100) if total_target > 0 else 0
            assignment_stats[leave_type] = {'successful': successful_assignments, 'attempted': total_target}
            logger.info(f"{leave_type}: {successful_assignments}/{total_target:.1f} assignments ({success_rate:.1f}% success)")

        # Handle parental leave with simplified logic respecting config ratio
        logger.info(f"Assigning Parental Leave...")
        target_parental = sum(self.calculate_monthly_starters('Parental Leave', seed=seed))
        
        # Get gender split from config (calculated dynamically)
        parental_config = self.config.get('parental_leave', {})
        female_ratio, male_ratio = parental_config.get('split_female_male', [0.6, 0.4])
        
        # Calculate assignments per gender
        target_female = int(target_parental * female_ratio)
        target_male = int(target_parental * male_ratio)
        
        logger.info(f"Target split: {target_female} female / {target_male} male ({female_ratio:.0%}/{male_ratio:.0%})")
        
        # Separate pools
        female_pool = personnel_df[personnel_df['gender'] == 'female']
        male_pool = personnel_df[personnel_df['gender'] == 'male']
        
        parental_assignments = 0
        
        # Assign female parental leaves
        for _ in range(target_female):
            attempts = 0
            while attempts < 100:  # 100 attempts per assignment
                attempts += 1
                
                if len(female_pool) == 0:
                    break
                    
                candidate = female_pool.sample(1).iloc[0]
                person_id = candidate['person_id']
                
                # Check constraints
                person_leaves = len(running_df[running_df['person_id'] == person_id])
                if person_leaves >= max_leaves_per_person:
                    continue
                    
                # Random timing
                month_idx = random.randint(0, len(self.months) - 1)
                start_date = self.months[month_idx].replace(day=random.randint(1, 10))
                
                # Female duration from dynamic config with variability
                female_duration = self.config.get('parental_leave', {}).get('female_avg_duration', 7.5)
                duration = random.uniform(female_duration * 0.8, female_duration * 1.2)
                end_date = start_date + timedelta(days=int(duration * DAYS_PER_MONTH))
                
                # Check overlap
                if not running_df.empty:
                    person_records = running_df[running_df['person_id'] == person_id]
                    overlap_found = False
                    
                    for _, record in person_records.iterrows():
                        existing_start = pd.to_datetime(record['start_date'])
                        existing_end = pd.to_datetime(record['end_date'])
                        
                        if start_date < existing_end and end_date > existing_start:
                            overlap_found = True
                            break
                    
                    if overlap_found:
                        continue
                
                # Success! Add female parental leave
                parental_record = {
                    'person_id': person_id,
                    'leave_type': 'Parental Leave', 
                    'start_date': start_date.strftime('%Y-%m-%d'),
                    'end_date': end_date.strftime('%Y-%m-%d'),
                    'duration_months': duration
                }
                
                all_records.append(parental_record)
                running_df = pd.concat([running_df, pd.DataFrame([parental_record])], ignore_index=True)
                parental_assignments += 1
                break
        
        # Assign male parental leaves
        for _ in range(target_male):
            attempts = 0
            while attempts < 100:  # 100 attempts per assignment
                attempts += 1
                
                if len(male_pool) == 0:
                    break
                    
                candidate = male_pool.sample(1).iloc[0]
                person_id = candidate['person_id']
                
                # Check constraints
                person_leaves = len(running_df[running_df['person_id'] == person_id])
                if person_leaves >= max_leaves_per_person:
                    continue
                    
                # Random timing
                month_idx = random.randint(0, len(self.months) - 1)
                start_date = self.months[month_idx].replace(day=random.randint(1, 10))
                
                # Male duration from dynamic config with variability
                male_duration = self.config.get('parental_leave', {}).get('male_avg_duration', 2.0)
                duration = random.uniform(male_duration * 0.8, male_duration * 1.2)
                end_date = start_date + timedelta(days=int(duration * DAYS_PER_MONTH))
                
                # Check overlap
                if not running_df.empty:
                    person_records = running_df[running_df['person_id'] == person_id]
                    overlap_found = False
                    
                    for _, record in person_records.iterrows():
                        existing_start = pd.to_datetime(record['start_date'])
                        existing_end = pd.to_datetime(record['end_date'])
                        
                        if start_date < existing_end and end_date > existing_start:
                            overlap_found = True
                            break
                    
                    if overlap_found:
                        continue
                
                # Success! Add male parental leave
                parental_record = {
                    'person_id': person_id,
                    'leave_type': 'Parental Leave', 
                    'start_date': start_date.strftime('%Y-%m-%d'),
                    'end_date': end_date.strftime('%Y-%m-%d'),
                    'duration_months': duration
                }
                
                all_records.append(parental_record)
                running_df = pd.concat([running_df, pd.DataFrame([parental_record])], ignore_index=True)
                parental_assignments += 1
                break
            
        success_rate = (parental_assignments / target_parental * 100) if target_parental > 0 else 0
        logger.info(f"Parental Leave: {parental_assignments}/{target_parental:.1f} assignments ({success_rate:.1f}% success)")

        # Convert to DataFrame format expected by export
        if all_records:
            result_df = pd.DataFrame(all_records)
            result_df['start_date'] = pd.to_datetime(result_df['start_date'])
            result_df['end_date'] = pd.to_datetime(result_df['end_date'])
        else:
            result_df = pd.DataFrame(columns=['person_id', 'leave_type', 'start_date', 'end_date'])

        return result_df

    def assign_leaves(self, 
                     personnel_df: pd.DataFrame,
                     max_leaves_per_person: int = 3,  # Increased for longer period
                     duration_variability: float = 0.15,
                     existing_inactivity_df: Optional[pd.DataFrame] = None,
                     prefer_unique_people: bool = True,
                     seed: Optional[int] = None) -> pd.DataFrame:
        """
        Assign leave periods to personnel based on calculated requirements.
        
        Args:
            personnel_df: DataFrame with columns ['person_id', 'gender']
            max_leaves_per_person: Maximum leaves per person
            duration_variability: Variability in leave duration
            existing_inactivity_df: DataFrame with existing inactivity records
            seed: Random seed
            
        Returns:
            DataFrame with leave assignments
        """
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)
            
        # Initialize with existing records if provided
        all_records = []
        if existing_inactivity_df is not None and len(existing_inactivity_df) > 0:
            # Convert existing records to our format
            for _, row in existing_inactivity_df.iterrows():
                # Convert to our format if the person is in our personnel list
                if row['Unique ID'] in personnel_df['person_id'].values:
                    existing_record = {
                        'person_id': row['Unique ID'],
                        'leave_type': row['Assignable Name'],
                        'start_date': pd.to_datetime(row['Start']).strftime('%Y-%m-%d'),
                        'end_date': pd.to_datetime(row['End']).strftime('%Y-%m-%d'),
                        'duration_months': (pd.to_datetime(row['End']) - pd.to_datetime(row['Start'])).days / DAYS_PER_MONTH
                    }
                    all_records.append(existing_record)
            logger.info(f"Loaded {len(all_records)} existing inactivity records")
            
        assignment_stats = {}
        maternity_records = []  # Track maternity records for parental leave assignment
        
        # Process leave types in priority order (most constrained first)
        leave_types_prioritized = []
        for leave_type, params in self.leave_parameters.items():
            if leave_type == 'Parental Leave':
                continue  # Handle separately
            
            priority = self._get_assignment_priority(
                leave_type, params['gender'], params['duration_months']
            )
            leave_types_prioritized.append((priority, leave_type))
        
        # Sort by priority (highest first)
        leave_types_prioritized.sort(reverse=True)
        
        for priority, leave_type in leave_types_prioritized:
                
            logger.info(f"Assigning {leave_type}...")
            
            monthly_starters = self.calculate_monthly_starters(leave_type, seed=seed)
            params = self.leave_parameters[leave_type]
            base_duration = params['duration_months']
            required_gender = params['gender']
            
            # Filter candidate pool by gender if required
            if required_gender == 'female':
                candidate_pool = personnel_df[personnel_df['gender'] == 'female']
            elif required_gender == 'male':
                candidate_pool = personnel_df[personnel_df['gender'] == 'male']
            else:
                candidate_pool = personnel_df
                
            assignments_made = 0
            assignments_skipped = 0
            
            for month_idx, starters in enumerate(monthly_starters):
                month_start = self.months[month_idx]
                num_starters = int(round(starters))
                
                for _ in range(num_starters):
                    # Random start day within first 10 days of month
                    start_day = random.randint(1, 10)
                    start_date = month_start.replace(day=start_day)
                    
                    # Calculate duration with variability
                    duration = base_duration * (1 + np.random.uniform(-duration_variability, 
                                                                     duration_variability))
                    end_date = start_date + timedelta(days=int(duration * DAYS_PER_MONTH))
                    
                    # Find suitable candidate with smart distribution
                    found_candidate = False
                    
                    if prefer_unique_people:
                        # First, try people with no leaves, then 1 leave, etc.
                        for max_existing_leaves in range(max_leaves_per_person):
                            eligible_candidates = []
                            for _, candidate in candidate_pool.iterrows():
                                person_id = candidate['person_id']
                                current_leaves = self._count_person_leaves(person_id, all_records)
                                if current_leaves == max_existing_leaves:
                                    eligible_candidates.append(candidate)
                            
                            if not eligible_candidates:
                                continue
                                
                            # Try candidates with this number of existing leaves
                            random.shuffle(eligible_candidates)
                            max_attempts = self.config.get('assignment', {}).get('max_assignment_attempts', MAX_ASSIGNMENT_ATTEMPTS)
                            for candidate in eligible_candidates[:max_attempts]:
                                person_id = candidate['person_id']
                                
                                # Check for same-type restrictions (e.g., no multiple maternity leaves)
                                if leave_type in ['Maternity Leave'] and self._count_person_leaves_by_type(person_id, leave_type, all_records) > 0:
                                    continue  # Skip if person already has this type of leave
                                
                                # Check for overlaps only (leave count already filtered)
                                if not self._check_overlap(person_id, start_date, end_date, all_records):
                                    found_candidate = True
                                    break
                            
                            if found_candidate:
                                break
                    else:
                        # Improved intelligent candidate selection
                        max_attempts = self.config.get('assignment', {}).get('max_assignment_attempts', MAX_ASSIGNMENT_ATTEMPTS)
                        
                        # Create assignment request for the intelligent selector
                        assignment_request = {
                            'leave_type': leave_type,
                            'start_date': start_date,
                            'end_date': end_date,
                            'required_gender': required_gender
                        }
                        
                        # Use intelligent candidate finder
                        person_id = self._find_best_candidate(
                            assignment_request, candidate_pool, all_records, 
                            max_leaves_per_person, max_attempts
                        )
                        
                        if person_id:
                            found_candidate = True
                    
                    if found_candidate:
                        # Assign leave
                        record = {
                            'person_id': person_id,
                            'leave_type': leave_type,
                            'start_date': start_date.strftime('%Y-%m-%d'),
                            'end_date': end_date.strftime('%Y-%m-%d'),
                            'duration_months': duration
                        }
                        all_records.append(record)
                        assignments_made += 1
                        found_candidate = True
                        
                        # Track maternity records for parental leave assignment
                        if leave_type == 'Maternity Leave':
                            maternity_records.append(record)
                        
                        break
                        
                    if not found_candidate:
                        assignments_skipped += 1
                        
            assignment_stats[leave_type] = {
                'assigned': assignments_made,
                'skipped': assignments_skipped,
                'target': sum(monthly_starters)
            }
        
        # Handle parental leave with new rules - 1% ON LEAVE calculation
        logger.info("Assigning Parental Leave...")
        
        # Calculate how many people need to START leave to maintain 1% ON LEAVE
        total_crew = len(personnel_df)
        target_on_leave_monthly = total_crew * 0.01  # 1% of crew on leave at any time
        
        # For parental leave: get average durations from dynamic config
        parental_config = self.config.get('parental_leave', {})
        female_avg_duration = parental_config.get('female_avg_duration', 7.5)  # months
        male_avg_duration = parental_config.get('male_avg_duration', 2.0)   # months
        
        # Split target using dynamic config ratios
        female_ratio, male_ratio = parental_config.get('split_female_male', [0.6, 0.4])
        female_on_leave_target = target_on_leave_monthly * female_ratio
        male_on_leave_target = target_on_leave_monthly * male_ratio
        
        # Calculate starters needed: starters_needed = people_on_leave / duration_months * 12
        female_starters_needed = (female_on_leave_target / female_avg_duration) * 12
        male_starters_needed = (male_on_leave_target / male_avg_duration) * 12
        
        logger.info(f"Target: {target_on_leave_monthly:.1f} people on parental leave monthly")
        logger.info(f"Female: {female_on_leave_target:.1f} on leave → {female_starters_needed:.1f} starters/year")
        logger.info(f"Male: {male_on_leave_target:.1f} on leave → {male_starters_needed:.1f} starters/year")
        
        # Convert to integer targets
        female_target = round(female_starters_needed)
        male_target = round(male_starters_needed)
        
        # Female parental leave (after maternity) - calculate participation rate dynamically
        max_possible_female = len(maternity_records)
        female_participation_rate = min(0.8, female_target / max_possible_female) if max_possible_female > 0 else 0
        
        female_parental_records = self._assign_parental_leave_after_maternity(
            maternity_records, personnel_df, all_records, max_leaves_per_person, 
            participation_rate=female_participation_rate
        )
        
        # Male parental leave (anytime, 1-3 months) - exact target
        male_parental_records = self._assign_male_parental_leave(
            personnel_df, all_records, max_leaves_per_person, male_target, seed
        )
        
        # Add parental leave records to all_records
        all_records.extend(female_parental_records)
        all_records.extend(male_parental_records)
        
        # Update assignment stats for parental leave
        total_parental_assigned = len(female_parental_records) + len(male_parental_records)
        total_target_starters = female_target + male_target
        assignment_stats['Parental Leave'] = {
            'assigned': total_parental_assigned,
            'skipped': max(0, total_target_starters - total_parental_assigned),
            'target': total_target_starters
        }
        
        logger.info(f"Female participation rate: {female_participation_rate:.1%} of {max_possible_female} maternity leaves")
        logger.info(f"Female parental leave (after maternity): {len(female_parental_records)} assignments")
        logger.info(f"Male parental leave (anytime): {len(male_parental_records)} assignments")
            
        # Log assignment statistics
        for leave_type, stats in assignment_stats.items():
            success_rate = stats['assigned'] / max(stats['target'], 1) * 100
            logger.info(f"{leave_type}: {stats['assigned']}/{stats['target']:.1f} "
                       f"assignments ({success_rate:.1f}% success)")
            
        return pd.DataFrame(all_records)
    
    def calculate_monthly_on_leave(self, assignments_df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate how many people are on leave each month for each leave type.
        
        Args:
            assignments_df: DataFrame with leave assignments
            
        Returns:
            DataFrame with leave types as rows, months as columns
        """
        assignments_df = assignments_df.copy()
        assignments_df['start_date'] = pd.to_datetime(assignments_df['start_date'])
        assignments_df['end_date'] = pd.to_datetime(assignments_df['end_date'])
        
        month_labels = [month.strftime('%b %Y') for month in self.months]
        leave_types = list(self.leave_parameters.keys())
        
        result_df = pd.DataFrame(0.0, index=leave_types, columns=month_labels)
        
        for month_label, month_start in zip(month_labels, self.months):
            month_end = month_start + relativedelta(months=1)
            days_in_month = (month_end - month_start).days
            
            for leave_type in leave_types:
                # Filter records for this leave type that overlap with this month
                mask = (
                    (assignments_df['leave_type'] == leave_type) &
                    (assignments_df['start_date'] < month_end) &
                    (assignments_df['end_date'] > month_start)
                )
                
                overlapping_leaves = assignments_df.loc[mask]
                total_person_months = 0.0
                
                for _, record in overlapping_leaves.iterrows():
                    overlap_start = max(record['start_date'], month_start)
                    overlap_end = min(record['end_date'], month_end)
                    overlap_days = (overlap_end - overlap_start).days
                    
                    if overlap_days > 0:
                        total_person_months += overlap_days / days_in_month
                        
                result_df.loc[leave_type, month_label] = total_person_months
                
        result_df.index.name = "Leave Type"
        return result_df
    
    def export_results(self, 
                      assignments_df: pd.DataFrame,
                      output_prefix: str = "leave_simulation"):
        """
        Export simulation results to Excel files.
        
        Args:
            assignments_df: DataFrame with leave assignments
            output_prefix: Prefix for output filenames
        """
        # Export individual assignments
        assignments_file = self.config['output']['assignments_file']
        assignments_df.to_excel(assignments_file, index=False)
        logger.info(f"Exported assignments to {assignments_file}")
        
        # Export monthly summary
        monthly_summary = self.calculate_monthly_on_leave(assignments_df)
        
        summary_file = self.config['output']['summary_file']
        monthly_summary.to_excel(summary_file)
        logger.info(f"Exported monthly summary to {summary_file}")
        
        return assignments_file, summary_file


def load_cdb_personnel(cdb_file_path: str, rank_name: str = "PU") -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load real crew member data from CDB export file.
    
    Args:
        cdb_file_path: Path to the CDB export Excel file
        
    Returns:
        Tuple of (personnel_df, existing_inactivity_df)
        - personnel_df: DataFrame with person_id, first_name, last_name, gender
        - existing_inactivity_df: DataFrame with existing inactivity records
    """
    logger.info(f"Loading crew data from {cdb_file_path}")
    
    # Read the key sheets
    rank_df = pd.read_excel(cdb_file_path, sheet_name="Rank")
    label_df = pd.read_excel(cdb_file_path, sheet_name="Label")
    inactivity_df = pd.read_excel(cdb_file_path, sheet_name="Inactivity")
    
    # Get specified rank members only
    rank_df_filtered = rank_df[rank_df["Assignable Name"] == rank_name].copy()
    logger.info(f"Found {len(rank_df_filtered)} {rank_name} members")
    
    # Get gender information
    female_df = label_df[label_df["Assignable Name"] == "Female"]
    male_df = label_df[label_df["Assignable Name"] == "Male"]
    
    # Merge gender with rank members
    female_rank_df = pd.merge(female_df, rank_df_filtered, on="Unique ID", how="inner")
    male_rank_df = pd.merge(male_df, rank_df_filtered, on="Unique ID", how="inner")
    
    logger.info(f"{rank_name} Gender breakdown: {len(female_rank_df)} female, {len(male_rank_df)} male")
    
    # Create personnel DataFrame
    personnel_data = []
    
    # Add female rank members
    for _, row in female_rank_df.iterrows():
        personnel_data.append({
            'person_id': row['Unique ID'],
            'first_name': row['First name_x'],
            'last_name': row['Last name_x'],
            'gender': 'female'
        })
        
    # Add male rank members
    for _, row in male_rank_df.iterrows():
        personnel_data.append({
            'person_id': row['Unique ID'],
            'first_name': row['First name_x'],
            'last_name': row['Last name_x'],
            'gender': 'male'
        })
        
    personnel_df = pd.DataFrame(personnel_data)
    
    # Process existing inactivity data
    existing_inactivity_df = inactivity_df.copy()
    if len(existing_inactivity_df) > 0:
        logger.info(f"Found {len(existing_inactivity_df)} existing inactivity records")
    
    return personnel_df, existing_inactivity_df


def create_sample_personnel(crew_size: int, female_ratio: float = 0.3) -> pd.DataFrame:
    """
    Create sample personnel DataFrame for testing (fallback method).
    
    Args:
        crew_size: Total number of crew members
        female_ratio: Proportion of female crew members
        
    Returns:
        DataFrame with person_id and gender columns
    """
    num_females = int(crew_size * female_ratio)
    num_males = crew_size - num_females
    
    personnel_data = []
    
    # Add female personnel
    for i in range(num_females):
        personnel_data.append({
            'person_id': f'F{i+1:03d}',
            'first_name': f'Female{i+1}',
            'last_name': f'Test{i+1}',
            'gender': 'female'
        })
        
    # Add male personnel  
    for i in range(num_males):
        personnel_data.append({
            'person_id': f'M{i+1:03d}',
            'first_name': f'Male{i+1}',
            'last_name': f'Test{i+1}',
            'gender': 'male'
        })
        
    return pd.DataFrame(personnel_data)


def main():
    """Main execution function."""
    # Load configuration
    config = load_config()
    
    # Try to load real CDB data first, fallback to sample data
    cdb_file_path = config['cdb_file']
    rank_name = config['crew']['rank_name']
    
    try:
        personnel_df, existing_inactivity_df = load_cdb_personnel(cdb_file_path, rank_name)
        crew_size = len(personnel_df)
        logger.info(f"Loaded real crew data: {crew_size} members "
                    f"({len(personnel_df[personnel_df['gender'] == 'female'])} female, "
                    f"{len(personnel_df[personnel_df['gender'] == 'male'])} male)")
    except FileNotFoundError:
        logger.warning(f"CDB file {cdb_file_path} not found, using sample data")
        crew_size = 495
        personnel_df = create_sample_personnel(crew_size, 0.3)
        existing_inactivity_df = None
        logger.info(f"Created sample personnel pool: {len(personnel_df)} members")
    
    # Update config with actual crew size
    config['crew']['actual_size'] = crew_size
    
    # Initialize simulator
    simulator = InactivitySimulator(config)
    simulator.crew_size = crew_size  # Set crew size after initialization
    
    # Run simulation with SIMPLIFIED approach (based on original working script)
    assignments = simulator.assign_leaves_simple(
        personnel_df=personnel_df,
        max_leaves_per_person=config['crew']['max_leaves_per_person'],
        existing_inactivity_df=existing_inactivity_df,
        seed=config['assignment']['random_seed']
    )
    
    logger.info(f"Generated {len(assignments)} leave assignments")
    
    # Export results using config filenames
    simulator.export_results(assignments, "")
    
    # Print summary statistics
    print("\n=== SIMULATION SUMMARY ===")
    for leave_type in simulator.leave_parameters.keys():
        count = len(assignments[assignments['leave_type'] == leave_type])
        print(f"{leave_type}: {count} assignments")
        
    print(f"\nTotal assignments: {len(assignments)}")
    unique_people = assignments['person_id'].nunique()
    print(f"People with leaves: {unique_people}/{crew_size} ({unique_people/crew_size*100:.1f}%)")
    
    # Show existing vs new assignments if we had existing data
    if existing_inactivity_df is not None and len(existing_inactivity_df) > 0:
        print(f"Existing inactivity records: {len(existing_inactivity_df)}")
        print(f"Total records (existing + new): {len(assignments)}")


if __name__ == "__main__":
    main()