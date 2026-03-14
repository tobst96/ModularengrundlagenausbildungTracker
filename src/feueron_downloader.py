"""
FeuerOn Auto-Downloader
=======================
Loggt sich auf feueron.de ein und lädt die Ausbildungsmodul-PDF
direkt via API herunter (kein Browser-Klicken nötig).

Aufruf: python src/feueron_downloader.py <unit_id>
"""

import io
import logging
import os
import re
import sys
from datetime import datetime
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger("TrainingTracker")

FEUERON_BASE_URL = "https://www.feueron.de/feueron"
LOGIN_URL = f"{FEUERON_BASE_URL}/"
API_REPORTS_URL = f"{FEUERON_BASE_URL}/api/person-reports"
# QS-Stufen IDs (alle):
ALL_QS_STUFEN = ["1", "2", "3", "7", "5", "4"]


def _get_db_config(unit_id: int) -> Optional[dict]:
    unit_id = 1
    from src.database import get_connection
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM feueron_sync_config WHERE unit_id = ?", (unit_id,))
        row = c.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _update_sync_status(unit_id: int, status: str, message: str = ""):
    unit_id = 1
    from src.database import get_connection
    conn = get_connection()
    try:
        now = datetime.now().isoformat()
        conn.execute(
            "UPDATE feueron_sync_config SET last_sync_at=?, last_sync_status=?, last_sync_message=? WHERE unit_id=?",
            (now, status, message[:2000], unit_id)
        )
        conn.commit()
    finally:
        conn.close()


