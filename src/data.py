import pandas as pd
import numpy as np
from typing import List, Dict, Any

def process_training_data(raw_data: List[Dict[str, Any]]) -> pd.DataFrame:
    """
    Converts raw training data into a structured DataFrame with calculated metrics.
    Uses vectorized operations for performance.
    """
    if not raw_data:
        return pd.DataFrame()
        
    df = pd.DataFrame(raw_data)
    
    # Ensure person_name exists and normalize to short name.
    # The PDF parser may return "Max Müller, geb. 01.01.1990";
    # DB stores just "Max Müller". Always use the short form so that
    # _get_birthday_for_name() lookups work after fresh imports.
    if 'person_name' not in df.columns:
        df['person_name'] = 'Unbekannt'
    else:
        df['person_name'] = df['person_name'].apply(
            lambda x: x.split(',')[0].strip() if isinstance(x, str) and ',' in x else x
        )

    # Calculate Total Hours (Ist and Soll)
    df['Total_Ist'] = df['T_Ist'] + df['P_Ist'] + df['K_Ist']
    df['Total_Soll'] = df['T_Soll'] + df['P_Soll'] + df['K_Soll']
    
    # Calculate Effective Progress (Vectorized)
    # Logic: You cannot compensate missing Practice with extra Theory.
    df['Effective_Ist'] = (
        np.minimum(df['T_Ist'], df['T_Soll']) +
        np.minimum(df['P_Ist'], df['P_Soll']) +
        np.minimum(df['K_Ist'], df['K_Soll'])
    )

    # Calculate Progress Percentage for the MODULE
    # The user requested: "in arbeit ist so wie nicht gemacht" -> 0% Progress unless Absolviert
    mask_completed = df['status'] == 'Absolviert'
    mask_soll = df['Total_Soll'] > 0
    df['Progress'] = 0.0
    
    # Only completed modules get 100%
    df.loc[mask_completed, 'Progress'] = 100.0
    
    # Cap progress at 100% (just in case)
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
    
    # Calculate hours: Soll from ALL modules, Ist from COMPLETED modules only
    total_hours_soll = df['Total_Soll'].sum()
    df_completed = df[df['status'] == 'Absolviert']
    # sum of strictly capped Effective_Ist, not raw Total_Ist, to prevent >100%
    total_hours_ist = df_completed['Effective_Ist'].sum() if not df_completed.empty else 0.0
    
    # Overall progress is based on hours (Ist of Absolviert vs Soll of ALL)
    # This correctly gives weight to larger modules.
    if total_hours_soll > 0:
        overall_progress = int(round((total_hours_ist / total_hours_soll) * 100))
    else:
        # If there are no required hours at all, count completed modules
        overall_progress = int(round((completed_modules / total_modules) * 100)) if total_modules > 0 else 0
        
    overall_progress = min(100, overall_progress) # Cap at 100 just in case
    
    return {
        "total_modules": total_modules,
        "completed_modules": completed_modules,
        "total_hours_ist": total_hours_ist,
        "total_hours_soll": total_hours_soll,
        "overall_progress": overall_progress
    }
