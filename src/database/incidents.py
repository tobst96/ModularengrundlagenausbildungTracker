import logging
import json
from typing import List, Dict, Any, Tuple, Optional
from .core import get_connection, _lock

logger = logging.getLogger(__name__)

def get_vehicles(unit_id: int = 1) -> List[Dict[str, Any]]:
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vehicles WHERE unit_id = ?", (unit_id,))
            return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

def get_vehicle_by_token(token: str) -> Optional[Dict[str, Any]]:
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vehicles WHERE token = ?", (token,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

def create_vehicle(call_sign: str, seats: int, unit_id: int = 1) -> Tuple[bool, str]:
    import secrets
    with _lock:
        conn = get_connection()
        try:
            token = secrets.token_hex(16)
            conn.execute("INSERT INTO vehicles (unit_id, call_sign, seats, token) VALUES (?, ?, ?, ?)", (unit_id, call_sign, seats, token))
            conn.commit()
            return True, ""
        except Exception as e: return False, str(e)
        finally:
            conn.close()

def update_vehicle(v_id: int, call_sign: str, seats: int) -> Tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            conn.execute("UPDATE vehicles SET call_sign=?, seats=? WHERE id=?", (call_sign, seats, v_id))
            conn.commit()
            return True, ""
        except Exception as e: return False, str(e)
        finally:
            conn.close()

def delete_vehicle(v_id: int) -> Tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            conn.execute("DELETE FROM vehicles WHERE id=?", (v_id,))
            conn.commit()
            return True, ""
        except Exception as e: return False, str(e)
        finally:
            conn.close()

def create_incident_report(keyword: str, vehicle_id: Optional[int], commander_id: Optional[int], unit_leader_id: Optional[int], crew_json: str, situation: str, actions: str, unit_id: int = 1) -> Tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            conn.execute("INSERT INTO incident_reports (unit_id, keyword, vehicle_id, commander_id, unit_leader_id, crew_json, situation, actions) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (unit_id, keyword, vehicle_id, commander_id, unit_leader_id, crew_json, situation, actions))
            conn.commit()
            return True, ""
        except Exception as e: return False, str(e)
        finally:
            conn.close()

def get_unsent_incident_reports(unit_id: int = 1) -> List[Dict[str, Any]]:
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM incident_reports WHERE unit_id = ? AND sent_at IS NULL", (unit_id,))
            return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

def mark_reports_as_sent(report_ids: List[int]) -> Tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            placeholders = ','.join('?' for _ in report_ids)
            conn.execute(f"UPDATE incident_reports SET sent_at = CURRENT_TIMESTAMP WHERE id IN ({placeholders})", report_ids)
            conn.commit()
            return True, ""
        except Exception as e: return False, str(e)
        finally:
            conn.close()
