import streamlit as st
import pandas as pd
import datetime
import time
from src.database import (
    get_participants_with_qualifications,
    get_qualifications,
    assign_qualification,
    remove_qualification,
    update_person_hours,
    delete_expired_participants,
    touch_participant,
    delete_participant,
    get_stundennachweis_zeitraum,
    update_stundennachweis_zeitraum,
    update_participant_hours as update_db_participant_hours
)
from src.parser import parse_stundennachweis_excel

# Aufräumen abgelaufener Personen (360 Tage inaktiv) bevor die Liste geladen wird
delete_expired_participants(360)

st.title("👥 Personalverwaltung")
st.info("Übersicht aller Personen und ihrer zugewiesenen Ausbildungen. Du kannst hier manuell Ausbildungen in der Tabelle hinzufügen oder entfernen.")

# Verstecke die Plus/Minus Buttons in den numereischen Eingabefeldern
st.markdown("""
    <style>
        input[type="number"]::-webkit-inner-spin-button, 
        input[type="number"]::-webkit-outer-spin-button {
            -webkit-appearance: none;
            margin: 0;
        }
        input[type="number"] {
            -moz-appearance: textfield;
        }
    </style>
""", unsafe_allow_html=True)
# Lade alle nötigen Daten aus der Datenbank
db_participants = get_participants_with_qualifications()
all_quals = get_qualifications()
qual_names = [q['name'] for q in all_quals]
name_to_id = {q['name']: q['id'] for q in all_quals}

# Merge with Session State DataFrame to ensure we see everyone from MGLA
participants_dict = {f"{p['name']} ({p['birthday']})": p for p in db_participants}

if st.session_state.get('df') is not None:
    df = st.session_state.df
    # Performance-Optimierung: Nicht über 15.000 Modul-Zeilen iterieren, sondern nur über eindeutige Personen
    cols = ['person_name']
    if 'birthday' in df.columns: cols.append('birthday')
    
    unique_persons = df[cols].drop_duplicates() if 'person_name' in df.columns else pd.DataFrame()
    
    for _, row in unique_persons.iterrows():
        p_name_raw = row.get('person_name', 'Unknown')
        if p_name_raw != "Unknown":
            name = p_name_raw.split(',')[0].strip()
            birthday = str(row.get('birthday', 'Unknown')).strip()
            
            if birthday == "Unknown" and "geb." in p_name_raw:
                try:
                    birthday = p_name_raw.split('geb.')[1].split(',')[0].strip()
                except: pass
            
            key = f"{name} ({birthday})"
            if key not in participants_dict:
                # Add a dummy participant record for display
                # We save it to DB so they have an ID for qualifications
                from src.database import get_connection
                conn = get_connection()
                try:
                    c = conn.cursor()
                    if birthday == "Unknown":
                        continue
                        
                    c.execute("INSERT OR IGNORE INTO participants (name, birthday, unit_id) VALUES (?, ?, ?)", (name, birthday, 1))
                    conn.commit()
                    # Re-fetch the specific assigned ID
                    c.execute("SELECT id FROM participants WHERE name=? AND birthday=?", (name, birthday))
                    row = c.fetchone()
                    if not row:
                        continue
                    new_id = row['id']
                    
                    participants_dict[key] = {
                        'id': new_id,
                        'name': name,
                        'birthday': birthday,
                        'qualifications': [],
                        'einsatzstunden': 0.0,
                        'dienststunden': 0.0,
                        'last_seen': str(datetime.date.today()),
                        'qs_level': '-',
                        'qs1_done': 0,
                        'qs2_done': 0,
                        'qs3_done': 0
                    }
                finally:
                    conn.close()

# Convert back to list
participants = list(participants_dict.values())

def calc_age(bday_str: str) -> str:
    if not bday_str or bday_str == "Unknown": return "?"
    try:
        bday = datetime.datetime.strptime(bday_str, "%d.%m.%Y").date()
        today = datetime.date.today()
        age = today.year - bday.year - ((today.month, today.day) < (bday.month, bday.day))
        return str(age)
    except:
        return "?"

