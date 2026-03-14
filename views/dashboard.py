import streamlit as st
import pandas as pd
from datetime import datetime
from src.database import get_connection
import logging

logger = logging.getLogger(__name__)

st.title("🚒 FeuerProfi - Dashboard")

st.markdown("""
Willkommen bei **FeuerProfi**! Deinem zentralen Hub für die Verwaltung von Ausbildungsständen, 
Personalübersichten und der intelligenten Gruppen-Einteilung deiner Feuerwehr.
""")

# --- QUICK STATS ---
try:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as c FROM participants WHERE unit_id = 1")
    total_persons = c.fetchone()['c']
    
    c.execute("""
        SELECT COUNT(*) as c 
        FROM module_history mh 
        JOIN participants p ON mh.participant_id = p.id 
        WHERE p.unit_id = 1
    """)
    total_modules = c.fetchone()['c']
    
    # Letzter Upload
    c.execute("SELECT upload_date FROM uploads ORDER BY id DESC LIMIT 1")
    last_ul = c.fetchone()
    last_upload_str = last_ul['upload_date'] if last_ul else "Noch kein Upload"
    
except Exception as e:
    logger.error(f"Fehler beim Laden der Dashboard-Statistiken: {e}")
    total_persons = 0
    total_modules = 0
    last_upload_str = "Fehler beim Laden"

st.divider()

col1, col2, col3 = st.columns(3)
with col1:
    st.metric(label="👥 Erfasstes Personal", value=total_persons)
with col2:
    st.metric(label="📚 Dokumentierte Ausbildungen", value=total_modules)
with col3:
    st.metric(label="⏱️ Letztes Daten-Update", value=last_upload_str.split(' ')[0] if ' ' in last_upload_str else last_upload_str)

st.divider()

# --- CHARTS ---
st.subheader("📊 Ausbildungs-Übersicht")
try:
    c.execute("""
        SELECT 
            -- Exclusive counts matching the 'Nächster Schritt' MGLA logic logic
            SUM(CASE WHEN pqs.qs1_done = 0 OR pqs.qs1_done IS NULL THEN 1 ELSE 0 END) as in_qs1,
            SUM(CASE WHEN pqs.qs1_done = 1 AND (pqs.qs2_done = 0 OR pqs.qs2_done IS NULL) THEN 1 ELSE 0 END) as in_qs2,
            SUM(CASE WHEN pqs.qs1_done = 1 AND pqs.qs2_done = 1 AND (pqs.qs3_done = 0 OR pqs.qs3_done IS NULL) THEN 1 ELSE 0 END) as in_qs3,
            -- Cumulative count for 'Einsatzbereitschaft' (anyone with at least QS1)
            SUM(CASE WHEN pqs.qs1_done = 1 THEN 1 ELSE 0 END) as qs1_cumulative,
            COUNT(p.id) as total
        FROM participants p
        LEFT JOIN person_qs_status pqs ON p.id = pqs.participant_id
        WHERE p.unit_id = 1 AND p.name != 'Unknown'
    """)
    qs_data = c.fetchone()
    if qs_data and qs_data['total'] > 0:
        c1, c2 = st.columns([2, 1])
        with c1:
            total_qs = (qs_data['in_qs1'] or 0) + (qs_data['in_qs2'] or 0) + (qs_data['in_qs3'] or 0)
            st.write(f"**Aktuelle Qualifikationsstufen (QS)** (Gesamt: {total_qs})")
            chart_data = pd.DataFrame({
                "Stufe": ["QS1", "QS2", "QS3"],
                "Anzahl": [
                    qs_data['in_qs1'] or 0, 
                    qs_data['in_qs2'] or 0, 
                    qs_data['in_qs3'] or 0
                ]
            })
            st.bar_chart(chart_data, x="Stufe", y="Anzahl", color="#d32f2f")
            
        with c2:
            st.write("**Einsatzbereitschaft**")
            ready = qs_data['qs1_cumulative'] or 0
            not_ready = qs_data['total'] - ready
            
            st.progress(ready / qs_data['total'] if qs_data['total'] > 0 else 0, text=f"{ready} von {qs_data['total']} einsatzbereit")
            st.caption("Personen mit abgeschlossener QS1 gelten als einsatzbereit.")
            
            from src.database import get_promotion_config
            p_cfg = get_promotion_config(1)
            
            c.execute("""
                SELECT 
                    p.name, 
                    CASE 
                        WHEN pqs.qs1_done = 0 OR pqs.qs1_done IS NULL THEN 'QS1'
                        WHEN pqs.qs2_done = 0 THEN 'QS2'
                        WHEN pqs.qs3_done = 0 THEN 'QS3'
                    END as waiting_for,
                    SUM(CASE WHEN mh.status = 'Absolviert' THEN 1 ELSE 0 END) * 100.0 / COUNT(mh.id) as progress
                FROM participants p
                LEFT JOIN person_qs_status pqs ON p.id = pqs.participant_id
                JOIN module_history mh ON p.id = mh.participant_id
                JOIN modules m ON mh.module_id = m.id
                WHERE p.unit_id = 1 AND p.name != 'Unknown' AND m.qs_level = (
                    CASE 
                        WHEN pqs.qs1_done = 0 OR pqs.qs1_done IS NULL THEN 'QS1'
                        WHEN pqs.qs2_done = 0 THEN 'QS2'
                        WHEN pqs.qs3_done = 0 THEN 'QS3'
                    END
                )
                GROUP BY p.name, waiting_for
                HAVING progress >= (
                    CASE waiting_for 
                        WHEN 'QS1' THEN ? 
                        WHEN 'QS2' THEN ? 
                        WHEN 'QS3' THEN ? 
                    END
                )
            """, (p_cfg.get('qs1_threshold', 90), p_cfg.get('qs2_threshold', 90), p_cfg.get('qs3_threshold', 100)))
            ready_for_upgrade = c.fetchall()
            if ready_for_upgrade:
                st.write("**Bereit für Prüfung/Hochstufung**")
                for u in ready_for_upgrade:
                    st.success(f"🎓 **{u['name']}** ({u['waiting_for']})")
