import streamlit as st
from src.utils_ui import apply_custom_design
apply_custom_design()
import time
import json
from datetime import datetime
import src.db_base as storage
import src.sync_updater as sync_upd

# Sichern der Seite: Nur für Admins
if st.session_state.get('username', '').lower() != 'admin':
    st.error("Zugriff verweigert. Diese Seite ist nur für Administratoren zugänglich.")
    st.stop()
    
tab_ausb, tab_fahrz, tab_email, tab_benut, tab_sync, tab_sich, tab_wart, tab_update, tab_backup = st.tabs([
    "🎓 Ausbildungen", "🚒 Fahrzeuge", "✉️ E-Mail", "👥 Benutzer", "🔄 Auto-Download & Sync", "🛡️ Sicherheit", "⚙️ Wartung", "🚀 Update", "💾 Backup"
])

# --- TAB AUSBILDUNGEN ---
with tab_ausb:
    st.subheader("Ausbildungen verwalten")
    st.info("Hier kannst du alle Ausbildungen, deren Wertigkeit für den Fortschritt, Voraussetzungen und Gleichstellungen global für das System konfigurieren.")

    # Lade bestehende Ausbildungen für Dropdowns
    quals = storage.get_qualifications()
    qual_names = ["- Keine -"] + [q['name'] for q in quals]

    # Hilfs-Dicts für ID/Name Mapping
    name_to_id = {q['name']: q['id'] for q in quals}
    id_to_name = {q['id']: q['name'] for q in quals}

    # --- NEUE AUSBILDUNG ANLEGEN ---
    with st.expander("➕ Neue Ausbildung hinzufügen", expanded=True):
        with st.form("new_qualification_form"):
            col1, col2 = st.columns(2)
            with col1:
                q_name = st.text_input("Name der Ausbildung*", placeholder="z.B. Gruppenführer")
                q_prereq = st.selectbox("Voraussetzung", options=qual_names, help="Welche Ausbildung muss vorher absolviert sein?")
            with col2:
                q_value = st.number_input("Wertigkeit*", min_value=0, max_value=10000, value=100, step=50, help="Punkte/Gewichtung für den Fortschritt")
                q_equiv = st.selectbox("Gleichzusetzen mit", options=qual_names, help="Gilt diese Ausbildung auch als ... (z.B. QS2 = Truppführer)")
                
            submitted = st.form_submit_button("Ausbildung speichern", type="primary")
            if submitted:
                if not q_name.strip():
                    st.error("Bitte einen Namen für die Ausbildung eingeben.")
                else:
                    # Resolve String -> ID
                    prereq_id = name_to_id.get(q_prereq) if q_prereq != "- Keine -" else None
                    equiv_id = name_to_id.get(q_equiv) if q_equiv != "- Keine -" else None
                    
                    ok, err = storage.create_qualification(q_name.strip(), int(q_value), prereq_id, equiv_id)
                    if ok:
                        st.success(f"Ausbildung '{q_name}' erfolgreich angelegt!")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error(f"Fehler beim Anlegen: {err}")

    # --- BESTEHENDE AUSBILDUNGEN ANZEIGEN ---
    st.write("**Aktuell hinterlegte Ausbildungen**")

    if not quals:
        st.info("Noch keine Ausbildungen konfiguriert.")
    else:
        import pandas as pd
        
        # We create a dataframe out of the quals list for easier editing
        # Map the IDs to names for the UI columns
        for q in quals:
            q['prerequisite'] = q.get('prerequisite_name')
            q['equivalent'] = q.get('equivalent_name')
            
        df_quals = pd.DataFrame(quals)
        
        # Only keep the columns we want to show/edit
        display_cols = ["id", "name", "value", "prerequisite", "equivalent"]
        df_quals = df_quals[[col for col in display_cols if col in df_quals.columns]]
        
        # Create the config for the columns
        column_config = {
            "id": None, # Hide ID column
            "name": st.column_config.TextColumn("Ausbildung (Name)", required=True),
            "value": st.column_config.NumberColumn("Wertigkeit", required=True, min_value=0, step=10),
            "prerequisite": st.column_config.SelectboxColumn(
                "Voraussetzung",
                options=qual_names
            ),
            "equivalent": st.column_config.SelectboxColumn(
                "Gleichzusetzen mit",
                options=qual_names
            )
        }

        # Track changes using st.data_editor
        edited_df = st.data_editor(
            df_quals,
            column_config=column_config,
            use_container_width=True,
            num_rows="dynamic",
            key="quals_editor",
            hide_index=True
        )
        
        # Detect if save is needed by comparing original and edited
        if not df_quals.equals(edited_df):
            if st.button("💾 Änderungen speichern", type="primary", use_container_width=True):
                errors = []
                
                # Find modified/added rows
                for idx, row in edited_df.iterrows():
                    q_id = row.get("id")
                    q_name = row["name"]
                    q_value = row["value"]
                    
                    # Get selected names
                    q_req_name = row.get("prerequisite") if pd.notna(row.get("prerequisite")) else None
                    q_eq_name = row.get("equivalent") if pd.notna(row.get("equivalent")) else None
                    
                    # Resolve IDs
                    req_id = name_to_id.get(q_req_name) if q_req_name and q_req_name != "- Keine -" else None
                    eq_id = name_to_id.get(q_eq_name) if q_eq_name and q_eq_name != "- Keine -" else None
                    
                    if pd.notna(q_id):
                        # Existing row
                        ok, err = storage.update_qualification(int(q_id), q_name, int(q_value), req_id, eq_id)
                        if not ok: errors.append(err)
                    else:
                        # New row added via datagrid
                        ok, err = storage.create_qualification(q_name, int(q_value), req_id, eq_id)
                        if not ok: errors.append(err)
                        
                # Find deleted rows
                original_ids = set(df_quals["id"].dropna().tolist())
                current_ids = set(edited_df["id"].dropna().tolist())
                deleted_ids = original_ids - current_ids
                
                for d_id in deleted_ids:
                    ok, err = storage.delete_qualification(int(d_id))
                    if not ok: errors.append(err)
                    
                if errors:
                    st.error("Einige Fehler traten auf:\\n" + "\\n".join(set(errors)))
                else:
                    st.success("Änderungen erfolgreich gespeichert!")
                    time.sleep(0.5)
                    st.rerun()

