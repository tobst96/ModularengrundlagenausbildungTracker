import streamlit as st
import datetime
import qrcode
from PIL import Image
import io
import urllib.parse
import pandas as pd
import sys
import os
import re
import io
import time
from src.parser import extract_data_from_pdf
from src.data import process_training_data, get_summary_stats
import json
import logging
from logging.handlers import RotatingFileHandler

# Set up logging with 5MB max size and 3 backups
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DATA_DIR = log_dir  # Absolute path used for PDF cache etc.
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "app.log")

logger = logging.getLogger("TrainingTracker")
logger.setLevel(logging.INFO)

# Check if handler already exists to avoid duplicate logs in Streamlit reruns
if not logger.handlers:
    handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.info("Application started")

from src.db_base import (
    init_db, save_upload_data, get_person_history, verify_user, init_admin_user, 
    delete_person, delete_all_persons, get_units, create_unit, delete_unit, 
    get_all_users, create_user_with_unit, delete_user, get_all_participants_admin, 
    export_unit_backup, import_unit_backup, get_all_person_qs_status_cached, 
    get_latest_upload_data_cached, get_person_qs_status_cached, update_person_qs_status,
    log_login, get_login_history, get_feueron_config, save_feueron_config, get_all_feueron_configs,
    save_pdf_cache, get_pdf_cache
)
from streamlit_cookies_manager import EncryptedCookieManager

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

st.set_page_config(page_title="Ausbildungs-Tracker", page_icon="🚒", layout="wide")





def generate_isolated_pdf_for_person(pdf_path: str, target_name: str):
    import pdfplumber
    import io

    pages_to_extract = []
    with pdfplumber.open(pdf_path) as pdf:
        start_found = False
        for i, page in enumerate(pdf.pages):
            words = page.extract_words()
            person_headers_y = []
            for w in words:
                if w['text'] == 'geb.':
                    person_headers_y.append(w['top'])
                    
            grouped_y = []
            for y in sorted(list(set(person_headers_y))):
                if not grouped_y or y - grouped_y[-1] > 10:
                    grouped_y.append(y)
                    
            target_y_start = None
            next_person_y_start = None
            
            for y in grouped_y:
                line_text = " ".join([w['text'] for w in words if abs(w['top'] - y) < 5])
                if target_name in line_text:
                    target_y_start = max(0, y - 10)
                elif start_found and next_person_y_start is None:
                    next_person_y_start = max(0, y - 10)
                    
            if not start_found:
                if target_y_start is not None:
                    start_found = True
                    if next_person_y_start is not None:
                        pages_to_extract.append((i, target_y_start, next_person_y_start))
                        break
                    else:
                        pages_to_extract.append((i, target_y_start, page.height))
            else:
                if next_person_y_start is not None:
                    pages_to_extract.append((i, 0, next_person_y_start))
                    break
                else:
                    pages_to_extract.append((i, 0, page.height))
                    
        images = []
        for (i, top, bottom) in pages_to_extract:
            page = pdf.pages[i]
            cropped_page = page.crop((0, float(top), float(page.width), float(bottom)))
            im = cropped_page.to_image(resolution=150).original
            images.append(im)
            
        if not images:
            return None, None
            
        pdf_bytes = io.BytesIO()
        images[0].save(pdf_bytes, format="PDF", save_all=True, append_images=images[1:], resolution=150)
        pdf_bytes.seek(0)
        return pdf_bytes.getvalue(), images

# --- PUBLIC VIEW ROUTING ---
if st.query_params.get("view") == "public":
    st.markdown("## 🚒 Feuerwehr Ausbildungs-Tracker")
    st.markdown("### Teilnehmer-Ansicht")
    
    # URL Parameter auslesen falls vorhanden
    url_name = st.query_params.get("name", "")
    url_bday = st.query_params.get("bday", "")
    
    # 1. Such-Maske wenn keine URL Parameter da sind
    search_name = url_name
    search_bday = url_bday
    
    if not url_name or not url_bday:
        st.info("Bitte gib deinen Namen und dein Geburtsdatum ein, um dein Ausbildungs-Profil zu öffnen.")
        with st.form("public_search_form"):
            search_name = st.text_input("Name (z.B. Max Mustermann)", value=url_name)
            search_bday_date = st.date_input("Geburtsdatum", min_value=datetime.date(1920, 1, 1), max_value=datetime.date.today(), format="DD.MM.YYYY")
            submitted = st.form_submit_button("Profil suchen")
            
            if submitted:
                if search_name:
                    st.query_params["view"] = "public"
                    st.query_params["name"] = search_name
                    st.query_params["bday"] = search_bday_date.strftime("%d.%m.%Y")
                    st.rerun()
                else:
                    st.error("Bitte einen Namen eingeben.")
        st.stop()
        
    # 2. Wenn Parameter vorliegen -> Passwort-Abfrage
    # In Public View the user should enter the shared fixed password
    _public_pw = os.environ.get("PUBLIC_VIEW_PASSWORD", "feuerprofi")
    if not st.session_state.get(f"public_auth_{search_name}_{search_bday}"):
        with st.form("public_auth_form"):
            st.warning(f"Sichere Ansicht für: **{search_name}** ({search_bday})")
            pwd = st.text_input("Passwort (Einheitscode)", type="password")
            auth_submit = st.form_submit_button("Freischalten")
            if auth_submit:
                if pwd == _public_pw:
                    st.session_state[f"public_auth_{search_name}_{search_bday}"] = True
                    st.success("Erfolgreich autorisiert. Einen Moment...")
                    st.rerun()
                else:
                    st.error("Falsches Passwort.")
        st.stop()

    # 3. Wenn autorisiert -> Person suchen und Read-Only Render
    from src.db_base import get_person_data_public
    print(f"DEBUG APP.PY: Searching for name='{search_name}', bday='{search_bday}'")
    person_data = get_person_data_public(search_name, search_bday)
    
    if not person_data or not person_data.get('person'):
        st.error(f"Die Person '{search_name}' mit Geburtsdatum '{search_bday}' konnte nicht gefunden werden.")
        if st.button("⬅️ Zurück zur Suche"):
            st.query_params.clear()
            st.query_params["view"] = "public"
            st.rerun()
        st.stop()
        
    # Rendere die Übersicht read-only
    p_info = person_data['person']
    mod_raw = person_data['modules']
    
    import pandas as pd
    p_df = pd.DataFrame(mod_raw)

    st.header(f"👤 {p_info['name']}")
    st.caption(f"Geburtsdatum: {p_info['birthday']}")
    
    st.divider()
    
    if not p_df.empty:
        qs1 = "bereits absolviert!" if (person_data.get('qs_status') or {}).get('qs1_done') else "nicht absolviert."
        qs2 = "bereits absolviert!" if (person_data.get('qs_status') or {}).get('qs2_done') else "nicht absolviert."
        qs3 = "bereits absolviert!" if (person_data.get('qs_status') or {}).get('qs3_done') else "nicht absolviert."
        
        st.markdown(f"**Qualifikationsstufen-Status (Laut Meta-Daten):**")
        st.markdown(f"- **QS1 (Einsatzfähigkeit):** {qs1}")
        st.markdown(f"- **QS2 (Truppmitglied):** {qs2}")
        st.markdown(f"- **QS3 (Truppführer):** {qs3}")
        
        st.subheader("Module nach Qualifikationsstufen")
        grouped = p_df.groupby('qs_level', dropna=False)
        
        for qs, group in grouped:
            st.markdown(f"#### {qs if pd.notna(qs) and qs != '' else 'Sonstige'}")
            
            disp = group[['module_name', 'status', 'hours_t', 'hours_p', 'hours_k']].copy()
            disp.columns = ['Modul', 'Status', 'T', 'P', 'K']
            
            def color_status(val):
                if pd.isna(val): return ''
                v = str(val).strip()
                if v == "Absolviert": return 'color: green;'
                if v == "In Arbeit": return 'color: orange;'
                if v == "Nicht absolviert": return 'color: red;'
                return ''
                
            st.dataframe(disp.style.map(color_status, subset=['Status']), use_container_width=True, hide_index=True)
            
    else:
        st.info("Bislang keine Module verzeichnet.")
        
    st.write("---")
    st.subheader("📄 Original Ausdruck (PDF)")
    try:
        _uid_for_pdf = p_info.get('unit_id') or st.session_state.get('unit_id')
        raw_pdf = get_pdf_cache(int(_uid_for_pdf)) if _uid_for_pdf else None
        if raw_pdf:
            with st.spinner("Isoliere Original-Dokument (PDF)..."):
                import io as _io
                target_name = p_info['name']
                pdf_bytes, images = generate_isolated_pdf_for_person(_io.BytesIO(raw_pdf), target_name)
                if pdf_bytes and images:
                    st.download_button(
                        label="📥 Eigenes PDF-Zertifikat herunterladen",
                        data=pdf_bytes,
                        file_name=f"Ausbildungsnachweis_{target_name.replace(' ', '_')}.pdf",
                        mime="application/pdf"
                    )
                    for im in images:
                        st.image(im)
                else:
                    st.info("Diese Person wurde im aktuell hinterlegten PDF-Ausdruck nicht als Text gefunden.")
        else:
            st.info("Kein PDF-Cache für diese Einheit vorhanden. Bitte PDF einmal hochladen oder Auto-Download starten.")
    except Exception as e:
        st.warning(f"Fehler beim Laden der PDF: {e}")
        
    if st.button("⬅️ Abmelden / Andere Person suchen"):

        st.session_state[f"public_auth_{search_name}_{search_bday}"] = False
        st.query_params.clear()
        st.query_params["view"] = "public"
        st.rerun()

    st.stop()
