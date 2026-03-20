import streamlit as st
from src.utils_ui import apply_custom_design
apply_custom_design()
import pandas as pd
import json
from src.db_base import get_connection

st.title("📜 Einsatz-Historie")
import time

col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    st.info("Übersicht aller abgeschlossenen Einsatzberichte.")
with col_h2:
    if st.button("✉️ Jetzt Senden", use_container_width=True, type="primary", help="Versendet alle noch nicht verschickten Berichte sofort."):
        import src.mailer
        import importlib
        importlib.reload(src.mailer)
        with st.spinner("Sende..."):
            ok, msg = src.mailer.trigger_incident_email(1)
            if ok:
                st.success(msg)
                time.sleep(1.5)
                st.rerun()
            else:
                st.error(msg)

# Add simple auth redirect fallback
if st.session_state.get('is_token_auth', False):
    st.error("Token-User haben keinen Zugriff auf das Archiv.")
    st.stop()

from src.database.incidents import get_active_incidents, close_incident

# --- AKTIVE EINSÄTZE (Management) ---
st.subheader("📡 Laufende Einsätze (Tracking)", divider="orange")
active_incidents = get_active_incidents(1)
if active_incidents:
    for inc in active_incidents:
        with st.expander(f"📍 {inc['keyword']} (Seit {inc['created_at'][11:16]})", expanded=True):
            col_a1, col_a2 = st.columns([3, 1])
            with col_a1:
                st.write(f"**Anlage:** {pd.to_datetime(inc['created_at']).strftime('%d.%m.%Y %H:%M')}")
                if inc['situation']: st.write(f"**Lage:** {inc['situation'][:150]}...")
            with col_a2:
                if st.button("🏁 Einsatz beenden", key=f"close_inc_{inc['id']}", use_container_width=True, help="Entfernt den Einsatz aus der Auswahl für neue Berichte."):
                    ok_close, err_close = close_incident(inc['id'])
                    if ok_close:
                        st.toast(f"Einsatz {inc['keyword']} wurde beendet.", icon="🏁")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(err_close)
else:
    st.caption("Aktuell keine parallelen Einsätze aktiv.")

st.divider()

# Load incident reports from DB
try:
    conn = get_connection()
    c = conn.cursor()
    # Join with vehicles, commanders, etc. to get readable names
    query = """
    SELECT 
        i.id,
        i.created_at,
        i.keyword,
        v.call_sign as vehicle_name,
        p_cmd.name as commander_name,
        p_ldr.name as unit_leader_name,
        i.situation,
        i.actions,
        i.crew_json,
        i.sent_at
    FROM incident_reports i
    LEFT JOIN vehicles v ON i.vehicle_id = v.id
    LEFT JOIN participants p_cmd ON i.commander_id = p_cmd.id
    LEFT JOIN participants p_ldr ON i.unit_leader_id = p_ldr.id
    ORDER BY i.created_at DESC
    LIMIT 200
    """
    rows = c.execute(query).fetchall()
    conn.close()
    
    if not rows:
        st.warning("Noch keine Einsatzberichte vorhanden.")
        st.stop()
        
    hist_data = [dict(r) for r in rows]
    
except Exception as e:
    st.error(f"Fehler beim Laden der Einsätze: {e}")
    st.stop()

# --- Grouping Logic ---
batches = {}
for r in hist_data:
    # Use sent_at as key, or a unique ID for unsent ones (or group all unsent together?)
    # The user wants "Batches" that are summarized. Batches define things sent at the same time.
    batch_key = r['sent_at'] if r['sent_at'] else "unsent"
    if batch_key not in batches:
        batches[batch_key] = []
    batches[batch_key].append(r)

# Display batches
# We sort batches: 'unsent' first (key 1), then sent ones (key 0) by sent_at DESC
sorted_batch_keys = sorted(
    batches.keys(),
    key=lambda k: (1 if k == "unsent" else 0, k if k != "unsent" else ""),
    reverse=True
)

for b_key in sorted_batch_keys:
    batch_reports = batches[b_key]
    # Sort reports within batch by call_sign
    batch_reports = sorted(batch_reports, key=lambda x: x['vehicle_name'] or "")
    
    first_r = batch_reports[0]
    
    if b_key == "unsent":
        header_title = f"⏳ Warteschlange ({len(batch_reports)} Fahrzeuge / Berichte)"
        header_color = "orange"
    else:
        sent_date = pd.to_datetime(b_key).strftime('%d.%m.%Y %H:%M')
        # We can also pick the keyword from the first report or common keyword
        keywords = list(set([r['keyword'] for r in batch_reports if r['keyword']]))
        kw_str = " / ".join(keywords) if keywords else "Kein Stichwort"
        header_title = f"🚒 {sent_date} - {kw_str} ({len(batch_reports)} Fahrzeuge)"
        header_color = "green"

    with st.expander(header_title, expanded=(b_key == "unsent")):
        st.markdown(f"**Status:** {'✅ Versendet am ' + pd.to_datetime(b_key).strftime('%d.%m.%Y %H:%M') if b_key != 'unsent' else '⏳ In der Warteschlange'}")
        
        # Recollate unique personnel/commanders for the batch
        all_commanders = list(set([r['commander_name'] for r in batch_reports if r['commander_name']]))
        all_leaders = list(set([r['unit_leader_name'] for r in batch_reports if r['unit_leader_name']]))
        
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"**Einsatzleiter:** {', '.join(all_commanders) if all_commanders else '-'}")
        with c2:
            st.markdown(f"**Einheitsführer:** {', '.join(all_leaders) if all_leaders else '-'}")
            
        st.divider()
        
        # Nest vehicle details
        for r in batch_reports:
            v_name = r['vehicle_name'] or "Unbekanntes Fahrzeug"
            created_str = pd.to_datetime(r['created_at']).strftime('%H:%M')
            st.subheader(f"📟 {v_name} (Erfasst um {created_str})")
            
            sc1, sc2 = st.columns(2)
            with sc1:
                st.markdown("**Lage:**")
                st.write(r['situation'] or "-")
            with sc2:
                st.markdown("**Tätigkeiten:**")
                st.write(r['actions'] or "-")
            
            # Crew display simplified for nesting
            try:
                crew = json.loads(r['crew_json'])
                crew_list = []
                for seat, p_data in crew.items():
                    # Nur seat_X keys verarbeiten
                    if not seat.startswith("seat_"): continue
                    
                    if isinstance(p_data, dict):
                        p_name = p_data.get("name")
                        vab = p_data.get("vab", False)
                        agt = p_data.get("agt", 0)
                    else:
                        p_name = p_data
                        vab = False
                        agt = 0
                    
                    if p_name and p_name != "- Niemand -":
                        s_num = seat.replace("seat_", "")
                        vab_label = " 💰" if vab else ""
                        agt_label = f" 💨({agt}m)" if agt and agt > 0 else ""
                        crew_list.append(f"**P{s_num}:** {p_name}{vab_label}{agt_label}")
                
                if crew_list:
                    st.caption(f"**Besatzung:** {', '.join(crew_list)}")
            except:
                pass
            
            st.divider()