# --- TAB FAHRZEUGE ---
with tab_fahrz:
    st.subheader("Fahrzeuge verwalten")
    st.info("Lege hier Einsatzfahrzeuge an. Diese stehen dir dann im Einsatzbericht zur Verfügung, um das aufgesessene Personal zu besetzen.")

    with st.expander("➕ Neues Fahrzeug hinzufügen", expanded=True):
        with st.form("new_vehicle_form"):
            col1, col2 = st.columns(2)
            with col1:
                v_callsign = st.text_input("Funkrufkennung*", placeholder="z.B. 15-47-1 (LF)")
            with col2:
                v_seats = st.number_input("Sitzplätze*", min_value=1, max_value=20, value=9, step=1, help="Gibt die Anzahl der Dropdowns für das Personal im Einsatzbericht vor.")
                
            v_submitted = st.form_submit_button("Fahrzeug speichern", type="primary")
            if v_submitted:
                if not v_callsign.strip():
                    st.error("Bitte eine Funkrufkennung eingeben.")
                else:
                    ok, err = storage.create_vehicle(v_callsign.strip(), int(v_seats))
                    if ok:
                        st.success(f"Fahrzeug '{v_callsign}' angelegt!")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error(f"Fehler beim Anlegen: {err}")

    st.write("**Aktuell hinterlegte Fahrzeuge**")
    vehicles = storage.get_vehicles()

    if not vehicles:
        st.info("Noch keine Fahrzeuge konfiguriert.")
    else:
        import pandas as pd
        df_veh = pd.DataFrame(vehicles)
        
        # Baue Link für Token
        try:
            base_url = st.context.headers.get("Host", "localhost:8501") if hasattr(st, 'context') else "localhost:8501"
        except:
            base_url = "localhost:8501"
        
        df_veh['link'] = df_veh['token'].apply(lambda t: f"http://{base_url}/?token={t}" if t else "")
        
        display_cols_veh = ["id", "call_sign", "seats", "link"]
        df_veh = df_veh[[col for col in display_cols_veh if col in df_veh.columns]]
        
        col_config_veh = {
            "id": None, 
            "call_sign": st.column_config.TextColumn("Funkrufkennung", required=True),
            "seats": st.column_config.NumberColumn("Sitzplätze", required=True, min_value=1, max_value=20, step=1),
            "link": st.column_config.LinkColumn("Öffentlicher Link (Bericht)", display_text="LINK KOPIEREN", disabled=True)
        }

        edited_df_veh = st.data_editor(
            df_veh,
            column_config=col_config_veh,
            use_container_width=True,
            num_rows="dynamic",
            key="vehicles_editor",
            hide_index=True
        )
        
        if not df_veh.equals(edited_df_veh):
            if st.button("💾 Fahrzeug-Änderungen speichern", type="primary", use_container_width=True):
                errors = []
                
                # Find modified/added rows
                for idx, row in edited_df_veh.iterrows():
                    v_id = row.get("id")
                    call_sign = row["call_sign"]
                    seats = row["seats"]
                    
                    if pd.notna(v_id):
                        ok, err = storage.update_vehicle(int(v_id), call_sign, int(seats))
                        if not ok: errors.append(err)
                    else:
                        ok, err = storage.create_vehicle(call_sign, int(seats))
                        if not ok: errors.append(err)
                        
                # Find deleted rows
                original_veh_ids = set(df_veh["id"].dropna().tolist())
                current_veh_ids = set(edited_df_veh["id"].dropna().tolist())
                deleted_veh_ids = original_veh_ids - current_veh_ids
                
                for d_id in deleted_veh_ids:
                    ok, err = storage.delete_vehicle(int(d_id))
                    if not ok: errors.append(err)
                    
                if errors:
                    st.error("Einige Fehler traten auf:\\n" + "\\n".join(set(errors)))
                else:
                    st.success("Fahrzeuge erfolgreich aktualisiert!")
                    time.sleep(0.5)
                    st.rerun()

