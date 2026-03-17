import sqlite3
import os
import threading
import logging

logger = logging.getLogger(__name__)

# Core database path and lock
def get_db_path():
    # Primary: Absolute path based on the directory of this file
    # This file is at root/src/database/core.py. 
    # Root is up 3 levels.
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(base_dir, "data", "local_cache.db")
    return path

_SQLITE_PATH = get_db_path()
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
            logger.info(f"Checking database at: {_SQLITE_PATH}")
            print(f"DEBUG: Checking database at: {_SQLITE_PATH}")
            
            c = conn.cursor()
            
            # 1. Base Tables Creation
            logger.debug("Creating base tables if missing...")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS units (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    public_view_password TEXT DEFAULT 'feuerprofi'
                );
                
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    unit_id INTEGER DEFAULT NULL,
                    is_admin INTEGER DEFAULT 0,
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
                    unit_id INTEGER,
                    FOREIGN KEY (unit_id) REFERENCES units(id) ON DELETE SET NULL
                    -- UNIQUE constraint intentionally omitted here if table already exists without unit_id
                );
                
                CREATE TABLE IF NOT EXISTS auto_update_config (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    update_day INTEGER NOT NULL,
                    update_hour INTEGER NOT NULL,
                    update_minute INTEGER NOT NULL,
                    last_check_at TEXT,
                    update_available INTEGER DEFAULT 0,
                    remote_commit TEXT DEFAULT NULL,
                    auto_update_enabled INTEGER DEFAULT 1
                );
                
                INSERT OR IGNORE INTO auto_update_config (id, update_day, update_hour, update_minute)
                VALUES (1, 0, 3, 0);

                CREATE TABLE IF NOT EXISTS pdf_cache (
                    unit_id INTEGER PRIMARY KEY,
                    pdf_content BLOB,
                    filename TEXT,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (unit_id) REFERENCES units(id) ON DELETE CASCADE
                );
            """)

            # 2. Key Table Migrations (Explicit Checks)
            def add_column_if_missing(table, column, definition):
                try:
                    c.execute(f"SELECT {column} FROM {table} LIMIT 1")
                    print(f"DEBUG: Column {column} in {table} already exists.")
                except sqlite3.OperationalError as e:
                    print(f"DEBUG: Adding column {column} to {table} (Error was: {e})")
                    logger.info(f"Adding missing column {column} to {table}...")
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                    conn.commit()

            # Fix 'users' table
            add_column_if_missing("users", "unit_id", "INTEGER DEFAULT NULL")
            add_column_if_missing("users", "is_admin", "INTEGER DEFAULT 0")

            # Fix 'participants' table
            add_column_if_missing("participants", "unit_id", "INTEGER DEFAULT NULL")

            # Fix 'auto_update_config'
            add_column_if_missing("auto_update_config", "remote_commit", "TEXT DEFAULT NULL")
            add_column_if_missing("auto_update_config", "auto_update_enabled", "INTEGER DEFAULT 1")

            # Fix 'pdf_cache' and 'person_pdf_cache'
            add_column_if_missing("pdf_cache", "pdf_content", "BLOB")
            add_column_if_missing("pdf_cache", "filename", "TEXT")
            
            # person_pdf_cache table handling
            try:
                c.execute("SELECT 1 FROM person_pdf_cache LIMIT 1")
                add_column_if_missing("person_pdf_cache", "pdf_content", "BLOB")
            except sqlite3.OperationalError:
                # Table missing, will be created below or was already handled
                pass

            # 3. Tables that might be completely missing in older DBs
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS person_pdf_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    unit_id INTEGER,
                    person_name TEXT,
                    pdf_content BLOB,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(unit_id, person_name),
                    FOREIGN KEY (unit_id) REFERENCES units(id) ON DELETE CASCADE
                );
            """)

            # 3. Handle specific constraints (like UNIQUE index for participants)
            # If we just added unit_id, we might want the UNIQUE constraint.
            # But changing constraints in SQLite requires table rebuild.
            # For now, let's just make sure the column exists.

            # 4. Final safety commit
            conn.commit()
            logger.info("Database initialization complete.")
        finally:
            conn.close()
