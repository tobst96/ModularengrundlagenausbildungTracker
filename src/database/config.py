import logging
from typing import Optional, Dict, Any
from .core import get_connection, _lock

logger = logging.getLogger(__name__)

def get_auto_update_config() -> Optional[Dict[str, Any]]:
    with _lock:
        conn = get_connection()
        try:
            c = conn.cursor()
            c.execute("SELECT * FROM auto_update_config WHERE id = 1")
            row = c.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

def save_auto_update_config(data: Dict[str, Any]) -> bool:
    with _lock:
        conn = get_connection()
        try:
            fields = []
            values = []
            for k, v in data.items():
                if k != 'id':
                    fields.append(f"{k}=?")
                    values.append(v)
            
            if not fields:
                return True
                
            query = f"UPDATE auto_update_config SET {', '.join(fields)} WHERE id = 1"
            conn.execute(query, values)
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error saving auto_update_config: {e}")
            return False
        finally:
            conn.close()

def get_feueron_config(unit_id: int) -> Optional[dict]:
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM feueron_sync_config WHERE unit_id = ?", (unit_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

def save_feueron_config(unit_id: int, org: str, org_id: str, username: str, password: str,
                        hour: int, minute: int, enabled: bool) -> tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            conn.execute("""
                INSERT INTO feueron_sync_config 
                (unit_id, feueron_org, feueron_org_id, feueron_username, feueron_password, sync_hour, sync_minute, sync_enabled)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(unit_id) DO UPDATE SET
                feueron_org=excluded.feueron_org,
                feueron_org_id=excluded.feueron_org_id,
                feueron_username=excluded.feueron_username,
                feueron_password=excluded.feueron_password,
                sync_hour=excluded.sync_hour,
                sync_minute=excluded.sync_minute,
                sync_enabled=excluded.sync_enabled
            """, (unit_id, org, org_id, username, password, hour, minute, int(enabled)))
            conn.commit()
            return True, ""
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

def get_all_feueron_configs() -> list:
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM feueron_sync_config WHERE sync_enabled = 1")
            return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

def get_email_config(unit_id: int) -> Optional[Dict[str, Any]]:
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM email_config WHERE unit_id = ?", (unit_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

def save_email_config(unit_id: int, server: str, port: int, user: str, password: str, sender: str, recipients: str, delay: int) -> tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            conn.execute("""
                INSERT INTO email_config (unit_id, smtp_server, smtp_port, smtp_user, smtp_password, sender_email, recipient_emails, delay_minutes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(unit_id) DO UPDATE SET
                smtp_server=excluded.smtp_server,
                smtp_port=excluded.smtp_port,
                smtp_user=excluded.smtp_user,
                smtp_password=excluded.smtp_password,
                sender_email=excluded.sender_email,
                recipient_emails=excluded.recipient_emails,
                delay_minutes=excluded.delay_minutes
            """, (unit_id, server, port, user, password, sender, recipients, delay))
            conn.commit()
            return True, ""
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

def get_promotion_config(unit_id: int) -> dict:
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM promotion_config WHERE unit_id = ?", (unit_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return {'qs1_threshold': 90, 'qs2_threshold': 90, 'qs3_threshold': 100}
        finally:
            conn.close()

def update_promotion_config(unit_id: int, qs1: int, qs2: int, qs3: int) -> bool:
    with _lock:
        conn = get_connection()
        try:
            conn.execute("""
                INSERT INTO promotion_config (unit_id, qs1_threshold, qs2_threshold, qs3_threshold)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(unit_id) DO UPDATE SET
                qs1_threshold=excluded.qs1_threshold,
                qs2_threshold=excluded.qs2_threshold,
                qs3_threshold=excluded.qs3_threshold
            """, (unit_id, qs1, qs2, qs3))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error updating promotion_config: {e}")
            return False
        finally:
            conn.close()

def get_public_view_password(unit_id: int) -> Optional[str]:
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT public_view_password FROM units WHERE id = ?", (unit_id,))
            row = cursor.fetchone()
            return row['public_view_password'] if row else None
        finally:
            conn.close()

def save_public_view_password(unit_id: int, password: str) -> Tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            conn.execute("UPDATE units SET public_view_password = ? WHERE id = ?", (password, unit_id))
            conn.commit()
            return True, ""
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()