# --- TAB EMAIL ---
with tab_email:
    st.subheader("E-Mail Versand konfigurieren")
    st.info("Richte hier den automatischen E-Mail-Versand (z.B. für Einsatzberichte) ein.")
    
    
    unit_id = 1
    config = storage.get_email_config(unit_id) or {}
    
    with st.form("email_settings_form"):
        st.write("### SMTP Server Einstellungen")
        col_s1, col_s2 = st.columns([3, 1])
        with col_s1:
            smtp_server = st.text_input("SMTP Server", value=config.get("smtp_server", ""), placeholder="z.B. smtp.strato.de")
        with col_s2:
            smtp_port = st.number_input("SMTP Port", value=config.get("smtp_port", 587), step=1, min_value=1)
            
        col_s3, col_s4 = st.columns(2)
        with col_s3:
            smtp_user = st.text_input("SMTP Benutzername / E-Mail", value=config.get("smtp_user", ""))
            sender_email = st.text_input("Absender E-Mail Adresse", value=config.get("sender_email", ""))
        with col_s4:
            smtp_password = st.text_input("SMTP Passwort", value=config.get("smtp_password", ""), type="password")
            
        st.divider()
        st.write("### Empfänger & Verzögerung")
        recipient_emails = st.text_input("Empfänger E-Mail(s)", value=config.get("recipient_emails", ""), help="Mehrere durch Komma getrennt (z.B. 'chef@feuerwehr.de, wache@feuerwehr.de')")
        delay_minutes = st.number_input("Verzögerung für Zusammenfassung (in Minuten)", min_value=0, max_value=1440, value=config.get("delay_minutes", 60), help="Wie lange sollen Einsatzberichte nach Erstellung gesammelt werden, bevor sie in einer Liste versendet werden?")
        
        submitted_email = st.form_submit_button("E-Mail Einstellungen speichern", type="primary")
        if submitted_email:
            ok, err = storage.save_email_config(unit_id, smtp_server, smtp_port, smtp_user, smtp_password, sender_email, recipient_emails, delay_minutes)
            if ok:
                st.success("E-Mail Einstellungen erfolgreich gespeichert!")
                time.sleep(1)
                st.rerun()
            else:
                st.error(f"Fehler: {err}")
                
    st.write("### Test-Versand")
    st.info("Speichere die Einstellungen, bevor du einen Test durchführst.")
    
    # We use a separate button outside the form for testing
    from src.mailer import send_test_email
    test_rcpt = st.text_input("Test-Empfänger:", value=config.get("sender_email", ""))
    
    if st.button("✉️ Testmail senden"):
        with st.spinner("Sende..."):
            ok, msg = send_test_email(config, test_rcpt)
            if ok:
                st.success(msg)
            else:
                st.error(f"Fehler beim Mailversand: {msg}")

