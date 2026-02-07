import streamlit as st
import pandas as pd
import sys
import os

# Add current directory to path so we can import src
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.parser import extract_data_from_pdf
from src.data import process_training_data, get_summary_stats

st.set_page_config(page_title="Ausbildungs-Tracker", page_icon="🚒", layout="wide")

# Custom CSS for better "Profile Cards"
st.markdown("""
<style>
    .profile-card {
        padding: 1.5rem;
        border-radius: 0.75rem;
        background-color: #f8f9fa;
        border: 1px solid #e9ecef;
        margin-bottom: 1rem;
        transition: transform 0.2s;
    }
    .profile-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
    }
</style>
""", unsafe_allow_html=True)

st.title("🚒 Ausbildungs-Tracker")

if 'df' not in st.session_state:
    st.session_state.df = None
if 'selected_person' not in st.session_state:
    st.session_state.selected_person = None

uploaded_file = st.sidebar.file_uploader("PDF Datei hochladen", type=["pdf"])

if uploaded_file is not None:
    @st.cache_data
    def load_data(file):
        raw = extract_data_from_pdf(file)
        return process_training_data(raw)

    try:
        df = load_data(uploaded_file)
        st.session_state.df = df
    except Exception as e:
        st.error(f"Fehler beim Analysieren der Datei: {e}")

