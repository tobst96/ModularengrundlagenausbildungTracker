import streamlit as st
from src.utils_ui import apply_custom_design
apply_custom_design()
from datetime import datetime
import json
import time
import pandas as pd
from src.database.incidents import get_vehicles, create_incident_report, get_active_incidents, create_active_incident
from src.database.core import get_connection

def get_all_participants():
    conn = get_connection()
    try:
        rows = conn.execute("SELECT id, name FROM participants ORDER BY name ASC").fetchall()
        return [dict(r) for r in rows]
    except:
        return []
    finally:
        conn.close()

st.title("🚒 Gesamterfassung (Einsatz)")
st.info("Erfasse hier schnell und übersichtlich alle Kräfte für den gesamten Einsatz.")

vehicles = get_vehicles()
participants = get_all_participants()
person_names = ["- Niemand -"] + [p['name'] for p in participants]
vehicle_names = [v['call_sign'] for v in vehicles]
vehicle_id_map = {v['call_sign']: v['id'] for v in vehicles}

if not vehicles or not participants:
    st.warning("Stammdaten fehlen.")
    st.stop()

# --- ALLGEMEINE DATEN ---
with st.container():
    # --- Einsatz-Auswahl (Neu oder Beitreten) ---
    active_incidents = get_active_incidents(1)
    incident_options = ["- Neuen Einsatz anlegen -"] + [f"ID {i['id']}: {i['keyword']} ({i['created_at'][11:16]})" for i in active_incidents]
    selected_inc_str = st.selectbox("Laufenden Einsatz beitreten (Optional)", options=incident_options, key="ge_incident_select")
    
    current_incident_id = None
    default_stichwort = ""
    if selected_inc_str != "- Neuen Einsatz anlegen -":
        current_incident_id = int(selected_inc_str.split(":")[0].replace("ID ", ""))
        inc_data = next((i for i in active_incidents if i['id'] == current_incident_id), None)
        if inc_data:
            default_stichwort = inc_data['keyword']
            st.info(f"Berichte werden dem Einsatz **{default_stichwort}** zugeordnet.")

    stichwort = st.text_input("Einsatzstichwort", value=default_stichwort, key="ge_stichwort", placeholder="z.B. FEU BMA")
    with col2:
        einsatzleiter = st.selectbox("Einsatzleiter", options=person_names, key="ge_einsatzleiter")
        c1, c2 = st.columns(2)
        with c1: vab_cmd = st.toggle("💰 VAB", key="ge_vab_cmd", help="Verdienstausfall")
        with c2: agt_cmd = st.number_input("💨 AGT (Min)", min_value=0, step=5, key="ge_agt_cmd")
    with col3:
        einheitsfuehrer = st.selectbox("Einheitsführer", options=person_names, key="ge_einheitsfuehrer")
        c1, c2 = st.columns(2)
        with c1: vab_ldr = st.toggle("💰 VAB", key="ge_vab_ldr")
        with c2: agt_ldr = st.number_input("💨 AGT (Min)", min_value=0, step=5, key="ge_agt_ldr")

st.divider()

# --- BESCHREIBUNG (Jetzt Section 2) ---
st.subheader("2. Einsatzverlauf", divider="orange")
col_l, col_a = st.columns(2)
with col_l:
    lage = st.text_area("Lage bei Eintreffen", height=150, key="ge_lage")
with col_a:
    taetigkeiten = st.text_area("Maßnahmen & Tätigkeiten", height=150, key="ge_taetigkeiten")

st.divider()

# --- PERSONAL ERFASSUNG (Jetzt Section 3) ---
st.subheader("3. Mannschaft & Fahrzeuge", divider="orange")
st.caption("Füge hier zeilenweise das eingesetzte Personal hinzu. Wähle Fahrzeug, Name und trage Sonderfunktionen/Minuten ein.")

if "ge_table_data" not in st.session_state:
    st.session_state.ge_table_data = [
        {"Fahrzeug": vehicle_names[0], "Name": "- Niemand -", "GF": False, "MA": False, "VAB": False, "AGT_Min": 0}
    ]

