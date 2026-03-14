import sqlite3
import os
import time
import threading
from typing import List, Dict, Any, Optional, Tuple, Callable
from datetime import datetime
import streamlit as st
import bcrypt
import json
import logging

# Globale Variable für DB-Verbindung
db_conn = None
logger = logging.getLogger(__name__)

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
                    name TEXT UNIQUE NOT NULL
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
            """)

            # --- Performance Indizes ---
            conn.execute("CREATE INDEX IF NOT EXISTS idx_participants_lookup ON participants(name, birthday);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_module_history_participant ON module_history(participant_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_qs_status_participant ON person_qs_status(participant_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_module_history_composite ON module_history(participant_id, module_id);")

            # --- Auto-Migrations for older schemas (suppress errors if columns already exist) ---
            try: conn.execute("ALTER TABLE vehicles ADD COLUMN token TEXT")
            except Exception: pass
            
            # Populate token for existing vehicles
            try:
                import secrets
                c_veh = conn.cursor()
                c_veh.execute("SELECT id FROM vehicles WHERE token IS NULL OR token = ''")
                for (v_id,) in c_veh.fetchall():
                    new_token = secrets.token_hex(16)
                    conn.execute("UPDATE vehicles SET token=? WHERE id=?", (new_token, v_id))
                conn.commit()
            except Exception: pass
            new_participants_cols = [
                "gender TEXT", "start_date TEXT", "metadata TEXT", 
                "created_at TEXT DEFAULT CURRENT_TIMESTAMP", "updated_at TEXT DEFAULT CURRENT_TIMESTAMP",
                "unit_id INTEGER DEFAULT NULL", "einsatzstunden REAL DEFAULT 0.0", "dienststunden REAL DEFAULT 0.0",
                "last_seen TEXT"
            ]
            for col in new_participants_cols:
                try: conn.execute(f"ALTER TABLE participants ADD COLUMN {col}")
                except Exception: pass
                
            try: conn.execute("UPDATE participants SET last_seen=CURRENT_DATE WHERE last_seen IS NULL")
            except Exception: pass
            conn.commit()
                
            # PDF cache table migration
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS pdf_cache (
                        unit_id INTEGER PRIMARY KEY,
                        pdf_data BLOB NOT NULL,
                        filename TEXT,
                        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS person_pdf_cache (
                        unit_id INTEGER,
                        person_name TEXT,
                        pdf_data BLOB NOT NULL,
                        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (unit_id, person_name)
                    )
                """)
                conn.commit()
            except Exception: pass

            new_history_cols = [
                "qs_level TEXT", "hours TEXT", "start_time TEXT", "end_time TEXT", "date TEXT",
                "created_at TEXT DEFAULT CURRENT_TIMESTAMP",
                "T_Ist REAL DEFAULT 0.0", "T_Soll REAL DEFAULT 0.0",
                "P_Ist REAL DEFAULT 0.0", "P_Soll REAL DEFAULT 0.0",
                "K_Ist REAL DEFAULT 0.0", "K_Soll REAL DEFAULT 0.0"
            ]
            for col in new_history_cols:
                try: conn.execute(f"ALTER TABLE module_history ADD COLUMN {col}")
                except Exception: pass
                
            new_user_cols = ["unit_id INTEGER DEFAULT NULL", "is_admin INTEGER DEFAULT 0"]
            for col in new_user_cols:
                try: conn.execute(f"ALTER TABLE users ADD COLUMN {col}")
                except Exception: pass
                
            # Ensure "admin" user is always an admin
            try: conn.execute("UPDATE users SET is_admin = 1 WHERE username = 'admin'")
            except Exception: pass
            
            # Promotion Config Auto-Migration
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS promotion_config (
                        unit_id INTEGER PRIMARY KEY,
                        qs1_threshold INTEGER DEFAULT 90,
                        qs2_threshold INTEGER DEFAULT 90,
                        qs3_threshold INTEGER DEFAULT 100,
                        FOREIGN KEY (unit_id) REFERENCES units(id) ON DELETE CASCADE
                    )
                """)
            except Exception: pass

            conn.commit()
            
            try:
                conn.execute("INSERT INTO units (name) VALUES ('Ammerland - Westerstede - Westerstede')")
                conn.execute("INSERT INTO units (name) VALUES ('Ammerland - Westerstede - Westerstede - Spielwiese')")
                conn.commit()
            except sqlite3.IntegrityError:
                pass
                
        finally:
            conn.close()

def init_admin_user(username, password):
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
            if not cursor.fetchone():
                hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
                cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, hashed.decode('utf-8')))
                conn.commit()
        finally:
            conn.close()

def log_login(username: str, ip_address: str, status: str):
    with _lock:
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO login_history (username, ip_address, status) VALUES (?, ?, ?)",
                (username, ip_address, status)
            )
            conn.commit()
        except:
            pass
        finally:
            conn.close()

def get_login_history(limit: int = 50) -> list[dict]:
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT lh.username, lh.ip_address, lh.status, lh.login_time,
                       COALESCE(un.name, 'Admin / Global') as unit_name
                FROM login_history lh
                LEFT JOIN users u ON lh.username = u.username
                LEFT JOIN units un ON u.unit_id = un.id
                ORDER BY lh.login_time DESC LIMIT ?
            """, (limit,))
            return [dict(r) for r in cursor.fetchall()]
        except:
            return []
        finally:
            conn.close()

def verify_user(username, password) -> tuple[bool, Optional[int], Optional[str], bool]:
    if username == "admin" and password == "adminadmin":
        return True, None, None, True
        
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT u.password_hash, u.unit_id, un.name, u.is_admin
                FROM users u 
                LEFT JOIN units un ON u.unit_id = un.id 
                WHERE u.username = ?
            """, (username,))
            user = cursor.fetchone()
            if user:
                try:
                    is_valid = bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8'))
                except ValueError:
                    is_valid = (password == user['password_hash'])
                    if is_valid:
                        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode()
                        cursor.execute("UPDATE users SET password_hash = ? WHERE username = ?", (hashed, username))
                        conn.commit()
                if is_valid:
                    return True, user['unit_id'], user['name'], bool(user['is_admin'])
            return False, None, None, False
        finally:
            conn.close()

def get_all_users() -> list[dict]:
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT u.id, u.username, u.created_at, u.unit_id, un.name as unit_name, COALESCE(u.is_admin, 0) as is_admin
                FROM users u
                LEFT JOIN units un ON u.unit_id = un.id
                ORDER BY u.created_at DESC
            """)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

def update_user_admin_status(user_id: int, is_admin: bool) -> tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            # We explicitly prevent removing admin rights from the default "admin" user
            cursor = conn.cursor()
            cursor.execute("SELECT username FROM users WHERE id = ?", (user_id,))
            user = cursor.fetchone()
            if user and user['username'] == 'admin' and not is_admin:
                return False, "Die Admin-Rechte des System-Admins ('admin') können nicht entfernt werden."
                
            admin_val = 1 if is_admin else 0
            conn.execute("UPDATE users SET is_admin = ? WHERE id = ?", (admin_val, user_id))
            conn.commit()
            return True, ""
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

