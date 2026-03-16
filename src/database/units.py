import logging
from .core import get_connection, _lock

logger = logging.getLogger(__name__)

def get_units() -> list[dict]:
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM units")
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
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

def delete_unit(unit_id: int) -> tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            conn.execute("DELETE FROM units WHERE id = ?", (unit_id,))
            conn.commit()
            return True, ""
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()
