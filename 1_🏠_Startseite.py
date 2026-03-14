import streamlit as st

st.set_page_config(
    page_title="FeuerProfi",
    page_icon="🚒",
    layout="wide"
)

# === GLOBAL CUSTOM CSS (Graphics Enhancement) ===
st.markdown("""
<style>
    /* Modern Glasscard Look for main blocks */
    div.block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    
    /* Beautify metric boxes */
    div[data-testid="metric-container"] {
        background-color: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(128, 128, 128, 0.2);
        padding: 1rem;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        transition: transform 0.2s ease;
    }
    div[data-testid="metric-container"]:hover {
        transform: translateY(-2px);
    }
    
    /* Make DataFrames pop with slight shadows */
    div[data-testid="stDataFrame"] {
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    }
    
    /* Stylish Tabs */
    button[data-baseweb="tab"] {
        font-weight: 500;
        border-radius: 6px 6px 0 0;
        transition: background-color 0.2s;
    }
    
    /* Primary buttons */
    button[data-testid="baseButton-primary"] {
        border-radius: 8px;
        font-weight: bold;
        transition: all 0.2s;
        box-shadow: 0 2px 4px rgba(255, 75, 75, 0.3);
    }
    button[data-testid="baseButton-primary"]:hover {
        box-shadow: 0 4px 8px rgba(255, 75, 75, 0.5);
        transform: translateY(-1px);
    }
    
    /* Custom Firetruck Loading Spinner at top right */
    [data-testid="stStatusWidget"] {
        display: flex !important;
        align-items: center !important;
    }
    [data-testid="stStatusWidget"] svg {
        display: none !important; /* Hide default running man */
    }
    [data-testid="stStatusWidget"]::before {
        content: '🚒';
        font-size: 1.3rem;
        line-height: 1;
        margin-right: 8px;
        animation: flip_icons 2.5s infinite, pulse_scale 0.5s infinite alternate;
    }
    @keyframes flip_icons {
        0%, 19% { content: '🚒'; }
        20%, 39% { content: '📟'; }
        40%, 59% { content: '🧯'; }
        60%, 79% { content: '👨‍🚒'; }
        80%, 100% { content: '🔥'; }
    }
    @keyframes pulse_scale {
        0% { transform: scale(0.9); }
        100% { transform: scale(1.1); }
    }
</style>
""", unsafe_allow_html=True)


import os
import sys
import glob
from datetime import datetime
import logging

# --- LOGGING SETUP ---
import seqlog
from logging.handlers import RotatingFileHandler

# Ensure data directory exists for logs
os.makedirs("data", exist_ok=True)

seq_server_url = os.environ.get("SEQ_SERVER_URL")
seq_api_key = os.environ.get("SEQ_API_KEY")

formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Primary Log File
file_handler = RotatingFileHandler(
    'data/app.log',
    maxBytes=10 * 1024 * 1024, # 10 MB limit
    backupCount=3,
    encoding='utf-8'
)
file_handler.setFormatter(formatter)
file_handler.setLevel(logging.DEBUG)

# Secondary Error Log File
error_handler = RotatingFileHandler(
    'data/error.log',
    maxBytes=10 * 1024 * 1024, # 10 MB limit
    backupCount=3,
    encoding='utf-8'
)
error_handler.setFormatter(formatter)
error_handler.setLevel(logging.WARNING)

console = logging.StreamHandler(sys.stdout)
console.setFormatter(formatter)
console.setLevel(logging.DEBUG)

root_logger = logging.getLogger('')
for h in root_logger.handlers[:]:
    root_logger.removeHandler(h)

root_logger.setLevel(logging.DEBUG)
root_logger.addHandler(console)
root_logger.addHandler(file_handler)
root_logger.addHandler(error_handler)

if seq_server_url:
    seqlog.log_to_seq(
        server_url=seq_server_url,
        api_key=seq_api_key,
        level=logging.DEBUG,
        batch_size=1,
        auto_flush_timeout=1,
        override_root_logger=True
    )
    # SEQ logger overrides root, so add local handlers again if we want dual logging
    logging.getLogger('').addHandler(console)
    logging.getLogger('').addHandler(file_handler)
    logging.getLogger('').addHandler(error_handler)

logger = logging.getLogger(__name__)

from src.database import verify_user, log_login, init_db, delete_expired_participants, export_db_to_json, is_default_password, change_password
try:
    from src.database import get_connection
    init_db()
    db_ok = True
    logger.info("Database initialized successfully.")
except Exception as e:
    logger.error(f"DB Error during initialization: {e}")
    db_ok = False
import streamlit_cookies_manager
from apscheduler.schedulers.background import BackgroundScheduler

