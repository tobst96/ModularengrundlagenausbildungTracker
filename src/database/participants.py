import logging
import streamlit as st
from typing import List, Dict, Any, Optional, Tuple, Callable
from .core import get_connection, _lock

logger = logging.getLogger(__name__)

@st.cache_data
def get_all_participants_admin(unit_id: Optional[int] = None) -> list[dict]:
    unit_id = 1 # Hardcoded in original db_base.py
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            if unit_id is not None:
                cursor.execute("""
                    SELECT p.id, p.name, p.birthday, p.unit_id, un.name as unit_name
                    FROM participants p
                    LEFT JOIN units un ON p.unit_id = un.id
                    WHERE p.unit_id = ?
                    ORDER BY p.name
                """, (unit_id,))
            else:
                cursor.execute("""
                    SELECT p.id, p.name, p.birthday, p.unit_id, un.name as unit_name
                    FROM participants p
                    LEFT JOIN units un ON p.unit_id = un.id
                    ORDER BY p.name
                """)
            return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

def delete_person(name: str, birthday: str, unit_id: Optional[int] = None) -> tuple[bool, str]:
    unit_id = 1 # Hardcoded in original db_base.py
    with _lock:
        conn = get_connection()
        try:
            c = conn.cursor()
            if unit_id is not None:
                c.execute("SELECT id FROM participants WHERE name = ? AND birthday = ? AND unit_id = ?", (name, birthday, unit_id))
            else:
                c.execute("SELECT id FROM participants WHERE name = ? AND birthday = ? AND unit_id IS NULL", (name, birthday))
            
            row = c.fetchone()
            if not row:
                return False, "Person nicht gefunden"
                
            p_id = row['id']
            
            # Alle abhängigen Daten löschen
            conn.execute("DELETE FROM module_history WHERE participant_id = ?", (p_id,))
            conn.execute("DELETE FROM person_qs_status WHERE participant_id = ?", (p_id,))
            conn.execute("DELETE FROM participant_qualifications WHERE participant_id = ?", (p_id,))
            conn.execute("UPDATE incident_reports SET commander_id = NULL WHERE commander_id = ?", (p_id,))
            conn.execute("UPDATE incident_reports SET unit_leader_id = NULL WHERE unit_leader_id = ?", (p_id,))
            
            # Person löschen
            conn.execute("DELETE FROM participants WHERE id = ?", (p_id,))
            
            conn.commit()
            st.cache_data.clear()
            return True, ""
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            conn.close()

def delete_all_unknown_persons(unit_id: Optional[int] = None) -> tuple[bool, str, int]:
    unit_id = 1 # Hardcoded in original db_base.py
    deleted_count = 0
    with _lock:
        conn = get_connection()
        try:
            c = conn.cursor()
            if unit_id is not None:
                c.execute("SELECT id FROM participants WHERE birthday = 'Unknown' AND unit_id = ?", (unit_id,))
            else:
                c.execute("SELECT id FROM participants WHERE birthday = 'Unknown' AND unit_id IS NULL")
            
            p_ids = [r['id'] for r in c.fetchall()]
            if not p_ids:
                return True, "", 0
                
            deleted_count = len(p_ids)
            
            # Alle abhängigen Daten löschen
            placeholders = ','.join('?' for _ in p_ids)
            
            c.execute(f"DELETE FROM module_history WHERE participant_id IN ({placeholders})", p_ids)
            c.execute(f"DELETE FROM person_qs_status WHERE participant_id IN ({placeholders})", p_ids)
            c.execute(f"DELETE FROM participant_qualifications WHERE participant_id IN ({placeholders})", p_ids)
            
            # Personen löschen
            c.execute(f"DELETE FROM participants WHERE id IN ({placeholders})", p_ids)
            
            conn.commit()
            st.cache_data.clear()
            return True, "", deleted_count
        except Exception as e:
            conn.rollback()
            return False, str(e), 0
        finally:
            conn.close()