# Konfiguration für den Editor
column_config = {
    "Fahrzeug": st.column_config.SelectboxColumn("Fahrzeug 🚒", options=vehicle_names, required=True),
    "Name": st.column_config.SelectboxColumn("Einsatzkraft 👤", options=person_names, required=True),
    "GF": st.column_config.CheckboxColumn("GF 🚩", help="Gruppenführer/Einheitsführer"),
    "MA": st.column_config.CheckboxColumn("MA ⚙️", help="Maschinist"),
    "VAB": st.column_config.CheckboxColumn("VAB 💰", help="Verdienstausfall"),
    "AGT_Min": st.column_config.NumberColumn("AGT 💨 (Min)", min_value=0, step=5, help="Atemschutzminuten")
}

edited_data = st.data_editor(
    st.session_state.ge_table_data,
    column_config=column_config,
    num_rows="dynamic",
    use_container_width=True,
    key="ge_editor",
    hide_index=True
)

st.divider()

if st.button("💾 Alle Berichte speichern & Archivieren", type="primary", use_container_width=True):
    if not stichwort.strip():
        st.error("Bitte ein Stichwort angeben.")
    else:
        # Gruppiere nach Fahrzeugen
        by_vehicle = {}
        valid_rows = [r for r in edited_data if r.get("Name") and r.get("Name") != "- Niemand -"]
        
        for row in valid_rows:
            v = row["Fahrzeug"]
            if v not in by_vehicle: by_vehicle[v] = []
            by_vehicle[v].append(row)
            
        if not by_vehicle:
            st.warning("Keine Personen erfasst.")
        else:
            def get_id_for_name(n):
                if n == "- Niemand -": return None
                for p in participants:
                    if p['name'] == n: return p['id']
                return None

            cmd_id = get_id_for_name(einsatzleiter)
            ldr_id = get_id_for_name(einheitsfuehrer)
            
            # Falls kein Einsatz gewählt wurde: Ersten Master anlegen
            if current_incident_id is None:
                current_incident_id, err_inc = create_active_incident(
                    unit_id=1,
                    keyword=stichwort.strip(),
                    situation=lage.strip(),
                    actions=taetigkeiten.strip(),
                    cmd_id=cmd_id,
                    ldr_id=ldr_id
                )
                if not current_incident_id:
                    st.error(f"Fehler beim Erstellen des Einsatzes: {err_inc}")
                    st.stop()

            success_count = 0
            for v_name, crew_list in by_vehicle.items():
                v_id = vehicle_id_map[v_name]
                # Baue crew_json
                crew_dict = {
                    "commander_vab": vab_cmd,
                    "commander_agt": agt_cmd,
                    "unit_leader_vab": vab_ldr,
                    "unit_leader_agt": agt_ldr
                }
                for idx, p in enumerate(crew_list):
                    # Sanitize inputs to avoid NaN in JSON
                    p_name = str(p.get("Name", "")).strip()
                    p_vab = bool(p.get("VAB", False))
                    try:
                        p_agt = int(p.get("AGT_Min", 0))
                    except:
                        p_agt = 0
                        
                    # Default seat assignment
                    seat_key = f"seat_{idx+1}"
                    # Override based on role if needed for mail compatibility
                    if p.get("GF"): seat_key = "seat_1"
                    elif p.get("MA"): seat_key = "seat_2"
                    
                    crew_dict[seat_key] = {"name": p_name, "vab": p_vab, "agt": p_agt}
                
                ok, err = create_incident_report(
                    keyword=stichwort.strip(),
                    vehicle_id=v_id,
                    commander_id=cmd_id,
                    unit_leader_id=ldr_id,
                    crew_json=json.dumps(crew_dict, ensure_ascii=False),
                    situation=lage.strip(),
                    actions=taetigkeiten.strip(),
                    unit_id=1,
                    incident_id=current_incident_id
                )
                if ok: success_count += 1
                
            if success_count > 0:
                st.success(f"✅ {success_count} Fahrzeug-Einsatzberichte erfolgreich gespeichert!")
                # Reset all fields
                st.session_state.ge_table_data = [{"Fahrzeug": vehicle_names[0], "Name": "- Niemand -", "GF": False, "MA": False, "VAB": False, "AGT_Min": 0}]
                keys_to_reset = [
                    "ge_stichwort", "ge_lage", "ge_taetigkeiten", "ge_einsatzleiter", "ge_einheitsfuehrer",
                    "ge_vab_cmd", "ge_agt_cmd", "ge_vab_ldr", "ge_agt_ldr"
                ]
                for k in keys_to_reset:
                   if k in st.session_state: del st.session_state[k]
                
                time.sleep(1.5)
                st.rerun()
