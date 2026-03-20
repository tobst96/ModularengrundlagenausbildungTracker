import streamlit as st
from src.utils_ui import apply_custom_design
apply_custom_design()
from datetime import datetime
from src.database.core import get_connection
from src.database.incidents import get_vehicles, get_active_incidents, create_active_incident, create_incident_report

def get_all_participants():
    """Hilfsfunktion: Lädt alle Personen (nur Name) für die Dropdowns"""
    conn = get_connection()
    try:
        rows = conn.execute("SELECT id, name FROM participants ORDER BY name ASC").fetchall()
        return [dict(r) for r in rows]
    except:
        return []
    finally:
        conn.close()

st.title("🚒 Einsatzbericht")
st.info("Dokumentiere Einsätze und weise das aufgesessene Personal den jeweiligen Funktionen auf dem Fahrzeug zu.")

# Lade Daten aus der Datenbank
vehicles = get_vehicles()
participants = get_all_participants()
person_names = ["- Niemand -"] + [p['name'] for p in participants]

if not vehicles:
    st.warning("Es wurden noch keine Fahrzeuge angelegt. Bitte wechsle zu 'Einstellungen', um Fahrzeuge hinzuzufügen.")
    st.stop()
if not participants:
    st.warning("Es ist kein Personal in der Datenbank vorhanden (bitte MGLA / FeuerOn Sync nutzen).")
    st.stop()