def delete_all_persons(unit_id: Optional[int] = None) -> tuple[bool, str]:
    unit_id = 1 # Hardcoded in original db_base.py
    with _lock:
        conn = get_connection()
        try:
            if unit_id is not None:
                c = conn.cursor()
                c.execute("SELECT id FROM participants WHERE unit_id = ?", (unit_id,))
                p_ids = [r['id'] for r in c.fetchall()]
                if p_ids:
                    id_list = ",".join(map(str, p_ids))
                    conn.execute(f"DELETE FROM module_history WHERE participant_id IN ({id_list})")
                    conn.execute(f"DELETE FROM person_qs_status WHERE participant_id IN ({id_list})")
                    conn.execute("DELETE FROM participants WHERE unit_id = ?", (unit_id,))
            else:
                conn.execute("DELETE FROM module_history")
                conn.execute("DELETE FROM person_qs_status")
                conn.execute("DELETE FROM participants WHERE unit_id IS NULL")
            conn.commit()
            st.cache_data.clear()
            return True, ""
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            conn.close()

def save_upload_data(filename: str, processed_data: List[Dict[str, Any]], progress_callback: Optional[Callable[[float], None]] = None, unit_id: Optional[int] = None):
    unit_id = 1 # Hardcoded in original db_base.py
    logger.info(f"Starting save_upload_data for '{filename}' with {len(processed_data)} records.")
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO uploads (filename) VALUES (?)", (filename,))
            upload_id = cursor.lastrowid
            
            if unit_id is not None:
                cursor.execute("SELECT id, name, birthday FROM participants WHERE unit_id = ?", (unit_id,))
            else:
                cursor.execute("SELECT id, name, birthday FROM participants WHERE unit_id IS NULL")
            all_db_parts = cursor.fetchall()
            
            db_persons_by_key = {(r['name'], r['birthday']): r['id'] for r in all_db_parts}
            db_unknowns_by_name = {r['name']: r['id'] for r in all_db_parts if r['birthday'] == 'Unknown'}
            
            new_participants_to_insert = {}
            participants_to_update = {}
            
            for row in processed_data:
                full_name = row.get('person_name', 'Unknown')
                name = full_name.split(',')[0].strip() if full_name else 'Unknown'
                birthday = row.get('person_birthday', 'Unknown')
                
                if name == 'Unknown' or not name:
                    continue
                
                key = (name, birthday)
                if key in db_persons_by_key:
                    continue
                    
                if birthday != 'Unknown' and name in db_unknowns_by_name:
                    participants_to_update[key] = {
                        'id': db_unknowns_by_name[name],
                        'birthday': birthday,
                        'metadata': full_name
                    }
                    db_persons_by_key[key] = db_unknowns_by_name[name]
                    del db_unknowns_by_name[name]
                    continue
                
                if birthday == 'Unknown':
                    continue
                    
                if key not in new_participants_to_insert:
                    new_participants_to_insert[key] = {
                        'name': name,
                        'birthday': birthday,
                        'metadata': full_name
                    }
            
            for key, data in participants_to_update.items():
                cursor.execute("UPDATE participants SET birthday = ?, metadata = ? WHERE id = ?", (data['birthday'], data['metadata'], data['id']))
            for key, data in new_participants_to_insert.items():
                cursor.execute("INSERT INTO participants (name, birthday, metadata, unit_id) VALUES (?, ?, ?, ?)", (data['name'], data['birthday'], data['metadata'], unit_id))
                
            if unit_id is not None:
                cursor.execute("SELECT id, name, birthday FROM participants WHERE unit_id = ?", (unit_id,))
            else:
                cursor.execute("SELECT id, name, birthday FROM participants WHERE unit_id IS NULL")
            all_db_parts = cursor.fetchall()
            
            db_persons_by_key = {(r['name'], r['birthday']): r['id'] for r in all_db_parts}
            fallback_name_map = {}
            for r in all_db_parts:
                if r['name'] not in fallback_name_map or r['birthday'] != 'Unknown':
                    fallback_name_map[r['name']] = r['id']
                
            history_data = []
            modules_to_insert = {}

            for row in processed_data:
                full_name = row.get('person_name', 'Unknown')
                name = full_name.split(',')[0].strip() if full_name else 'Unknown'
                birthday = row.get('person_birthday', 'Unknown')
                
                if name == 'Unknown' or not name:
                    continue
                    
                key = (name, birthday)
                p_id = db_persons_by_key.get(key)
                if not p_id and birthday == 'Unknown':
                    p_id = fallback_name_map.get(name)
                    
                if not p_id:
                    continue
                
                mod_id = row.get('id')
                if mod_id and mod_id not in modules_to_insert:
                    modules_to_insert[mod_id] = (mod_id, row.get('title'), row.get('qs_level'), row.get('T_Soll', 0.0), row.get('P_Soll', 0.0), row.get('K_Soll', 0.0))
                
                history_data.append((p_id, upload_id, mod_id, row.get('status'), row.get('T_Ist', 0.0), row.get('P_Ist', 0.0), row.get('K_Ist', 0.0)))
            
            if modules_to_insert:
                cursor.executemany("INSERT OR IGNORE INTO modules (id, title, qs_level, T_Soll, P_Soll, K_Soll) VALUES (?, ?, ?, ?, ?, ?)", list(modules_to_insert.values()))
                
            cursor.executemany("INSERT INTO module_history (participant_id, upload_id, module_id, status, T_Ist, P_Ist, K_Ist) VALUES (?, ?, ?, ?, ?, ?, ?)", history_data)
            
            if unit_id is not None:
                p_ids = list(set([h[0] for h in history_data if h[0] is not None]))
                if p_ids:
                    id_list = ",".join(map(str, p_ids))
                    cursor.execute(f"UPDATE OR IGNORE participants SET unit_id = ?, last_seen = CURRENT_DATE WHERE id IN ({id_list})", (unit_id,))
            
            conn.commit()
            st.cache_data.clear()
            logger.info(f"Successfully saved upload data for '{filename}'.")
        except Exception as e:
            logger.error(f"Error saving upload data for '{filename}': {e}")
            conn.rollback()
            raise
        finally:
            conn.close()

