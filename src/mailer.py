import smtplib
from email.message import EmailMessage
import logging
from typing import Dict, Any, Tuple

logger = logging.getLogger(__name__)

def send_test_email(config: Dict[str, Any], to_email: str) -> Tuple[bool, str]:
    """
    Versendet synchron eine einfache Test-Email anhand der übergebenen SMTP-Konfiguration.
    Dient der Fehler-Überprüfung im Einstellungsmenü.
    """
    server = config.get("smtp_server")
    port = config.get("smtp_port", 587)
    user = config.get("smtp_user")
    password = config.get("smtp_password")
    sender = config.get("sender_email")
    
    if not all([server, port, user, password, sender, to_email]):
        return False, "E-Mail Einstelldaten (SMTP, Absender, Empfänger) sind unvollständig."

    try:
        msg = EmailMessage()
        msg.set_content("Dies ist eine Test-Nachricht von deinem Training-Tracker zur Validierung der SMTP-Einstellungen.\\n\\nWenn du diese E-Mail erhältst, funktioniert der Versand!")
        msg["Subject"] = "Test E-Mail: Training-Tracker"
        msg["From"] = sender
        msg["To"] = to_email

        logger.info(f"Attempting to send test email via {server}:{port} as {user}")
        with smtplib.SMTP(server, port, timeout=10) as smtp:
            smtp.starttls()
            smtp.login(user, password)
            smtp.send_message(msg)
            
        logger.info("Test email sent successfully.")
        return True, "Test E-Mail wurde erfolgreich versandt! Bitte prüfe dein Postfach."
    except Exception as e:
        logger.error(f"Failed to send test email: {e}")
        return False, str(e)


def send_incident_report_summary(config: Dict[str, Any], reports: list) -> Tuple[bool, str]:
    """
    Versendet eine E-Mail-Zusammenfassung über neue Einsatzberichte an die eingestellten Empfänger.
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
        # Build email content
        num_reports = len(reports)
        subject = f"Neue Einsatzberichte ({num_reports})"
        
        body_text = f"Hallo,\\n\\nes gibt {num_reports} neue Einsatzberichte im System:\\n\\n"
        
        for r in reports:
            created = r.get('created_at', 'Unbekannt')
            callsign = r.get('call_sign', 'Unbekanntes Fahrzeug')
            keyword = r.get('keyword', 'Kein Stichwort')
            situation = r.get('situation', '')
            
            body_text += f"--- {callsign} | {keyword} ---\\n"
            body_text += f"Erstellt: {created}\\n"
            body_text += f"Kurze Lage: {situation[:100]}...\\n\\n"
            
        body_text += "Bitte prüfe das System für vollständige Details, Personal und Maßnahmen."

        msg = EmailMessage()
        msg.set_content(body_text)
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = ", ".join(recipients)

        logger.info(f"Sending incident report summary to {len(recipients)} recipients via {server}:{port}")
        with smtplib.SMTP(server, port, timeout=10) as smtp:
            smtp.starttls()
            smtp.login(user, password)
            smtp.send_message(msg)
            
        logger.info(f"Successfully sent incident summary for {num_reports} reports.")
        return True, ""
    except Exception as e:
        logger.error(f"Failed to send incident report summary email: {e}")
        return False, str(e)