# --- END PUBLIC VIEW ROUTING ---


# --- COOKIE MANAGER (Login-Persistenz) ---
_cookies = EncryptedCookieManager(prefix="mga_tracker_", password="mga-session-secret-2024")
if not _cookies.ready():
    st.stop()

# --- INITIALIZATION ---

@st.cache_resource
def setup_db():
    try:
        init_db()
        admin_pass = os.environ.get("ADMIN_PASSWORD", "admin")
        init_admin_user("admin", admin_pass)
        return True, None
    except Exception as e:
        return False, str(e)

if 'db_ok' not in st.session_state:
    st.session_state.db_ok, st.session_state.db_err = setup_db()

db_ok = st.session_state.db_ok

# --- APSCHEDULER: Täglicher FeuerOn Auto-Download ---
@st.cache_resource
def start_scheduler():
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from src.feueron_downloader import run_download
        from src.db_base import get_all_feueron_configs
        
        scheduler = BackgroundScheduler()
        
        def reload_jobs():
            """Lädt alle aktiven Sync-Jobs aus der DB."""
            scheduler.remove_all_jobs()
            configs = get_all_feueron_configs()
            for cfg in configs:
                if cfg.get('sync_enabled'):
                    scheduler.add_job(
                        run_download,
                        'cron',
                        args=[cfg['unit_id']],
                        hour=cfg.get('sync_hour', 3),
                        minute=cfg.get('sync_minute', 0),
                        id=f"feueron_sync_{cfg['unit_id']}",
                        replace_existing=True
                    )
                    logger.info(f"Scheduler-Job registriert: Einheit {cfg['unit_id']} um {cfg.get('sync_hour',3):02d}:{cfg.get('sync_minute',0):02d} Uhr")
        
        reload_jobs()
        scheduler.start()
        logger.info("APScheduler gestartet")
        return scheduler, reload_jobs
    except Exception as e:
        logger.error(f"Scheduler-Start fehlgeschlagen: {e}")
        return None, None

if db_ok:
    _scheduler, _reload_jobs = start_scheduler()
else:
    _scheduler, _reload_jobs = None, None


# --- CACHED FUNCTIONS ---

@st.cache_data
def get_cached_person_stats(df):
    valid_people = sorted([p for p in df['person_name'].unique() if p != "Unknown"])
    person_stats = []
    for p in valid_people:
        p_df = df[df['person_name'] == p]
        # For overall progress, exclude "Ergänzungsmodule"
        p_df_core = p_df[~p_df['qs_level'].astype(str).str.contains("Ergänzungsmodule", case=False)]
        overall_stats = get_summary_stats(p_df_core if not p_df_core.empty else p_df)
        qs1_stats = get_summary_stats(p_df[p_df['qs_level'].astype(str).str.contains("QS1")])
        qs2_stats = get_summary_stats(p_df[p_df['qs_level'].astype(str).str.contains("QS2")])
        erg_stats = get_summary_stats(p_df[p_df['qs_level'].astype(str).str.contains("Ergänzungsmodule")])
        estabk_stats = get_summary_stats(p_df[p_df['qs_level'].astype(str).str.contains("EStabK")])
        person_stats.append({
            "Name": p, "Gesamt %": overall_stats['overall_progress'],
            "QS1 %": qs1_stats['overall_progress'], "QS2 %": qs2_stats['overall_progress'],
            "Ergänzung %": erg_stats['overall_progress'], "EStabK %": estabk_stats['overall_progress'],
            "Module": f"{overall_stats['completed_modules']}/{overall_stats['total_modules']}"
        })
    return pd.DataFrame(person_stats)

@st.cache_data
def get_cached_mod_stats(df):
    grouped = df.groupby(['id', 'title', 'qs_level'])
    def calc_stats(x):
        return pd.Series({
            'Absolventen': len(x[x['status'] == 'Absolviert']),
            'Gesamt': len(x),
            'Quote': round(len(x[x['status'] == 'Absolviert']) / len(x) * 100) if len(x) > 0 else 0
        })
    return grouped.apply(calc_stats, include_groups=False).reset_index().rename(columns={'id': 'ID', 'title': 'Modul', 'qs_level': 'QS-Stufe'})

@st.cache_data(ttl=300)
def get_cached_history(name, birthday, unit_id=None):
    return get_person_history(name, birthday, unit_id=unit_id) if db_ok else None

# --- APP STATE ---

if 'df' not in st.session_state:
    st.session_state.df = None
        
if 'selected_person' not in st.session_state: st.session_state.selected_person = None
if 'last_loaded_file' not in st.session_state: st.session_state.last_loaded_file = None if 'last_loaded_file' not in st.session_state else st.session_state.last_loaded_file
if 'pending_save' not in st.session_state: st.session_state.pending_save = None


# --- AUTHENTICATION (mit Cookie-Persistenz) ---
if 'authenticated' not in st.session_state:
    # Prüfe ob ein gültiges Login-Cookie existiert
    cookie_user = _cookies.get("username", "")
    cookie_auth = _cookies.get("auth", "")
    if cookie_user and cookie_auth == "1":
        st.session_state.authenticated = True
        st.session_state.username = cookie_user
        
        # Hol die definierte Einheit für den Auto-Login aus der DB
        from src.db_base import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT u.unit_id, un.name FROM users u LEFT JOIN units un ON u.unit_id = un.id WHERE u.username=?", (cookie_user,))
        res = cur.fetchone()
        cur.close()
        conn.close()
        if res:
            st.session_state.unit_id = res['unit_id']
            st.session_state.unit_name = res['name']
        else:
            st.session_state.unit_id = None
            st.session_state.unit_name = None
    else:
        st.session_state.authenticated = False