@st.cache_data
def get_latest_upload_data_cached(unit_id: Optional[int] = None) -> Optional[List[Dict[str, Any]]]:
    unit_id = 1 # Hardcoded in original db_base.py
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            if unit_id is not None:
                cursor.execute("""
                    SELECT mh.participant_id, MAX(mh.upload_id) as latest_upload_id
                    FROM module_history mh
                    JOIN participants p ON mh.participant_id = p.id
                    WHERE p.unit_id = ?
                    GROUP BY mh.participant_id
                """, (unit_id,))
            else:
                cursor.execute("""
                    SELECT mh.participant_id, MAX(mh.upload_id) as latest_upload_id
                    FROM module_history mh
                    JOIN participants p ON mh.participant_id = p.id
                    WHERE p.unit_id IS NULL
                    GROUP BY mh.participant_id
                """)
            
            person_latest = cursor.fetchall()
            if not person_latest:
                return None
            
            conditions = " OR ".join(f"(mh.participant_id = {r['participant_id']} AND mh.upload_id = {r['latest_upload_id']})" for r in person_latest)
            
            query = f"""
                SELECT p.name as person_name, p.birthday as birthday, p.metadata as metadata, p.unit_id as unit_id,
                    mh.module_id as id, m.title, mh.status, m.qs_level, mh.T_Ist, m.T_Soll, mh.P_Ist, m.P_Soll, mh.K_Ist, m.K_Soll,
                    COALESCE(qs.qs1_done, 0) as meta_qs1_done, COALESCE(qs.qs2_done, 0) as meta_qs2_done, COALESCE(qs.qs3_done, 0) as meta_qs3_done
                FROM module_history mh
                JOIN modules m ON mh.module_id = m.id
                JOIN participants p ON mh.participant_id = p.id
                LEFT JOIN person_qs_status qs ON p.id = qs.participant_id
                WHERE ({conditions})
            """
            cursor.execute(query)
            records = cursor.fetchall()
            
            return [{
                "person_name": r["metadata"] if r["metadata"] else f"{r['person_name']}, geb. {r['birthday']}",
                "id": r["id"], "title": r["title"], "status": r["status"], "qs_level": r["qs_level"],
                "T_Ist": r["T_Ist"], "T_Soll": r["T_Soll"], "P_Ist": r["P_Ist"], "P_Soll": r["P_Soll"], "K_Ist": r["K_Ist"], "K_Soll": r["K_Soll"],
                "meta_qs1_done": bool(r["meta_qs1_done"]), "meta_qs2_done": bool(r["meta_qs2_done"]), "meta_qs3_done": bool(r["meta_qs3_done"])
            } for r in records]
        finally:
            conn.close()