# --- TAB BENUTZERVERWALTUNG ---
with tab_benut:

    st.subheader("Benutzerverwaltung (Admin-Rechte)")
    st.info("Lege fest, welche verknüpften Accounts Zugriff auf diese Einstellungen haben. Das System-Konto 'admin' lässt sich nicht verändern.")

    with st.expander("➕ Neuen Benutzer hinzufügen", expanded=False):
        with st.form("new_user_form"):
            col1, col2 = st.columns(2)
            with col1:
                u_name = st.text_input("Benutzername*", help="Darf keine Leerzeichen enthalten.")
            with col2:
                u_pass = st.text_input("Passwort*", type="password")
                
            submitted_u = st.form_submit_button("Benutzer anlegen", type="primary")
            if submitted_u:
                if not u_name.strip() or not u_pass.strip():
                    st.error("Bitte Benutzername und Passwort eingeben.")
                else:
                    # In this system, user creates are implicitly tied to unit_id 1 unless a unit dropdown is meant to be used
                    ok, err = storage.create_user_with_unit(u_name.strip(), u_pass, 1)
                    if ok:
                        st.success(f"Benutzer '{u_name}' erfolgreich angelegt!")
                        import time
                        time.sleep(1)
                        st.rerun()
    users_list = storage.get_all_users()
    if not users_list:
        st.warning("Keine Benutzer gefunden (außer dem System-Admin).")
    else:
        st.write("---")
        st.write("**Aktuelle Benutzer**")
        
        
        for u in users_list:
            is_admin_user = (u['username'].lower() == 'admin')
            with st.expander(f"👤 {u['username']} {'(System-Admin)' if is_admin_user else ''}"):
                col_info, col_actions = st.columns([2, 1])
                
                with col_info:
                    st.write(f"**Benutzername:** `{u['username']}`")
                    
                    # Admin Toggle
                    current_admin_status = bool(u['is_admin'])
                    new_admin_status = st.toggle(
                        "Administrator-Rechte", 
                        value=current_admin_status, 
                        key=f"toggle_admin_{u['id']}",
                        disabled=is_admin_user # cannot change admin status of 'admin'
                    )
                    
                    if new_admin_status != current_admin_status:
                        ok, err = storage.update_user_admin_status(u['id'], new_admin_status)
                        if ok:
                            st.success("Berechtigungen aktualisiert!")
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.error(f"Fehler: {err}")

                with col_actions:
                    # Delete Button (not for system admin)
                    if not is_admin_user:
                        if st.button("🗑️ Benutzer löschen", key=f"del_u_{u['id']}", type="secondary", use_container_width=True):
                            ok, err = storage.delete_user(u['id'])
                            if ok:
                                st.success("Benutzer gelöscht.")
                                time.sleep(0.5)
                                st.rerun()
                            else:
                                st.error(f"Fehler: {err}")
                    else:
                        st.info("System-Konto")

                st.divider()
                st.write("**Passwort ändern**")
                with st.form(f"pw_change_modern_{u['id']}", clear_on_submit=True):
                    new_pwd = st.text_input("Neues Passwort", type="password", key=f"new_pw_mod_{u['id']}")
                    pw_submit = st.form_submit_button("Passwort aktualisieren", use_container_width=True)
                    if pw_submit:
                        if new_pwd:
                            ok, err = storage.update_user_password(u['id'], new_pwd)
                            if ok:
                                st.success(f"Passwort für {u['username']} erfolgreich geändert!")
                            else:
                                st.error(f"Fehler: {err}")
                        else:
                            st.warning("Bitte ein Passwort eingeben.")