def run_download(unit_id: int = 1) -> tuple:
    unit_id = 1
    """
    Hauptfunktion: Login via Playwright, dann PDF via direktem API-Call herunterladen.
    Gibt (success: bool, message: str) zurück.
    """
    logger.info(f"[FeuerOn] Starte Auto-Download für Einheit {unit_id}")
    _update_sync_status(unit_id, "running", "Verbindung wird aufgebaut...")

    config = _get_db_config(unit_id)
    if not config:
        msg = f"Keine FeuerOn-Zugangsdaten für Einheit {unit_id} konfiguriert."
        logger.error(f"[FeuerOn] {msg}")
        _update_sync_status(unit_id, "error", msg)
        return False, msg

    org = config.get("feueron_org", "")
    username = config.get("feueron_username", "")
    password = config.get("feueron_password", "")
    org_id = str(config.get("feueron_org_id", "")).strip()

    if not username or not password:
        msg = "Benutzername oder Passwort fehlt."
        _update_sync_status(unit_id, "error", msg)
        return False, msg

    if not org_id:
        msg = "Organisations-ID fehlt. Bitte in den Einstellungen eintragen."
        _update_sync_status(unit_id, "error", msg)
        return False, msg

    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
        import json

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            context = browser.new_context(
                accept_downloads=True,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = context.new_page()

            # --- SCHRITT 1: Login ---
            logger.info("[FeuerOn] Führe Login durch...")
            _update_sync_status(unit_id, "running", "Login wird durchgeführt...")
            page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)

            import time
            
            # 1. User & Pass eintragen (macht manchmal auch Dropdowns zu)
            page.fill("input[name='zmsLoginName']", username)
            page.fill("input[name='zmsLoginPassword']", password)

            # 2. Organisation auswählen (via Tastatur für maximale Kompatibilität)
            if org:
                try:
                    # Dropdown öffnen
                    page.click(".jqx-dropdownlist", timeout=5000)
                    time.sleep(0.5)
                    # Den Text tippen, was im JQX Dropdown meistens zum richtigen Item springt
                    page.keyboard.type(org[:5]) 
                    time.sleep(0.5)
                    page.keyboard.press("Enter")
                    time.sleep(0.5)
                except Exception as e:
                    logger.warning(f"[FeuerOn] Org-Tastaturauswahl fehlgeschlagen: {e}")

            # 3. Klick außerhalb um alles zu schließen
            page.mouse.click(0, 0)
            time.sleep(0.5)
            
            # 4. Formulardaten absenden (Login Button Click ODER Enter-Taste im Passwort-Feld)
            try:
                page.focus("input[name='zmsLoginPassword']")
                page.keyboard.press("Enter")
                time.sleep(0.5)
                # Fallback: Button Click
                if page.locator("#loginButton").is_visible():
                    page.evaluate("document.getElementById('loginButton').click()")
            except Exception as e:
                logger.warning(f"[FeuerOn] Login btn error: {e}")


            import time
            # Warte auf Navigation nach Login
            try:
                page.wait_for_url(lambda url: '/feueron/' in url and 'profile' in url, timeout=15000)
            except PWTimeout:
                # Ggf. ist der Login fehlgeschlagen
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=5000)
                except Exception:
                    pass

            time.sleep(1)  # Kurz warten bis Seite fertig geladen

            # Login prüfen: wenn immer noch auf Login-Seite
            current_url = page.url
            try:
                page_html = page.content()
                if 'zmsLoginName' in page_html or ('loginButton' in page_html and 'profile' not in current_url):
                    msg = "Login fehlgeschlagen – Zugangsdaten oder Organisation prüfen."
                    logger.error(f"[FeuerOn] {msg}")
                    _update_sync_status(unit_id, "error", msg)
                    browser.close()
                    return False, msg
            except Exception:
                # Wenn wir den Content nicht lesen können aber URL geändert hat = OK
                if LOGIN_URL in current_url or current_url.endswith('/feueron/'):
                    msg = "Login fehlgeschlagen – URL unverändert."
                    _update_sync_status(unit_id, "error", msg)
                    browser.close()
                    return False, msg

            logger.info(f"[FeuerOn] Login OK. URL: {page.url}")
            _update_sync_status(unit_id, "running", "Erstelle PDF-Report...")

            # --- SCHRITT 2: Sicherstellen, dass die Session gültig ist & CSRF-Token aus dem HTML holen ---
            # Navigiere IMMER zur Personenverwaltung, da nur dort der API Call 100% erlaubt ist bzgl. CSRF Referer
            try:
                logger.info("[FeuerOn] Navigiere zur Personenverwaltung für API Session...")
                page.goto(f"{FEUERON_BASE_URL}/personalverwaltung.do#/personalverwaltung/suche", timeout=15000)
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception as e:
                logger.warning(f"[FeuerOn] Navigation zur Personalverwaltung Timeout: {e}")
                
            
            try:
                # OWASP CSRF Token aus Meta-Tag oder Cookie
                csrf_token = page.evaluate("""
                    () => {
                        const meta = document.querySelector('meta[name="owasp-csrftoken"]');
                        if (meta) return meta.getAttribute('content');
                        // Alternativ aus Cookie
                        const cookies = document.cookie.split(';');
                        for (const c of cookies) {
                            if (c.trim().startsWith('owasp-csrftoken=')) {
                                return c.trim().split('=')[1];
                            }
                        }
                        return '';
                    }
                """)
            except Exception:
                pass

            if not csrf_token:
                # Navigiere kurz zur Personen-Seite um Token zu laden
                try:
                    page.goto(f"{FEUERON_BASE_URL}/personalverwaltung.do", timeout=10000)
                    page.wait_for_load_state("domcontentloaded", timeout=8000)
                    csrf_token = page.evaluate("""
                        () => {
                            const meta = document.querySelector('meta[name="owasp-csrftoken"]');
                            if (meta) return meta.getAttribute('content');
                            return '';
                        }
                    """)
                except Exception as e:
                    logger.warning(f"[FeuerOn] CSRF-Token nicht gefunden: {e}")

            # --- SCHRITT 3: Frisches CSRF-Token holen & PDF via API anfragen ---
            logger.info(f"[FeuerOn] Hole frisches CSRF-Token für API (OrgID: {org_id})...")

            pdf_bytes = None
            pdf_filename = None

            try:
                import time
                import json
                
                # Führe beide API-Schritte (Token-Hol-GET + PDF-POST) direkt im Browser-Kontext aus
                fetch_script = f"""
                    async () => {{
                        try {{
                            // Step 1: Frisches CSRF Token über Dummy-API Request holen
                            const warmUpRes = await fetch('{FEUERON_BASE_URL}/api/context-info', {{
                                headers: {{ 'X-Requested-With': 'XMLHttpRequest' }},
                                credentials: 'include'
                            }});
                            
                            const tokenHeader = warmUpRes.headers.get('owasp-csrftoken');
                            if (!tokenHeader) {{
                                return {{status: warmUpRes.status, is_pdf: false, text: "Fehlendes CSRF Token im Header"}};
                            }}
                            
                            const tokenData = JSON.parse(tokenHeader);
                            const token = Object.values(tokenData.pageTokens)[0];
                            
                            // Step 2: POST /api/person-reports mit dem dynamischen Token
                            const payload = {{
                                "type": "AUSBILDUNGSMODULE",
                                "fileFormat": "PDF",
                                "reportParameters": {{ "qualifikationsstufen": {json.dumps(ALL_QS_STUFEN)} }},
                                "reportSortParameters": [],
                                "filterParameters": {{ "organisationId": "{org_id}", "abteilung": ["Einsatzabteilung FF"] }}
                            }};

                            const resp = await fetch('{API_REPORTS_URL}', {{
                                method: 'POST',
                                credentials: 'include',
                                headers: {{
                                    'Content-Type': 'application/json',
                                    'Accept': 'application/pdf, application/json, */*',
                                    'owasp-csrftoken': token,
                                    'X-Requested-With': 'XMLHttpRequest',
                                    'Origin': 'https://www.feueron.de',
                                    'Referer': 'https://www.feueron.de/feueron/personalverwaltung.do'
                                }},
                                body: JSON.stringify(payload)
                            }});
                            
                            if (!resp.ok) return {{status: resp.status, is_pdf: false, text: await resp.text()}};
                            
                            // Buffer Array lesen
                            const buffer = await resp.arrayBuffer();
                            const bytes = new Uint8Array(buffer);
                            
                            let binary = '';
                            for (let i = 0; i < bytes.byteLength; i++) {{
                                binary += String.fromCharCode(bytes[i]);
                            }}
                            const b64 = btoa(binary);
                            
                            const cd = resp.headers.get('content-disposition');
                            return {{
                                status: resp.status,
                                b64: b64,
                                content_type: resp.headers.get('content-type'),
                                content_disposition: cd,
                                is_pdf: (resp.headers.get('content-type') || '').includes('pdf') || b64.startsWith('JVBEF')
                            }};
                            
                        }} catch (e) {{
                            return {{status: 500, text: e.toString()}};
                        }}
                    }}
                """
                
                logger.info(f"[FeuerOn] Führe API fetch in Browser Context aus...")
                api_res = page.evaluate(fetch_script)
                
                status_code = api_res.get('status')
                logger.info(f"[FeuerOn] API Response Status: {status_code}, Type: {api_res.get('content_type')}")
                
                if status_code in (200, 201):
                    if api_res.get('b64'):
                        import base64
                        pdf_bytes = base64.b64decode(api_res['b64'])
                        
                        cd = api_res.get('content_disposition', '')
                        import re
                        match = re.search(r'filename[^;=\n]*=\s*["\']?([^"\';\n]+)', cd) if cd else None
                        pdf_filename = match.group(1).strip() if match else f"Ausbildungsmodule-{datetime.now().strftime('%Y-%m-%d')}.pdf"
                        logger.info(f"[FeuerOn] PDF in Browser empfangen: {pdf_filename} ({len(pdf_bytes)} Bytes)")
                    else:
                        logger.error("[FeuerOn] Body fehlt in der API Antwort.")
                else:
                    logger.error(f"[FeuerOn] Browser-API-Fehler {status_code}: {api_res.get('text', '')[:200]}")

            except Exception as api_err:
                logger.error(f"[FeuerOn] API-Aufruf Exception: {api_err}")

            browser.close()

            if not pdf_bytes or len(pdf_bytes) < 1000:
                msg = f"PDF konnte nicht über API generiert werden."
                _update_sync_status(unit_id, "error", msg)
                return False, msg

            # --- SCHRITT 4: Importieren ---
            logger.info(f"[FeuerOn] Importiere {pdf_filename} ({len(pdf_bytes)} Bytes)...")
            _update_sync_status(unit_id, "running", f"PDF wird importiert...")

            from src.parser import extract_data_from_pdf
            from src.database import save_upload_data

            # PDF in Datenbank cachen (DB-basiert, Docker-sicher)
            from src.database import save_pdf_cache
            save_pdf_cache(unit_id, pdf_bytes, pdf_filename)
            raw_data = extract_data_from_pdf(io.BytesIO(pdf_bytes))
            
            if not raw_data:
                msg = "PDF enthält keine erkennbaren Ausbildungsmodule."
                logger.warning(f"[FeuerOn] {msg}")
                _update_sync_status(unit_id, "failed", msg)
                return False, msg

            from src.database import save_upload_data
            save_upload_data(
                filename=pdf_filename,
                processed_data=raw_data,
                unit_id=unit_id
            )
            
            # --- NEU: Bulk-Isolierung der Einzel-PDFs für den schnellen Abruf ---
            logger.info("[FeuerOn] Starte Bulk-Zerschneiden der PDF für Zertifikate...")
            _update_sync_status(unit_id, "running", f"Generiere Einzelzertifikate...")
            try:
                from src.parser import extract_all_person_pdfs
                from src.database import save_person_pdf_cache, clear_person_pdf_cache
                
                # Alte Caches dieser Unit leeren
                clear_person_pdf_cache(unit_id)
                
                person_pdfs = extract_all_person_pdfs(io.BytesIO(pdf_bytes))
                for p_name, p_bytes in person_pdfs.items():
                    save_person_pdf_cache(unit_id, p_name, p_bytes)
                logger.info(f"[FeuerOn] {len(person_pdfs)} Einzelzertifikate erfolgreich gespeichert.")
            except Exception as cache_err:
                logger.error(f"[FeuerOn] Fehler beim Cachen der Einzel-PDFs: {cache_err}")
                # Wir lassen den Gesamtvorgang trotzdem erfolgreich abschließen
            
            modules = len(raw_data) if raw_data else 0
            persons = len(set(r.get('person_name') for r in raw_data if r.get('person_name'))) if raw_data else 0
            msg = f"✅ {persons} Personen, {modules} Module importiert ({pdf_filename})"
            logger.info(f"[FeuerOn] {msg}")
            _update_sync_status(unit_id, "success", msg)
            return True, msg

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        msg = f"Unerwarteter Fehler: {e}"
        logger.error(f"[FeuerOn] {msg}\n{tb}")
        _update_sync_status(unit_id, "error", f"{msg}\n{tb[:800]}")
        return False, msg


if __name__ == "__main__":
    import argparse
    from logging.handlers import RotatingFileHandler
    
    # Base logging config
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    
    # Add file handlers
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    os.makedirs(log_dir, exist_ok=True)
    
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    root_logger = logging.getLogger()
    
    # Main log
    file_handler = RotatingFileHandler(os.path.join(log_dir, "app.log"), maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # Error log
    error_handler = RotatingFileHandler(os.path.join(log_dir, "error.log"), maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
    error_handler.setLevel(logging.WARNING)
    error_handler.setFormatter(formatter)
    root_logger.addHandler(error_handler)
    
    parser = argparse.ArgumentParser(description="FeuerOn PDF Auto-Download")
    parser.add_argument("--unit_id", type=int, default=1, help="DB-ID der Einheit")
    args = parser.parse_args()
    ok, message = run_download(args.unit_id)
    print(f"{'OK' if ok else 'FEHLER'}: {message}")
    sys.exit(0 if ok else 1)
