import streamlit as st
from datetime import datetime
from src.database import get_vehicles, get_connection

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
    st.subheader("Allgemeine Einsatzdaten")
    
    stichwort = st.text_input("Einsatzstichwort (z.B. F_BMA, H_Y_Gefahr)", placeholder="Stichwort eingeben...", key="eb_stichwort")
    
    col_v, col_l1, col_l2 = st.columns(3)
    with col_v:
        # Erstelle ein Dictionary für einfaches Nachschlagen der Sitzplätze
        vehicle_dict = {f"{v['call_sign']} ({v['seats']} Plätze)": v for v in vehicles}
        
        # Falls via Token angemeldet, wähle das Fahrzeug vor und sperre es
        is_token_auth = st.session_state.get('is_token_auth', False)
        default_idx = 0
        if is_token_auth:
            token_v_id = st.session_state.get('token_vehicle_id')
            token_v_name = st.session_state.get('token_vehicle_name')
            # Finde Index des vorselektierten Fahrzeugs
            for i, (k, v) in enumerate(vehicle_dict.items()):
                if v['id'] == token_v_id:
                    default_idx = i
                    break
                    
        selected_v_name = st.selectbox("Eingesetztes Fahrzeug", options=list(vehicle_dict.keys()), index=default_idx, disabled=is_token_auth)
        selected_vehicle = vehicle_dict[selected_v_name]
        
    with col_l1:
        einsatzleiter = st.selectbox("Einsatzleiter", options=person_names, key="eb_einsatzleiter")
        
    with col_l2:
        einheitsfuehrer = st.selectbox(
            "Einheitsführer", 
            options=person_names, 
            key="eb_einheitsfuehrer",
            help="Falls ein Ortsbrandmeister da war, ist dieser automatisch Einheitsführer. Ist kein Ortsbrandmeister da, dann einer der beiden Zugführer, andernfalls ist das der 1. eingetroffene ausgebildete Gruppenführer."
        )

st.divider()

# --- SITZPLÄTZE (Dynamisch) ---
st.subheader(f"Besatzung: {selected_vehicle['call_sign']}")
num_seats = selected_vehicle['seats']

# Generiere exakt so viele Dropdowns wie das Fahrzeug Sitze hat
cols = st.columns(3) # 3 Spalten für kompaktere Ansicht
for i in range(1, num_seats + 1):
    col_idx = (i - 1) % 3
    with cols[col_idx]:
        if i == 1:
            label = "Platz 1: Gruppenführer / Einheitsführer"
        elif i == 2:
            label = "Platz 2: Maschinist"
        else:
            label = f"Platz {i}: Truppmitglied / Besatzung"
        
        st.selectbox(label, options=person_names, key=f"seat_{i}")

st.divider()

# --- BESCHREIBUNG ---
st.subheader("Einsatzverlauf")
lage = st.text_area("Lage bei Eintreffen", height=200, placeholder="Kurze Beschreibung der Situation beim Ankommen an der Einsatzstelle...", key="eb_lage")
taetigkeiten = st.text_area("Tätigkeiten", height=250, placeholder="Ausgeführte Maßnahmen, eingesetztes Gerät, vorgehende Trupps...", key="eb_taetigkeiten")

from src.database import create_incident_report
import json
import time

st.divider()

if st.button("💾 Bericht abschließen und archivieren", type="primary", use_container_width=True):
    if not stichwort.strip():
        st.error("Bitte ein Einsatzstichwort angeben.")
    elif not lage.strip() and not taetigkeiten.strip():
        st.error("Bitte Lage bei Eintreffen oder Tätigkeiten ausfüllen.")
    else:
        # Sammle Sitzplatzdaten
        crew_data = {}
        for i in range(1, num_seats + 1):
            val = st.session_state.get(f"seat_{i}", "- Niemand -")
            crew_data[f"seat_{i}"] = val
            
        # IDs für Führungskräfte ermitteln (falls ausgewählt)
        def get_id_for_name(n):
            if n == "- Niemand -": return None
            for p in participants:
                if p['name'] == n: return p['id']
            return None
            
        cmd_id = get_id_for_name(einsatzleiter)
        ldr_id = get_id_for_name(einheitsfuehrer)
        
        ok, err = create_incident_report(
            keyword=stichwort.strip(),
            vehicle_id=selected_vehicle['id'],
            commander_id=cmd_id,
            unit_leader_id=ldr_id,
            crew_json=json.dumps(crew_data, ensure_ascii=False),
            situation=lage.strip(),
            actions=taetigkeiten.strip(),
            unit_id=selected_vehicle['unit_id'] # Wir nehmen unit_id vom Fahrzeug
        )
        
        if ok:
            st.toast("Einsatzbericht erfolgreich gespeichert! Mail-Versand ist getriggert.", icon="✅")
            time.sleep(0.8)
            # Formular leeren
            keys_to_clear = ["eb_stichwort", "eb_einsatzleiter", "eb_einheitsfuehrer", "eb_lage", "eb_taetigkeiten"]
            for i in range(1, num_seats + 1):
                keys_to_clear.append(f"seat_{i}")
                
            for k in keys_to_clear:
                if k in st.session_state:
                    del st.session_state[k]
                    
            st.rerun()
        else:
            st.error(f"Fehler beim Speichern des Berichts: {err}")