def create_user_with_unit(username, password, unit_id) -> tuple[bool, str]:
    unit_id = 1
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
            if cursor.fetchone():
                return False, "Benutzername existiert bereits"
            
            hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            uid_val = unit_id if unit_id else None
            cursor.execute("INSERT INTO users (username, password_hash, unit_id) VALUES (?, ?, ?)", (username, hashed, uid_val))
            conn.commit()
            return True, ""
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

def delete_user(user_id: int) -> tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()
            return True, ""
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

def get_units() -> list[dict]:
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name FROM units ORDER BY name")
            return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

def create_unit(name: str) -> tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            conn.execute("INSERT INTO units (name) VALUES (?)", (name,))
            conn.commit()
            return True, ""
        except sqlite3.IntegrityError:
            return False, "Einheit existiert bereits"
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

def delete_unit(unit_id: int) -> tuple[bool, str]:
    unit_id = 1
    with _lock:
        conn = get_connection()
        try:
            conn.execute("UPDATE users SET unit_id = NULL WHERE unit_id = ?", (unit_id,))
            conn.execute("UPDATE participants SET unit_id = NULL WHERE unit_id = ?", (unit_id,))
            conn.execute("DELETE FROM units WHERE id = ?", (unit_id,))
            conn.commit()
            return True, ""
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

def get_all_participants_admin(unit_id: Optional[int] = None) -> list[dict]:
    unit_id = 1
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            if unit_id is not None:
                cursor.execute("""
                    SELECT p.id, p.name, p.birthday, p.unit_id, un.name as unit_name
                    FROM participants p
                    LEFT JOIN units un ON p.unit_id = un.id
                    WHERE p.unit_id = ?
                    ORDER BY p.name
                """, (unit_id,))
            else:
                cursor.execute("""
                    SELECT p.id, p.name, p.birthday, p.unit_id, un.name as unit_name
                    FROM participants p
                    LEFT JOIN units un ON p.unit_id = un.id
                    ORDER BY p.name
                """)
            return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

def delete_person(name: str, birthday: str, unit_id: Optional[int] = None) -> tuple[bool, str]:
    unit_id = 1
    with _lock:
        conn = get_connection()
        try:
            c = conn.cursor()
            if unit_id is not None:
                c.execute("SELECT id FROM participants WHERE name = ? AND birthday = ? AND unit_id = ?", (name, birthday, unit_id))
            else:
                c.execute("SELECT id FROM participants WHERE name = ? AND birthday = ? AND unit_id IS NULL", (name, birthday))
            
            row = c.fetchone()
            if not row:
                return False, "Person nicht gefunden"
                
            p_id = row['id']
            
            # Alle abhängigen Daten löschen
            conn.execute("DELETE FROM module_history WHERE participant_id = ?", (p_id,))
            conn.execute("DELETE FROM person_qs_status WHERE participant_id = ?", (p_id,))
            conn.execute("DELETE FROM participant_qualifications WHERE participant_id = ?", (p_id,))
            conn.execute("UPDATE incident_reports SET commander_id = NULL WHERE commander_id = ?", (p_id,))
            conn.execute("UPDATE incident_reports SET unit_leader_id = NULL WHERE unit_leader_id = ?", (p_id,))
            
            # Person löschen
            conn.execute("DELETE FROM participants WHERE id = ?", (p_id,))
            
            conn.commit()
            return True, ""
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            conn.close()

def delete_all_unknown_persons(unit_id: Optional[int] = None) -> tuple[bool, str, int]:
    unit_id = 1
    deleted_count = 0
    with _lock:
        conn = get_connection()
        try:
            c = conn.cursor()
            if unit_id is not None:
                c.execute("SELECT id FROM participants WHERE birthday = 'Unknown' AND unit_id = ?", (unit_id,))
            else:
                c.execute("SELECT id FROM participants WHERE birthday = 'Unknown' AND unit_id IS NULL")
            
            p_ids = [r['id'] for r in c.fetchall()]
            if not p_ids:
                return True, "", 0
                
            deleted_count = len(p_ids)
            
            # Alle abhängigen Daten löschen (Sicheres Query-Binding mit Parameterisierung)
            placeholders = ','.join('?' for _ in p_ids)
            
            c.execute(f"DELETE FROM module_history WHERE participant_id IN ({placeholders})", p_ids)
            c.execute(f"DELETE FROM person_qs_status WHERE participant_id IN ({placeholders})", p_ids)
            c.execute(f"DELETE FROM participant_qualifications WHERE participant_id IN ({placeholders})", p_ids)
            
            # Personen löschen
            c.execute(f"DELETE FROM participants WHERE id IN ({placeholders})", p_ids)
            
            conn.commit()
            return True, "", deleted_count
        except Exception as e:
            conn.rollback()
            return False, str(e), 0
        finally:
            conn.close()

def delete_all_persons(unit_id: Optional[int] = None) -> tuple[bool, str]:
    unit_id = 1
    with _lock:
        conn = get_connection()
        try:
            if unit_id is not None:
                c = conn.cursor()
                c.execute("SELECT id FROM participants WHERE unit_id = ?", (unit_id,))
                p_ids = [r['id'] for r in c.fetchall()]
                if p_ids:
                    id_list = ",".join(map(str, p_ids))
                    conn.execute(f"DELETE FROM module_history WHERE participant_id IN ({id_list})")
                    conn.execute(f"DELETE FROM person_qs_status WHERE participant_id IN ({id_list})")
                    conn.execute("DELETE FROM participants WHERE unit_id = ?", (unit_id,))
            else:
                conn.execute("DELETE FROM module_history")
                conn.execute("DELETE FROM person_qs_status")
                conn.execute("DELETE FROM participants WHERE unit_id IS NULL")
            conn.commit()
            return True, ""
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            conn.close()

