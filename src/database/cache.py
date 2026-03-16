import logging
from .core import get_connection, _lock

logger = logging.getLogger(__name__)

def save_pdf_cache(unit_id: int, pdf_bytes: bytes, filename: str = "") -> None:
    with _lock:
        conn = get_connection()
        try:
            conn.execute("INSERT INTO pdf_cache (unit_id, pdf_content, filename) VALUES (?, ?, ?) ON CONFLICT(unit_id) DO UPDATE SET pdf_content=excluded.pdf_content, filename=excluded.filename, updated_at=CURRENT_TIMESTAMP", (unit_id, pdf_bytes, filename))
            conn.commit()
        finally:
            conn.close()

def get_pdf_cache(unit_id: int) -> bytes | None:
    with _lock:
        conn = get_connection()
        try:
            row = conn.execute("SELECT pdf_content FROM pdf_cache WHERE unit_id = ?", (unit_id,)).fetchone()
            return row['pdf_content'] if row else None
        finally:
            conn.close()

def save_person_pdf_cache(unit_id: int, person_name: str, pdf_bytes: bytes) -> None:
    with _lock:
        conn = get_connection()
        try:
            conn.execute("INSERT INTO person_pdf_cache (unit_id, person_name, pdf_content) VALUES (?, ?, ?) ON CONFLICT(unit_id, person_name) DO UPDATE SET pdf_content=excluded.pdf_content, updated_at=CURRENT_TIMESTAMP", (unit_id, person_name, pdf_bytes))
            conn.commit()
        finally:
            conn.close()

def get_person_pdf_cache(unit_id: int, person_name: str) -> bytes | None:
    with _lock:
        conn = get_connection()
        try:
            row = conn.execute("SELECT pdf_content FROM person_pdf_cache WHERE unit_id = ? AND person_name = ?", (unit_id, person_name)).fetchone()
            return row['pdf_content'] if row else None
        finally:
            conn.close()

def clear_person_pdf_cache(unit_id: int) -> None:
    with _lock:
        conn = get_connection()
        try:
            conn.execute("DELETE FROM person_pdf_cache WHERE unit_id = ?", (unit_id,))
            conn.commit()
        finally:
            conn.close()

def has_person_pdf_cache(unit_id: int, person_name: str) -> bool:
    with _lock:
        conn = get_connection()
        try:
            return conn.execute("SELECT 1 FROM person_pdf_cache WHERE unit_id = ? AND person_name = ?", (unit_id, person_name)).fetchone() is not None
        finally:
            conn.close()

def cleanup_old_pdfs(days: int = 7) -> int:
    with _lock:
        conn = get_connection()
        try:
            c = conn.cursor()
            date_modifier = f"-{days} days"
            c.execute("DELETE FROM person_pdf_cache WHERE updated_at <= datetime('now', ?)", (date_modifier,))
            p_del = c.rowcount
            c.execute("DELETE FROM pdf_cache WHERE updated_at <= datetime('now', ?)", (date_modifier,))
            u_del = c.rowcount
            conn.commit()
            return p_del + u_del
        except Exception as e:
            logger.error(f"Error during PDF cache cleanup: {e}")
            return 0
        finally:
            conn.close()
