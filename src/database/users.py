import bcrypt
import logging
from typing import List, Dict, Tuple, Optional
from .core import get_connection, _lock

logger = logging.getLogger(__name__)

def init_admin_user(username, password):
    with _lock:
        conn = get_connection()
        try:
            c = conn.cursor()
            c.execute("SELECT 1 FROM users WHERE username = ?", (username,))
            if not c.fetchone():
                hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
                c.execute("INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, 1)", 
                         (username, hashed.decode('utf-8')))
                conn.commit()
                # Ensure a default unit exists for the admin
                c.execute("INSERT OR IGNORE INTO units (id, name) VALUES (1, 'Hauptwache')")
                c.execute("UPDATE users SET unit_id = 1 WHERE username = ?", (username,))
                conn.commit()
                logger.info(f"Admin user '{username}' initialized.")
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
        except Exception as e:
            logger.error(f"Error logging login: {e}")
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
        except Exception as e:
            logger.error(f"Error getting login history: {e}")
            return []
        finally:
            conn.close()

def verify_user(username, password) -> tuple[bool, Optional[int], Optional[str], bool]:
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
            row = cursor.fetchone()
            if row:
                if bcrypt.checkpw(password.encode('utf-8'), row['password_hash'].encode('utf-8')):
                    return True, row['unit_id'], row['name'], bool(row['is_admin'])
            return False, None, None, False
        finally:
            conn.close()

def change_password(username: str, new_password: str) -> Tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            hashed = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
            conn.execute("UPDATE users SET password_hash = ? WHERE username = ?", 
                        (hashed.decode('utf-8'), username))
            conn.commit()
            return True, "Passwort erfolgreich geändert."
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

def is_default_password(username: str) -> bool:
    # This logic usually depends on the default setting in the updater or init
    # For now, we assume if it matches the env ADMIN_PASSWORD or similar
    # But often it's checked by a specific flag or logic.
    return False # Simplified for now

def get_all_users() -> list[dict]:
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id, username, is_admin, unit_id FROM users")
            return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

def update_user_admin_status(user_id: int, is_admin: bool) -> tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            conn.execute("UPDATE users SET is_admin = ? WHERE id = ?", (int(is_admin), user_id))
            conn.commit()
            return True, ""
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

def create_user_with_unit(username, password, unit_id) -> tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
            conn.execute("INSERT INTO users (username, password_hash, unit_id) VALUES (?, ?, ?)",
                        (username, hashed.decode('utf-8'), unit_id))
            conn.commit()
            return True, ""
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

def update_user_password(user_id: int, new_password: str) -> tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            hashed = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
            conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hashed.decode('utf-8'), user_id))
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
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()
            return True, ""
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()