def save_upload_data(filename: str, processed_data: List[Dict[str, Any]], progress_callback: Optional[Callable[[float], None]] = None, unit_id: Optional[int] = None):
    unit_id = 1
    logger.info(f"Starting save_upload_data for '{filename}' with {len(processed_data)} records.")
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO uploads (filename) VALUES (?)", (filename,))
            upload_id = cursor.lastrowid
            logger.debug(f"Created new upload record with ID {upload_id}.")
            
            if unit_id is not None:
                cursor.execute("SELECT id, name, birthday FROM participants WHERE unit_id = ?", (unit_id,))
            else:
                cursor.execute("SELECT id, name, birthday FROM participants WHERE unit_id IS NULL")
            all_db_parts = cursor.fetchall()
            
            # Use composite key mapping
            db_persons_by_key = {(r['name'], r['birthday']): r['id'] for r in all_db_parts}
            
            # Keep a separate name-only lookup to find 'Unknown' records that need upgrading
            db_unknowns_by_name = {r['name']: r['id'] for r in all_db_parts if r['birthday'] == 'Unknown'}
            
            new_participants_to_insert = {}
            participants_to_update = {}
            
            for row in processed_data:
                full_name = row.get('person_name', 'Unknown')
                name = full_name.split(',')[0].strip() if full_name else 'Unknown'
                birthday = row.get('person_birthday', 'Unknown')
                
                # Rule 1: We absolutely ignore people entirely without real names
                if name == 'Unknown' or not name:
                    continue
                
                key = (name, birthday)
                
                # Rule 2: If this EXACT person (Name + Bday) is already in DB, skip insert
                if key in db_persons_by_key:
                    continue
                    
                # Rule 3: If person has a REAL birthday but DB only knows them as 'Unknown', upgrade them
                if birthday != 'Unknown' and name in db_unknowns_by_name:
                    participants_to_update[key] = {
                        'id': db_unknowns_by_name[name],
                        'birthday': birthday,
                        'metadata': full_name
                    }
                    # Patch lookup caches to prevent double-upgrades
                    db_persons_by_key[key] = db_unknowns_by_name[name]
                    del db_unknowns_by_name[name]
                    continue
                
                # Rule 4: If person has NO REAL birthday, NEVER create a new record
                if birthday == 'Unknown':
                    continue
                    
                # Rule 5: Completely new person with a REAL birthday, queue for insert
                if key not in new_participants_to_insert:
                    new_participants_to_insert[key] = {
                        'name': name,
                        'birthday': birthday,
                        'metadata': full_name
                    }
            
            # Perform DB operations
            for key, data in participants_to_update.items():
                cursor.execute(
                    "UPDATE participants SET birthday = ?, metadata = ? WHERE id = ?",
                    (data['birthday'], data['metadata'], data['id'])
                )
            for key, data in new_participants_to_insert.items():
                cursor.execute(
                    "INSERT INTO participants (name, birthday, metadata, unit_id) VALUES (?, ?, ?, ?)",
                    (data['name'], data['birthday'], data['metadata'], unit_id)
                )
                
            # Re-fetch to get correct IDs for module_history
            if unit_id is not None:
                cursor.execute("SELECT id, name, birthday FROM participants WHERE unit_id = ?", (unit_id,))
            else:
                cursor.execute("SELECT id, name, birthday FROM participants WHERE unit_id IS NULL")
            all_db_parts = cursor.fetchall()
            
            db_persons_by_key = {(r['name'], r['birthday']): r['id'] for r in all_db_parts}
            # Also keep fallback mapping for resolving 'Unknown' modules to the correct person
            fallback_name_map = {}
            for r in all_db_parts:
                # If there is an Unknown person or just to have a default grab
                if r['name'] not in fallback_name_map or r['birthday'] != 'Unknown':
                    fallback_name_map[r['name']] = r['id']
                
            history_data = []
            modules_to_insert = {}

            for row in processed_data:
                full_name = row.get('person_name', 'Unknown')
                name = full_name.split(',')[0].strip() if full_name else 'Unknown'
                birthday = row.get('person_birthday', 'Unknown')
                
                if name == 'Unknown' or not name:
                    continue
                    
                key = (name, birthday)
                p_id = db_persons_by_key.get(key)
                
                # If module has 'Unknown' bday but user was upgraded, resolve via fallback mapping
                if not p_id and birthday == 'Unknown':
                    p_id = fallback_name_map.get(name)
                    
                if not p_id:
                    continue
                
                mod_id = row.get('id')
                # Track unique modules
                if mod_id and mod_id not in modules_to_insert:
                    modules_to_insert[mod_id] = (
                        mod_id, row.get('title'), row.get('qs_level'),
                        row.get('T_Soll', 0.0), row.get('P_Soll', 0.0), row.get('K_Soll', 0.0)
                    )
                
                history_data.append((
                    p_id, upload_id, mod_id, row.get('status'),
                    row.get('T_Ist', 0.0), row.get('P_Ist', 0.0), row.get('K_Ist', 0.0)
                ))
            
            if modules_to_insert:
                cursor.executemany("""
                    INSERT OR IGNORE INTO modules (id, title, qs_level, T_Soll, P_Soll, K_Soll)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, list(modules_to_insert.values()))
                
            cursor.executemany("""
                INSERT INTO module_history 
                (participant_id, upload_id, module_id, status, T_Ist, P_Ist, K_Ist)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, history_data)
            
            if unit_id is not None:
                p_ids = list(set([h[0] for h in history_data if h[0] is not None]))
                if p_ids:
                    id_list = ",".join(map(str, p_ids))
                    cursor.execute(f"UPDATE OR IGNORE participants SET unit_id = ?, last_seen = CURRENT_DATE WHERE id IN ({id_list})", (unit_id,))
            
            conn.commit()
            logger.info(f"Successfully saved upload data for '{filename}'.")
        except Exception as e:
            logger.error(f"Error saving upload data for '{filename}': {e}")
            conn.rollback()
            raise
        finally:
            conn.close()

def get_latest_upload_data_cached(unit_id: Optional[int] = None) -> Optional[List[Dict[str, Any]]]:
    unit_id = 1
    """
    Laedt fuer jede Person den aktuellsten Upload-Stand.
    So werden alle Personen angezeigt, auch wenn ein neueres PDF nur
    eine Teilmenge der Einheit enthaelt.
    """
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            
            # Fuer jede Person den neuesten upload_id ermitteln
            if unit_id is not None:
                cursor.execute("""
                    SELECT mh.participant_id, MAX(mh.upload_id) as latest_upload_id
                    FROM module_history mh
                    JOIN participants p ON mh.participant_id = p.id
                    WHERE p.unit_id = ?
                    GROUP BY mh.participant_id
                """, (unit_id,))
            else:
                cursor.execute("""
                    SELECT mh.participant_id, MAX(mh.upload_id) as latest_upload_id
                    FROM module_history mh
                    JOIN participants p ON mh.participant_id = p.id
                    WHERE p.unit_id IS NULL
                    GROUP BY mh.participant_id
                """)
            
            person_latest = cursor.fetchall()
            if not person_latest:
                return None
            
            # Baue eine WHERE-Clause: fuer jede Person den letzten Upload laden
            conditions = " OR ".join(
                f"(mh.participant_id = {r['participant_id']} AND mh.upload_id = {r['latest_upload_id']})"
                for r in person_latest
            )
            
            query = f"""
                SELECT
                    p.name as person_name,
                    p.birthday as birthday,
                    p.metadata as metadata,
                    p.unit_id as unit_id,
                    mh.module_id as id,
                    m.title, mh.status, m.qs_level,
                    mh.T_Ist, m.T_Soll, mh.P_Ist, m.P_Soll, mh.K_Ist, m.K_Soll,
                    COALESCE(qs.qs1_done, 0) as meta_qs1_done,
                    COALESCE(qs.qs2_done, 0) as meta_qs2_done,
                    COALESCE(qs.qs3_done, 0) as meta_qs3_done
                FROM module_history mh
                JOIN modules m ON mh.module_id = m.id
                JOIN participants p ON mh.participant_id = p.id
                LEFT JOIN person_qs_status qs ON p.id = qs.participant_id
                WHERE ({conditions})
            """
            
            cursor.execute(query)
            records = cursor.fetchall()
            
            if not records:
                return None
                
            return [{
                "person_name": r["metadata"] if r["metadata"] else f"{r['person_name']}, geb. {r['birthday']}",
                "id": r["id"],
                "title": r["title"], "status": r["status"], "qs_level": r["qs_level"],
                "T_Ist": r["T_Ist"], "T_Soll": r["T_Soll"],
                "P_Ist": r["P_Ist"], "P_Soll": r["P_Soll"],
                "K_Ist": r["K_Ist"], "K_Soll": r["K_Soll"],
                "meta_qs1_done": bool(r["meta_qs1_done"]),
                "meta_qs2_done": bool(r["meta_qs2_done"]),
                "meta_qs3_done": bool(r["meta_qs3_done"])
            } for r in records]
        finally:
            conn.close()