if st.session_state.df is not None:
    df = st.session_state.df
    valid_people = sorted([p for p in df['person_name'].unique() if p != "Unknown"])
    
    # Navigation Sidebar
    st.sidebar.header("Menü")
    if st.sidebar.button("🏠 Gruppen-Übersicht"):
        st.session_state.selected_person = None
        st.rerun()

    st.sidebar.divider()
    st.sidebar.subheader("Schnell-Suche")
    search_query = st.sidebar.text_input("Name eingeben...", key="sidebar_search")
    
    if search_query:
        matches = [p for p in valid_people if search_query.lower() in p.lower()]
        if matches:
            for p in matches[:5]: # Show top 5 in sidebar
                if st.sidebar.button(p, key=f"btn_{p}"):
                    st.session_state.selected_person = p
                    st.rerun()
            if len(matches) > 5:
                st.sidebar.caption(f"...und {len(matches)-5} weitere")
    
    # Main Page Logic
    if st.session_state.selected_person is None:
        # --- DASHBOARD ---
        st.header("📊 Gruppen-Übersicht")
        
        # 1. Participants Table with Selection
        st.subheader("Teilnehmer (Klicken zur Detailansicht)")
        
        person_stats = []
        for p in valid_people:
            p_df = df[df['person_name'] == p]
            overall_stats = get_summary_stats(p_df)
            qs1_stats = get_summary_stats(p_df[p_df['qs_level'].astype(str).str.contains("QS1")])
            qs2_stats = get_summary_stats(p_df[p_df['qs_level'].astype(str).str.contains("QS2")])
            person_stats.append({
                "Name": p,
                "Gesamt %": overall_stats['overall_progress'],
                "QS1 %": qs1_stats['overall_progress'],
                "QS2 %": qs2_stats['overall_progress'],
                "Module": f"{overall_stats['completed_modules']}/{overall_stats['total_modules']}"
            })
        
        stats_df = pd.DataFrame(person_stats)
        
        # Interactive Dataframe for selection
        selected_rows = st.dataframe(
            stats_df,
            column_config={
                "Gesamt %": st.column_config.ProgressColumn("Gesamt", format="%.0f%%", min_value=0, max_value=100),
                "QS1 %": st.column_config.ProgressColumn("QS1", format="%.0f%%", min_value=0, max_value=100),
                "QS2 %": st.column_config.ProgressColumn("QS2", format="%.0f%%", min_value=0, max_value=100),
            },
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row"
        )
        
        if selected_rows and len(selected_rows.selection.rows) > 0:
            idx = selected_rows.selection.rows[0]
            st.session_state.selected_person = stats_df.iloc[idx]['Name']
            st.rerun()

        # 2. Module Stats
        st.divider()
        st.subheader("Modul-Statistik (Erfolgsquote)")
        
        # Fix FutureWarning: include_groups=False
        mod_stats = df.groupby(['id', 'title', 'qs_level'], as_index=False).apply(
            lambda x: pd.Series({
                'Absolventen': len(x[x['status'] == 'Absolviert']),
                'Gesamt': len(x),
                'Quote': (len(x[x['status'] == 'Absolviert']) / len(x) * 100) if len(x) > 0 else 0
            }),
            include_groups=False
        )
        
        mod_stats = mod_stats.rename(columns={'id': 'ID', 'title': 'Modul', 'qs_level': 'QS-Stufe'})
        
        st.dataframe(
            mod_stats,
            column_config={
                "Quote": st.column_config.ProgressColumn("Quote", format="%.0f%%", min_value=0, max_value=100)
            },
            use_container_width=True,
            hide_index=True
        )

    else:
        # --- INDIVIDUAL VIEW ---
        person = st.session_state.selected_person
        
        # Header with Back button
        col_back, col_title = st.columns([1, 10])
        if col_back.button("⬅️"):
            st.session_state.selected_person = None
            st.rerun()
        col_title.header(f"Ausbildungsstand: {person}")
        
        p_df = df[df['person_name'] == person].copy()
        
        # Metadata
        if not p_df.empty:
            first_row = p_df.iloc[0]
            meta_cols = [c for c in p_df.columns if c.startswith("meta_") and pd.notna(first_row[c])]
            if meta_cols:
                cols = st.columns(len(meta_cols))
                for i, col in enumerate(meta_cols):
                    with cols[i % len(cols)]:
                        st.info(f"**{col.replace('meta_', '')}**\n\n{first_row[col].split(' ', 1)[1] if ' ' in first_row[col] else first_row[col]}")

        stats = get_summary_stats(p_df)
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Gesamtfortschritt", f"{stats['overall_progress']:.1f}%")
        m2.metric("Absolvierte Module", f"{stats['completed_modules']} / {stats['total_modules']}")
        m3.progress(stats['overall_progress']/100)
        
        # Detailed Tabs
        priority = {"QS1": 0, "QS2": 1, "QS3": 2, "Ergänzungsmodule": 3}
        unique_levels = p_df['qs_level'].unique()
        qs_levels = sorted(unique_levels, key=lambda x: priority.get(str(x).split(' - ')[0], 99))
        
        tabs = st.tabs([str(l) for l in qs_levels] + ["Alle"])
        
        cfg = {
            "Progress": st.column_config.ProgressColumn("Erfüllung (T/P/K)", format="%.0f%%", min_value=0, max_value=100),
            "status": "Status", "title": "Modul", "id": "ID",
            "T_Ist": st.column_config.NumberColumn("T (Ist)", format="%.1f h"),
            "T_Soll": st.column_config.NumberColumn("T (Soll)", format="%.1f h"),
            "P_Ist": st.column_config.NumberColumn("P (Ist)", format="%.1f h"),
            "P_Soll": st.column_config.NumberColumn("P (Soll)", format="%.1f h"),
            "K_Ist": st.column_config.NumberColumn("K (Ist)", format="%.1f h"),
            "K_Soll": st.column_config.NumberColumn("K (Soll)", format="%.1f h"),
        }
        cols = ['id', 'title', 'status', 'Progress', 'T_Ist', 'T_Soll', 'P_Ist', 'P_Soll', 'K_Ist', 'K_Soll']

        for i, level in enumerate(qs_levels):
            with tabs[i]:
                subset = p_df[p_df['qs_level'] == level]
                st.dataframe(subset[cols], use_container_width=True, column_config=cfg, hide_index=True)
        
        with tabs[-1]:
            st.dataframe(p_df[['qs_level'] + cols], use_container_width=True, column_config=cfg, hide_index=True)

else:
    st.info("Bitte laden Sie eine MGA-Übersicht (PDF) hoch, um zu beginnen.")
