import sqlite3
import os
import threading
import logging

logger = logging.getLogger(__name__)

# Core database path and lock
_SQLITE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "local_cache.db")
os.makedirs(os.path.dirname(_SQLITE_PATH), exist_ok=True)
_lock = threading.Lock()

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(_SQLITE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn

def init_db():
    with _lock:
        conn = get_connection()
        try:
            logger.debug("Initializing database schema...")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS units (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    public_view_password TEXT DEFAULT 'feuerprofi'
                );
                
                CREATE TABLE IF NOT EXISTS stundennachweis_config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    unit_id INTEGER UNIQUE NOT NULL,
                    letzter_zeitraum TEXT,
                    last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (unit_id) REFERENCES units(id) ON DELETE CASCADE
                );
                
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    unit_id INTEGER DEFAULT NULL,
                    FOREIGN KEY (unit_id) REFERENCES units(id) ON DELETE SET NULL
                );
                
                CREATE TABLE IF NOT EXISTS participants (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    birthday TEXT NOT NULL,
                    gender TEXT,
                    start_date TEXT,
                    metadata TEXT,
                    einsatzstunden REAL DEFAULT 0.0,
                    dienststunden REAL DEFAULT 0.0,
                    last_seen TEXT DEFAULT CURRENT_DATE,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(name, birthday, unit_id),
                    FOREIGN KEY (unit_id) REFERENCES units(id) ON DELETE SET NULL
                );
                
                CREATE TABLE IF NOT EXISTS uploads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    upload_date TEXT DEFAULT CURRENT_TIMESTAMP,
                    filename TEXT
                );
                
                CREATE TABLE IF NOT EXISTS login_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    ip_address TEXT,
                    status TEXT,
                    login_time TEXT DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE TABLE IF NOT EXISTS person_qs_status (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    participant_id INTEGER UNIQUE,
                    qs1_done INTEGER DEFAULT 0,
                    qs2_done INTEGER DEFAULT 0,
                    qs3_done INTEGER DEFAULT 0,
                    FOREIGN KEY (participant_id) REFERENCES participants(id) ON DELETE CASCADE
                );
                
                CREATE TABLE IF NOT EXISTS modules (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    qs_level TEXT,
                    T_Soll REAL DEFAULT 0.0,
                    P_Soll REAL DEFAULT 0.0,
                    K_Soll REAL DEFAULT 0.0
                );
                
                CREATE TABLE IF NOT EXISTS module_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    participant_id INTEGER,
                    upload_id INTEGER,
                    module_id TEXT,
                    status TEXT,
                    hours REAL,
                    start_time TEXT,
                    end_time TEXT,
                    date TEXT,
                    T_Ist REAL DEFAULT 0.0,
                    P_Ist REAL DEFAULT 0.0,
                    K_Ist REAL DEFAULT 0.0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (participant_id) REFERENCES participants(id) ON DELETE CASCADE,
                    FOREIGN KEY (upload_id) REFERENCES uploads(id) ON DELETE CASCADE,
                    FOREIGN KEY (module_id) REFERENCES modules(id) ON DELETE CASCADE
                );
                
                CREATE TABLE IF NOT EXISTS feueron_sync_config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    unit_id INTEGER UNIQUE NOT NULL,
                    feueron_org TEXT,
                    feueron_org_id TEXT,
                    feueron_username TEXT,
                    feueron_password TEXT,
                    sync_hour INTEGER DEFAULT 3,
                    sync_minute INTEGER DEFAULT 0,
                    sync_enabled INTEGER DEFAULT 0,
                    last_sync_at TEXT,
                    last_sync_status TEXT,
                    last_sync_message TEXT,
                    FOREIGN KEY (unit_id) REFERENCES units(id) ON DELETE CASCADE
                );
                
                CREATE TABLE IF NOT EXISTS qualifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    value INTEGER NOT NULL,
                    prerequisite_id INTEGER,
                    equivalent_id INTEGER,
                    FOREIGN KEY (prerequisite_id) REFERENCES qualifications (id) ON DELETE SET NULL,
                    FOREIGN KEY (equivalent_id) REFERENCES qualifications (id) ON DELETE SET NULL
                );
                
                CREATE TABLE IF NOT EXISTS participant_qualifications (
                    participant_id INTEGER,
                    qualification_id INTEGER,
                    assigned_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (participant_id, qualification_id),
                    FOREIGN KEY (participant_id) REFERENCES participants (id) ON DELETE CASCADE,
                    FOREIGN KEY (qualification_id) REFERENCES qualifications (id) ON DELETE CASCADE
                );
                
                CREATE TABLE IF NOT EXISTS vehicles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    unit_id INTEGER NOT NULL,
                    call_sign TEXT NOT NULL,
                    seats INTEGER NOT NULL DEFAULT 1,
                    token TEXT UNIQUE,
                    FOREIGN KEY (unit_id) REFERENCES units(id) ON DELETE CASCADE
                );
                
                CREATE TABLE IF NOT EXISTS incident_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    unit_id INTEGER NOT NULL,
                    keyword TEXT,
                    vehicle_id INTEGER,
                    commander_id INTEGER,
                    unit_leader_id INTEGER,
                    crew_json TEXT,
                    situation TEXT,
                    actions TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    sent_at TEXT DEFAULT NULL,
                    FOREIGN KEY (unit_id) REFERENCES units(id) ON DELETE CASCADE,
                    FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE SET NULL,
                    FOREIGN KEY (commander_id) REFERENCES participants(id) ON DELETE SET NULL,
                    FOREIGN KEY (unit_leader_id) REFERENCES participants(id) ON DELETE SET NULL
                );
                
                CREATE TABLE IF NOT EXISTS email_config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    unit_id INTEGER UNIQUE NOT NULL,
                    smtp_server TEXT,
                    smtp_port INTEGER,
                    smtp_user TEXT,
                    smtp_password TEXT,
                    sender_email TEXT,
                    recipient_emails TEXT,
                    delay_minutes INTEGER DEFAULT 60,
                    FOREIGN KEY (unit_id) REFERENCES units(id) ON DELETE CASCADE
                );
                
                CREATE TABLE IF NOT EXISTS promotion_config (
                    unit_id INTEGER PRIMARY KEY,
                    qs1_threshold INTEGER DEFAULT 90,
                    qs2_threshold INTEGER DEFAULT 90,
                    qs3_threshold INTEGER DEFAULT 100,
                    FOREIGN KEY (unit_id) REFERENCES units(id) ON DELETE CASCADE
                );
                
                CREATE TABLE IF NOT EXISTS auto_update_config (
                    id INTEGER PRIMARY KEY CHECK (id = 1), -- Nur ein Eintrag erlaubt
                    update_day INTEGER NOT NULL,
                    update_hour INTEGER NOT NULL,
                    update_minute INTEGER NOT NULL,
                    last_check_at TEXT,
                    update_available INTEGER DEFAULT 0
                );
                
                -- Standardwerte einfügen falls Tabelle leer
                INSERT OR IGNORE INTO auto_update_config (id, update_day, update_hour, update_minute)
                VALUES (1, 0, 3, 0); -- Montag 03:00 Uhr
            """)
            conn.commit()
        finally:
            conn.close()