def calc_expiry(ls_str: str) -> str:
    if not ls_str: return "-"
    try:
        ls_date = datetime.datetime.strptime(ls_str, "%Y-%m-%d").date()
        delta = (ls_date + datetime.timedelta(days=360)) - datetime.date.today()
        days_left = delta.days
        if days_left < 30: return f"🔴 {days_left}d"
        return f"🟢 {days_left}d"
    except:
        return "-"

if not participants:
    st.warning("Keine Teilnehmer in der Datenbank gefunden.")
else:
    st.markdown("---")
    
    # Stundennachweis Upload
    with st.expander("🕒 Stundennachweis (Excel) hochladen"):
        # We assume unit_id = 1 for now (globally used in this app)
        current_unit = 1 
        last_period = get_stundennachweis_zeitraum(current_unit)
        if last_period:
            st.info(f"Derzeit hinterlegter Zeitraum für Einsatz/Dienststunden: **{last_period}**")
        else:
            st.info("Bisher wurde kein Zeitraum hinterlegt.")
            
        uploaded_file = st.file_uploader("Wähle die Datei 'Stundennachweis...'", type=["xlsx", "xls"], key="stunden_upl")
        if uploaded_file is not None:
            if st.button("Stunden aus Excel einlesen und überschreiben", type="primary"):
                with st.spinner("Lese Stunden ein..."):
                    zeitraum, hour_mapping = parse_stundennachweis_excel(uploaded_file.getvalue())
                    
                    if not hour_mapping:
                        st.error("Fehler beim Lesen. Bitte prüfe das Excel-Format.")
                    else:
                        match_count = 0
                        new_persons = 0
                        diff_count = 0
                        
                        # Update DB
                        if zeitraum:
                            update_stundennachweis_zeitraum(current_unit, zeitraum)
                            
                        # Existing keys to skip DB checks if possible
                        existing_keys = {(p['name'], p['birthday']) for p in participants}
                        
                        from src.database import get_connection
                        
                        for key, hours in hour_mapping.items():
                            name, bday = key
                            einsatz = hours["einsatzstunden"]
                            dienst = hours["dienststunden"]
                            
                            # Find old values if person exists
                            old_e, old_d = 0.0, 0.0
                            person_existed = False
                            for p in participants:
                                if p['name'] == name and p['birthday'] == bday:
                                    old_e = float(p.get('einsatzstunden') or 0.0)
                                    old_d = float(p.get('dienststunden') or 0.0)
                                    person_existed = True
                                    break
                            
                            # Auto-Create Person if unknown
                            if not person_existed:
                                try:
                                    conn = get_connection()
                                    c = conn.cursor()
                                    c.execute("INSERT OR IGNORE INTO participants (name, birthday, unit_id) VALUES (?, ?, ?)", (name, bday, current_unit))
                                    conn.commit()
                                    if c.rowcount > 0:
                                        new_persons += 1
                                finally:
                                    conn.close()
                            else:
                                # Report differences if old values were not 0 
                                # (If old values are 0, it is either a new person or just someone who previously had no hours, so no "difference" warning needed)
                                if (old_e > 0.0 or old_d > 0.0) and (old_e != einsatz or old_d != dienst):
                                    st.toast(f"ℹ️ {name}: Zeiten aktualisiert (Einsatz: {old_e} ➔ {einsatz}, Dienst: {old_d} ➔ {dienst})", icon="ℹ️")
                                    diff_count += 1
                                    
                            if update_db_participant_hours(current_unit, name, bday, einsatz, dienst):
                                match_count += 1
                                    
                        st.success(f"Erfolgreich! {match_count} aktualisiert, {new_persons} neu angelegt, {diff_count} mit Abweichungen zum Vorwert.")
                        time.sleep(4)
                        if "stunden_upl" in st.session_state:
                            del st.session_state["stunden_upl"]
                        st.rerun()
                        
    st.markdown("---")
    # Such-Filter
    search = st.text_input("🔍 Person suchen", "")
    st.markdown("---")
    
    # Filtere Liste einmal im Backend
    filtered_participants = [p for p in participants if not search or search.lower() in p['name'].lower()]
    
    # Kopfzeile
    c_name, c_bday, c_qs, c_exp, c_e, c_d, c_aus, c_del = st.columns([1.5, 1, 0.8, 0.8, 0.8, 0.8, 2, 0.5])
    c_name.markdown("**Name**")
    c_bday.markdown("**Geburtstag (Alter)**")
    c_qs.markdown("**QS-Stufe**")
    c_exp.markdown("**Ablauf in**")
    c_e.markdown("**Einsatzstd.**")
    c_d.markdown("**Dienststd.**")
    c_aus.markdown("**Ausbildungen**")
    c_del.markdown("**Aktion**")
    st.markdown("---")
    
    # Callbacks für automatisches Speichern
    def on_hours_change(p_id, old_e, old_d, e_key, d_key):
        new_e = st.session_state[e_key]
        new_d = st.session_state[d_key]
        if new_e != old_e or new_d != old_d:
            update_person_hours(p_id, new_e, new_d)

    def on_quals_change(p_id, old_quals, key, name_to_id_map):
        new_quals = st.session_state[key]
        added = set(new_quals) - set(old_quals)
        removed = set(old_quals) - set(new_quals)
        
        changed = False
        for qname in added:
            assign_qualification(p_id, name_to_id_map[qname])
            changed = True
        for qname in removed:
            remove_qualification(p_id, name_to_id_map[qname])
            changed = True
            
        if changed:
            touch_participant(p_id)
            
    # Raster zeichnen
    for p in filtered_participants:
        c_name, c_bday, c_qs, c_exp, c_e, c_d, c_aus, c_del = st.columns([1.5, 1, 0.8, 0.8, 0.8, 0.8, 2, 0.5])
        
        # Stammdaten
        c_name.write(p['name'])
        c_bday.write(f"{p['birthday']} ({calc_age(p['birthday'])})")
        
        # QS-Stufe 
        cur_qs = str(p.get('qs_level', '-'))
        c_qs.write(cur_qs)
        
        # Ablauf
        expiry_str = calc_expiry(p.get('last_seen'))
        c_exp.write(expiry_str)
        
        # Stundenfelder
        e_hrs = float(p.get('einsatzstunden', 0.0) or 0.0)
        d_hrs = float(p.get('dienststunden', 0.0) or 0.0)
        
        e_key = f"e_hrs_{p['id']}"
        d_key = f"d_hrs_{p['id']}"
        
        with c_e:
            st.number_input(
                "Einsatzstd.", value=e_hrs, min_value=0.0, step=0.5, 
                key=e_key, label_visibility="collapsed",
                on_change=on_hours_change, args=(p['id'], e_hrs, d_hrs, e_key, d_key)
            )
        with c_d:
            st.number_input(
                "Dienststd.", value=d_hrs, min_value=0.0, step=0.5, 
                key=d_key, label_visibility="collapsed",
                on_change=on_hours_change, args=(p['id'], e_hrs, d_hrs, e_key, d_key)
            )
            
        # Ausbildungen
        assigned_names = [q['name'] for q in p.get('qualifications', [])]
        quals_key = f"ms_quals_{p['id']}"
        
        with c_aus:
            st.multiselect(
                "Ausbildungen",
                options=qual_names,
                default=assigned_names,
                key=quals_key,
                label_visibility="collapsed",
                on_change=on_quals_change, args=(p['id'], assigned_names, quals_key, name_to_id)
            )
            
        with c_del:
            if st.button("🗑️", key=f"del_btn_{p['id']}", help="Person löschen"):
                delete_participant(p['id'])
                st.rerun()
                
        st.divider()
