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
                );
                
                CREATE UNIQUE INDEX IF NOT EXISTS idx_participants_unique_identity 
                ON participants(name, birthday, unit_id);
                
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
            def rebuild_pdf_table_if_legacy(table_name, create_sql, select_mapping):
                try:
                    c.execute(f"PRAGMA table_info({table_name})")
                    columns = {r[1]: {"notnull": r[3]} for r in c.fetchall()}
                    
                    if not columns: return # Table doesn't exist yet
                    
                    # If pdf_data exists AND is NOT NULL, we MUST rebuild to get rid of the constraint
                    # OR if pdf_content is missing.
                    needs_rebuild = False
                    if "pdf_data" in columns and columns["pdf_data"]["notnull"] == 1:
                        needs_rebuild = True
                    if "pdf_content" not in columns:
                        needs_rebuild = True
                        
                    if needs_rebuild:
                        logger.info(f"Rebuilding {table_name} to fix legacy NOT NULL constraints...")
                        c.execute(f"ALTER TABLE {table_name} RENAME TO {table_name}_old")
                        c.execute(create_sql)
                        
                        # Try to migrate data. select_mapping maps new_col -> old_col_to_select
                        new_cols = []
                        old_cols = []
                        for nc, oc in select_mapping.items():
                            new_cols.append(nc)
                            old_cols.append(oc)
                        
                        cols_str = ", ".join(new_cols)
                        select_str = ", ".join(old_cols)
                        
                        try:
                            c.execute(f"INSERT OR IGNORE INTO {table_name} ({cols_str}) SELECT {select_str} FROM {table_name}_old")
                            logger.info(f"Successfully migrated data for {table_name}")
                        except Exception as e:
                            logger.warning(f"Data migration failed for {table_name} (data loss in cache is ok): {e}")
                        
                        c.execute(f"DROP TABLE {table_name}_old")
                        conn.commit()
                except Exception as e:
                    logger.error(f"Error rebuilding {table_name}: {e}")

            # Rebuild pdf_cache
            rebuild_pdf_table_if_legacy(
                "pdf_cache",
                """CREATE TABLE pdf_cache (
                    unit_id INTEGER PRIMARY KEY,
                    pdf_content BLOB,
                    filename TEXT,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (unit_id) REFERENCES units(id) ON DELETE CASCADE
                )""",
                {"unit_id": "unit_id", "pdf_content": "COALESCE(pdf_content, pdf_data)", "filename": "filename", "updated_at": "updated_at"}
            )

            # Rebuild person_pdf_cache
            rebuild_pdf_table_if_legacy(
                "person_pdf_cache",
                """CREATE TABLE person_pdf_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    unit_id INTEGER,
                    person_name TEXT,
                    pdf_content BLOB,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(unit_id, person_name),
                    FOREIGN KEY (unit_id) REFERENCES units(id) ON DELETE CASCADE
                )""",
                {"unit_id": "unit_id", "person_name": "person_name", "pdf_content": "COALESCE(pdf_content, pdf_data)", "updated_at": "updated_at"}
            )

            # 3. Final safety commit for standard Tables that might be completely missing
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS units (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    public_view_password TEXT DEFAULT 'feuerprofi'
                );
                
                -- Ensure tables exist even if rebuild was skipped
                CREATE TABLE IF NOT EXISTS pdf_cache (
                    unit_id INTEGER PRIMARY KEY,
                    pdf_content BLOB,
                    filename TEXT,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (unit_id) REFERENCES units(id) ON DELETE CASCADE
                );

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

            conn.commit()
            logger.info("Database initialization complete.")
        finally:
            conn.close()
