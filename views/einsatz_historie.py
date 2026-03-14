import streamlit as st
import pandas as pd
import json
from src.database import get_connection

st.title("📜 Einsatz-Historie")
st.info("Übersicht aller abgeschlossenen Einsatzberichte.")

# Add simple auth redirect fallback
if st.session_state.get('is_token_auth', False):
    st.error("Token-User haben keinen Zugriff auf das Archiv.")
    st.stop()

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

# Layout for history
for r in hist_data:
    date_str = pd.to_datetime(r['created_at']).strftime('%d.%m.%Y %H:%M')
    v_name = r['vehicle_name'] or "Unbekanntes Fahrzeug"
    sent_status = "✅ Versendet" if r['sent_at'] else "⏳ Warteschlange"
    
    with st.expander(f"🚒 {date_str} - {r['keyword']} ({v_name}) - {sent_status}"):
        
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"**Einsatzleiter:** {r['commander_name'] or '-'}")
            st.markdown(f"**Einheitsführer:** {r['unit_leader_name'] or '-'}")
            st.markdown(f"**Status:** {sent_status}")
        with c2:
            st.markdown(f"**Lage:**\n{r['situation'] or '-'}")
            st.markdown(f"**Tätigkeiten:**\n{r['actions'] or '-'}")
            
        st.divider()
        st.markdown("**Besatzung:**")
        try:
            crew = json.loads(r['crew_json'])
            crew_list = []
            for seat, person in crew.items():
                if person and person != "- Niemand -":
                    # Format "seat_1" to "Platz 1"
                    s_num = seat.replace("seat_", "")
                    crew_list.append(f"Platz {s_num}: {person}")
                    
            if crew_list:
                for c_item in crew_list:
                    st.write(f"- {c_item}")
            else:
                st.write("- Niemand eingetragen")
        except:
            st.write("Konnte Besatzung nicht lesen.")
            
        # Optional: PDF Export Button could go here for individual reports