def login():
    st.title("🔐 Login")
    
    from src.db_base import get_units
    units = get_units()
    unit_options = {u['id']: u['name'] for u in units}
    
    tab_admin, tab_teilnehmer = st.tabs(["🛡️ Admin / Führungskraft", "👨‍🚒 Teilnehmer (Eigene Daten)"])
    
    with tab_teilnehmer:
        st.info("Hier kannst du deinen eigenen Ausbildungsstand direkt abfragen.")
        import datetime
        with st.form("teilnehmer_login_form"):
            search_name_login = st.text_input("Dein Name (ungefähre Eingabe reicht)")
            search_bday_login = st.date_input("Dein Geburtsdatum", min_value=datetime.date(1920, 1, 1), max_value=datetime.date.today(), format="DD.MM.YYYY")
            submitted_tl = st.form_submit_button("Zum Teilnehmer-Bereich", type="primary")
            if submitted_tl:
                if search_name_login:
                    st.query_params["view"] = "public"
                    st.query_params["name"] = search_name_login
                    st.query_params["bday"] = search_bday_login.strftime("%d.%m.%Y")
                    st.rerun()
                else:
                    st.error("Bitte einen Namen eingeben.")
                    
    with tab_admin:
        username = st.text_input("Benutzername")
        
        def try_login():
            st.session_state.do_login = True
            
        password = st.text_input("Passwort", type="password", on_change=try_login)
        
        selected_unit_name = None
        if username.strip().lower() == "admin":
            st.write("---")
            st.info("🚨 **Hinweis für Admins:** Bitte wählen Sie die Einheit, die Sie bearbeiten möchten.")
            selected_unit_name = st.selectbox("Aktivierte Einheit", options=list(unit_options.values()))
            st.write("---")
        
        remember = st.checkbox("Angemeldet bleiben", value=True)
        
        if st.button("Anmelden", use_container_width=True, type="primary") or st.session_state.pop("do_login", False):
            if not username or not password:
                st.error("Bitte Benutzername und Passwort eingeben.")
            else:
                success, db_unit_id, db_unit_name = verify_user(username, password)
                if success:
                    client_ip = st.context.headers.get("X-Forwarded-For", "Unknown IP") if hasattr(st, 'context') else "Unknown IP"
                    log_login(username, client_ip, "Erfolgreich")
                    import logging
                    lo = logging.getLogger("TrainingTracker")
                    lo.info(f"User {username} logged in successfully")
                    st.session_state.authenticated = True
                    st.session_state.username = username
                    st.session_state.df = None
                    st.session_state.last_loaded_file = None
                    
                    if username.lower() == 'admin':
                        for uid, uname in unit_options.items():
                            if uname == selected_unit_name:
                                st.session_state.unit_id = uid
                                st.session_state.unit_name = uname
                                break
                    else:
                        st.session_state.unit_id = db_unit_id
                        st.session_state.unit_name = db_unit_name
                        
                    if remember:
                        _cookies["username"] = username
                        _cookies["auth"] = "1"
                        _cookies.save()
                    st.success("Erfolgreich angemeldet!")
                    import time
                    time.sleep(0.5)
                    st.rerun()
                else:
                    client_ip = st.context.headers.get("X-Forwarded-For", "Unknown IP") if hasattr(st, 'context') else "Unknown IP"
                    log_login(username, client_ip, "Fehlgeschlagen")
                    import logging
                    lo = logging.getLogger("TrainingTracker")
                    lo.warning(f"Failed login attempt for user {username}")
                    st.error("Ungültiger Benutzername oder Passwort.")

if not st.session_state.authenticated:
    login()
    st.stop()

# --- LOAD DATA FOR UNIT ---
if st.session_state.df is None and st.session_state.get('unit_id'):
    if db_ok:
        latest = get_latest_upload_data_cached(unit_id=st.session_state.unit_id)
        if latest:
            st.session_state.df = process_training_data(latest)
            st.session_state.last_loaded_file = 'loaded_from_db'


# --- SIDEBAR ---

