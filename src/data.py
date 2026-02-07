import pandas as pd
from typing import List, Dict, Any

def process_training_data(raw_data: List[Dict[str, Any]]) -> pd.DataFrame:
    """
    Converts raw training data into a structured DataFrame with calculated metrics.
    """
    if not raw_data:
        return pd.DataFrame()
        
    df = pd.DataFrame(raw_data)
    
    # Ensure person_name exists
    if 'person_name' not in df.columns:
        df['person_name'] = 'Unbekannt'
    
    # Calculate Total Hours (Ist and Soll) - useful for internal stats
    df['Total_Ist'] = df['T_Ist'] + df['P_Ist'] + df['K_Ist']
    df['Total_Soll'] = df['T_Soll'] + df['P_Soll'] + df['K_Soll']
    
    # Calculate Effective Progress
    # Logic: You cannot compensate missing Practice with extra Theory.
    # So we take the min(Ist, Soll) for each category to get "Effective Ist"
    df['Effective_Ist'] = (
        df.apply(lambda x: min(x['T_Ist'], x['T_Soll']), axis=1) +
        df.apply(lambda x: min(x['P_Ist'], x['P_Soll']), axis=1) +
        df.apply(lambda x: min(x['K_Ist'], x['K_Soll']), axis=1)
    )

    # Calculate Progress Percentage for the MODULE
    # (Individual module progress bar still uses hours for partial completion, which is fair)
    df['Progress'] = df.apply(
        lambda x: (x['Effective_Ist'] / x['Total_Soll'] * 100) if x['Total_Soll'] > 0 else 100.0, 
        axis=1
    )
    
    # Cap progress at 100%
    df['Progress'] = df['Progress'].clip(upper=100.0)
    
    return df

def get_summary_stats(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Calculates summary statistics from the processed DataFrame.
    """
    if df.empty:
        return {
            "total_modules": 0,
            "completed_modules": 0,
            "total_hours_ist": 0.0,
            "total_hours_soll": 0.0,
            "overall_progress": 0.0
        }
        
    total_modules = len(df)
    completed_modules = len(df[df['status'] == 'Absolviert'])
    
    total_hours_ist = df['Total_Ist'].sum()
    total_hours_soll = df['Total_Soll'].sum()
    
    # Overall progress is based on module completion count, not hours
    overall_progress = (completed_modules / total_modules * 100) if total_modules > 0 else 0.0
    
    return {
        "total_modules": total_modules,
        "completed_modules": completed_modules,
        "total_hours_ist": total_hours_ist,
        "total_hours_soll": total_hours_soll,
        "overall_progress": overall_progress
    }

def get_cohort_stats(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Calculates statistics across the entire cohort (multiple people).
    """
    if df.empty:
        return {}
        
    people = df['person_name'].unique()
    total_people = len(people)
    
    # Per-Person Progress
    person_progress = []
    for person in people:
        p_df = df[df['person_name'] == person]
        stats = get_summary_stats(p_df)
        person_progress.append({
            "Name": person,
            "Progress": stats['overall_progress'],
            "Completed": stats['completed_modules'],
            "Total": stats['total_modules']
        })
        
    # Module Completion Rates
    # How many people have completed each module?
    module_stats = []
    unique_modules = df[['id', 'title', 'qs_level']].drop_duplicates()
    
    for _, row in unique_modules.iterrows():
        mid = row['id']
        m_title = row['title']
        qs = row['qs_level']
        
        # Get all records for this module
        mod_records = df[df['id'] == mid]
        
        total_attempts = len(mod_records)
        completed = len(mod_records[mod_records['status'] == 'Absolviert'])
        
        rate = (completed / total_attempts * 100) if total_attempts > 0 else 0.0
        
        module_stats.append({
            "ID": mid,
            "Modul": m_title,
            "QS": qs,
            "Absolventen": completed,
            "Gesamt": total_attempts,
            "Quote": rate
        })
        
    return {
        "total_people": total_people,
        "person_progress": pd.DataFrame(person_progress),
        "module_stats": pd.DataFrame(module_stats)
    }
