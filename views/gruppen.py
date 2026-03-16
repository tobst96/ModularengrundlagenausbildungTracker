import streamlit as st
from src.utils_ui import apply_custom_design
apply_custom_design()
import pandas as pd
import json
import os
from typing import List, Dict, Any
from src.db_base import get_participants_with_qualifications, get_qualifications
from io import BytesIO

SAVE_FILE = os.path.join("data", "last_assignment.json")

# Lade initial vom Dateisystem falls nicht in der Session
if 'group_assignment' not in st.session_state and os.path.exists(SAVE_FILE):
    try:
        with open(SAVE_FILE, 'r', encoding='utf-8') as f:
            saved_data = json.load(f)
            st.session_state.group_assignment = saved_data.get('groups', [])
            st.session_state.group_names = saved_data.get('group_names', [])
            st.session_state.target_quals = saved_data.get('target_quals', [])
            
            # Wl/Bl Lade-Logik
            st.session_state.whitelist_count = saved_data.get('whitelist_count', 1)
            st.session_state.blacklist_count = saved_data.get('blacklist_count', 1)
            
            # Restore selection into session state dynamically
            wl_g = saved_data.get('wl_groups', [])
            for i, wl_arr in enumerate(wl_g):
                st.session_state[f"wl_{i}"] = wl_arr
                
            bl_g = saved_data.get('bl_groups', [])
            for i, bl_arr in enumerate(bl_g):
                st.session_state[f"bl_{i}"] = bl_arr
                
    except Exception as e:
        st.error(f"Konnte letzte Zuweisung nicht laden: {e}")

st.title("🧑‍🤝‍🧑 Gruppen-Einteilung")
st.info("Teile Teilnehmer automatisch in gleichmäßige Gruppen auf. Du kannst bestimmte Ausbildungen und geleistete Stunden ausbalancieren sowie harte Regeln (Auschluss, White-/Blacklist) definieren.")

# Lade Daten
participants = get_participants_with_qualifications()
all_quals = get_qualifications()
qual_names = [q['name'] for q in all_quals]
participant_names = [p['name'] for p in participants]

if not participants:
    st.warning("Keine Teilnehmer gefunden.")
    st.stop()

# --- Konfigurationsbereich ---
with st.expander("⚙️ Einstellungen für die Gruppen", expanded=True):
    col1, col2 = st.columns(2)
    with col1:
        num_groups = st.number_input("Anzahl der Gruppen", min_value=2, max_value=10, value=2, step=1)
        target_quals = st.multiselect("Diese Ausbildungen gleichmäßig verteilen (höchste Priorität):", options=qual_names)
        
    with col2:
        exclusions = st.multiselect("Ausschluss-Liste (Personen die NICHT eingeteilt werden sollen):", options=participant_names)
        
    if 'whitelist_count' not in st.session_state:
        st.session_state.whitelist_count = 1
    if 'blacklist_count' not in st.session_state:
        st.session_state.blacklist_count = 1
    st.markdown("---")
    st.markdown("**Spezialregeln (optional)**")
    
    col3, col4 = st.columns(2)
    with col3:
        st.markdown("**Whitelist (Immer zusammen)**")
        st.caption("Diese Personen werden garantiert in derselben Gruppe platziert.")
        for i in range(st.session_state.whitelist_count):
            st.multiselect(f"Gehören zusammen {i+1}", options=participant_names, key=f"wl_{i}")
        if st.button("➕ Whitelist-Regel hinzufügen", use_container_width=True):
            st.session_state.whitelist_count += 1
            st.rerun()
            
    with col4:
        st.markdown("**Blacklist (Nie zusammen)**")
        st.caption("Diese Personen dürfen NICHT in derselben Gruppe landen.")
        for i in range(st.session_state.blacklist_count):
            st.multiselect(f"Müssen getrennt werden {i+1}", options=participant_names, key=f"bl_{i}")
        if st.button("➕ Blacklist-Regel hinzufügen", use_container_width=True):
            st.session_state.blacklist_count += 1
            st.rerun()

# Gruppen-Namen editierbar machen
st.markdown("### Gruppennamen")
cols_names = st.columns(num_groups)
group_names = []
for i in range(num_groups):
    with cols_names[i]:
        gname = st.text_input(f"Name Gruppe {i+1}", value=f"Gruppe {i+1}", key=f"gname_{i}")
        group_names.append(gname)