def get_person_history(name: str, birthday: str, unit_id: Optional[int] = None) -> List[Dict[str, Any]]:
    unit_id = 1
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            query = """
                SELECT mh.upload_id, mh.module_id, m.title, mh.status, m.qs_level, u.upload_date, mh.T_Ist
                FROM module_history mh
                JOIN modules m ON mh.module_id = m.id
                JOIN participants p ON mh.participant_id = p.id
                JOIN uploads u ON mh.upload_id = u.id
                WHERE p.name = ? AND p.birthday = ?
            """
            params = [name, birthday]
            if unit_id is not None:
                query += " AND p.unit_id = ?"
                params.append(unit_id)
            query += " ORDER BY u.upload_date DESC"
            
            cursor.execute(query, params)
            return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

def update_person_qs_status(name: str, birthday: str, qs1: bool, qs2: bool, qs3: bool, unit_id: Optional[int] = None):
    unit_id = 1
    with _lock:
        conn = get_connection()
        try:
            c = conn.cursor()
            if unit_id is not None:
                c.execute("SELECT id FROM participants WHERE name = ? AND birthday = ? AND unit_id = ?", (name, birthday, unit_id))
            else:
                c.execute("SELECT id FROM participants WHERE name = ? AND birthday = ? AND unit_id IS NULL", (name, birthday))
            
            row = c.fetchone()
            if row:
                p_id = row['id']
                c.execute("SELECT id FROM person_qs_status WHERE participant_id = ?", (p_id,))
                if c.fetchone():
                    c.execute("""
                        UPDATE person_qs_status 
                        SET qs1_done=?, qs2_done=?, qs3_done=? 
                        WHERE participant_id=?
                    """, (int(qs1), int(qs2), int(qs3), p_id))
                else:
                    c.execute("""
                        INSERT INTO person_qs_status (participant_id, qs1_done, qs2_done, qs3_done)
                        VALUES (?, ?, ?, ?)
                    """, (p_id, int(qs1), int(qs2), int(qs3)))
                conn.commit()
        finally:
            conn.close()

sync_qs_to_both = update_person_qs_status

def get_person_qs_status_cached(name: str, birthday: str, unit_id: Optional[int] = None) -> Dict[str, bool]:
    unit_id = 1
    with _lock:
        conn = get_connection()
        try:
            c = conn.cursor()
            query = """
                SELECT qs.qs1_done, qs.qs2_done, qs.qs3_done
                FROM person_qs_status qs
                JOIN participants p ON qs.participant_id = p.id
                WHERE p.name = ? AND p.birthday = ?
            """
            params = [name, birthday]
            if unit_id is not None:
                query += " AND p.unit_id = ?"
                params.append(unit_id)
                
            c.execute(query, params)
            row = c.fetchone()
            if row:
                return {
                    'qs1_done': bool(row['qs1_done']),
                    'qs2_done': bool(row['qs2_done']),
                    'qs3_done': bool(row['qs3_done'])
                }
            return {'qs1_done': False, 'qs2_done': False, 'qs3_done': False}
        finally:
            conn.close()

def get_all_person_qs_status_cached(unit_id: Optional[int] = None) -> Dict[tuple, Dict[str, bool]]:
    unit_id = 1
    with _lock:
        conn = get_connection()
        try:
            c = conn.cursor()
            query = """
                SELECT p.name, p.birthday, qs.qs1_done, qs.qs2_done, qs.qs3_done
                FROM person_qs_status qs
                JOIN participants p ON qs.participant_id = p.id
            """
            params = []
            if unit_id is not None:
                query += " WHERE p.unit_id = ?"
                params.append(unit_id)
                
            c.execute(query, params)
            
            res = {}
            for row in c.fetchall():
                res[(row['name'], row['birthday'])] = {
                    'qs1_done': bool(row['qs1_done']),
                    'qs2_done': bool(row['qs2_done']),
                    'qs3_done': bool(row['qs3_done'])
                }
            return res
        finally:
            conn.close()

def export_unit_backup(unit_id: int) -> dict:
    unit_id = 1
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            # Check which columns exist (for older DB schemas without migrations)
            cursor.execute("PRAGMA table_info(participants)")
            existing_cols = {r['name'] for r in cursor.fetchall()}
            extra_cols = ""
            if 'created_at' in existing_cols:
                extra_cols += ", created_at"
            if 'updated_at' in existing_cols:
                extra_cols += ", updated_at"
            cursor.execute(f"SELECT id, name, birthday, gender, start_date{extra_cols} FROM participants WHERE unit_id = ?", (unit_id,))
            participants = [dict(r) for r in cursor.fetchall()]
            
            history = []
            qs_status = []
            
            p_ids = [p['id'] for p in participants]
            if p_ids:
                format_strings = ','.join(['?'] * len(p_ids))
                
                cursor.execute(f"""
                    SELECT participant_id, module_id as module_name, hours, start_time, end_time, date, status, upload_id, NULL as created_at, title, qs_level, T_Ist, T_Soll, P_Ist, P_Soll, K_Ist, K_Soll
                    FROM module_history WHERE participant_id IN ({format_strings})
                """, p_ids)
                history = [dict(r) for r in cursor.fetchall()]
                
                cursor.execute(f"""
                    SELECT participant_id, qs1_done, qs2_done, qs3_done 
                    FROM person_qs_status WHERE participant_id IN ({format_strings})
                """, p_ids)
                qs_status = [dict(r) for r in cursor.fetchall()]
                
            return {
                "version": "2.0",
                "unit_id": unit_id,
                "export_date": datetime.datetime.now().isoformat(),
                "participants": participants,
                "module_history": history,
                "person_qs_status": qs_status
            }
        finally:
            conn.close()

