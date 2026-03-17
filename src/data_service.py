# Data processing and analysis logic for Training Tracker
import pandas as pd
import numpy as np
from typing import List, Dict, Any
import re

def natural_sort_key(s):
    """
    Utility for natural sorting of strings containing numbers (e.g., 1.0, 1.1, 1.2, 2.0, 10.0).
    Returns a tuple for hashability (required for pandas multi-column sorting).
    """
    import re
    return tuple(int(text) if text.isdigit() else text.lower()
                 for text in re.split(r'(\d+)', str(s)))


def get_qs_rank_label(qs1_done: bool, qs2_done: bool, qs3_done: bool) -> str:
    """
    Standardizes the rank label based on QS flags.
    一致性: 
    - QS1 incomplete -> QS1 - Einsatzfähigkeit (Working on QS1)
    - QS1 done, QS2 incomplete -> QS2 - Truppmitglied (Working on QS2)
    - QS2 done, QS3 incomplete -> QS3 - Truppführende/r (Working on QS3)
    - All done -> ✅ Abgeschlossen
    """
    if not qs1_done:
        return "QS1 - Einsatzfähigkeit"
    elif not qs2_done:
        return "QS2 - Truppmitglied"
    elif not qs3_done:
        return "QS3 - Truppführende/r"
    else:
        return "✅ Abgeschlossen"

def get_participant_ranks(unit_id: int = 1) -> Dict[str, str]:
    """
    Returns a mapping of participant names to their current QS-rank.
    Optimized to fetch all data in a single pass.
    """
    from src.db_base import get_connection, get_all_person_qs_status_cached
    
    # Pre-fetch birthdays for identification
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT name, birthday FROM participants WHERE unit_id = ?", (unit_id,))
        name_to_bday = {r['name'].strip(): r['birthday'] for r in c.fetchall()}
    finally:
        conn.close()

    all_qs = get_all_person_qs_status_cached(unit_id)
    
    ranks = {}
    for p_name, bday in name_to_bday.items():
        status = all_qs.get((p_name, bday), {'qs1_done': False, 'qs2_done': False, 'qs3_done': False})
        ranks[p_name] = get_qs_rank_label(status['qs1_done'], status['qs2_done'], status['qs3_done'])
        
    return ranks

def get_lehrgangs_check_matrix(df: pd.DataFrame, selected_ranks: List[str], selected_modules: List[str], unit_id: int = 1) -> pd.DataFrame:
    """
    Generates the status matrix for the Lehrgangs-Check.
    Filters by ranks and modules, then pivots.
    """
    if df.empty or not selected_ranks or not selected_modules:
        return pd.DataFrame()

    # 1. Get rank mapping
    rank_map = get_participant_ranks(unit_id)
    
    # 2. Identify people in selected ranks
    # Processed df has short names in 'person_name'
    all_people = df['person_name'].unique()
    people_at_rank = [p for p in all_people if rank_map.get(p) in selected_ranks]
    
    if not people_at_rank:
        return pd.DataFrame()

    # 3. Pivot logic
    plot_df = df[(df['person_name'].isin(people_at_rank)) & (df['id'].isin(selected_modules))]
    
    if plot_df.empty:
        matrix_df = pd.DataFrame(index=people_at_rank)
    else:
        matrix_df = plot_df.pivot_table(
            index='person_name',
            columns='id',
            values='status',
            aggfunc='first'
        )
        matrix_df = matrix_df.reindex(people_at_rank)

    # Ensure all columns present
    for m in selected_modules:
        if m not in matrix_df.columns:
            matrix_df[m] = "Fehlt"
            
    matrix_df = matrix_df.fillna("Fehlt")
    
    # Add summary column
    matrix_df['Offene Module'] = matrix_df.apply(
        lambda row: sum(1 for v in row if str(v).strip() != "Absolviert"), 
        axis=1
    )
    
    return matrix_df.sort_values(by='Offene Module', ascending=False)

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


