import logging
import sqlite3
from typing import List, Dict, Any, Tuple
from .core import get_connection, _lock

logger = logging.getLogger(__name__)

def merge_duplicate_participants():
    """
    Identifies duplicate participants by Name + Birthday and merges them.
    Consolidates module_history, person_qs_status, and participant_qualifications.
    """
    logger.info("Starting automated participant deduplication...")
    
    with _lock:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            
            # 1. Find potential duplicates (normalized Name + Birthday)
            query = """
                SELECT TRIM(name) as name, TRIM(birthday) as birthday, COUNT(*) as cnt
                FROM participants
                GROUP BY TRIM(name), TRIM(birthday)
                HAVING cnt > 1
            """
            cursor.execute(query)
            duplicates = cursor.fetchall()
            
            if not duplicates:
                logger.info("No duplicates found.")
                return
            
            for dup in duplicates:
                name, bday = dup['name'], dup['birthday']
                logger.info(f"Merging duplicates for: {name} ({bday})")
                
                # Get all IDs for this specific duplicate group (using TRIM for grouping)
                cursor.execute("SELECT id FROM participants WHERE TRIM(name) = ? AND TRIM(birthday) = ? ORDER BY id ASC", (name, bday))
                ids = [r['id'] for r in cursor.fetchall()]
                
                # Decide which ID is "Primary" (the one with the most history)
                id_stats = []
                for p_id in ids:
                    cursor.execute("SELECT COUNT(*) as cnt FROM module_history WHERE participant_id = ?", (p_id,))
                    count = cursor.fetchone()['cnt']
                    id_stats.append((p_id, count))
                
                # Sort by history count descending, then by original ID
                id_stats.sort(key=lambda x: x[1], reverse=True)
                primary_id = id_stats[0][0]
                redundant_ids = [x[0] for x in id_stats[1:]]
                
                logger.info(f"Primary ID: {primary_id}, Redundant IDs: {redundant_ids}")
                
                # 2. Re-assign related data in module_history
                for old_id in redundant_ids:
                    # Update module history
                    # Use INSERT OR IGNORE / UPDATE logic to avoid unique constraints if any
                    # Here we just update the foreign key
                    cursor.execute("UPDATE module_history SET participant_id = ? WHERE participant_id = ?", (primary_id, old_id))
                    
                    # Merge QS status (ensure primary has flags of any duplicate)
                    cursor.execute("SELECT qs1_done, qs2_done, qs3_done FROM person_qs_status WHERE participant_id = ?", (old_id,))
                    old_qs = cursor.fetchone()
                    if old_qs:
                        cursor.execute("SELECT qs1_done, qs2_done, qs3_done FROM person_qs_status WHERE participant_id = ?", (primary_id,))
                        primary_qs = cursor.fetchone()
                        
                        if not primary_qs:
                            # If primary has no entry yet, move the old one
                            cursor.execute("INSERT OR REPLACE INTO person_qs_status (participant_id, qs1_done, qs2_done, qs3_done) VALUES (?, ?, ?, ?)", 
                                           (primary_id, old_qs['qs1_done'], old_qs['qs2_done'], old_qs['qs3_done']))
                        else:
                            # Merge flags (OR logic)
                            n_qs1 = 1 if primary_qs['qs1_done'] or old_qs['qs1_done'] else 0
                            n_qs2 = 1 if primary_qs['qs2_done'] or old_qs['qs2_done'] else 0
                            n_qs3 = 1 if primary_qs['qs3_done'] or old_qs['qs3_done'] else 0
                            cursor.execute("UPDATE person_qs_status SET qs1_done = ?, qs2_done = ?, qs3_done = ? WHERE participant_id = ?",
                                           (n_qs1, n_qs2, n_qs3, primary_id))
                                           
                        # Delete the redundant QS status
                        cursor.execute("DELETE FROM person_qs_status WHERE participant_id = ?", (old_id,))

                    # Re-assign qualifications
                    cursor.execute("UPDATE participant_qualifications SET participant_id = ? WHERE participant_id = ?", (primary_id, old_id))
                    
                    # Delete the duplicate participant record
                    cursor.execute("DELETE FROM participants WHERE id = ?", (old_id,))
            
            conn.commit()
            logger.info("Deduplication completed successfully.")
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Error during deduplication: {e}")
            raise
        finally:
            conn.close()