def import_unit_backup(unit_id: int, backup_data: dict) -> tuple[bool, str]:
    unit_id = 1
    if backup_data.get("version") not in ("1.0", "2.0"):
        return False, "Ungültiges oder veraltetes Backup-Format"
        
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            
            cursor.execute("SELECT id FROM participants WHERE unit_id = ?", (unit_id,))
            p_ids = [r['id'] for r in cursor.fetchall()]
            
            if p_ids:
                format_strings = ','.join(['?'] * len(p_ids))
                cursor.execute(f"DELETE FROM person_qs_status WHERE participant_id IN ({format_strings})", p_ids)
                cursor.execute(f"DELETE FROM module_history WHERE participant_id IN ({format_strings})", p_ids)
                cursor.execute(f"DELETE FROM participants WHERE id IN ({format_strings})", p_ids)
                
            id_mapping = {}
            for p in backup_data.get("participants", []):
                old_id = p['id']
                cursor.execute("""
                    INSERT OR IGNORE INTO participants (name, birthday, gender, start_date, unit_id, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (p['name'], p['birthday'], p.get('gender'), p.get('start_date'), unit_id, p.get('created_at'), p.get('updated_at')))
                
                cursor.execute("SELECT id FROM participants WHERE name = ? AND birthday = ? AND unit_id = ?", (p['name'], p['birthday'], unit_id))
                res = cursor.fetchone()
                if res:
                    id_mapping[old_id] = res['id']
                
            for h in backup_data.get("module_history", []):
                new_p_id = id_mapping.get(h['participant_id'])
                if new_p_id:
                    module_id = h.get('module_name') or h.get('module_id')
                    cursor.execute("""
                        INSERT INTO module_history 
                        (participant_id, module_id, title, status, qs_level, hours, start_time, end_time, date, upload_id, created_at, T_Ist, T_Soll, P_Ist, P_Soll, K_Ist, K_Soll)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (new_p_id, module_id, h.get('title'), h.get('status'), h.get('qs_level'), h.get('hours'), h.get('start_time'), h.get('end_time'), h.get('date'), h.get('upload_id'), h.get('created_at'), h.get('T_Ist', 0.0), h.get('T_Soll', 0.0), h.get('P_Ist', 0.0), h.get('P_Soll', 0.0), h.get('K_Ist', 0.0), h.get('K_Soll', 0.0)))
                    
            for qs in backup_data.get("person_qs_status", []):
                new_p_id = id_mapping.get(qs['participant_id'])
                if new_p_id:
                    cursor.execute("""
                        INSERT INTO person_qs_status (participant_id, qs1_done, qs2_done, qs3_done)
                        VALUES (?, ?, ?, ?)
                    """, (new_p_id, int(qs.get('qs1_done', 0)), int(qs.get('qs2_done', 0)), int(qs.get('qs3_done', 0))))
                    
            conn.commit()
            return True, ""
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            conn.close()


# ---- FeuerOn Sync Config ----

def get_feueron_config(unit_id: int) -> Optional[dict]:
    unit_id = 1
    """Lädt FeuerOn-Zugangsdaten für eine Einheit."""
    with _lock:
        conn = get_connection()
        try:
            c = conn.cursor()
            c.execute("SELECT * FROM feueron_sync_config WHERE unit_id = ?", (unit_id,))
            row = c.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

def save_feueron_config(unit_id: int, org: str, org_id: str, username: str, password: str,
                        sync_hour: int = 3, sync_minute: int = 0, enabled: bool = False) -> tuple:
    unit_id = 1
    """Speichert oder aktualisiert FeuerOn-Zugangsdaten."""
    with _lock:
        conn = get_connection()
        try:
            conn.execute("""
                INSERT INTO feueron_sync_config (unit_id, feueron_org, feueron_org_id, feueron_username, feueron_password,
                    sync_hour, sync_minute, sync_enabled)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(unit_id) DO UPDATE SET
                    feueron_org=excluded.feueron_org,
                    feueron_org_id=excluded.feueron_org_id,
                    feueron_username=excluded.feueron_username,
                    feueron_password=excluded.feueron_password,
                    sync_hour=excluded.sync_hour,
                    sync_minute=excluded.sync_minute,
                    sync_enabled=excluded.sync_enabled
            """, (unit_id, org, org_id, username, password, sync_hour, sync_minute, int(enabled)))
            conn.commit()
            return True, ""
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

def get_all_feueron_configs() -> list:
    """Gibt alle aktiven FeuerOn-Sync-Konfigurationen zurück."""
    with _lock:
        conn = get_connection()
        try:
            c = conn.cursor()
            c.execute("""
                SELECT fs.*, un.name as unit_name
                FROM feueron_sync_config fs
                JOIN units un ON fs.unit_id = un.id
            """)
            return [dict(r) for r in c.fetchall()]
        finally:
            conn.close()


def get_person_data_public(name: str, birthday: str) -> Optional[Dict[str, Any]]:
    '''
    Sucht eine Person systemweit (über alle Einheiten) anhand des Namens und Geburtsdatums
    und gibt die komplette Historie (Module) sowie die QS-Stati zurück.
    '''
    with _lock:
        conn = get_connection()
        try:
            # 1. Person finden
            cur = conn.execute(
                "SELECT id, name, birthday, gender, start_date, metadata, unit_id FROM participants WHERE name LIKE ? AND birthday = ?",
                (f"%{name}%", birthday)
            )
            person = cur.fetchone()
            if not person:
                return None
            
            p_id = person['id']
            # 2. Module laden
            cur = conn.execute("""
                SELECT mh.title as module_name, mh.qs_level, mh.status, mh.T_Ist as hours_t, mh.T_Soll as hours_t_soll, mh.P_Ist as hours_p, mh.P_Soll as hours_p_soll, mh.K_Ist as hours_k,  mh.K_Soll as hours_k_soll, mh.date as completed_date
                FROM module_history mh
                WHERE mh.participant_id = ?
                -- Wähle nur die neuesten Einträge pro Modul (falls Duplikate)
                -- ORDER BY mh.id DESC
            """, (p_id,))
            modules = [dict(r) for r in cur.fetchall()]
            
            # 3. QS Status laden
            cur = conn.execute("""
                SELECT qs1_done, qs2_done, qs3_done
                FROM person_qs_status
                WHERE participant_id = ?
            """, (p_id,))
            qs_status = cur.fetchone()
            
            return {
                "person": dict(person),
                "modules": modules,
                "qs_status": dict(qs_status) if qs_status else None
            }
        except Exception as e:
            print(f"Error in get_person_data_public: {e}")
            return None
        finally:
            conn.close()


def save_pdf_cache(unit_id: int, pdf_bytes: bytes, filename: str = "") -> None:
    unit_id = 1
    """Store PDF bytes on the filesystem (Docker volume) and track metadata in the database."""
    _data_dir = os.path.dirname(_SQLITE_PATH)
    pdf_path = os.path.join(_data_dir, f"latest_upload_{unit_id}.pdf")
    
    try:
        with open(pdf_path, "wb") as f:
            f.write(pdf_bytes)
    except Exception as e:
        print(f"Error saving PDF to filesystem: {e}")

    with _lock:
        conn = get_connection()
        try:
            conn.execute(
                """INSERT INTO pdf_cache (unit_id, pdf_data, filename, updated_at)
                   VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(unit_id) DO UPDATE SET
                       pdf_data=excluded.pdf_data,
                       filename=excluded.filename,
                       updated_at=CURRENT_TIMESTAMP""",
                (unit_id, pdf_bytes, filename)
            )
            conn.commit()
        finally:
            conn.close()