# Setup Background Scheduler for midnight deletions
def daily_db_backup():
    try:
        compressed_data = export_db_to_json(include_history=True)
        now_str = datetime.now().strftime("%Y-%m-%d")
        filepath = os.path.join("data", f"backup_{now_str}.json.gz")
        with open(filepath, "wb") as f:
            f.write(compressed_data)
        
        # Keep only the last 14 backups
        backups = sorted(glob.glob(os.path.join("data", "backup_*.json.gz")))
        if len(backups) > 14:
            for old_backup in backups[:-14]:
                os.remove(old_backup)
                logger.debug(f"Deleted old backup: {old_backup}")
        logger.info(f"Daily backup created: {filepath}")
    except Exception as e:
        logger.error(f"Daily backup failed: {e}")

from src.database import get_unsent_incident_reports, mark_reports_as_sent, get_email_config
from src.mailer import send_incident_report_summary

def check_unsent_reports():
    try:
        # Wir gehen hier von unit_id = 1 aus, in einer Multi-Tenant Umgebung müsste man iterieren.
        config = get_email_config(1)
        if not config:
            return  # Email nicht konfiguriert
            
        reports = get_unsent_incident_reports()
        if not reports:
            return
            
        # Verzögerung abrufen, Fallback 60
        delay_minutes_setting = config.get("delay_minutes", 60)
            
        # Find the timestamp of the newest report
        newest_time = max([datetime.strptime(r['created_at'], "%Y-%m-%d %H:%M:%S") for r in reports])
        now = datetime.now()
        diff_minutes = (now - newest_time).total_seconds() / 60.0
        
        if diff_minutes >= delay_minutes_setting:
            logger.info(f"Found {len(reports)} unsent reports older than configured delay ({delay_minutes_setting} mins). Sending now...")
            
            ok, err = send_incident_report_summary(config, reports)
            if ok:
                # Markiere die versendeten Berichte in der Datenbank
                report_ids = [r['id'] for r in reports]
                mark_ok, mark_err = mark_reports_as_sent(report_ids)
                if mark_ok:
                    logger.info("Reports successfully emailed and marked as sent.")
                else:
                    logger.error(f"Failed to mark reports as sent: {mark_err}")
            else:
                 logger.error(f"Failed to send incident report summary: {err}")
                 
    except Exception as e:
        logger.error(f"check_unsent_reports failed: {e}")

if "scheduler" not in st.session_state:
    scheduler = BackgroundScheduler()
    # Runs everyday at midnight (00:00)
    scheduler.add_job(delete_expired_participants, 'cron', hour=0, minute=0, args=[360])
    scheduler.add_job(daily_db_backup, 'cron', hour=0, minute=0)
    # Check for incident reports every 5 minutes
    scheduler.add_job(check_unsent_reports, 'interval', minutes=5)
    
    scheduler.start()
    logger.info("BackgroundScheduler started for daily jobs and auto-send.")
    st.session_state.scheduler = scheduler

_cookies = streamlit_cookies_manager.CookieManager()
if not _cookies.ready():
    st.stop()

if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

# --- PUBLIC VIEW ROUTING BYPASS ---
is_public_view = st.query_params.get("view") == "public"
if is_public_view:
    # Lade direkt NUR die MGLA Ansicht, die sich selbst authentifiziert (Einheitscode)
    mgla = st.Page("pages/MGLA.py", title="Qualifikationsnachweis", icon="🚒")
    pg = st.navigation([mgla])
    pg.run()
    st.stop()

# --- AUTHENTICATION (mit Cookie-Persistenz) ---
cookie_user = _cookies.get("username", "")
cookie_auth = _cookies.get("auth", "")

# --- TOKEN AUTHENTICATION BYPASS ---
from src.database import get_vehicle_by_token
token_param = st.query_params.get("token", "")

# Initialer Load durch Token URL
if token_param:
    vehicle = get_vehicle_by_token(token_param)
    if vehicle:
        st.session_state.authenticated = True
        st.session_state.username = f"Einsatz Modus: {vehicle['call_sign']}"
        st.session_state.is_token_auth = True
        st.session_state.token_vehicle_id = vehicle['id']
        st.session_state.token_vehicle_name = vehicle['call_sign']
    else:
        st.error("Ungültiger Token-Link.")