@st.cache_data
def get_person_history(name: str, birthday: str, unit_id: Optional[int] = None) -> List[Dict[str, Any]]:
    unit_id = 1 # Hardcoded
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            query = """
                SELECT mh.upload_id, mh.module_id, m.title, mh.status, m.qs_level, u.upload_date, mh.T_Ist
                FROM module_history mh
                JOIN modules m ON mh.module_id = m.id
                JOIN participants p ON mh.participant_id = p.id
                JOIN uploads u ON mh.upload_id = u.id
                WHERE p.name = ? AND p.birthday = ?
            """
            params = [name, birthday]
            if unit_id is not None:
                query += " AND p.unit_id = ?"
                params.append(unit_id)
            query += " ORDER BY u.upload_date DESC"
            cursor.execute(query, params)
            return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

def update_person_qs_status(name: str, birthday: str, qs1: bool, qs2: bool, qs3: bool, unit_id: Optional[int] = None):
    unit_id = 1 # Hardcoded
    with _lock:
        conn = get_connection()
        try:
            c = conn.cursor()
            if unit_id is not None:
                c.execute("SELECT id FROM participants WHERE name = ? AND birthday = ? AND unit_id = ?", (name, birthday, unit_id))
            else:
                c.execute("SELECT id FROM participants WHERE name = ? AND birthday = ? AND unit_id IS NULL", (name, birthday))
            
            row = c.fetchone()
            if row:
                p_id = row['id']
                c.execute("INSERT INTO person_qs_status (participant_id, qs1_done, qs2_done, qs3_done) VALUES (?, ?, ?, ?) ON CONFLICT(participant_id) DO UPDATE SET qs1_done=excluded.qs1_done, qs2_done=excluded.qs2_done, qs3_done=excluded.qs3_done", (p_id, int(qs1), int(qs2), int(qs3)))
                conn.commit()
                st.cache_data.clear()
        finally:
            conn.close()

@st.cache_data
def get_person_qs_status_cached(name: str, birthday: str, unit_id: Optional[int] = None) -> Dict[str, bool]:
    unit_id = 1 # Hardcoded
    with _lock:
        conn = get_connection()
        try:
            c = conn.cursor()
            query = "SELECT qs.qs1_done, qs.qs2_done, qs.qs3_done FROM person_qs_status qs JOIN participants p ON qs.participant_id = p.id WHERE p.name = ? AND p.birthday = ?"
            params = [name, birthday]
            if unit_id is not None:
                query += " AND p.unit_id = ?"
                params.append(unit_id)
            c.execute(query, params)
            row = c.fetchone()
            if row: return {'qs1_done': bool(row['qs1_done']), 'qs2_done': bool(row['qs2_done']), 'qs3_done': bool(row['qs3_done'])}
            return {'qs1_done': False, 'qs2_done': False, 'qs3_done': False}
        finally:
            conn.close()

@st.cache_data
def get_all_person_qs_status_cached(unit_id: Optional[int] = None) -> Dict[tuple, Dict[str, bool]]:
    unit_id = 1 # Hardcoded
    with _lock:
        conn = get_connection()
        try:
            c = conn.cursor()
            query = "SELECT p.name, p.birthday, qs.qs1_done, qs.qs2_done, qs.qs3_done FROM person_qs_status qs JOIN participants p ON qs.participant_id = p.id"
            params = []
            if unit_id is not None:
                query += " WHERE p.unit_id = ?"
                params.append(unit_id)
            c.execute(query, params)
            res = {}
            for row in c.fetchall():
                res[(row['name'], row['birthday'])] = {'qs1_done': bool(row['qs1_done']), 'qs2_done': bool(row['qs2_done']), 'qs3_done': bool(row['qs3_done'])}
            return res
        finally:
            conn.close()