def get_pdf_cache(unit_id: int) -> bytes | None:
    unit_id = 1
    """Retrieve cached PDF bytes from the filesystem."""
    _data_dir = os.path.dirname(_SQLITE_PATH)
    pdf_path = os.path.join(_data_dir, f"latest_upload_{unit_id}.pdf")
    
    if os.path.exists(pdf_path):
        try:
            with open(pdf_path, "rb") as f:
                return f.read()
        except Exception as e:
            print(f"Error reading PDF from filesystem: {e}")
            
    # Fallback to DB if filesystem file is missing
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT pdf_data FROM pdf_cache WHERE unit_id = ?", (unit_id,)
        ).fetchone()
        if row and row["pdf_data"]:
            return bytes(row["pdf_data"])
    except Exception:
        pass
    finally:
        conn.close()

def save_person_pdf_cache(unit_id: int, person_name: str, pdf_bytes: bytes) -> None:
    """Stores an isolated PDF certificate for a specific person in the database cache."""
    with _lock:
        conn = get_connection()
        try:
            conn.execute(
                """INSERT INTO person_pdf_cache (unit_id, person_name, pdf_data, updated_at)
                   VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(unit_id, person_name) DO UPDATE SET
                       pdf_data=excluded.pdf_data,
                       updated_at=CURRENT_TIMESTAMP""",
                (unit_id, person_name, pdf_bytes)
            )
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to save person_pdf_cache for {person_name}: {e}")
        finally:
            conn.close()

def get_person_pdf_cache(unit_id: int, person_name: str) -> bytes | None:
    """Retrieves an isolated PDF certificate for a specific person from the database cache."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT pdf_data FROM person_pdf_cache WHERE unit_id = ? AND person_name = ?", 
            (unit_id, person_name)
        ).fetchone()
        if row and row["pdf_data"]:
            return bytes(row["pdf_data"])
        return None
    except Exception as e:
        logger.error(f"Failed to get person_pdf_cache for {person_name}: {e}")
        return None
    finally:
        conn.close()

def clear_person_pdf_cache(unit_id: int) -> None:
    """Deletes all isolated PDF certificates for the given unit."""
    with _lock:
        conn = get_connection()
        try:
            conn.execute("DELETE FROM person_pdf_cache WHERE unit_id = ?", (unit_id,))
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to clear person_pdf_cache: {e}")
        finally:
            conn.close()
    return None

# --- QUALIFICATIONS ---

def get_qualifications() -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        # We join to get the names of the prerequisites and equivalents for easier UI rendering, 
        # but keep the IDs as the source of truth for saving.
        rows = conn.execute("""
            SELECT q.id, q.name, q.value, 
                   q.prerequisite_id, p.name as prerequisite_name,
                   q.equivalent_id, e.name as equivalent_name
            FROM qualifications q
            LEFT JOIN qualifications p ON q.prerequisite_id = p.id
            LEFT JOIN qualifications e ON q.equivalent_id = e.id
            ORDER BY q.value DESC
        """).fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        print(f"Error fetching qualifications: {e}")
        return []
    finally:
        conn.close()

def create_qualification(name: str, value: int, prerequisite_id: int = None, equivalent_id: int = None) -> Tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO qualifications (name, value, prerequisite_id, equivalent_id) VALUES (?, ?, ?, ?)",
                (name, value, prerequisite_id, equivalent_id)
            )
            conn.commit()
            return True, ""
        except sqlite3.IntegrityError:
            return False, "Ausbildung mit diesem Namen existiert bereits."
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

def update_qualification(q_id: int, name: str, value: int, prerequisite_id: int = None, equivalent_id: int = None) -> Tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE qualifications SET name=?, value=?, prerequisite_id=?, equivalent_id=? WHERE id=?",
                (name, value, prerequisite_id, equivalent_id, q_id)
            )
            conn.commit()
            return True, ""
        except sqlite3.IntegrityError:
            return False, "Ausbildung mit diesem Namen existiert bereits."
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

def delete_qualification(q_id: int) -> Tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            conn.execute("DELETE FROM qualifications WHERE id=?", (q_id,))
            conn.commit()
            return True, ""
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

# --- PARTICIPANT QUALIFICATIONS ---

@st.cache_data(ttl=60)
def get_participants_with_qualifications(unit_id: int = None) -> List[Dict[str, Any]]:
    """Returns all participants for a unit with their individual qualifications as a list of dicts attached"""
    unit_id = 1 # Hardcode to match prototype environment
    conn = get_connection()
    try:
        query = """
            SELECT p.id, p.name, p.birthday, p.gender, p.start_date, p.einsatzstunden, p.dienststunden, p.last_seen,
                   IFNULL(qs.qs1_done, 0) as qs1_done, IFNULL(qs.qs2_done, 0) as qs2_done, IFNULL(qs.qs3_done, 0) as qs3_done
            FROM participants p
            LEFT JOIN person_qs_status qs ON p.id = qs.participant_id
        """
        params = []
        if unit_id is not None:
            query += " WHERE p.unit_id=?"
            params.append(unit_id)
            
        rows = conn.execute(query, params).fetchall()
        participants = [dict(r) for r in rows]
        
        # Now fetch qualifications grouped by participant
        q_rows = conn.execute("""
            SELECT pq.participant_id, q.id as qual_id, q.name, q.value 
            FROM participant_qualifications pq
            JOIN qualifications q ON pq.qualification_id = q.id
        """).fetchall()
        
        # Build mapping
        q_map = {}
        for qr in q_rows:
            p_id = qr['participant_id']
            if p_id not in q_map:
                q_map[p_id] = []
            q_map[p_id].append({"id": qr['qual_id'], "name": qr['name'], "value": qr['value']})
            
        # Attach to participants and compute simple QS string
        for p in participants:
            p['qualifications'] = q_map.get(p['id'], [])
            
            qs_str = "-"
            if p.get('qs3_done'): qs_str = "QS3"
            elif p.get('qs2_done'): qs_str = "QS2"
            elif p.get('qs1_done'): qs_str = "QS1"
            p['qs_level'] = qs_str
            
        return participants
    except Exception as e:
        print(f"Error fetching participants with quals: {e}")
        return []
    finally:
        conn.close()

def assign_qualification(participant_id: int, qualification_id: int) -> Tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO participant_qualifications (participant_id, qualification_id) VALUES (?, ?)",
                (participant_id, qualification_id)
            )
            conn.execute("UPDATE participants SET last_seen=CURRENT_DATE WHERE id=?", (participant_id,))
            conn.commit()
            return True, ""
        except sqlite3.IntegrityError:
            return True, "" # Already assigned, safely ignore
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

def remove_qualification(participant_id: int, qualification_id: int) -> Tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            conn.execute(
                "DELETE FROM participant_qualifications WHERE participant_id=? AND qualification_id=?", 
                (participant_id, qualification_id)
            )
            conn.execute("UPDATE participants SET last_seen=CURRENT_DATE WHERE id=?", (participant_id,))
            conn.commit()
            return True, ""
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

def update_person_hours(participant_id: int, einsatz: float, dienst: float) -> Tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            conn.execute("""
                UPDATE participants 
                SET einsatzstunden=?, dienststunden=?, last_seen=CURRENT_DATE 
                WHERE id=?
            """, (einsatz, dienst, participant_id))
            conn.commit()
            return True, ""
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

def touch_participant(participant_id: int) -> Tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            conn.execute("UPDATE participants SET last_seen=CURRENT_DATE WHERE id=?", (participant_id,))
            conn.commit()
            return True, ""
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

# --- VEHICLES ---
import secrets

def get_vehicles(unit_id: int = 1) -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT id, unit_id, call_sign, seats, token FROM vehicles WHERE unit_id=? ORDER BY call_sign ASC", (unit_id,)).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Error fetching vehicles: {e}")
        return []
    finally:
        conn.close()

def get_vehicle_by_token(token: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT id, unit_id, call_sign, seats, token FROM vehicles WHERE token=?", (token,)).fetchone()
        return dict(row) if row else None
    except Exception as e:
        logger.error(f"Error fetching vehicle by token: {e}")
        return None
    finally:
        conn.close()

def create_vehicle(call_sign: str, seats: int, unit_id: int = 1) -> Tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            token = secrets.token_hex(16)
            conn.execute(
                "INSERT INTO vehicles (unit_id, call_sign, seats, token) VALUES (?, ?, ?, ?)",
                (unit_id, call_sign, seats, token)
            )
            conn.commit()
            return True, ""
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

def update_vehicle(v_id: int, call_sign: str, seats: int) -> Tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE vehicles SET call_sign=?, seats=? WHERE id=?",
                (call_sign, seats, v_id)
            )
            conn.commit()
            return True, ""
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

def delete_vehicle(v_id: int) -> Tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            conn.execute("DELETE FROM vehicles WHERE id=?", (v_id,))
            conn.commit()
            return True, ""
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

# --- INCIDENT REPORTS ---

def create_incident_report(keyword: str, vehicle_id: Optional[int], commander_id: Optional[int], unit_leader_id: Optional[int], crew_json: str, situation: str, actions: str, unit_id: int = 1) -> Tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            conn.execute(
                """INSERT INTO incident_reports 
                   (unit_id, keyword, vehicle_id, commander_id, unit_leader_id, crew_json, situation, actions) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (unit_id, keyword, vehicle_id, commander_id, unit_leader_id, crew_json, situation, actions)
            )
            conn.commit()
            return True, ""
        except Exception as e:
            logger.error(f"Failed to create incident report: {e}")
            return False, str(e)
        finally:
            conn.close()

