import logging
from typing import List, Dict, Any, Tuple
from .core import get_connection, _lock

logger = logging.getLogger(__name__)

def get_qualifications() -> List[Dict[str, Any]]:
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM qualifications ORDER BY value ASC")
            return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

def create_qualification(name: str, value: int, prerequisite_id: int = None, equivalent_id: int = None) -> Tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            conn.execute("INSERT INTO qualifications (name, value, prerequisite_id, equivalent_id) VALUES (?, ?, ?, ?)", (name, value, prerequisite_id, equivalent_id))
            conn.commit()
            return True, ""
        except Exception as e: return False, str(e)
        finally:
            conn.close()

def update_qualification(q_id: int, name: str, value: int, prerequisite_id: int = None, equivalent_id: int = None) -> Tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            conn.execute("UPDATE qualifications SET name=?, value=?, prerequisite_id=?, equivalent_id=? WHERE id=?", (name, value, prerequisite_id, equivalent_id, q_id))
            conn.commit()
            return True, ""
        except Exception as e: return False, str(e)
        finally:
            conn.close()

def delete_qualification(q_id: int) -> Tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            conn.execute("DELETE FROM qualifications WHERE id=?", (q_id,))
            conn.commit()
            return True, ""
        except Exception as e: return False, str(e)
        finally:
            conn.close()

def get_participants_with_qualifications(unit_id: int = None) -> List[Dict[str, Any]]:
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            query = "SELECT p.id, p.name, p.birthday, group_concat(q.name, ', ') as quals FROM participants p LEFT JOIN participant_qualifications pq ON p.id = pq.participant_id LEFT JOIN qualifications q ON pq.qualification_id = q.id"
            params = []
            if unit_id:
                query += " WHERE p.unit_id = ?"
                params.append(unit_id)
            query += " GROUP BY p.id"
            cursor.execute(query, params)
            return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

def assign_qualification(participant_id: int, qualification_id: int) -> Tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            conn.execute("INSERT OR IGNORE INTO participant_qualifications (participant_id, qualification_id) VALUES (?, ?)", (participant_id, qualification_id))
            conn.commit()
            return True, ""
        except Exception as e: return False, str(e)
        finally:
            conn.close()

def remove_qualification(participant_id: int, qualification_id: int) -> Tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            conn.execute("DELETE FROM participant_qualifications WHERE participant_id = ? AND qualification_id = ?", (participant_id, qualification_id))
            conn.commit()
            return True, ""
        except Exception as e: return False, str(e)
        finally:
            conn.close()