def generate_excel(groups: List[List[Dict[Any, Any]]], group_names: List[str], target_quals: set):
    # Erstellt ein Dataframe für den Excel Export
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for i, group in enumerate(groups):
            if not group: 
                continue
            df_data = []
            for p in group:
                p_quals = [q['name'] for q in p.get('qualifications',[]) if q['name'] in target_quals]
                df_data.append({
                    "Name": p['name'],
                    "Einsatzstunden": p.get('einsatzstunden', 0.0),
                    "Dienststunden": p.get('dienststunden', 0.0),
                    "Ziel-Ausbildungen": len(p_quals),
                    "Ausbildungen (Details)": ", ".join(p_quals)
                })
            df = pd.DataFrame(df_data)
            df.to_excel(writer, sheet_name=group_names[i][:31], index=False) # Excel sheet max length 31
    processed_data = output.getvalue()
    return processed_data

st.markdown("---")
# Buttons
c_btn1, c_btn2 = st.columns([1, 1])
if c_btn1.button("🔄 Personen neu einteilen", type="primary"):
    # ALGORITHMUS
    
    # 1. Filtere ausgeschlossene
    active_pool = [p for p in participants if p['name'] not in exclusions]
    
    # 2. Berechne Scores für jede Person: Wieviele Ziel-Ausbildungen hat sie?
    def get_qual_score(p):
        p_quals = [q['name'] for q in p.get('qualifications', [])]
        return sum(1 for target in target_quals if target in p_quals)
        
    # Sortiere aktiven Pool primär nach Qual-Score (absteigend) und sekundär nach Summe Stunden (absteigend)
    # Damit verteilen wir die 'wichtigsten' (ausbildungsstärksten) und 'fleißigsten' Leute zuerst.
    active_pool.sort(key=lambda x: (get_qual_score(x), x.get('einsatzstunden',0) + x.get('dienststunden',0)), reverse=True)
    
    # 3. Baue leere Gruppenbeschläge
    groups = [ [] for _ in range(num_groups) ]
    
    assigned_names = set()
    
    # Hilfsfunktion: Finde die Gruppe, die am besten geeignet ist (Greedy)
    def find_best_group(pool_of_groups, entities, possible_indices=None):
        if possible_indices is None:
            possible_indices = list(range(len(pool_of_groups)))
            
        b_targets = set()
        for p in entities:
            p_quals = [q['name'] for q in p.get('qualifications', [])]
            for tq in target_quals:
                if tq in p_quals:
                    b_targets.add(tq)
        
        best_idx = possible_indices[0]
        if b_targets:
            # Person(en) haben auszubalancierende Ausbildungen:
            # Prio 1: Wenigste Personen mit DERSELBEN Ausbildung in der Gruppe
            # Prio 2: Wenigste kumulierte Stunden der Personen mit DERSELBEN Ausbildung in der Gruppe
            # Prio 3: Wenigste Gesamtstunden der Gruppe
            # Prio 4: Kleinste Kopfstärke der Gruppe
            best_metrics = None
            for i in possible_indices:
                grp = pool_of_groups[i]
                grp_tq_headcount = 0
                grp_tq_hours = 0.0
                for member in grp:
                    m_quals = [q['name'] for q in member.get('qualifications', [])]
                    for tq in b_targets:
                        if tq in m_quals:
                            grp_tq_headcount += 1
                            grp_tq_hours += member.get('einsatzstunden', 0.0) + member.get('dienststunden', 0.0)
                            
                grp_headcount = len(grp)
                grp_total_hours = sum(m.get('einsatzstunden', 0.0) + m.get('dienststunden', 0.0) for m in grp)
                metrics = (grp_tq_headcount, grp_tq_hours, grp_total_hours, grp_headcount)
                
                if best_metrics is None or metrics < best_metrics:
                    best_metrics = metrics
                    best_idx = i
        else:
            # Person(en) haben KEINE Ziel-Ausbildungen:
            # Prio 1: Gesamtstunden ausbalancieren (Dienst + Einsatz)
            # Prio 2: Kopfstärke
            best_metrics = None
            for i in possible_indices:
                grp = pool_of_groups[i]
                grp_headcount = len(grp)
                grp_total_hours = sum(m.get('einsatzstunden', 0.0) + m.get('dienststunden', 0.0) for m in grp)
                metrics = (grp_total_hours, grp_headcount)
                
                if best_metrics is None or metrics < best_metrics:
                    best_metrics = metrics
                    best_idx = i
                    
        return best_idx
        
    # 4. Whitelist verarbeiten (Blobs)
    wl_groups = []
    for i in range(st.session_state.get('whitelist_count', 1)):
        selected_names = st.session_state.get(f"wl_{i}", [])
        if selected_names:
            wl_groups.append(selected_names)
    
    for names in wl_groups:
        # Finde Objekte
        blob = []
        for n in names:
            matched = [p for p in active_pool if p['name'] == n and p['name'] not in assigned_names]
            if matched:
                blob.append(matched[0])
                assigned_names.add(n)
        
        if blob:
            idx = find_best_group(groups, blob)
            groups[idx].extend(blob)
            
    # 5. Blacklist verarbeiten
    bl_groups = []
    for i in range(st.session_state.get('blacklist_count', 1)):
        selected_names = st.session_state.get(f"bl_{i}", [])
        if selected_names:
            bl_groups.append(selected_names)
            
    for names in bl_groups:
        blobs = []
        for n in names:
            matched = [p for p in active_pool if p['name'] == n and p['name'] not in assigned_names]
            if matched:
                blobs.append(matched[0])
                assigned_names.add(n)
                
        # Verteile sie der Reihe nach auf verschiedene Gruppen, wenn möglich
        bl_group_used = set()
        for b in blobs:
            possible_groups = []
            for i in range(num_groups):
                if i not in bl_group_used:
                    possible_groups.append(i)
                    
            if not possible_groups:
                # Fallback
                possible_groups = list(range(num_groups))
                
            best_sub_idx = find_best_group(groups, [b], possible_indices=possible_groups)
            groups[best_sub_idx].append(b)
            bl_group_used.add(best_sub_idx)

    # 6. Verteile den Rest
    for p in active_pool:
        if p['name'] not in assigned_names:
            idx = find_best_group(groups, [p])
            groups[idx].append(p)
            assigned_names.add(p['name'])
            
    st.session_state.group_assignment = groups
    st.session_state.group_names = group_names
    st.session_state.target_quals = target_quals
    
    # Speichere persistent
    try:
        with open(SAVE_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                "groups": groups,
                "group_names": group_names,
                "target_quals": target_quals,
                "whitelist_count": st.session_state.get('whitelist_count', 1),
                "blacklist_count": st.session_state.get('blacklist_count', 1),
                "wl_groups": wl_groups,
                "bl_groups": bl_groups
            }, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.error(f"Fehler beim Speichern der Einteilung: {e}")