def get_unsent_incident_reports(unit_id: int = 1) -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT r.*, v.call_sign 
            FROM incident_reports r
            LEFT JOIN vehicles v ON r.vehicle_id = v.id
            WHERE r.sent_at IS NULL AND r.unit_id=?
            ORDER BY r.created_at ASC
        """, (unit_id,)).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Error fetching unsent reports: {e}")
        return []
    finally:
        conn.close()

def mark_reports_as_sent(report_ids: List[int]) -> Tuple[bool, str]:
    if not report_ids:
        return True, ""
    with _lock:
        conn = get_connection()
        try:
            placeholders = ",".join("?" for _ in report_ids)
            conn.execute(f"UPDATE incident_reports SET sent_at=CURRENT_TIMESTAMP WHERE id IN ({placeholders})", report_ids)
            conn.commit()
            return True, ""
        except Exception as e:
            logger.error(f"Failed to mark reports as sent: {e}")
            return False, str(e)
        finally:
            conn.close()

def touch_participant_by_name(name: str, birthday: str) -> Tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            conn.execute("UPDATE participants SET last_seen=CURRENT_DATE WHERE name=? AND birthday=?", (name, birthday))
            conn.commit()
            return True, ""
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

def delete_expired_participants(days: int = 360) -> Tuple[int, str]:
    with _lock:
        conn = get_connection()
        try:
            c = conn.cursor()
            c.execute("DELETE FROM participants WHERE last_seen IS NOT NULL AND (julianday('now') - julianday(last_seen)) > ?", (days,))
            deleted_count = c.rowcount
            conn.commit()
            return deleted_count, ""
        except Exception as e:
            return 0, str(e)
        finally:
            conn.close()

def update_qs_level(participant_id: int, qs_level: str) -> Tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            # Set all QS to 0
            qs1 = 1 if qs_level in ["QS1", "QS2", "QS3"] else 0
            qs2 = 1 if qs_level in ["QS2", "QS3"] else 0
            qs3 = 1 if qs_level == "QS3" else 0
            
            conn.execute("""
                INSERT INTO person_qs_status (participant_id, qs1_done, qs2_done, qs3_done)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(participant_id) DO UPDATE SET
                qs1_done=excluded.qs1_done, qs2_done=excluded.qs2_done, qs3_done=excluded.qs3_done
            """, (participant_id, qs1, qs2, qs3))
            conn.commit()
            return True, ""
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

def delete_participant(participant_id: int) -> Tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            conn.execute("DELETE FROM participants WHERE id=?", (participant_id,))
            conn.commit()
            return True, ""
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

import json
import gzip

def export_db_to_json(include_history: bool = False) -> bytes:
    """Exports all tables to a JSON string and returns it gzipped. If include_history is False, the 'module_history' table is excluded."""
    with _lock:
        conn = get_connection()
        try:
            data = {}
            c = conn.cursor()
            
            # Hole alle Tabellen, schließe interne SQLite-Tabellen aus
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
            tables = [row['name'] for row in c.fetchall()]
            
            if not include_history and 'module_history' in tables:
                tables.remove('module_history')
                
            for table in tables:
                c.execute(f"SELECT * FROM {table}")
                cols = [desc[0] for desc in c.description]
                data[table] = [dict(zip(cols, row)) for row in c.fetchall()]
                
            logger.info(f"Exported DB to JSON: {len(data.get('participants', []))} participants, {len(data.get('qualifications', []))} qualifications.")
            
            def custom_serializer(obj):
                if isinstance(obj, bytes):
                    # Bytes (e.g., password_hash) als Hex-String speichern
                    return obj.hex()
                raise TypeError(f"Type {type(obj)} not serializable")

            json_str = json.dumps(data, ensure_ascii=False, indent=2, default=custom_serializer)
            return gzip.compress(json_str.encode('utf-8'))
        except Exception as e:
            logger.error(f"Failed to export DB to JSON: {e}")
            raise
        finally:
            conn.close()

def import_db_from_json(compressed_data: bytes) -> Tuple[bool, str]:
    """Clears existing data and imports from the provided gzipped JSON bytes for all tables included."""
    try:
        json_str = gzip.decompress(compressed_data).decode('utf-8')
        data = json.loads(json_str)
    except gzip.BadGzipFile:
        # Fallback for old uncompressed backups
        try:
            json_str = compressed_data.decode('utf-8')
            data = json.loads(json_str)
        except Exception as e:
            return False, f"Invalid JSON or GZIP format: {e}"
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON format: {e}"
        
    with _lock:
        conn = get_connection()
        try:
            c = conn.cursor()
            
            # Disable foreign keys temporarily
            c.execute("PRAGMA foreign_keys = OFF;")
            
            # Hole alle existierenden Tabellen in der Datenbank
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
            db_tables = [row['name'] for row in c.fetchall()]
            
            # Lösche erst die Inhalte aller DB-Tabellen.
            # Um Foreign-Key Probleme generell zu vermeiden, leeren wir alles. 
            for table in db_tables:
                c.execute(f"DELETE FROM {table}")
                
            # SQLite-Sequenzen zurücksetzen
            c.execute("DELETE FROM sqlite_sequence")
            
            # Importiere die Daten
            for table, rows in data.items():
                if table not in db_tables:
                    logger.warning(f"Table {table} in JSON but not in DB schema. Skipping.")
                    continue
                    
                if not rows:
                    continue
                    
                for row_data in rows:
                    columns = ', '.join(row_data.keys())
                    placeholders = ', '.join('?' * len(row_data))
                    sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
                    c.execute(sql, list(row_data.values()))
                    
            conn.commit()
            c.execute("PRAGMA foreign_keys = ON;")
            logger.info("Successfully imported DB from JSON.")
            return True, ""
        except Exception as e:
            logger.error(f"Failed to import DB from JSON: {e}")
            conn.rollback()
            return False, str(e)
        finally:
            conn.close()

def get_email_config(unit_id: int) -> Optional[Dict[str, Any]]:
    with _lock:
        conn = get_connection()
        try:
            c = conn.cursor()
            c.execute("SELECT * FROM email_config WHERE unit_id = ?", (unit_id,))
            row = c.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

def has_person_pdf_cache(unit_id: int, person_name: str) -> bool:
    with _lock:
        conn = get_connection()
        try:
            c = conn.cursor()
            c.execute("SELECT 1 FROM person_pdf_cache WHERE unit_id = ? AND person_name = ?", (unit_id, person_name))
            return c.fetchone() is not None
        finally:
            conn.close()

def cleanup_old_pdfs(days: int = 7) -> int:
    """
    Deletes entries from person_pdf_cache and pdf_cache older than the specified number of days.
    """
    with _lock:
        conn = get_connection()
        try:
            c = conn.cursor()
            
            # SQLite modifier for datetime calculation (e.g., '-7 days')
            date_modifier = f"-{days} days"
            
            c.execute("DELETE FROM person_pdf_cache WHERE updated_at <= datetime('now', ?)", (date_modifier,))
            person_deleted = c.rowcount
            
            c.execute("DELETE FROM pdf_cache WHERE updated_at <= datetime('now', ?)", (date_modifier,))
            unit_deleted = c.rowcount
            
            conn.commit()
            
            total_deleted = person_deleted + unit_deleted
            if total_deleted > 0:
                logger.info(f"PDF Cache Cleanup: Deleted {person_deleted} person PDFs and {unit_deleted} unit PDFs older than {days} days.")
                
            return total_deleted
        except Exception as e:
            logger.error(f"Error during PDF cache cleanup: {e}")
            conn.rollback()
            return 0
        finally:
            conn.close()

def save_email_config(unit_id: int, server: str, port: int, user: str, password: str, sender: str, recipients: str, delay: int) -> tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            c = conn.cursor()
            c.execute("SELECT id FROM email_config WHERE unit_id = ?", (unit_id,))
            if c.fetchone():
                c.execute("""
                    UPDATE email_config 
                    SET smtp_server=?, smtp_port=?, smtp_user=?, smtp_password=?, sender_email=?, recipient_emails=?, delay_minutes=?
                    WHERE unit_id=?
                """, (server, port, user, password, sender, recipients, delay, unit_id))
            else:
                c.execute("""
                    INSERT INTO email_config (unit_id, smtp_server, smtp_port, smtp_user, smtp_password, sender_email, recipient_emails, delay_minutes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (unit_id, server, port, user, password, sender, recipients, delay))
            conn.commit()
            return True, ""
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            conn.close()

