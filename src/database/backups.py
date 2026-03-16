import logging
import json
import gzip
from typing import Tuple
from .core import get_connection, _lock

logger = logging.getLogger(__name__)

def export_unit_backup(unit_id: int) -> dict:
    unit_id = 1
    # This was a placeholder in db_base.py or very specific. 
    # The actual full backup is export_db_to_json.
    return {"unit_id": unit_id, "timestamp": "placeholder"}

def import_unit_backup(unit_id: int, backup_data: dict) -> tuple[bool, str]:
    unit_id = 1
    return True, "Backup importiert (Simuliert)"

def export_db_to_json(include_history: bool = False) -> bytes:
    with _lock:
        conn = get_connection()
        try:
            data = {}
            c = conn.cursor()
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
            tables = [row['name'] for row in c.fetchall()]
            if not include_history and 'module_history' in tables: tables.remove('module_history')
            for table in tables:
                c.execute(f"SELECT * FROM {table}")
                cols = [desc[0] for desc in c.description]
                data[table] = [dict(zip(cols, row)) for row in c.fetchall()]
            def custom_serializer(obj):
                if isinstance(obj, bytes): return obj.hex()
                raise TypeError(f"Type {type(obj)} not serializable")
            json_str = json.dumps(data, ensure_ascii=False, indent=2, default=custom_serializer)
            return gzip.compress(json_str.encode('utf-8'))
        except Exception as e:
            logger.error(f"Failed to export DB to JSON: {e}")
            raise
        finally:
            conn.close()

def import_db_from_json(compressed_data: bytes) -> Tuple[bool, str]:
    try:
        json_str = gzip.decompress(compressed_data).decode('utf-8')
        data = json.loads(json_str)
    except Exception:
        try:
            json_str = compressed_data.decode('utf-8')
            data = json.loads(json_str)
        except Exception as e: return False, f"Invalid format: {e}"
        
    with _lock:
        conn = get_connection()
        try:
            c = conn.cursor()
            c.execute("PRAGMA foreign_keys = OFF;")
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
            db_tables = [row['name'] for row in c.fetchall()]
            for table in db_tables: c.execute(f"DELETE FROM {table}")
            c.execute("DELETE FROM sqlite_sequence")
            for table, rows in data.items():
                if table not in db_tables or not rows: continue
                for row_data in rows:
                    columns = ', '.join(row_data.keys()); placeholders = ', '.join('?' * len(row_data))
                    c.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", list(row_data.values()))
            conn.commit()
            c.execute("PRAGMA foreign_keys = ON;")
            return True, ""
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            conn.close()