if 'group_assignment' in st.session_state:
    groups = st.session_state.group_assignment
    saved_names = st.session_state.get('group_names', group_names)
    saved_target_quals = st.session_state.get('target_quals', [])
    
    excel_data = generate_excel(groups, saved_names, set(saved_target_quals))
    c_btn2.download_button(
        label="📥 Als Excel herunterladen", 
        data=excel_data, 
        file_name="Gruppeneinteilung.xlsx", 
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    
    st.success("Erfolgreich eingeteilt!")
    
    # Darstellung
    cols = st.columns(len(groups))
    
    for i in range(len(groups)):
        with cols[i]:
            grp = groups[i]
            # Name fallback falls durch Konfig-Änderungen Spalten wegfallen
            g_name = saved_names[i] if i < len(saved_names) else f"Gruppe {i+1}"
            st.markdown(f"### {g_name}")
            st.caption(f"{len(grp)} Personen")
            
            total_e = sum(m.get('einsatzstunden',0.0) for m in grp)
            total_d = sum(m.get('dienststunden',0.0) for m in grp)
            
            st.markdown(f"**E-Std:** {total_e:.2f} | **D-Std:** {total_d:.2f}")
            if saved_target_quals:
                st.markdown("**Ziel-Ausbildungen:**")
                for tq in saved_target_quals:
                    count = sum(1 for m in grp if any(q['name'] == tq for q in m.get('qualifications',[])))
                    if count > 0:
                        st.markdown(f"- {tq}: **{count}**")
                    else:
                        st.markdown(f"- <span style='color: gray'>{tq}: 0</span>", unsafe_allow_html=True)
                
            st.divider()
            
            # Personenliste
            for p in grp:
                p_e = p.get('einsatzstunden',0.0)
                p_d = p.get('dienststunden',0.0)
                p_quals = [q['name'] for q in p.get('qualifications',[]) if q['name'] in saved_target_quals]
                qual_str = f" ({', '.join(p_quals)})" if p_quals else ""
                
                st.markdown(f"- **{p['name']}** <span style='color: gray; font-size: 0.8em;'>[{p_e:.2f}h / {p_d:.2f}h]{qual_str}</span>", unsafe_allow_html=True)