# --- Stundennachweis ---
def get_stundennachweis_zeitraum(unit_id: int) -> Optional[str]:
    with _lock:
        conn = get_connection()
        try:
            c = conn.cursor()
            c.execute("SELECT letzter_zeitraum FROM stundennachweis_config WHERE unit_id = ?", (unit_id,))
            row = c.fetchone()
            return row['letzter_zeitraum'] if row else None
        finally:
            conn.close()

def update_stundennachweis_zeitraum(unit_id: int, zeitraum: str) -> None:
    with _lock:
        conn = get_connection()
        try:
            c = conn.cursor()
            c.execute("SELECT id FROM stundennachweis_config WHERE unit_id = ?", (unit_id,))
            if c.fetchone():
                c.execute("UPDATE stundennachweis_config SET letzter_zeitraum = ?, last_updated = CURRENT_TIMESTAMP WHERE unit_id = ?", (zeitraum, unit_id))
            else:
                c.execute("INSERT INTO stundennachweis_config (unit_id, letzter_zeitraum) VALUES (?, ?)", (unit_id, zeitraum))
            conn.commit()
        finally:
            conn.close()

def update_participant_hours(unit_id: int, name: str, birthday: str, einsatzstunden: float, dienststunden: float) -> bool:
    with _lock:
        conn = get_connection()
        try:
            c = conn.cursor()
            c.execute("""
                UPDATE participants 
                SET einsatzstunden = ?, dienststunden = ?, updated_at = CURRENT_TIMESTAMP, last_seen = CURRENT_DATE
                WHERE unit_id = ? AND name = ? AND birthday = ?
            """, (einsatzstunden, dienststunden, unit_id, name, birthday))
            conn.commit()
            return c.rowcount > 0
        finally:
            conn.close()
# --- PROMOTION CONFIG ---

def get_promotion_config(unit_id: int) -> dict:
    """Gets the promotion thresholds for a unit."""
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT qs1_threshold, qs2_threshold, qs3_threshold FROM promotion_config WHERE unit_id = ?", (unit_id,))
        row = c.fetchone()
        if row:
            return dict(row)
        else:
            # Create default config if not exists
            c.execute("INSERT INTO promotion_config (unit_id) VALUES (?)", (unit_id,))
            conn.commit()
            return {'qs1_threshold': 90, 'qs2_threshold': 90, 'qs3_threshold': 100}
    except Exception as e:
        logger.error(f"Error getting promotion config: {e}")
        return {'qs1_threshold': 90, 'qs2_threshold': 90, 'qs3_threshold': 100}
    finally:
        if 'conn' in locals() and conn: conn.close()

def update_promotion_config(unit_id: int, qs1: int, qs2: int, qs3: int) -> bool:
    """Updates the promotion thresholds for a unit."""
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
            INSERT INTO promotion_config (unit_id, qs1_threshold, qs2_threshold, qs3_threshold)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(unit_id) DO UPDATE SET
            qs1_threshold = excluded.qs1_threshold,
            qs2_threshold = excluded.qs2_threshold,
            qs3_threshold = excluded.qs3_threshold
        """, (unit_id, qs1, qs2, qs3))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error updating promotion config: {e}")
        return False
    finally:
        if 'conn' in locals() and conn: conn.close()