# --- TAB AUTO-DOWNLOAD & SYNC ---
with tab_sync:
    st.subheader("🔄 FeuerOn Auto-Download")
    st.caption("Täglich automatisch auf feueron.de einloggen, PDF herunterladen und importieren.")
    
    sel_uid = 1
    cfg = storage.get_feueron_config(sel_uid)
    
    st.divider()
    st.subheader("🔑 FeuerOn Zugangsdaten")
    
    with st.form(key="feueron_config_form"):
        col1, col2 = st.columns(2)
        with col1:
            f_org = st.text_input(
                "Organisation (Dropdown-Wert)",
                value=cfg.get('feueron_org', '') if cfg else '',
                placeholder="z.B. Westerstede, Stadt",
                help="Genaue Bezeichnung wie sie in FeuerOn erscheint"
            )
            f_org_id = st.text_input(
                "Organisations-ID",
                value=cfg.get('feueron_org_id', '') if cfg else '',
                placeholder="z.B. 3455",
                help="Interne ID aus FeuerOn. Für Westerstede, OF = 3455"
            )
            f_user = st.text_input(
                "Benutzername",
                value=cfg.get('feueron_username', '') if cfg else '',
                placeholder="FeuerOn Benutzername"
            )
            f_pass = st.text_input(
                "Passwort",
                value=cfg.get('feueron_password', '') if cfg else '',
                type="password",
                placeholder="FeuerOn Passwort"
            )
        with col2:
            f_hour = st.number_input(
                "Uhrzeit (Stunde)",
                min_value=0, max_value=23,
                value=cfg.get('sync_hour', 3) if cfg else 3
            )
            f_minute = st.number_input(
                "Uhrzeit (Minute)",
                min_value=0, max_value=59,
                value=cfg.get('sync_minute', 0) if cfg else 0
            )
            f_enabled = st.toggle(
                "Auto-Download aktiv",
                value=bool(cfg.get('sync_enabled', False)) if cfg else False
            )
        
        save_btn = st.form_submit_button("💾 Synchronisation speichern", use_container_width=True)
        if save_btn:
            ok, err = storage.save_feueron_config(
                sel_uid, f_org, f_org_id, f_user, f_pass,
                int(f_hour), int(f_minute), f_enabled
            )
            if ok:
                try:
                    from src.feueron_downloader import _reload_jobs
                    _reload_jobs()
                except:
                    pass
                st.success(f"✅ Gespeichert! {'Auto-Download ist aktiv.' if f_enabled else 'Auto-Download ist deaktiviert.'}")
            else:
                st.error(f"Fehler: {err}")
    
    st.divider()
    st.subheader("📊 Sync-Status")
    
    cfg_live = storage.get_feueron_config(sel_uid)
    if cfg_live:
        s = cfg_live.get('last_sync_status')
        s_msg = cfg_live.get('last_sync_message', '')
        s_time = cfg_live.get('last_sync_at', '')
        
        if s == 'success':
            st.success(f"✅ Letzter Sync: {s_time}")
            if s_msg: st.caption(s_msg)
        elif s == 'error':
            st.error(f"❌ Fehler beim letzten Sync: {s_time}")
            if s_msg: st.code(s_msg, language=None)
        elif s == 'running':
            st.info(f"⏳ Sync läuft gerade... ({s_msg})")
        else:
            st.info("Noch kein Sync durchgeführt.")
        
        if cfg_live.get('sync_enabled') and cfg_live.get('sync_hour') is not None:
            next_h = cfg_live['sync_hour']
            next_m = cfg_live.get('sync_minute', 0)
            st.caption(f"🕰️ Geplanter täglicher Sync: {next_h:02d}:{next_m:02d} Uhr")
    
    st.divider()
    # Manual Trigger
    col_btn1, col_btn2 = st.columns([2, 1])
    with col_btn1:
        if st.button("▶️ Jetzt manuell ausführen", use_container_width=True, type="primary"):
            if not cfg_live or not cfg_live.get('feueron_username'):
                st.error("Bitte zuerst Zugangsdaten speichern!")
            else:
                from src.feueron_downloader import run_download as _run_dl
                with st.spinner("⏳ Synchronisiere mit FeuerOn..."):
                    ok, msg = _run_dl(sel_uid)
                if ok:
                    st.success(f"{msg}")
                    st.cache_data.clear()
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error(f"❌ Fehler: {msg}")
    with col_btn2:
        if st.button("🔄 Status aktualisieren", use_container_width=True):
            st.rerun()