def get_person_data_public(name: str, birthday: str) -> Optional[Dict[str, Any]]:
    """
    Fetches all training data for a person, returning a structure 
    compatible with the MGLA_Dashboard public view.
    """
    logger.info(f"Public lookup for: '{name}' | '{birthday}'")
    with _lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            # 1. Look for participant - use broad LIKE to avoid whitespace/case issues
            query = "SELECT id, name, birthday, metadata FROM participants WHERE (name LIKE ? OR metadata LIKE ?) AND (birthday LIKE ? OR metadata LIKE ?)"
            cursor.execute(query, (f"%{name.strip()}%", f"%{name.strip()}%", f"%{birthday.strip()}%", f"%{birthday.strip()}%"))
            all_matches = cursor.fetchall()
                
            if not all_matches:
                logger.warning(f"No participant found for '{name}' and '{birthday}'")
                return None
            
            # Find the match with module history
            target_match = None
            target_rows = None
            
            for match in all_matches:
                p_id = match['id']
                logger.debug(f"Checking module history for match candidate ID {p_id} ({match['name']})")
                
                # 2. Get the latest status for EACH module this person has ever had
                query = """
                    SELECT mh.module_id, m.title, mh.status, m.qs_level, 
                           mh.T_Ist, m.T_Soll, mh.P_Ist, m.P_Soll, mh.K_Ist, m.K_Soll
                    FROM module_history mh
                    JOIN modules m ON mh.module_id = m.id
                    JOIN (
                        SELECT module_id, MAX(upload_id) as latest_upload
                        FROM module_history
                        WHERE participant_id = ?
                        GROUP BY module_id
                    ) latest ON mh.module_id = latest.module_id AND mh.upload_id = latest.latest_upload
                    WHERE mh.participant_id = ?
                """
                cursor.execute(query, (p_id, p_id))
                rows = cursor.fetchall()
                
                if rows:
                    target_match = match
                    target_rows = rows
                    logger.info(f"Found participant ID {p_id} with {len(rows)} modules for {name}")
                    break
            
            if not target_match:
                logger.warning(f"Found {len(all_matches)} participant records for {name}, but none have module history.")
                return None
            
            p_id = target_match['id']
            person = target_match
            rows = target_rows
                
            # 3. Get QS status
            cursor.execute("SELECT qs1_done, qs2_done, qs3_done FROM person_qs_status WHERE participant_id = ?", (p_id,))
            qs_row = cursor.fetchone()
            qs_status = {
                'qs1_done': bool(qs_row['qs1_done']) if qs_row else False,
                'qs2_done': bool(qs_row['qs2_done']) if qs_row else False,
                'qs3_done': bool(qs_row['qs3_done']) if qs_row else False
            }
            
            # 4. Construct Response with expected keys for Dashboard
            modules = []
            for r in rows:
                modules.append({
                    'id': r['module_id'],
                    'module_name': r['title'],
                    'status': r['status'],
                    'qs_level': r['qs_level'],
                    'hours_t': r['T_Ist'],
                    'hours_p': r['P_Ist'],
                    'hours_k': r['K_Ist'],
                    'hours_t_soll': r['T_Soll'],
                    'hours_p_soll': r['P_Soll'],
                    'hours_k_soll': r['K_Soll']
                })
                
            return {
                'person': {
                    'name': person['name'],
                    'birthday': person['birthday'],
                    'id': p_id,
                    'metadata': person['metadata']
                },
                'modules': modules,
                'qs_status': qs_status
            }
        finally:
            conn.close()