with st.sidebar:
    st.header("⚙️ Menü")
    
    is_admin = st.session_state.get('username', '').lower() == 'admin'
    st.markdown(f"**Einheit:** {st.session_state.get('unit_name', 'Keine')}")
        
    st.divider()
    
    # 1. Section: Data Upload
    if not st.session_state.get('unit_id'):
        st.info("⚠️ Bitte wähle erst eine Einheit aus (⚙️ Admin-Bereich), um Daten hochladen zu können.")
    else:
        with st.expander("📂 Daten-Upload", expanded=(st.session_state.df is None)):
            
            # Neuer FeuerOn API Auto-Download Button im Haupt-Upload-Menü
            from src.db_base import get_feueron_config
            cfg = get_feueron_config(st.session_state.unit_id)
            if cfg and cfg.get('feueron_username'):
                st.markdown("🔄 **Automatisch via FeuerOn API:**")
                if st.button("🔗 Ausbildungsmodule jetzt herunterladen", use_container_width=True, type="primary"):
                    with st.spinner("⏳ Verbinde mit FeuerOn und lade Trainingsdaten herunter... (Bitte warten)"):
                        from src.feueron_downloader import run_download as _run_dl
                        import time
                        from src.db_base import get_latest_upload_data_cached
                        from src.data import process_training_data
                        
                        ok, msg = _run_dl(st.session_state.unit_id)
                        if ok:
                            st.success(f"{msg}")
                            st.cache_data.clear()
                            latest = get_latest_upload_data_cached(unit_id=st.session_state.unit_id)
                            if latest:
                                st.session_state.df = process_training_data(latest)
                                st.session_state.last_loaded_file = 'loaded_from_api'
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(f"❌ Fehler: {msg}")
                st.divider()

            uploaded_file = st.file_uploader("Oder manuell PDF hochladen", type=["pdf"], label_visibility="visible")
            if uploaded_file is not None:
                file_id = f"{uploaded_file.name}_{uploaded_file.size}"
                if st.session_state.last_loaded_file != file_id:
                    prog = st.progress(0, text="PDF wird analysiert... 0%")
                    try:
                        import os
                        # PDF-Bytes sichern (DB-basiert, Docker-sicher)
                        uploaded_bytes = uploaded_file.getvalue()
                        save_pdf_cache(st.session_state.unit_id, uploaded_bytes, uploaded_file.name)
                        uploaded_file.seek(0)
                        
                        raw = extract_data_from_pdf(uploaded_file, progress_callback=lambda p: prog.progress(p, text=f"PDF wird analysiert... {int(p*100)}%"))
                        prog.empty()
                        with st.spinner("Daten werden aufbereitet und geladen..."):
                            st.session_state.df = process_training_data(raw)
                            st.session_state.last_loaded_file = file_id
                            st.session_state.last_file_name = uploaded_file.name
                            
                        if db_ok:
                            with st.status("📌 Speichern...", expanded=True) as status:
                                prog_db = st.progress(0, text="Upload in Datenbank... 0%")
                                save_upload_data(uploaded_file.name, raw,
                                                 progress_callback=lambda p: prog_storage.progress(p, text=f"Upload in Datenbank... {int(p*100)}%"), unit_id=st.session_state.unit_id)
                                status.update(label="✅ Gespeichert", state="complete")
                        st.cache_data.clear()
                        st.rerun()  # Show data IMMEDIATELY
                    except Exception as e:
                        st.error(f"Fehler: {e}")

    # 2. Section: Navigation
    st.divider()
    st.subheader("🧭 Navigation")
    
    if 'main_view' not in st.session_state:
        st.session_state.main_view = "Gesamtübersicht"
        
    views = ["Gesamtübersicht", "QS1 - Einsatzfähigkeit", "QS2 - Truppmitglied", "QS3 - Truppführende/r", "EStabK"]
    if is_admin:
        views.append("⚙️ Admin-Bereich")
        
    for v in views:
        is_active = (st.session_state.main_view == v)
        if st.button(f"👉 {v}" if is_active else v, use_container_width=True, type="primary" if is_active else "secondary"):
            if st.session_state.main_view != v:
                st.session_state.main_view = v
                st.session_state.selected_person = None
                st.rerun()

    if st.session_state.df is not None:
        full_df = st.session_state.df
        
        # Determine df_view and valid_people using session_state before rendering the checkbox
        hide_extra_val = st.session_state.get('hide_extra_cb', False)
        df_view = full_df[full_df['qs_level'] != "Ergänzungsmodule"].copy() if hide_extra_val else full_df.copy()
        valid_people = sorted([p for p in df_view['person_name'].unique() if p != "Unknown"])
        
        st.divider()
        st.subheader("👤 Teilnehmer")
        # Wenn die gespeicherte Person nicht mehr in der Liste ist (Filterwechsel etc.), zurücksetzen
        if st.session_state.selected_person is not None and st.session_state.selected_person not in valid_people:
            st.session_state.selected_person = None
        selected = st.selectbox("Detailansicht", options=["-- Keine (" + st.session_state.main_view + ") --"] + valid_people,
                                index=0 if st.session_state.selected_person is None else (valid_people.index(st.session_state.selected_person) + 1))
        
        if selected.startswith("--"):
            if st.session_state.selected_person is not None:
                st.session_state.selected_person = None
                st.rerun()
        elif selected != st.session_state.selected_person:
            st.session_state.selected_person = selected
            st.rerun()
            
        st.divider()
        st.subheader("🔍 Filter & Optionen")
        hide_extra = st.checkbox("Ergänzungsmodule ausblenden", value=hide_extra_val, key='hide_extra_cb')

    st.markdown("---")
    
    st.markdown("---")
    if st.button("🚪 Abmelden", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.df = None
        st.session_state.unit_id = None
        st.session_state.unit_name = None
        st.session_state.last_loaded_file = None
        _cookies["auth"] = ""
        _cookies["username"] = ""
        _cookies.save()
        st.rerun()

    # --- DB SAVE IN SIDEBAR ---
    # Moved to Data Upload section


def _get_birthday_for_name(name: str) -> str:
    """Schlägt das Geburtsdatum einer Person in SQLite nach, um den DB-Key zu ermitteln."""
    try:
        from src.db_base import get_connection
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT birthday FROM participants WHERE name = ? LIMIT 1", (name,))
        row = c.fetchone()
        conn.close()
        return row["birthday"] if row else "Unknown"
    except Exception:
        return "Unknown"

# --- MAIN CONTENT ---

view_mode = st.session_state.get('main_view', 'Gesamtübersicht')

# --- 1. ADMIN BEREICH (Immer sichtbar, wenn ausgewählt) ---
if view_mode == "⚙️ Admin-Bereich" and is_admin:
    st.header("⚙️ Admin-Bereich")
    
    # -- ADMIN UNIT SWITCHER --
    st.markdown("---")
    st.subheader("Aktuelle Admin-Sicht wechseln")
    units = get_units()
    unit_options = {u['id']: u['name'] for u in units}
    
    if len(units) > 0:
        current_unit_index = list(unit_options.keys()).index(st.session_state.unit_id) if st.session_state.unit_id in unit_options else 0
        selected_unit_name = st.selectbox(
            "Wähle hier die Einheit, für welche du Daten sehen bzw. hochladen möchtest", 
            options=list(unit_options.values()), 
            index=current_unit_index,
            key="admin_unit_selector_top"
        )
        
        # Check if changed
        for uid, uname in unit_options.items():
            if uname == selected_unit_name and uname != st.session_state.get('unit_name'):
                st.session_state.unit_id = uid
                st.session_state.unit_name = uname
                st.session_state.df = None
                st.session_state.selected_person = None
                st.session_state.last_loaded_file = None # Clear this to force a full fresh reload
                
                # Immediately fetch the data for the new unit
                from src.db_base import get_latest_upload_data_cached
                from src.data import process_training_data
                if db_ok:
                    latest = get_latest_upload_data_cached(unit_id=uid)
                    if latest:
                        st.session_state.df = process_training_data(latest)
                        st.session_state.last_loaded_file = 'loaded_from_db'
                
                st.rerun()
    st.markdown("---")
    # --------------------------
    

    with st.expander("💾 Backup & Wiederherstellung (Aktuelle Einheit)", expanded=False):
        st.info(f"Sichere oder lade alle Daten der Einheit **{st.session_state.get('unit_name')}**.")
        curr_uid = st.session_state.get('unit_id')
        unit_n = st.session_state.get('unit_name', 'Einheit')
        
        ca_db1, ca_db2 = st.columns(2)
        with ca_db1:
            st.write("**1. Backup erstellen**")
            st.caption("Daten werden auf deinem Gerät gesichert.")
            if st.button("📦 Backup generieren", key="btn_gen_backup"):
                backup_data = export_unit_backup(curr_uid)
                json_str = json.dumps(backup_data, indent=2, ensure_ascii=False)
                st.download_button(
                    label="⬇️ Download (.json)",
                    data=json_str,
                    file_name=f"backup_{unit_n.replace(' ', '_')}_{time.strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json",
                    type="primary"
                )
                
        with ca_db2:
            st.write("**2. Wiederherstellung**")
            st.error("⚠️ Überschreibt aktuelle Profile!")
            uploaded_backup = st.file_uploader("Backup-Datei (.json) hier hochladen", type=['json'], key="backup_uploader")
            if uploaded_backup is not None:
                try:
                    backup_content = json.load(uploaded_backup)
                    if st.button("🔄 Jetzt einspielen", type="primary", use_container_width=True):
                        with st.spinner("Restore läuft..."):
                            ok, err = import_unit_backup(curr_uid, backup_content)
                            if ok:
                                st.session_state.df = None
                                st.session_state.last_loaded_file = None
                                st.cache_data.clear()
                                st.success("✅ Erledigt! Lade neu...")
                                time.sleep(2)
                                st.rerun()
                            else:
                                st.error(f"Fehler: {err}")
                except json.JSONDecodeError:
                    st.error("Ungültiges JSON.")
    st.markdown("---")

    tab_units, tab_users, tab_persons, tab_logins, tab_autodownload = st.tabs(["Struktur (Einheiten)", "Benutzer", "Personen in DB", "Login-Historie", "🔄 Auto-Download"])
    
    with tab_units:
        st.subheader("Einheiten verwalten")
        colA, colB = st.columns([3, 1])
        new_unit_name = colA.text_input("Neue Einheit erstellen (Landkreis - Stadt - Feuerwehr)")
        if colB.button("Einheit anlegen", use_container_width=True):
            if new_unit_name:
                ok, err = create_unit(new_unit_name)
                if ok:
                    st.success(f"Einheit '{new_unit_name}' erstellt.")
                    st.rerun()
                else:
                    st.error(f"Fehler: {err}")
                    
        st.divider()
        st.write("**Bestehende Einheiten**")
        units = get_units()
        for u in units:
            cu1, cu2 = st.columns([5, 1])
            cu1.write(f"- {u['name']}")
            if cu2.button("🗑️", key=f"del_unit_{u['id']}", help="Einheit löschen"):
                ok, err = delete_unit(u['id'])
                if ok:
                    st.success("Gelöscht!")
                    st.rerun()
                else:
                    st.error(f"Konnte nicht gelöscht werden: {err}")
                    


    with tab_users:
        st.subheader("Benutzer verwalten")
        with st.form("new_user_form"):
            nu_name = st.text_input("Benutzername")
            nu_pass = st.text_input("Passwort", type="password")
            units = get_units()
            nu_unit = st.selectbox("Einheit", options={u['id']: u['name'] for u in units}.items(), format_func=lambda x: x[1])
            submitted = st.form_submit_button("Benutzer anlegen")
            if submitted:
                if nu_name and nu_pass and nu_unit:
                    ok, err = create_user_with_unit(nu_name, nu_pass, nu_unit[0])
                    if ok:
                        st.success("Benutzer erstellt!")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error(f"Fehler: {err}")
                        
        st.divider()
        st.write("**Alle Benutzer**")
        all_u = get_all_users()
        for u in all_u:
            col1, col2, col3 = st.columns([3, 4, 1])
            col1.write(f"👤 **{u['username']}**")
            col2.write(f"🏢 {u['unit_name'] or 'Admin / Keine'}")
            if u['username'] != 'admin':
                if col3.button("🗑️", key=f"del_user_{u['id']}", help="Benutzer löschen"):
                    delete_user(u['id'])
                    st.rerun()
                    
    with tab_persons:
        st.subheader(f"Personen in der Einheit: {st.session_state.get('unit_name', 'Keine')}")
        all_p = get_all_participants_admin(unit_id=st.session_state.get('unit_id'))
        if all_p:
            df_p = pd.DataFrame(all_p)
            # Let's map columns
            df_p = df_p.rename(columns={'name': 'Name', 'birthday': 'Geburtsdatum', 'unit_name': 'Einheit'})
            st.dataframe(df_p[['id', 'Name', 'Geburtsdatum', 'Einheit']], hide_index=True, use_container_width=True)
        else:
            st.info("Keine Personen in dieser Einheit gefunden.")

    with tab_logins:
        st.subheader("Letzte Logins (Global)")
        from src.db_base import get_login_history
        history = get_login_history(limit=50)
        if history:
            df_hist = pd.DataFrame(history)
            
            # Formatiere das Datum schoen
            df_hist['login_time'] = pd.to_datetime(df_hist['login_time']).dt.strftime('%d.%m.%Y %H:%M:%S')
            
            # Status Emojis
            df_hist['status'] = df_hist['status'].apply(lambda x: "✅ Erfolg" if x == "SUCCESS" else "❌ Fehler")
            
            df_hist = df_hist.rename(columns={
                'username': 'Benutzer',
                'unit_name': 'Einheit',
                'login_time': 'Zeitpunkt',
                'status': 'Status'
            })
            # Sicherheitsnetz: Einheit-Spalte ggf. hinzufügen
            if 'Einheit' not in df_hist.columns:
                df_hist['Einheit'] = 'Unbekannt'
            show_cols = [c for c in ['Zeitpunkt', 'Benutzer', 'Einheit', 'Status'] if c in df_hist.columns]
            st.dataframe(df_hist[show_cols], hide_index=True, use_container_width=True)
        else:
            st.info("Noch keine Logins verzeichnet.")


    # ---- AUTO-DOWNLOAD TAB ----
    with tab_autodownload:
        st.subheader("🔄 FeuerOn Auto-Download")
        st.caption("Täglich automatisch auf feueron.de einloggen, PDF herunterladen und importieren.")
        
        units_list = get_units()
        if not units_list:
            st.warning("Noch keine Einheiten angelegt.")
        else:
            # Einheit auswählen
            unit_names = [u['name'] for u in units_list]
            selected_unit_name = st.selectbox("Einheit auswählen", unit_names, key="feueron_unit_sel")
            selected_unit = next((u for u in units_list if u['name'] == selected_unit_name), None)
            
            if selected_unit:
                sel_uid = selected_unit['id']
                cfg = get_feueron_config(sel_uid)
                
                st.divider()
                st.subheader("🔑 FeuerOn Zugangsdaten")
                
                with st.form(key="feueron_config_form"):
                    col1, col2 = st.columns(2)
                    with col1:
                        f_org = st.text_input(
                            "Organisation (Dropdown-Wert)",
                            value=cfg.get('feueron_org', '') if cfg else '',
                            placeholder="z.B. Westerstede, Stadt",
                            help="Genaue Bezeichnung wie sie in FeuerOn erscheint"
                        )
                        f_org_id = st.text_input(
                            "Organisations-ID",
                            value=cfg.get('feueron_org_id', '') if cfg else '',
                            placeholder="z.B. 3455",
                            help="Interne ID aus FeuerOn. Für Westerstede, OF = 3455"
                        )
                        f_user = st.text_input(
                            "Benutzername",
                            value=cfg.get('feueron_username', '') if cfg else '',
                            placeholder="FeuerOn Benutzername"
                        )
                        f_pass = st.text_input(
                            "Passwort",
                            value=cfg.get('feueron_password', '') if cfg else '',
                            type="password",
                            placeholder="FeuerOn Passwort"
                        )
                    with col2:
                        f_hour = st.number_input(
                            "Uhrzeit (Stunde)",
                            min_value=0, max_value=23,
                            value=cfg.get('sync_hour', 3) if cfg else 3
                        )
                        f_minute = st.number_input(
                            "Uhrzeit (Minute)",
                            min_value=0, max_value=59,
                            value=cfg.get('sync_minute', 0) if cfg else 0
                        )
                        f_enabled = st.toggle(
                            "Auto-Download aktiv",
                            value=bool(cfg.get('sync_enabled', False)) if cfg else False
                        )
                    
                    save_btn = st.form_submit_button("💾 Einstellungen speichern", use_container_width=True)
                    if save_btn:
                        ok, err = save_feueron_config(
                            sel_uid, f_org, f_org_id, f_user, f_pass,
                            int(f_hour), int(f_minute), f_enabled
                        )
                        if ok:
                            # Scheduler-Jobs neu laden
                            if _reload_jobs:
                                try:
                                    _reload_jobs()
                                except Exception as e:
                                    logger.warning(f"Scheduler reload: {e}")
                            st.success(f"✅ Gespeichert! {'Auto-Download ist aktiv.' if f_enabled else 'Auto-Download ist deaktiviert.'}")
                        else:
                            st.error(f"Fehler: {err}")
                
                st.divider()
                st.subheader("📊 Sync-Status")
                
                # Aktuellen Status anzeigen (immer neu laden)
                cfg_live = get_feueron_config(sel_uid)
                if cfg_live:
                    s = cfg_live.get('last_sync_status')
                    s_msg = cfg_live.get('last_sync_message', '')
                    s_time = cfg_live.get('last_sync_at', '')
                    
                    if s == 'success':
                        st.success(f"✅ Letzter Sync: {s_time}")
                        if s_msg:
                            st.caption(s_msg)
                    elif s == 'error':
                        st.error(f"❌ Fehler beim letzten Sync: {s_time}")
                        if s_msg:
                            st.code(s_msg, language=None)
                    elif s == 'running':
                        st.info(f"⏳ Sync läuft gerade... ({s_msg})")
                    else:
                        st.info("Noch kein Sync durchgeführt.")
                    
                    if cfg_live.get('sync_enabled') and cfg_live.get('sync_hour') is not None:
                        next_h = cfg_live['sync_hour']
                        next_m = cfg_live.get('sync_minute', 0)
                        st.caption(f"🕰️ Geplanter täglicher Sync: {next_h:02d}:{next_m:02d} Uhr")
                
                st.divider()
                # Manueller Trigger
                col_btn1, col_btn2 = st.columns([2, 1])
                with col_btn1:
                    if st.button("▶️ Jetzt manuell ausführen", use_container_width=True, type="primary"):
                        if not cfg_live or not cfg_live.get('feueron_username'):
                            st.error("Bitte zuerst Zugangsdaten speichern!")
                        else:
                            from src.feueron_downloader import run_download as _run_dl
                            with st.spinner("⏳ Verbinde mit FeuerOn und lade Trainingsdaten herunter... (Das kann ca. 30s dauern)"):
                                ok, msg = _run_dl(sel_uid)
                            
                            if ok:
                                st.success(f"{msg}")
                                # Verhalte dich exakt so wie beim manuellen PDF Upload: Lade die neu gespeicherten DB-Daten und update die Session
                                from src.db_base import get_latest_upload_data_cached
                                from src.data import process_training_data
                                st.cache_data.clear()
                                latest = get_latest_upload_data_cached(unit_id=sel_uid)
                                if latest:
                                    st.session_state.df = process_training_data(latest)
                                    st.session_state.last_loaded_file = 'loaded_from_db_auto'
                                time.sleep(2)
                                st.rerun()
                            else:
                                st.error(f"❌ Fehler: {msg}")
                with col_btn2:
                    if st.button("🔄 Status aktualisieren", use_container_width=True):
                        st.rerun()

    st.stop() # Main content ends here for Admin tab


# --- 2. NORMALE DATENANSICHT (Braucht df) ---
if st.session_state.df is not None:
    df = df_view
    if st.session_state.selected_person is None:
        
        # Lade QS Stände aller Teilnehmer
        all_qs = get_all_person_qs_status_cached() if db_ok else {}
        
        # DataFrame mit QS Info anreichern
        def get_next_qs(name):
            # Geburtsdatum aus SQLite-Cache holen statt aus String parsen
            n = name.split(',')[0].strip()
            bday = _get_birthday_for_name(n)
            status = all_qs.get((n, bday), {'qs1_done': False, 'qs2_done': False, 'qs3_done': False})

            if not status['qs1_done']: return "1-Einsatzfähigkeit"
            if not status['qs2_done']: return "2-Truppmitglied"
            if not status['qs3_done']: return "3-Truppführende/r"
            return "4-Fertig"

        stats_df = get_cached_person_stats(df)
        stats_df['Nächster Schritt'] = stats_df['Name'].apply(get_next_qs)
        
        # Exclude completed users from the main overview stats
        active_users = stats_df[stats_df['Nächster Schritt'] != '4-Fertig']['Name'].tolist()
        # Determine which participants to show based on view_mode
        if view_mode == "Gesamtübersicht":
            display_df = stats_df[stats_df['Nächster Schritt'] != '4-Fertig'].copy()
        else:
            mapping = {
                "QS1 - Einsatzfähigkeit": "1-Einsatzfähigkeit",
                "QS2 - Truppmitglied": "2-Truppmitglied",
                "QS3 - Truppführende/r": "3-Truppführende/r",
                "EStabK": "4-Fertig" # Only fully completed people can take EStabK
            }
            display_df = stats_df[stats_df['Nächster Schritt'] == mapping.get(view_mode, "")].copy()
            
        # Sort display_df based on the view_mode (Pre-sort for UI)
        try:
            if view_mode == "QS1 - Einsatzfähigkeit" and "QS1 %" in display_df.columns:
                display_df = display_df.sort_values(by=["QS1 %", "Name"], ascending=[False, True]).reset_index(drop=True)
            elif view_mode == "QS2 - Truppmitglied" and "QS2 %" in display_df.columns:
                display_df = display_df.sort_values(by=["QS2 %", "Name"], ascending=[False, True]).reset_index(drop=True)
            elif view_mode == "QS3 - Truppführende/r" and "Ergänzung %" in display_df.columns:
                display_df = display_df.sort_values(by=["Ergänzung %", "Name"], ascending=[False, True]).reset_index(drop=True)
            elif view_mode == "EStabK" and "EStabK %" in display_df.columns:
                display_df = display_df.sort_values(by=["EStabK %", "Name"], ascending=[False, True]).reset_index(drop=True)
            elif view_mode == "Gesamtübersicht":
                display_df = display_df.sort_values(by="Name").reset_index(drop=True)
        except Exception as e:
            logger.error(f"Error sorting display_df: {e}")
            
        # Calculate module stats restricted to the display cohort
        display_names = display_df['Name'].tolist()
        df_display_only = df[df['person_name'].isin(display_names)].copy()
        if df_display_only.empty and not df.empty:
            # Fallback for empty cohort to prevent total breakdown, though typically we just show 0
            df_display_only = pd.DataFrame(columns=df.columns)
            
        mod_stats_df = get_cached_mod_stats(df_display_only if not df_display_only.empty else df)
        
        # If the cohort is empty, zero out the stats for accuracy in UI
        if df_display_only.empty:
            mod_stats_df['Absolventen'] = 0
            mod_stats_df['Gesamt'] = 0
            mod_stats_df['Quote'] = 0
        
        st.header(f"📊 {view_mode}")
        cl, ce = st.columns([10, 2])
        
        cohort_label = "Teilnehmer" if view_mode != "Gesamtübersicht" else "Teilnehmer (ohne Abgeschlossene)"
        cl.subheader(f"{cohort_label} ({len(display_df)})")

        with ce:
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine='openpyxl') as wr:
                stats_df.to_excel(wr, sheet_name='Teilnehmer', index=False)
                mod_stats_df.to_excel(wr, sheet_name='Modul_Statistik', index=False)
                df.to_excel(wr, sheet_name='Rohdaten', index=False)
            st.download_button("📥 Excel Export", buf.getvalue(), "mga_status.xlsx", "application/vnd.openxml", use_container_width=True)
        
        # Aktuelle QS-Stufe als lesbaren String rendern
        def _qs_label(schritt: str) -> str:
            return {"1-Einsatzfähigkeit": "QS1", "2-Truppmitglied": "QS2",
                    "3-Truppführende/r": "QS3", "4-Fertig": "✅ Abgeschlossen"}.get(schritt, schritt)

        # Prüfe ob jemand bereit für Hochstufung ist
        promotable = []
        for _, row in display_df.iterrows():
            schritt = row['Nächster Schritt']
            name = row['Name']
            if schritt == "1-Einsatzfähigkeit" and row.get('QS1 %', 0) >= 90:
                promotable.append((name, schritt, "QS2", row.get('QS1 %', 0)))
            elif schritt == "2-Truppmitglied" and row.get('QS2 %', 0) >= 90:
                promotable.append((name, schritt, "QS3", row.get('QS2 %', 0)))
            elif schritt == "3-Truppführende/r" and row.get('Ergänzung %', 0) >= 100:
                promotable.append((name, schritt, "Abgeschlossen", 100))

        if promotable:
            st.subheader(f"🎯 Bereit für Prüfung ({len(promotable)})")
            for p_name, aktuell, naechste, prozent in promotable:
                col_i, col_b2 = st.columns([8, 2])
                col_i.info(f"🟢 **{p_name}** hat {_qs_label(aktuell)} ({prozent}%) absolviert – bereit für **{naechste}**!")
                
                p_bday = _get_birthday_for_name(p_name)
                qs_cur = all_qs.get((p_name, p_bday), {'qs1_done': False, 'qs2_done': False, 'qs3_done': False})
                
                if col_b2.button(f"➡ {naechste}", key=f"promote_{p_name}"):
                    if naechste == "QS2": qs_cur['qs1_done'] = True
                    elif naechste == "QS3": qs_cur['qs1_done'] = True; qs_cur['qs2_done'] = True
                    elif naechste == "Abgeschlossen": qs_cur['qs1_done'] = True; qs_cur['qs2_done'] = True; qs_cur['qs3_done'] = True
                    update_person_qs_status(p_name, p_bday, qs_cur['qs1_done'], qs_cur['qs2_done'], qs_cur['qs3_done'], unit_id=st.session_state.get('unit_id'))
                    st.success(f"{p_name} wurde auf {naechste} hochgesetzt!")
                    st.rerun()
            st.divider()

        # Admin: Alle Personen löschen
        if st.session_state.get('username', '').lower() == 'admin':
            with st.expander("🔴 Admin: Alle Personen dieser Einheit löschen", expanded=False):
                st.warning(f"⚠️ Löscht ALLE Teilnehmer der Einheit **{st.session_state.get('unit_name')}** aus der Datenbank. Nicht rückgängig zu machen!")
                _del_confirm_key = "admin_delete_all_confirm"
                if st.button("🗑️ Alle Personen dieser Einheit löschen", key="admin_del_all_btn", use_container_width=True, type="primary"):
                    st.session_state[_del_confirm_key] = "pending"
                if st.session_state.get(_del_confirm_key) == "pending":
                    st.error("Bist du absolut sicher? Diese Aktion kann NICHT rückgängig gemacht werden.")
                    ca2, cb2 = st.columns(2)
                    if ca2.button("✅ Ja, alle löschen", key="admin_del_all_confirm_btn", use_container_width=True):
                        del st.session_state[_del_confirm_key]
                        curr_uid = st.session_state.get('unit_id')
                        ok_db, err_db = delete_all_persons(unit_id=curr_uid)
                        if ok_db:
                            st.session_state.df = None
                            st.session_state.last_loaded_file = None
                            st.session_state.selected_person = None
                            st.cache_data.clear()
                            st.success("✅ Alle Personen wurden gelöscht.")
                            st.rerun()
                        else:
                            st.error(f"Fehler: {err_db}")
                    if cb2.button("✖ Abbrechen", key="admin_del_all_cancel_btn", use_container_width=True):
                        del st.session_state[_del_confirm_key]
                        st.rerun()



        if not display_df.empty:
            display_df['Aktuelle Stufe'] = display_df['Nächster Schritt'].apply(_qs_label)
            cfg = {
                "Gesamt %": st.column_config.ProgressColumn("Gesamt", format="%.0f%%", min_value=0, max_value=100),
                "QS1 %": st.column_config.ProgressColumn("QS1", format="%.0f%%", min_value=0, max_value=100),
                "QS2 %": st.column_config.ProgressColumn("QS2", format="%.0f%%", min_value=0, max_value=100),
                "Ergänzung %": st.column_config.ProgressColumn("Ergänzung", format="%.0f%%", min_value=0, max_value=100),
                "EStabK %": st.column_config.ProgressColumn("EStabK", format="%.0f%%", min_value=0, max_value=100),
                "Aktuelle Stufe": st.column_config.TextColumn("Aktuelle QS-Stufe"),
                "Nächster Schritt": None,
                "Module": "Module"
            }
            
            base_cols = ['Name', 'Aktuelle Stufe', 'Gesamt %', 'QS1 %', 'QS2 %', 'Ergänzung %']
            if view_mode == "EStabK":
                base_cols.append('EStabK %')
            base_cols.append('Module')
            
            cols_to_show = [c for c in base_cols if c in display_df.columns]
            
            
            
            sel_key = f"sel_{view_mode.replace(' ', '_')}"
            
            event = st.dataframe(
                display_df[cols_to_show], 
                column_config=cfg, 
                use_container_width=True, 
                hide_index=True,
                selection_mode="single-row",
                on_select="rerun",
                key=sel_key
            )
            
            if event and len(event.selection.rows) > 0:
                selected_idx = event.selection.rows[0]
                person_name = display_df.iloc[selected_idx]['Name']
                if st.session_state.get('selected_person') != person_name:
                    st.session_state.selected_person = person_name
                    st.rerun()
        else:
            st.info("Zurzeit sind keine Teilnehmer in dieser Qualifikationsstufe.")

        st.divider()
        st.subheader("Modul-Statistik")
        
        display_mod_stats = mod_stats_df.copy()
        if view_mode != "Gesamtübersicht":
            qs_prefix = view_mode.split()[0]  # Extracts "QS1", "QS2", "QS3", "EStabK"
            if qs_prefix == "QS3":
                display_mod_stats = display_mod_stats[
                    display_mod_stats['QS-Stufe'].astype(str).str.contains("QS3", case=False) | 
                    display_mod_stats['QS-Stufe'].astype(str).str.contains("Ergänzung", case=False)
                ]
            elif qs_prefix == "EStabK":
                 display_mod_stats = display_mod_stats[display_mod_stats['QS-Stufe'].astype(str).str.contains("EStabK", case=False)]
            else:
                display_mod_stats = display_mod_stats[display_mod_stats['QS-Stufe'].astype(str).str.contains(qs_prefix, case=False)]
            
        st.dataframe(display_mod_stats, column_config={"Quote": st.column_config.ProgressColumn("Quote", format="%.0f%%", min_value=0, max_value=100)}, width='stretch', hide_index=True)

    else:
        # Individual View
        p = st.session_state.selected_person
        name_del = p.strip()
        bday_del = _get_birthday_for_name(name_del)

        # Löschen-Logik: ausstehende Löschaktion ausführen
        if st.session_state.get(f"confirm_delete_{p}") == "confirmed":
            del st.session_state[f"confirm_delete_{p}"]
            curr_unit = st.session_state.get('unit_id')
            ok_sq, err_sq = delete_person_from_cache(name_del, bday_del, unit_id=curr_unit)
            ok_db, err_db = delete_person(name_del, bday_del, unit_id=curr_unit)
            if ok_db or ok_sq:
                # Session-State bereinigen
                st.session_state.df = st.session_state.df[st.session_state.df['person_name'] != p]
                st.session_state.selected_person = None
                st.cache_data.clear()
                st.success(f"✅ {name_del} wurde gelöscht.")
                st.rerun()
            else:
                st.error(f"Fehler beim Löschen: {err_db or err_sq}")

        col_head, col_nav, col_del = st.columns([6, 2, 2])
        col_head.header(f"👤 {p}")

        # QR-Code generieren Button
        col_qr1, col_qr2 = st.columns([1, 4])
        with col_qr1:
            if st.button("📱 QR-Code für Teilnehmer", help="Zeigt einen QR-Code an, den der Teilnehmer scannen kann, um seine eigene Übersicht zu öffnen"):
                st.session_state[f"show_qr_{p}"] = not st.session_state.get(f"show_qr_{p}", False)
                
        if st.session_state.get(f"show_qr_{p}", False):
            # Domain-Fallback, Streamlit host name from window location would be best, but we use env var or fallback
            base_url = os.environ.get("BASE_URL", "http://localhost:8501")
            
            # Fix if running in Streamlit Community Cloud or behind proxy
            if "localhost" in base_url and st.context.headers.get("host"):
                host = st.context.headers.get("host")
                proto = st.context.headers.get("x-forwarded-proto", "http")
                base_url = f"{proto}://{host}"
                
            public_url = f"{base_url}/?view=public&name={urllib.parse.quote(p.strip())}&bday={urllib.parse.quote(bday_del)}"
            
            qr = qrcode.QRCode(version=1, box_size=10, border=4)
            qr.add_data(public_url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            
            st.info("Lass den Teilnehmer diesen QR-Code scannen (Web-Browser). Das Passwort lautet: **15-52-1**")
            st.image(buf.getvalue(), width=250)
            
            st.code(public_url, language="text")
            st.divider()
        
        # Navigation
        all_persons_list = sorted(list(df['person_name'].unique()))
        try:
            curr_idx = all_persons_list.index(p)
            prev_p = all_persons_list[curr_idx - 1] if curr_idx > 0 else None
            next_p = all_persons_list[curr_idx + 1] if curr_idx < len(all_persons_list) - 1 else None
        except ValueError:
            prev_p, next_p = None, None

        with col_nav:
            c_prev, c_next = st.columns(2)
            if c_prev.button("◀", disabled=(prev_p is None), use_container_width=True, help="Vorherige Person"):
                st.session_state.selected_person = prev_p
                st.rerun()
            if c_next.button("▶", disabled=(next_p is None), use_container_width=True, help="Nächste Person"):
                st.session_state.selected_person = next_p
                st.rerun()

        if col_del.button("🗑️ Person löschen", key=f"del_btn_{p}", type="secondary", use_container_width=True):
            st.session_state[f"confirm_delete_{p}"] = "pending"

        # Sicherheitsabfrage anzeigen
        if st.session_state.get(f"confirm_delete_{p}") == "pending":
            st.warning(f"⚠️ Soll **{name_del}** wirklich unwiderruflich gelöscht werden? Alle Daten (Modulliste, QS-Status, Verlauf) werden aus der Datenbank entfernt.")
            ca, cb = st.columns(2)
            if ca.button("🗑️ Ja, endgültig löschen", key=f"del_confirm_{p}", type="primary", use_container_width=True):
                st.session_state[f"confirm_delete_{p}"] = "confirmed"
                st.rerun()
            if cb.button("✖ Abbrechen", key=f"del_cancel_{p}", use_container_width=True):
                del st.session_state[f"confirm_delete_{p}"]
                st.rerun()
            st.stop()

        p_df = df[df['person_name'] == p].copy()
        
        if not p_df.empty:
            first = p_df.iloc[0]
            meta = [c for c in p_df.columns if c.startswith("meta_") and pd.notna(first[c]) and c not in ['meta_qs1_done', 'meta_qs2_done', 'meta_qs3_done']]
            if meta:
                cols = st.columns(min(len(meta), 3))
                for j, c in enumerate(meta):
                    with cols[j % 3]: st.info(f"**{c.replace('meta_', '')}**\n\n{first[c]}")

        # Exclude both Ergänzung and EStabK from main core progress
        p_df_core = p_df[~p_df['qs_level'].astype(str).str.contains("Ergänzungsmodule|EStabK", case=False, regex=True)]
        stats = get_summary_stats(p_df_core if not p_df_core.empty else p_df)
        m1, m2, m3 = st.columns(3)
        m1.metric("Gesamtfortschritt", f"{int(stats['overall_progress'])}%")
        m2.metric("Absolvierte Module", f"{stats['completed_modules']} / {stats['total_modules']}")
        m3.progress(stats['overall_progress']/100)
        
        if db_ok:
            st.divider()
            st.subheader("🎓 Qualifikationsstufen")
            name = p.strip()
            bday = _get_birthday_for_name(name)

            _pending_key = f"qs_pending_{p}"  # wird noch als Reset-Key verwendet

            qs_status = get_person_qs_status_cached(name, bday)
            _qs_options = ["QS1 - Einsatzfähigkeit", "QS2 - Truppmitglied", "QS3 - Truppführende/r", "✅ Abgeschlossen"]
            if not qs_status['qs1_done']:
                _current_idx = 0
            elif not qs_status['qs2_done']:
                _current_idx = 1
            elif not qs_status['qs3_done']:
                _current_idx = 2
            else:
                _current_idx = 3

            # Alle Stufen anbieten – manuelles Runtersetzen in der Detailansicht erlaubt
            _available = _qs_options
            _qs_sel_key = f"qs_sel_{p}"

            # Selectbox-Wert aus session_state lesen (verhindert Reset beim Rerun)
            _sel_default = st.session_state.get(_qs_sel_key, _qs_options[_current_idx])
            if _sel_default not in _available:
                _sel_default = _qs_options[_current_idx]

            def confirm_qs():
                new_qs1 = st.session_state.get(_qs_sel_key) in _available[1:] or st.session_state.get(_qs_sel_key) == _available[0]
                # Actually, better to calculate it based on index
                idx = _available.index(st.session_state.get(_qs_sel_key))
                update_person_qs_status(name, bday, idx >= 1, idx >= 2, idx >= 3, unit_id=st.session_state.get('unit_id'))
                
            def cancel_qs():
                st.session_state[_qs_sel_key] = _available[_current_idx]

            _sel = st.selectbox(
                "Aktuelle QS-Stufe",
                options=_available,
                index=_available.index(_sel_default),
                key=_qs_sel_key,
                help="Stufe manuell setzen – hoch- und runtersetzen möglich."
            )

            _new_idx = _qs_options.index(_sel)
            if _new_idx != _current_idx:
                st.warning(f"QS-Stufe für **{name}** auf **{_sel}** setzen?")
                _c1, _c2 = st.columns(2)
                if _c1.button("✅ Übernehmen", key=f"qs_confirm_{p}", use_container_width=True, type="primary", on_click=confirm_qs):
                    pass # logic handled in callback
                if _c2.button("✖ Abbrechen", key=f"qs_cancel_{p}", use_container_width=True, on_click=cancel_qs):
                    pass # logic handled in callback
            else:
                st.info(f"Aktuelle Stufe: **{_qs_options[_current_idx]}**")

        if db_ok:
            st.subheader("📊 Fortschritts-Verlauf")
            try:
                name = p.strip()
                bday = _get_birthday_for_name(name)
                h_data = get_cached_history(name, bday)
                if h_data:
                    h_df = pd.DataFrame(h_data)
                    h_df['upload_date'] = pd.to_datetime(h_df['upload_date'])
                    st.line_chart(h_df.set_index('upload_date')['completed_modules'])
                else: st.info("Noch keine Daten.")
            except: pass

        st.divider()
        unique_l = sorted(p_df['qs_level'].unique())
        tabs = st.tabs([str(l) for l in unique_l] + ["Alle"])
        cfg = {"Progress": st.column_config.ProgressColumn("Erfüllung", format="%.0f%%", min_value=0, max_value=100)}
        for i, l in enumerate(unique_l):
            with tabs[i]: st.dataframe(p_df[p_df['qs_level'] == l], width='stretch', column_config=cfg, hide_index=True)
        with tabs[-1]: st.dataframe(p_df, width='stretch', column_config=cfg, hide_index=True)
        
        st.write("---")
        st.subheader("📄 Original Ausdruck (PDF)")
        try:
            import io as _io
            raw_pdf = get_pdf_cache(int(st.session_state.unit_id))
            if raw_pdf:
                with st.spinner("Isoliere Original-Dokument (PDF)..."):
                    target_name = p.strip()
                    pdf_bytes, images = generate_isolated_pdf_for_person(_io.BytesIO(raw_pdf), target_name)
                    if pdf_bytes and images:
                        st.download_button(
                            label="📥 Eigenes PDF-Zertifikat herunterladen",
                            data=pdf_bytes,
                            file_name=f"Ausbildungsnachweis_{target_name.replace(' ', '_')}.pdf",
                            mime="application/pdf"
                        )
                        for im in images:
                            st.image(im)
                    else:
                        st.info("Diese Person wurde im aktuell hinterlegten PDF-Ausdruck nicht als Text gefunden.")
            else:
                st.info("Kein PDF-Cache für diese Einheit. Bitte PDF einmal hochladen oder Auto-Download starten.")
        except Exception as e:
            st.warning(f"Fehler beim Laden der PDF: {e}")


else:
    st.markdown("### 👋 Willkommen beim Ausbildungs-Tracker")
    st.info("Bitte laden Sie ein PDF in der Seitenleiste hoch.")