# --- TAB SICHERHEIT ---
with tab_sich:
    st.subheader("Sicherheit & Zugriffscodes")
    st.info("Hier kannst du Passwörter und Zugriffscodes konfigurieren, die nicht direkt mit Benutzerkonten verknüpft sind.")
    
    # --- PUBLIC VIEW PASSWORD ---
    st.write("### 🔑 Teilnehmer-Abfrage (Public View)")
    st.write("Dieser Code ermöglicht es Teilnehmern, ihren Ausbildungsstand abzufragen, ohne ein volles Benutzerkonto zu besitzen.")
    
    current_pw = storage.get_public_view_password(1) or "feuerprofi"
    
    with st.form("public_view_pw_form"):
        new_public_pw = st.text_input("Zugriffscode (z.B. Funkrufname)", value=current_pw, help="Wird für die Anmeldung im Teilnehmer-Bereich benötigt.")
        submitted_pw = st.form_submit_button("Zugriffscode speichern", type="primary")
        
        if submitted_pw:
            if not new_public_pw.strip():
                st.error("Der Zugriffscode darf nicht leer sein.")
            else:
                ok, err = storage.save_public_view_password(1, new_public_pw.strip())
                if ok:
                    st.success("Zugriffscode erfolgreich aktualisiert!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(f"Fehler beim Speichern: {err}")

    st.divider()
    st.write("### 📝 Letzte Logins (Global)")
    import pandas as pd
    history = storage.get_login_history(limit=50)
    if history:
        df_hist = pd.DataFrame(history)
        
        # Formatiere das Datum schön
        try:
            df_hist['login_time'] = pd.to_datetime(df_hist['login_time']).dt.strftime('%d.%m.%Y %H:%M:%S')
        except:
            pass # Keep as is if parsing fails
            
        # Status Emojis (handle SUCCESS, FAILED and German legacy strings)
        def map_status(s):
            if not s: return "❌ Unbekannt"
            s_str = str(s).strip()
            if s_str.upper() in ["SUCCESS", "ERFOLGREICH", "OK"]:
                return "✅ Erfolg"
            if s_str.upper() in ["FAILED", "FEHLER", "ABGEBROCHEN"]:
                return "❌ Fehlgeschlagen"
            return f"⚠️ {s_str}"
            
        df_hist['status'] = df_hist['status'].apply(map_status)
        
        df_hist = df_hist.rename(columns={
            'username': 'Benutzer',
            'unit_name': 'Einheit',
            'login_time': 'Zeitpunkt',
            'status': 'Status',
            'ip_address': 'IP-Adresse'
        })
        
        # Sicherheitsnetz: Einheit-Spalte ggf. hinzufügen
        if 'Einheit' not in df_hist.columns:
            df_hist['Einheit'] = 'Unbekannt'
            
        show_cols = [c for c in ['Zeitpunkt', 'Benutzer', 'Einheit', 'Status', 'IP-Adresse'] if c in df_hist.columns]
        st.dataframe(df_hist[show_cols], hide_index=True, use_container_width=True)
    else:
        st.info("Noch keine Logins verzeichnet.")

# --- TAB WARTUNG ---
with tab_wart:
    # --- DATEN-BEREINIGUNG ---

    st.subheader("Daten-Bereinigung")
    st.info("Hier kannst du aufräumen. Beispielsweise fehlerhafte 'Unknown'-Personen entfernen, die beim Import oder PDF-Upload doppelt angelegt wurden.")

    col_clean1, _ = st.columns(2)
    with col_clean1:
        if st.button("🗑️ Alle 'Unknown'-Personen löschen", type="primary"):
            ok, err, count = storage.delete_all_unknown_persons(unit_id=1)
            if ok:
                st.success(f"Erfolgreich {count} 'Unknown'-Person(en) gelöscht!")
                time.sleep(1.5)
                st.rerun()
            else:
                st.error(f"Fehler beim Löschen: {err}")

    st.divider()
    st.divider()

    # --- SYSTEM-STEUERUNG ---
    st.subheader("🖥️ System-Steuerung")
    st.info("Hier kannst du die Anwendung neu starten. Dies ist nützlich, um den Cache zu leeren oder bei unvorhergesehenen Problemen.")
    
    if st.button("🔄 Anwendung jetzt neu starten", type="primary", use_container_width=True):
        st.toast("Anwendung wird neu gestartet...")
        import importlib
        importlib.reload(sync_upd)
        time.sleep(1)
        sync_upd.restart_application()

    st.divider()

# --- TAB UPDATE ---
with tab_update:
    import src.sync_updater as sync_upd
    st.subheader("🚀 System-Update")
    st.caption("Prüfe auf neue Versionen direkt von GitHub und aktualisiere das System.")
    
    # Auto-Update Info
    upd_config = storage.get_auto_update_config()
    if upd_config:
        st.info("🕒 **Automatisches Update**")
        days = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
        day_str = days[upd_config['update_day']]
        st.write(f"Nächstes wöchentliches Update: **Jeden {day_str} um {upd_config['update_hour']:02d}:{upd_config['update_minute']:02d} Uhr**")
        
        last_check = upd_config.get('last_check_at', 'Nie')
        st.write(f"Letzte Prüfung: `{last_check}`")
        if upd_config.get('update_available'):
            st.warning("⚠️ Ein Update ist verfügbar und wird zum nächsten Termin automatisch installiert.")
        else:
            st.success("✅ System ist aktuell.")

    st.divider()
    
    col1, col2 = st.columns(2)
    with col1:
        st.info(f"**Aktuelle Version (lokal):** `{sync_upd.get_local_commit()}`")
        st.write(f"Zweig: `{sync_upd.get_current_branch()}`")

    with col2:
        if st.button("🔍 Auf Updates prüfen", use_container_width=True):
            with st.spinner("Prüfe auf Updates..."):
                available = sync_upd.check_for_updates()
                remote = sync_upd.get_remote_commit()
                if remote == "Unknown":
                    st.error("Konnte keine Verbindung zu GitHub herstellen.")
                elif available:
                    st.warning(f"⚠️ Eine neue Version ist verfügbar! (`{remote}`)")
                    st.rerun()
                else:
                    st.success("Das System ist auf dem neuesten Stand.")

    st.divider()
    
    if st.button("🚀 Jetzt Update starten", type="primary", use_container_width=True):
        st.toast("Update wird gestartet... Der Server startet gleich neu.")
        import time
        time.sleep(2)
        ok, msg = sync_upd.perform_auto_update()
        if not ok:
            st.error(f"Fehler beim Update: {msg}")

    if st.button("🛠️ Erzwungenes Update (Force Reset)", use_container_width=True, help="Setzt das System hart auf den GitHub-Stand zurück. Hilfreich bei Datei-Konflikten."):
        st.toast("Force-Update wird gestartet... Alle lokalen Änderungen werden überschrieben.")
        import time
        time.sleep(2)
        ok, msg = sync_upd.perform_force_update()
        if not ok:
            st.error(f"Fehler beim Force-Update: {msg}")

# --- TAB BACKUP ---
with tab_backup:
    # --- DATENBANK BACKUP & WIEDERHERSTELLUNG ---
    st.subheader("Datenbank Backup & Wiederherstellung")
    st.info("Sichere die komplette Datenbank als JSON-Datei oder lade ein bestehendes Backup wieder hoch. Achtung: Beim Hochladen wird der aktuelle Stand komplett überschrieben!")

    col_bak1, col_bak2 = st.columns(2)

    with col_bak1:
        st.markdown("**Manuelles Backup erstellen**")
        include_hist = st.checkbox("Historien-Daten (Modul-Historie) in Backup einschließen", value=False, help="Wenn deaktiviert, wird die große Historien-Tabelle ausgelassen, was die Backup-Datei verkleinert.")
        try:
            # We delay loading to not lock the UI
            compressed_data = storage.export_db_to_json(include_history=include_hist)
            now_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            st.download_button(
                label="📥 Backup herunterladen (.json.gz)",
                data=compressed_data,
                file_name=f"feuerprofi_backup_{now_str}.json.gz",
                mime="application/gzip",
                type="primary",
                use_container_width=True
            )
        except Exception as e:
            st.error(f"Fehler beim Generieren des Backups: {e}")

    with col_bak2:
        st.markdown("**Aus Backup wiederherstellen**")
        uploaded_file = st.file_uploader("JSON/GZIP Backup-Datei hochladen", type=["json", "gz"])
        if uploaded_file is not None:
            if st.button("🚨 Datenbank jetzt überschreiben", type="primary", use_container_width=True):
                compressed_content = uploaded_file.getvalue()
                ok, err = storage.import_db_from_json(compressed_content)
                if ok:
                    st.success("Datenbank erfolgreich wiederhergestellt!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(f"Fehler bei Wiederherstellung: {err}")

    # --- LIVE SYSTEM-LOGS ---
    st.divider()
    st.subheader("📝 Live System-Logs")
    st.info("Hier kannst du das Anwendungs-Logbuch live einsehen.")
    
    import os
    
    col_log1, col_log2 = st.columns([1, 1])
    with col_log1:
        log_type = st.radio("Log-Datei auswählen:", ["app.log", "error.log"], horizontal=True)
    with col_log2:
        auto_refresh = st.checkbox("🔄 Auto-Refresh (alle 5s)", value=False)
        lines_to_show = st.slider("Letzte N Zeilen anzeigen", min_value=10, max_value=500, value=100, step=10)
        
    def read_log_tail(filepath, lines=100):
        try:
            if not os.path.exists(filepath):
                return "Keine Logdatei gefunden."
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.readlines()
                return "".join(content[-lines:])
        except Exception as e:
            return f"Fehler beim Lesen des Logs: {e}"
            
    log_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", log_type)
    log_content = read_log_tail(log_path, lines=lines_to_show)
    
    st.text_area(f"Inhalt von {log_type}", value=log_content, height=400, disabled=True)
    
    if st.button("🗑️ Ausgewähltes Log leeren"):
        try:
            with open(log_path, 'w', encoding='utf-8') as f:
                f.write("")
            st.success(f"{log_type} wurde erfolgreich geleert.")
            time.sleep(0.5)
            st.rerun()
        except Exception as e:
            st.error(f"Fehler beim Leeren: {e}")
            
    if auto_refresh:
        import time
        time.sleep(5)
        st.rerun()