def get_stundennachweis_zeitraum(unit_id: int) -> Optional[str]:
    with _lock:
        conn = get_connection()
        try:
            c = conn.cursor()
            c.execute("SELECT letzter_zeitraum FROM stundennachweis_config WHERE unit_id = ?", (unit_id,))
            row = c.fetchone()
            return row['letzter_zeitraum'] if row else None
        finally:
            conn.close()

def update_stundennachweis_zeitraum(unit_id: int, zeitraum: str) -> None:
    with _lock:
        conn = get_connection()
        try:
            conn.execute("INSERT INTO stundennachweis_config (unit_id, letzter_zeitraum) VALUES (?, ?) ON CONFLICT(unit_id) DO UPDATE SET letzter_zeitraum=excluded.letzter_zeitraum, last_updated=CURRENT_TIMESTAMP", (unit_id, zeitraum))
            conn.commit()
            st.cache_data.clear()
        finally:
            conn.close()

def update_participant_hours(unit_id: int, name: str, birthday: str, einsatzstunden: float, dienststunden: float) -> bool:
    with _lock:
        conn = get_connection()
        try:
            c = conn.cursor()
            c.execute("UPDATE participants SET einsatzstunden = ?, dienststunden = ?, updated_at = CURRENT_TIMESTAMP, last_seen = CURRENT_DATE WHERE unit_id = ? AND name = ? AND birthday = ?", (einsatzstunden, dienststunden, unit_id, name, birthday))
            conn.commit()
            st.cache_data.clear()
            return c.rowcount > 0
        finally:
            conn.close()

def update_person_hours(participant_id: int, einsatz: float, dienst: float) -> Tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            conn.execute("UPDATE participants SET einsatzstunden = ?, dienststunden = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (einsatz, dienst, participant_id))
            conn.commit()
            st.cache_data.clear()
            return True, ""
        except Exception as e: return False, str(e)
        finally:
            conn.close()

def touch_participant(participant_id: int) -> Tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            conn.execute("UPDATE participants SET last_seen = CURRENT_DATE WHERE id = ?", (participant_id,))
            conn.commit()
            st.cache_data.clear()
            return True, ""
        except Exception as e: return False, str(e)
        finally:
            conn.close()

def touch_participant_by_name(name: str, birthday: str) -> Tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            conn.execute("UPDATE participants SET last_seen = CURRENT_DATE WHERE name = ? AND birthday = ?", (name, birthday))
            conn.commit()
            st.cache_data.clear()
            return True, ""
        except Exception as e: return False, str(e)
        finally:
            conn.close()

def delete_expired_participants(days: int = 360) -> Tuple[int, str]:
    with _lock:
        conn = get_connection()
        try:
            c = conn.cursor()
            c.execute("DELETE FROM participants WHERE last_seen IS NOT NULL AND (julianday('now') - julianday(last_seen)) > ?", (days,))
            deleted_count = c.rowcount
            conn.commit()
            st.cache_data.clear()
            return deleted_count, ""
        except Exception as e: return 0, str(e)
        finally:
            conn.close()

def update_qs_level(participant_id: int, qs_level: str) -> Tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            qs1 = 1 if qs_level in ["QS1", "QS2", "QS3"] else 0
            qs2 = 1 if qs_level in ["QS2", "QS3"] else 0
            qs3 = 1 if qs_level == "QS3" else 0
            conn.execute("INSERT INTO person_qs_status (participant_id, qs1_done, qs2_done, qs3_done) VALUES (?, ?, ?, ?) ON CONFLICT(participant_id) DO UPDATE SET qs1_done=excluded.qs1_done, qs2_done=excluded.qs2_done, qs3_done=excluded.qs3_done", (participant_id, qs1, qs2, qs3))
            conn.commit()
            st.cache_data.clear()
            return True, ""
        except Exception as e: return False, str(e)
        finally:
            conn.close()

def delete_participant(participant_id: int) -> Tuple[bool, str]:
    with _lock:
        conn = get_connection()
        try:
            conn.execute("DELETE FROM participants WHERE id=?", (participant_id,))
            conn.commit()
            st.cache_data.clear()
            return True, ""
        except Exception as e: return False, str(e)
        finally:
            conn.close()
