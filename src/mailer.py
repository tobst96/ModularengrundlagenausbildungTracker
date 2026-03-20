import smtplib
from email.message import EmailMessage
import logging
from typing import Dict, Any, Tuple

logger = logging.getLogger(__name__)

def send_test_email(config: Dict[str, Any], to_email: str) -> Tuple[bool, str]:
    """
    Versendet eine HTML Test-Email, die eine realistische Einsatz-Zusammenfassung simuliert.
    """
    server = config.get("smtp_server")
    port = config.get("smtp_port", 587)
    user = config.get("smtp_user")
    password = config.get("smtp_password")
    sender = config.get("sender_email")
    
    if not all([server, port, user, password, sender, to_email]):
        return False, "E-Mail Einstelldaten (SMTP, Absender, Empfänger) sind unvollständig."

    try:
        from datetime import datetime
        
        # MOCK DATA for preview
        date_now = datetime.now().strftime("%d.%m.%Y %H:%M")
        subject = "🔥 Test: Einsatz-Zusammenfassung (Vorschau)"
        
        # Mock Reports
        mock_reports = [
            {"v": "15-48-1 (HLF)", "kw": "F_BMA", "sit": "BMA hat ausgelöst, Erkundung läuft.", "cmd": "Max Mustermann"},
            {"v": "15-47-1 (LF)", "kw": "F_BMA", "sit": "Bereitstellung am Hydranten.", "cmd": "Max Mustermann"}
        ]
        
        # Mock Personnel
        mock_personnel = [
            {"n": "Max Mustermann", "v": "15-48-1, 15-47-1", "gf": True, "ma": False},
            {"n": "Erika Musterfrau", "v": "15-48-1", "gf": False, "ma": True},
            {"n": "Hans Schmidt", "v": "15-47-1", "gf": False, "ma": False}
        ]

        html_style = """
            <style>
                body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; }
                .container { max-width: 800px; margin: 0 auto; background-color: #f9f9f9; padding: 20px; border-radius: 8px; }
                .header { background-color: #FFA633; color: white; padding: 15px; border-radius: 8px 8px 0 0; text-align: center; }
                .card { background: white; margin-bottom: 20px; padding: 15px; border-left: 5px solid #FFA633; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
                .footer { font-size: 0.8em; color: #777; text-align: center; margin-top: 30px; }
                table { width: 100%; border-collapse: collapse; margin-top: 15px; }
                th { background-color: #F6F6F6; text-align: left; padding: 10px; border-bottom: 2px solid #ddd; }
                td { padding: 10px; border-bottom: 1px solid #eee; }
            </style>
        """
        
        html_reports = ""
        for r in mock_reports:
            html_reports += f"""
            <div class="card">
                <h3 style="margin-top:0;">🚒 {r['v']} | {r['kw']}</h3>
                <p><strong>Einsatzleiter:</strong> {r['cmd']}</p>
                <p><strong>Lage:</strong> {r['sit']}</p>
            </div>
            """
            
        html_personnel = "<table><tr><th>Name</th><th>Fahrzeug(e)</th><th style='text-align:center;'>GF</th><th style='text-align:center;'>MA</th></tr>"
        for p in mock_personnel:
            gf = "✅" if p['gf'] else "-"
            ma = "✅" if p['ma'] else "-"
            html_personnel += f"<tr><td>{p['n']}</td><td>{p['v']}</td><td style='text-align:center;'>{gf}</td><td style='text-align:center;'>{ma}</td></tr>"
        html_personnel += "</table>"
        
        full_html = f"""
        <html>
        <head>{html_style}</head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🚒 Einsatz-Vorschau (Test)</h1>
                    <p>Simulierte Zusammenfassung vom {date_now}</p>
                </div>
                <p>Hallo! Dies ist eine <strong>Vorschau</strong>, wie deine Einsatzberichte zukünftig per E-Mail aussehen werden:</p>
                {html_reports}
                <h2 style="border-bottom: 2px solid #FFA633; padding-bottom: 5px;">👨‍🚒 Personal-Übersicht (Beispiel)</h2>
                {html_personnel}
                <div class="footer">
                    <p>Dies ist eine Test-E-Mail von deinem Training-Tracker zur Validierung des Designs.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = to_email
        msg.set_content("Dies ist die Text-Version der Einsatz-Vorschau. Dein Client unterstützt scheinbar kein HTML.")
        msg.add_alternative(full_html, subtype='html')

        logger.info(f"Sending mock HTML preview to {to_email}")
        with smtplib.SMTP(str(server), int(port), timeout=10) as smtp:
            smtp.starttls()
            smtp.login(str(user), str(password))
            smtp.send_message(msg)
            
        return True, "Schöne Vorschau-E-Mail wurde versandt! Prüfe dein Postfach."
    except Exception as e:
        logger.error(f"Failed to send test email: {e}")
        return False, str(e)


def send_incident_report_summary(config: Dict[str, Any], reports: list) -> Tuple[bool, str]:
    """
    Versendet eine E-Mail-Zusammenfassung über neue Einsatzberichte an die eingestellten Empfänger.
    Verwendet ein modernes HTML-Design und aggregiert das Personal.
    """
    if not reports:
        return True, "Keine Berichte zum Versenden."
        
    server = config.get("smtp_server")
    port = config.get("smtp_port", 587)
    user = config.get("smtp_user")
    password = config.get("smtp_password")
    sender = config.get("sender_email")
    recipients_raw = config.get("recipient_emails", "")
    
    if not all([server, port, user, password, sender, recipients_raw]):
        logger.warning("SMTP konfiguration für Einsatzberichte ist unvollständig. Überspringe E-Mail Versand.")
        return False, "E-Mail Einstelldaten unvollständig."

    # Parse recipients
    recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]
    if not recipients:
        return False, "Keine validen Empfänger-Adressen konfiguriert."

    try:
        import json
        from datetime import datetime
        
        # 1. Personal aggregieren und sortieren
        # Datenstruktur: { person_name: { "vehicles": [], "is_gf": set(), "is_ma": set() } }
        personnel_map = {}
        
        def add_person(name, vehicle, role, is_vab=False, agt_min=0):
            if not name or name == "- Niemand -" or name is True: return
            name_str = str(name).strip()
            if not name_str: return
            
            if name_str not in personnel_map:
                personnel_map[name_str] = {"vehicles": set(), "is_gf": False, "is_ma": False, "is_vab": False, "agt_min": 0}
            
            p_data = personnel_map[name_str]
            p_data["vehicles"].add(str(vehicle))
                
            if role == "GF": p_data["is_gf"] = True
            if role == "MA": p_data["is_ma"] = True
            if is_vab: p_data["is_vab"] = True
            
            try:
                p_data["agt_min"] += int(agt_min or 0)
            except:
                pass

        for r in reports:
            v_name = str(r.get('vehicle_name', 'Unbekannt'))
            # Crew auslesen
            crew = {}
            try:
                crew_raw = r.get('crew_json', '{}')
                if isinstance(crew_raw, str):
                    try:
                        crew = json.loads(crew_raw)
                    except json.JSONDecodeError:
                        # Fallback for NaN values in JSON (common with pandas)
                        fixed_raw = crew_raw.replace('NaN', 'null').replace('nan', 'null')
                        crew = json.loads(fixed_raw)
                else:
                    crew = crew_raw or {}
                    
                # VAB & AGT für Führungskräfte aus crew_json lesen
                cmd_vab = bool(crew.get("commander_vab", False))
                cmd_agt = int(crew.get("commander_agt", 0) or 0)
                ldr_vab = bool(crew.get("unit_leader_vab", False))
                ldr_agt = int(crew.get("unit_leader_agt", 0) or 0)
                
                for seat, p_data in crew.items():
                    if seat in ["commander_vab", "unit_leader_vab", "commander_agt", "unit_leader_agt"]: continue
                    
                    if isinstance(p_data, dict):
                        p_name = p_data.get("name")
                        vab = bool(p_data.get("vab", False))
                        agt = int(p_data.get("agt", 0) or 0)
                    else:
                        p_name = p_data
                        vab = False
                        agt = 0
                        
                    role = None
                    if seat == "seat_1": role = "GF"
                    elif seat == "seat_2": role = "MA"
                    add_person(p_name, v_name, role, vab, agt)
            except Exception as e:
                logger.debug(f"Error parsing crew_json for report {r.get('id')}: {e}")
                cmd_vab, cmd_agt, ldr_vab, ldr_agt = False, 0, False, 0
            
            # Führungskräfte (Commander/Leader) falls nicht in Crew
            add_person(r.get('commander_name'), v_name, "EL", cmd_vab, cmd_agt)
            add_person(r.get('unit_leader_name'), v_name, "EF", ldr_vab, ldr_agt)

        # Sortieren nach Nachname (letztes Wort im String)
        sorted_names = sorted(personnel_map.keys(), key=lambda n: str(n).split()[-1] if n and str(n).split() else "")
        
        # 2. HTML Body bauen
        num_reports = len(reports)
        date_now = datetime.now().strftime("%d.%m.%Y %H:%M")
        
        # Gruppierung der Berichte nach Einsatz (Incident)
        incidents_grouped = {}
        for r in reports:
            inc_id = r.get('incident_id') or "unassigned"
            if inc_id not in incidents_grouped:
                incidents_grouped[inc_id] = []
            incidents_grouped[inc_id].append(r)
            
        subject = f"🚨 Einsatz-Zusammenfassung ({len(incidents_grouped)} Einsätze)"
        if len(incidents_grouped) == 1 and "unassigned" not in incidents_grouped:
            first_r = incidents_grouped[list(incidents_grouped.keys())[0]][0]
            subject = f"🚨 Einsatzbericht: {first_r.get('keyword', 'Unbekannt')}"
        
        html_reports = ""
        for inc_id, inc_reports in incidents_grouped.items():
            # Header für den Einsatz (falls es mehrere Berichte gibt)
            first_r = inc_reports[0]
            inc_kw = first_r.get('keyword', 'Unbekannt')
            
            html_reports += f"""
            <div style="background-color: #eee; padding: 10px; border-radius: 5px; margin-bottom: 10px; border-left: 5px solid #FFA633;">
                <h2 style="margin:0; font-size: 1.2em;">🚩 Einsatz: {inc_kw}</h2>
            </div>
            """
            
            for r in inc_reports:
                v_name = r.get('vehicle_name', 'Unbekannt')
                sit = r.get('situation', '')
                act = r.get('actions', '')
                cmd = r.get('commander_name', '-')
                
                html_reports += f"""
                <div class="card" style="margin-left: 15px;">
                    <h3 style="margin-top:0;">🚒 {v_name}</h3>
                    <p style="margin: 5px 0;"><strong>EL:</strong> {cmd} | <strong>Stichwort:</strong> {inc_kw}</p>
                    <p style="margin: 5px 0; font-style: italic;">{sit[:300]}{"..." if len(sit) > 300 else ""}</p>
                    <p style="margin: 5px 0; border-top: 1px dashed #ddd; padding-top: 5px;">{act[:500]}{"..." if len(act) > 500 else ""}</p>
                </div>
                """
            
        # HTML Template
        html_style = """
            <style>
                body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; }
                .container { max-width: 800px; margin: 0 auto; background-color: #f9f9f9; padding: 20px; border-radius: 8px; }
                .header { background-color: #FFA633; color: white; padding: 15px; border-radius: 8px 8px 0 0; text-align: center; }
                .card { background: white; margin-bottom: 20px; padding: 15px; border-left: 5px solid #FFA633; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
                .footer { font-size: 0.8em; color: #777; text-align: center; margin-top: 30px; }
                table { width: 100%; border-collapse: collapse; margin-top: 15px; }
                th { background-color: #F6F6F6; text-align: left; padding: 10px; border-bottom: 2px solid #ddd; }
                td { padding: 10px; border-bottom: 1px solid #eee; }
                .badge { background: #eee; padding: 2px 6px; border-radius: 4px; font-size: 0.85em; }
            </style>
        """
        
        html_personnel = "<table><tr><th>Name</th><th>Fahrzeug(e)</th><th style='text-align:center;'>GF</th><th style='text-align:center;'>MA</th><th style='text-align:center;'>VAB</th><th style='text-align:center;'>AGT</th></tr>"
        for name in sorted_names:
            p_data = personnel_map[name]
            v_set = p_data["vehicles"]
            v_str = ", ".join(v_set) if isinstance(v_set, set) else str(v_set)
            gf_check = "✅" if p_data["is_gf"] else "-"
            ma_check = "✅" if p_data["is_ma"] else "-"
            vab_check = "✅" if p_data.get("is_vab") else "-"
            agt_val = str(p_data.get("agt_min", 0)) + " Min" if p_data.get("agt_min", 0) > 0 else "-"
            html_personnel += f"<tr><td>{name}</td><td>{v_str}</td><td style='text-align:center;'>{gf_check}</td><td style='text-align:center;'>{ma_check}</td><td style='text-align:center;'>{vab_check}</td><td style='text-align:center;'>{agt_val}</td></tr>"
        html_personnel += "</table>"
        
        full_html = f"""
        <html>
        <head>{html_style}</head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🚒 Neue Einsatzberichte</h1>
                    <p>Zusammenfassung vom {date_now}</p>
                </div>
                
                <p>Hallo zusammen,<br>es wurden <strong>{num_reports}</strong> neue Fahrzeug-Berichte im System erfasst:</p>
                
                {html_reports}
                
                <h2 style="border-bottom: 2px solid #FFA633; padding-bottom: 5px;">👨‍🚒 Eingesetztes Personal ({len(sorted_names)})</h2>
                {html_personnel}
                
                <div class="footer">
                    <p>Dies ist eine automatisch generierte Nachricht von deinem Training-Tracker.<br>
                    Bitte logge dich im Dashboard ein, um die vollständigen Berichte zu sehen.</p>
                </div>
            </div>
        </body>
        </html>
        """

        # 3. Email zusammenstellen
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = ", ".join(recipients)
        
        # Text-Fallback (Verwendung korrekter Zeilenumbrüche)
        text_body = f"Hallo,\n\nes gibt {num_reports} neue Einsatzberichte im System.\n\nPersonal-Übersicht:\n"
        for name in sorted_names:
            p_v = personnel_map[name]['vehicles']
            v_info = ", ".join(p_v) if isinstance(p_v, set) else str(p_v)
            text_body += f"- {name} ({v_info})\n"
        text_body += "\nBitte prüfe das System für vollständige Details."
        
        msg.set_content(text_body)
        msg.add_alternative(full_html, subtype='html')

        logger.info(f"Sending HTML incident report summary to {len(recipients)} recipients via {server}:{port}")
        with smtplib.SMTP(str(server), int(port), timeout=10) as smtp:
            smtp.starttls()
            smtp.login(str(user), str(password))
            smtp.send_message(msg)
            
        logger.info(f"Successfully sent HTML incident summary for {num_reports} reports.")
        return True, ""
    except Exception as e:
        logger.error(f"Failed to send incident report summary email: {e}")
        return False, str(e)

def trigger_incident_email(unit_id: int = 1) -> Tuple[bool, str]:
    """
    Manuelles Triggern des E-Mail-Versands für alle noch nicht versandten Berichte einer Einheit.
    """
    from .database import get_email_config, get_unsent_incident_reports, mark_reports_as_sent
    
    config = get_email_config(unit_id)
    if not config:
        return False, "E-Mail Versand ist nicht konfiguriert."
        
    reports = get_unsent_incident_reports(unit_id)
    if not reports:
        return True, "Keine neuen Berichte zum Versenden gefunden."
        
    ok, err = send_incident_report_summary(config, reports)
    if ok:
        mark_reports_as_sent([r['id'] for r in reports])
        return True, f"Erfolgreich versendet ({len(reports)} Berichte)."
    else:
        return False, f"Fehler beim Versand: {err}"