if not st.session_state.authenticated:
    # Prüfe ob ein gültiges Login-Cookie existiert
    if cookie_user and cookie_auth == "1":
        st.session_state.authenticated = True
        st.session_state.username = cookie_user
        st.session_state.is_token_auth = False
        
        # Hol die definierte Einheit für den Auto-Login aus der DB
        from src.database import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT u.unit_id, u.is_admin, un.name FROM users u LEFT JOIN units un ON u.unit_id = un.id WHERE u.username=?", (cookie_user,))
        res = cur.fetchone()
        cur.close()
        conn.close()
        if res:
            pass # unit_id is hardcoded
            st.session_state.unit_name = res['name']
            st.session_state.is_admin = bool(res['is_admin'])
        else:
            pass # unit_id is hardcoded
            st.session_state.unit_name = None
            st.session_state.is_admin = False
    else:
        st.session_state.authenticated = False
        if "is_token_auth" not in st.session_state:
            st.session_state.is_token_auth = False
        st.session_state.is_admin = False

def login():
    st.title("🔐 Login")
    
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
        
        
        
        remember = st.checkbox("Angemeldet bleiben", value=True)
        
        if st.button("Anmelden", use_container_width=True, type="primary") or st.session_state.pop("do_login", False):
            if not username or not password:
                st.error("Bitte Benutzername und Passwort eingeben.")
            else:
                success, db_unit_id, db_unit_name, is_admin_flag = verify_user(username, password)
                if success:
                    client_ip = st.context.headers.get("X-Forwarded-For", "Unknown IP") if hasattr(st, 'context') else "Unknown IP"
                    log_login(username, client_ip, "Erfolgreich")
                    import logging
                    lo = logging.getLogger("TrainingTracker")
                    lo.info(f"User {username} logged in successfully")
                    st.session_state.authenticated = True
                    st.session_state.username = username
                    st.session_state.is_admin = is_admin_flag
                    st.session_state.df = None
                    st.session_state.last_loaded_file = None
                    st.session_state.unit_name = "Feuerwehr"
                        
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

# --- FORCED PASSWORD CHANGE (if default password is still set) ---
if st.session_state.authenticated and not st.session_state.get('is_token_auth', False):
    current_user = st.session_state.get('username', '')
    if current_user and is_default_password(current_user):
        st.warning("🔒 **Sicherheitshinweis:** Du verwendest noch das Standard-Passwort. Bitte lege jetzt ein neues Passwort fest.")
        with st.form("force_password_change"):
            new_pw = st.text_input("Neues Passwort", type="password")
            new_pw_confirm = st.text_input("Neues Passwort bestätigen", type="password")
            submitted = st.form_submit_button("Passwort ändern", type="primary", use_container_width=True)
            if submitted:
                if not new_pw or len(new_pw) < 4:
                    st.error("Das Passwort muss mindestens 4 Zeichen lang sein.")
                elif new_pw == "admin":
                    st.error("Das neue Passwort darf nicht 'admin' sein.")
                elif new_pw != new_pw_confirm:
                    st.error("Die Passwörter stimmen nicht überein.")
                else:
                    ok, err = change_password(current_user, new_pw)
                    if ok:
                        st.success("✅ Passwort erfolgreich geändert!")
                        import time
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(f"Fehler: {err}")
        st.stop()


# Initialize pages
dashboard = st.Page("views/dashboard.py", title="Startseite", icon="🏠", default=True)
mgla = st.Page("pages/2_📊_MGLA_Dashboard.py", title="MGLA Dashboard", icon="📊")
personal = st.Page("views/personal.py", title="Personal", icon="👥")
gruppen = st.Page("views/gruppen.py", title="Gruppen-Einteilung", icon="🧑‍🤝‍🧑")
einsatzbericht = st.Page("views/einsatzbericht.py", title="Einsatz erfassen", icon="📋")
einsatz_historie = st.Page("views/einsatz_historie.py", title="Einsatz-Historie", icon="📜")
settings = st.Page("views/settings.py", title="Einstellungen", icon="⚙️")

pages = [dashboard]

# Conditionally show pages based on role
if st.session_state.get('is_token_auth', False):
    # Wenn über Token angemeldet, zeige NUR den Einsatzbericht
    pages = [einsatzbericht]
else:
    # Always include mgla, personal, gruppen, einsatzbericht, historie for authenticated users
    pages.extend([mgla, personal, gruppen, einsatzbericht, einsatz_historie])
    
    # Settings only for admins
    if st.session_state.get('is_admin', False):
        pages.append(settings)

pg = st.navigation(pages)

with st.sidebar:
    st.write(f"Angemeldet als: **{st.session_state.get('username', 'Unbekannt')}**")
    
    if not st.session_state.get('is_token_auth', False):
        if st.button("🚪 Abmelden", use_container_width=True):
            st.session_state.authenticated = False
            st.session_state.username = None
            _cookies["username"] = ""
            _cookies["auth"] = ""
            _cookies.save()
            st.rerun()

pg.run()