except Exception as e:
    st.warning("Diagramme konnten nicht geladen werden.")
    logger.error(f"Chart Error: {e}")

st.divider()

# --- FEATURES ---
st.subheader("🚀 Kernfunktionen & Navigation")

c1, c2 = st.columns(2)

with c1:
    st.info("#### 👨‍🚒 Personal\nVerwalte die Stammdaten aller Kameradinnen und Kameraden. Trage Einsatz- und Dienststunden ein und analysiere den individuellen Ausbildungsstand im Detail.")
    st.success("#### 🧑‍🤝‍🧑 Gruppen-Einteilung\nNutze unseren intelligenten Algorithmus, um dein Personal fair und gleichmäßig auf Gruppen aufzuteilen. Der Algorithmus balanciert dabei kritische Qualifikationen (z.B. Atemschutz) und geleistete Stunden automatisch aus.")

with c2:
    st.warning("#### 🚒 MGLA (PDF & FeuerOn)\nImportiere die offiziellen Ausbildungs-PDFs oder verbinde dich direkt mit der FeuerOn API. Alle Ausbildungen und Qualifikationsstufen (QS1-QS3) werden automatisch ausgelesen und in der Datenbank aktualisiert.")
    st.error("#### 📋 Einsatzberichte\nDirekt auf dem Tablet im Fahrzeug einsetzbar! Dokumentiere Einsätze unmittelbar am Einsatzende, weise das Personal den Sitzplätzen zu und lass den fertigen Bericht automatisch per E-Mail an die Führungskräfte versenden.")

st.divider()

# --- GETTING STARTED ---
st.subheader("📖 Erste Schritte")
with st.expander("Wie starte ich mit FeuerProfi?", expanded=False):
    st.markdown("""
    1. **FeuerOn konfigurieren:** Gehe in der Navigation auf **MGLA (Admin)** und scrolle nach unten zu *FeuerOn Zugangsdaten*. Trage dort deine Organisations-ID und deine Logindaten ein. Speichere die Konfiguration.
    2. **Daten importieren:** Klicke ebenfalls im Bereich **MGLA (Admin)** oben bei *Daten-Upload* auf den Button **Ausbildungsmodule jetzt herunterladen**, um den automatischen Sync zu starten. Alternativ kannst du dort auch ein System-PDF manuell hochladen.
    3. **Personal prüfen:** Wechsle links im Menü in den Tab **Personal**. Hier siehst du nun alle importierten Personen deiner Einheit. Du kannst manuell Einsatzstunden oder Dienststunden eintragen oder einzelne Personen anklicken, um zu sehen, wer welche Module (z.B. QS1, QS2) abgeschlossen hat.
    4. **Gruppen einteilen:** Gehe zu **Gruppen-Einteilung**. Definiere wie viele Gruppen du brauchst und welche Ausbildungen (z.B. *Atemschutzgeräteträger*) zwingend gleichmäßig auf alle Gruppen verteilt werden sollen. Nutze die Whitelist oder Blacklist für Ausnahmen. Klicke auf *Neu zuweisen* und exportiere das Ergebnis bei Bedarf komplett als Excel-Datei.
    5. **Einsätze dokumentieren:** Nutze **Einsatzbericht** für die schnelle Erfassung von Einsätzen direkt nach Einrücken noch im Fahrzeug.
    6. **Backups & Sicherheit:** Unter **Einstellungen** kannst du jederzeit ein manuelles Backup der vollständigen Datenbank erstellen. FeuerProfi sichert zudem jede Nacht um 0:00 Uhr automatisch ein Backup für dich (die letzten 14 Tage werden vorgehalten).
    """)