# --- EINGABEFORMULAR ---
with st.container():
    current_incident_id = None
    
    default_stichwort = ""

    # Vehicle Selection (Outside form, so changing it re-runs context)
    vehicle_dict = {f"{v['call_sign']} ({v['seats']} Plätze)": v for v in vehicles}
    
    # Falls via Token angemeldet, wähle das Fahrzeug vor und sperre es
    is_token_auth = st.session_state.get('is_token_auth', False)
    default_idx = 0
    if is_token_auth:
        token_v_id = st.session_state.get('token_vehicle_id')
        token_v_name = st.session_state.get('token_vehicle_name')
        for i, (k, v) in enumerate(vehicle_dict.items()):
            if v['id'] == token_v_id:
                default_idx = i
                break
                
    selected_v_name = st.selectbox("Eingesetztes Fahrzeug", options=list(vehicle_dict.keys()), index=default_idx, disabled=is_token_auth)
    selected_vehicle = vehicle_dict[selected_v_name]
    num_seats = selected_vehicle['seats']

    # --- Einsatz-Auswahl (Optional) ---
    active_incidents = get_active_incidents(1)
    incident_options = ["- Neuer Einsatz -"] + [f"ID {i['id']}: {i['keyword']} ({i['created_at'][11:16]})" for i in active_incidents]
    selected_inc_str = st.selectbox("An bestehenden Einsatz anschließen?", options=incident_options, help="Falls dies ein zweites Fahrzeug für einen laufenden Einsatz ist, wähle ihn hier aus.")
    
    if selected_inc_str != "- Neuer Einsatz -":
        try:
            inc_id = int(selected_inc_str.split(":")[0].replace("ID ", ""))
            current_incident_id = inc_id
            # Stichwort vorbelegen
            for inc in active_incidents:
                if inc['id'] == inc_id:
                    default_stichwort = inc['keyword']
                    break
        except: pass

    # We create the form for the actual report details
    with st.form("incident_report_form", clear_on_submit=False, border=False):
        col_l1, col_l2 = st.columns(2)
        with col_l1:
            st.selectbox("Einsatzleiter 🧑‍⚖️", options=person_names, key="eb_einsatzleiter")
            c1, c2 = st.columns(2)
            with c1: st.toggle("VAB 💰", key="vab_commander", help="Verdienstausfall")
            with c2: st.number_input("AGT 💨 (Min)", min_value=0, step=5, key="agt_commander")
            
        with col_l2:
            st.selectbox("Einheitsführer 🚩", options=person_names, key="eb_einheitsfuehrer")
            c1, c2 = st.columns(2)
            with c1: st.toggle("VAB 💰", key="vab_unit_leader")
            with c2: st.number_input("AGT 💨 (Min)", min_value=0, step=5, key="agt_unit_leader")

        st.divider()

        # --- SITZPLÄTZE (Dynamisch) ---
        st.subheader(f"Besatzung: {selected_vehicle['call_sign']}", divider="orange")

        # Generiere exakt so viele Dropdowns wie das Fahrzeug Sitze hat
        cols = st.columns(2) # 2 statt 3 Spalten für mehr Platz pro Person
        for i in range(1, num_seats + 1):
            col_idx = (i - 1) % 2
            with cols[col_idx]:
                if i == 1:
                    label = "Platz 1: Gruppenführer / Einheitsführer"
                elif i == 2:
                    label = "Platz 2: Maschinist"
                else:
                    label = f"Platz {i}: Besatzung"
                
                # Container für bessere Optik
                with st.container(border=True):
                    st.selectbox(label, options=person_names, key=f"seat_{i}")
                    sub_col1, sub_col2 = st.columns([1, 1])
                    with sub_col1:
                        st.toggle("💰 VAB", key=f"vab_seat_{i}", help="Verdienstausfall")
                    with sub_col2:
                        st.number_input("💨 AGT (Min)", min_value=0, step=5, key=f"agt_seat_{i}", help="Atemschutz-Minuten")

        st.divider()

        # --- EINSATZ DETAILS ---
        st.subheader("Einsatz-Details", divider="orange")
        stichwort = st.text_input("Einsatzstichwort (z.B. F_BMA, H_Y_Gefahr)", value=default_stichwort, placeholder="Stichwort eingeben...", key="eb_stichwort")
        
        lage = st.text_area("Lage bei Eintreffen", height=150, placeholder="Kurze Beschreibung der Situation beim Ankommen an der Einsatzstelle...", key="eb_lage")
        taetigkeiten = st.text_area("Tätigkeiten", height=200, placeholder="Ausgeführte Maßnahmen, eingesetztes Gerät, vorgehende Trupps...", key="eb_taetigkeiten")

        st.divider()

        save_btn = st.form_submit_button("💾 Bericht abschließen und archivieren", type="primary", use_container_width=True)

    from src.database.incidents import get_active_incidents, close_incident
    import json
    import time

    if save_btn:
        final_stichwort = stichwort.strip()
        if not final_stichwort:
            st.error("Bitte ein Einsatzstichwort angeben.")
        elif not lage.strip() and not taetigkeiten.strip():
            st.error("Bitte Lage bei Eintreffen oder Tätigkeiten ausfüllen.")
        else:
            # Sammle Sitzplatzdaten + VAB + AGT
            # Sammle Sitzplatzdaten + VAB + AGT
            crew_data = {}
            for i in range(1, num_seats + 1):
                nm = st.session_state.get(f"seat_{i}", "- Niemand -")
                vb = st.session_state.get(f"vab_seat_{i}", False)
                at = st.session_state.get(f"agt_seat_{i}", 0)
                crew_data[f"seat_{i}"] = {"name": nm, "vab": vb, "agt": at}
                
            # VAB & AGT für Führungskräfte mitspeichern
            crew_data["commander_vab"] = st.session_state.get("vab_commander", False)
            crew_data["commander_agt"] = st.session_state.get("agt_commander", 0)
            crew_data["unit_leader_vab"] = st.session_state.get("vab_unit_leader", False)
            crew_data["unit_leader_agt"] = st.session_state.get("agt_unit_leader", 0)
                
            # IDs für Führungskräfte ermitteln (falls ausgewählt)
            def get_id_for_name(n):
                if n == "- Niemand -": return None
                for p in participants:
                    if p['name'] == n: return p['id']
                return None
                
            e_leiter = st.session_state.get("eb_einsatzleiter", "- Niemand -")
            e_fuehrer = st.session_state.get("eb_einheitsfuehrer", "- Niemand -")
            
            cmd_id = get_id_for_name(e_leiter)
            ldr_id = get_id_for_name(e_fuehrer)
            
            # Falls kein Einsatz gewählt wurde oder es ein neuer ist: Master anlegen/finden
            if current_incident_id is None:
                # Wir erstellen einen neuen Master-Eintrag
                new_inc_id, err_inc = create_active_incident(
                    unit_id=selected_vehicle['unit_id'],
                    keyword=final_stichwort,
                    situation=lage.strip(),
                    actions=taetigkeiten.strip(),
                    cmd_id=cmd_id,
                    ldr_id=ldr_id
                )
                if not new_inc_id:
                    st.error(f"Fehler beim Erstellen des Einsatzes: {err_inc}")
                    st.stop()
                current_incident_id = new_inc_id

            ok, err = create_incident_report(
                keyword=final_stichwort,
                vehicle_id=selected_vehicle['id'],
                commander_id=cmd_id,
                unit_leader_id=ldr_id,
                crew_json=json.dumps(crew_data, ensure_ascii=False),
                situation=lage.strip(),
                actions=taetigkeiten.strip(),
                unit_id=selected_vehicle['unit_id'],
                incident_id=current_incident_id
            )
        
            if ok:
                st.toast("Einsatzbericht erfolgreich gespeichert! Mail-Versand ist getriggert.", icon="✅")
                time.sleep(0.8)
                
                # Formular leeren
                keys_to_clear = [
                    "eb_stichwort", "eb_einsatzleiter", "eb_einheitsfuehrer", 
                    "eb_lage", "eb_taetigkeiten", "vab_commander", "vab_unit_leader",
                    "agt_commander", "agt_unit_leader"
                ]
                for i in range(1, num_seats + 1):
                    keys_to_clear.append(f"seat_{i}")
                    keys_to_clear.append(f"vab_seat_{i}")
                    keys_to_clear.append(f"agt_seat_{i}")
                    
                for k in keys_to_clear:
                    if k in st.session_state:
                        del st.session_state[k]
                st.rerun()
            else:
                st.error(f"Fehler beim Speichern: {err}")
