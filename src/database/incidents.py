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

def create_incident_report(keyword: str, vehicle_id: Optional[int], commander_id: Optional[int], unit_leader_id: Optional[int], crew_json: str, situation: str, actions: str, unit_id: int = 1, incident_id: Optional[int] = None) -> Tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            conn.execute("INSERT INTO incident_reports (unit_id, incident_id, keyword, vehicle_id, commander_id, unit_leader_id, crew_json, situation, actions) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (unit_id, incident_id, keyword, vehicle_id, commander_id, unit_leader_id, crew_json, situation, actions))
            conn.commit()
            return True, ""
        except Exception as e: return False, str(e)
        finally:
            conn.close()

def get_active_incidents(unit_id: int = 1) -> List[Dict[str, Any]]:
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM active_incidents WHERE unit_id = ? AND is_active = 1 ORDER BY created_at DESC", (unit_id,))
            return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

def create_active_incident(unit_id: int, keyword: str, situation: str = "", actions: str = "", cmd_id: Optional[int] = None, ldr_id: Optional[int] = None) -> Tuple[Optional[int], str]:
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO active_incidents (unit_id, keyword, situation, actions, commander_id, unit_leader_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (unit_id, keyword, situation, actions, cmd_id, ldr_id))
            new_id = cursor.lastrowid
            conn.commit()
            return new_id, ""
        except Exception as e: return None, str(e)
        finally:
            conn.close()

def update_active_incident(incident_id: int, keyword: str, situation: str, actions: str, cmd_id: Optional[int] = None, ldr_id: Optional[int] = None) -> Tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            conn.execute("""
                UPDATE active_incidents 
                SET keyword=?, situation=?, actions=?, commander_id=?, unit_leader_id=?
                WHERE id=?
            """, (keyword, situation, actions, cmd_id, ldr_id, incident_id))
            conn.commit()
            return True, ""
        except Exception as e: return False, str(e)
        finally:
            conn.close()

def close_incident(incident_id: int) -> Tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            conn.execute("UPDATE active_incidents SET is_active = 0 WHERE id = ?", (incident_id,))
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
            query = """
                SELECT 
                    i.*, 
                    v.call_sign as vehicle_name,
                    p_cmd.name as commander_name,
                    p_ldr.name as unit_leader_name
                FROM incident_reports i
                LEFT JOIN vehicles v ON i.vehicle_id = v.id
                LEFT JOIN participants p_cmd ON i.commander_id = p_cmd.id
                LEFT JOIN participants p_ldr ON i.unit_leader_id = p_ldr.id
                WHERE i.unit_id = ? AND i.sent_at IS NULL
            """
            cursor.execute(query, (unit_id,))
            return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

def get_incident_reports(incident_id: int) -> List[Dict[str, Any]]:
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            query = """
                SELECT 
                    i.*, 
                    v.call_sign as vehicle_name,
                    p_cmd.name as commander_name,
                    p_ldr.name as unit_leader_name
                FROM incident_reports i
                LEFT JOIN vehicles v ON i.vehicle_id = v.id
                LEFT JOIN participants p_cmd ON i.commander_id = p_cmd.id
                LEFT JOIN participants p_ldr ON i.unit_leader_id = p_ldr.id
                WHERE i.incident_id = ?
            """
            cursor.execute(query, (incident_id,))
            return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

def cleanup_old_reports() -> Tuple[bool, str]:
    """
    Behält nur die letzten 10 Batches (nach sent_at) in der Datenbank.
    Ältere Berichte werden gelöscht, um Speicherplatz zu sparen.
    """
    with _lock:
        conn = get_connection()
        try:
            # Finde die 10 neuesten Versand-Zeitstempel
            query_get_recent = """
                SELECT DISTINCT sent_at 
                FROM incident_reports 
                WHERE sent_at IS NOT NULL 
                ORDER BY sent_at DESC 
                LIMIT 10
            """
            cursor = conn.cursor()
            cursor.execute(query_get_recent)
            recent_stamps = [r[0] for r in cursor.fetchall() if r[0]]
            
            if not recent_stamps:
                return True, ""
                
            # Lösche alle versandten Berichte, deren Zeitstempel nicht in den Top 10 ist
            placeholders = ','.join('?' for _ in recent_stamps)
            delete_query = f"""
                DELETE FROM incident_reports 
                WHERE sent_at IS NOT NULL 
                AND sent_at NOT IN ({placeholders})
            """
            conn.execute(delete_query, recent_stamps)
            conn.commit()
            return True, ""
        except Exception as e:
            logger.error(f"Failed to cleanup old incident reports: {e}")
            return False, str(e)
        finally:
            conn.close()

def mark_reports_as_sent(report_ids: List[int]) -> Tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            placeholders = ','.join('?' for _ in report_ids)
            conn.execute(f"UPDATE incident_reports SET sent_at = CURRENT_TIMESTAMP WHERE id IN ({placeholders})", report_ids)
            conn.commit()
            
            # Automatische Bereinigung nach dem Versenden
            cleanup_old_reports()
            
            return True, ""
        except Exception as e: return False, str(e)
        finally:
            conn.close()
