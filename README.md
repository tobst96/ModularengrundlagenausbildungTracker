# 🚒 FeuerProfi

**Digitaler Ausbildungs- & Einsatztracker für die Freiwillige Feuerwehr**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.24+-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](https://docker.com)
[![SQLite](https://img.shields.io/badge/SQLite-Datenbank-003B57?logo=sqlite&logoColor=white)](https://sqlite.org)

*Verwalte Ausbildungsstände, Qualifizierungsstufen, Stundennachweise und Einsatzberichte deiner Feuerwehr-Einheit – alles in einer modernen Web-App.*

---

## 📋 Inhaltsverzeichnis

- [Features](#-features)
- [Schnellstart](#-schnellstart)
  - [Lokal starten](#option-1-lokal-starten)
  - [Mit Docker starten](#option-2-mit-docker-empfohlen)
- [Konfiguration](#%EF%B8%8F-konfiguration)
- [Projektstruktur](#-projektstruktur)
- [Datenbank & Backup](#-datenbank--backup)
- [Technologie-Stack](#-technologie-stack)

---

## ✨ Features

### 📊 Dashboard

- Übersicht über erfasstes Personal, dokumentierte Ausbildungen und letztes Daten-Update
- Balkendiagramm der QS-Stufenverteilung (QS1 / QS2 / QS3)
- Einsatzbereitschafts-Anzeige und Hochstufungs-Empfehlungen

### 📚 MGLA-Dashboard

- **PDF-Import** – Lade FeuerOn-Ausbildungs-PDFs hoch und die Daten werden automatisch extrahiert
- **FeuerOn Auto-Sync** – Automatischer Download der aktuellen Ausbildungsdaten via Hintergrund-Job (Playwright-basiert)
- Detaillierte Modul-Tabellen mit Fortschrittsbalken pro Person
- QS-Stufen-Tracking (QS1 → QS2 → QS3) mit konfigurierbaren Schwellwerten
- **Öffentliche Teilnehmer-Ansicht** – Passwortgeschützter Zugang über URL-Parameter

### 👥 Personalverwaltung

- Übersicht aller Mitglieder mit Alter, Qualifikationen, Einsatz- & Dienststunden
- Einzelne Qualifikationen zuweisen und entfernen
- **Stundennachweis-Import** – Einsatz- und Dienststunden direkt aus Excel-Dateien einlesen
- Automatische Altersberechnung und Ablaufwarnungen

### 🧑‍🤝‍🧑 Gruppen-Einteilung

- Automatische, ausbalancierte Aufteilung in konfigurierbare Gruppen
- Berücksichtigung von Qualifikationen und geleisteten Stunden
- **Whitelist** (müssen zusammen sein) und **Blacklist** (müssen getrennt werden) Regeln
- Excel-Export der Gruppeneinteilung

### 🚒 Einsatzbericht

- Digitale Erfassung von Einsätzen direkt nach dem Einrücken
- Fahrzeug-Auswahl mit dynamischer Sitzplatz-Zuweisung
- Einsatzleiter & Einheitsführer dokumentieren
- Lage und Tätigkeiten beschreiben
- **Token-basierter Zugang** – QR-Code pro Fahrzeug für schnellen Zugriff im Einsatz

### 📜 Einsatz-Historie

- Chronologische Übersicht aller archivierten Einsatzberichte
- Detailansicht mit Besatzung, Lage und Maßnahmen
- Versandstatus für E-Mail-Benachrichtigungen

### ⚙️ Einstellungen (Admin)

- **Ausbildungen verwalten** – Anlegen, Bearbeiten und Verknüpfen von Qualifikationen
- **Fahrzeuge verwalten** – Funkrufname, Sitzplätze, QR-Code/Token-Link generieren
- **E-Mail-Versand** – SMTP-Konfiguration für automatische Einsatzbericht-Zusammenfassungen
- **Benutzerverwaltung** – Benutzer anlegen, Admin-Rechte vergeben
- **Wartung** – Personen-Cache leeren, alte Einträge bereinigen, Login-Historie
- **Backup / Restore** – Manuelles & automatisches Datenbank-Backup (GZIP-komprimiert), Import/Export

### 🔧 Weitere Highlights

- 🔐 Login mit Cookie-basierter Sitzungspersistenz & Admin-Rollenkonzept
- 📧 Automatischer E-Mail-Versand neuer Einsatzberichte per Hintergrund-Scheduler
- 🗑️ Automatische Bereinigung inaktiver Teilnehmer (nach 360 Tagen)
- 🕛 Tägliches automatisches Backup um Mitternacht (letzte 14 Tage)
- 📊 Seq-Logging-Integration für zentrales Monitoring (optional)
- 🎨 Modernes Dark-Theme mit Feuerwehr-Rot als Akzentfarbe

---

## 🚀 Schnellstart

### Option 1: Lokal starten

**Voraussetzungen:** Python 3.11+ und pip

```bash
# 1. Repository klonen
git clone https://github.com/<dein-benutzername>/feuerprofi.git
cd feuerprofi

# 2. Virtuelle Umgebung erstellen & aktivieren
python -m venv .venv
source .venv/bin/activate   # macOS/Linux
# .venv\Scripts\activate    # Windows

# 3. Abhängigkeiten installieren
pip install -r requirements.txt

# 4. Playwright-Browser installieren (für FeuerOn Auto-Sync)
playwright install chromium

# 5. App starten
streamlit run 1_🏠_Startseite.py
```

Die App ist anschließend unter **http://localhost:8501** erreichbar.

> **Erster Login:** Beim ersten Start wird automatisch ein Admin-Benutzer `admin` mit Passwort `admin` angelegt. **Bitte sofort ändern!** Das Passwort kann über die Umgebungsvariable `ADMIN_PASSWORD` gesetzt werden.

---

### Option 2: Mit Docker (Empfohlen)

**Voraussetzungen:** [Docker](https://docs.docker.com/get-docker/) & [Docker Compose](https://docs.docker.com/compose/install/)

#### 🐳 Starten mit Docker Compose

```bash
# 1. Repository klonen
git clone https://github.com/<dein-benutzername>/feuerprofi.git
cd feuerprofi

# 2. Container bauen & starten
docker compose up -d --build
```

Die App ist anschließend unter **http://localhost:8501** erreichbar.

#### Docker Compose Konfiguration

Die mitgelieferte `docker-compose.yml`:

```yaml
version: '3.8'

services:
  feuerprofi:
    build: .
    container_name: feuerprofi_app
    restart: unless-stopped
    ports:
      - "8501:8501"
    volumes:
      - ./data:/app/data
    environment:
      - TZ=Europe/Berlin
      - SEQ_SERVER_URL=${SEQ_SERVER_URL:-}
      - SEQ_API_KEY=${SEQ_API_KEY:-}
```

| Parameter | Beschreibung |
|---|---|
| `ports: "8501:8501"` | Web-UI erreichbar auf Port 8501 |
| `volumes: ./data:/app/data` | Persistenter Speicher für Datenbank, Logs & Backups |
| `TZ=Europe/Berlin` | Zeitzone für Scheduler (Backup, FeuerOn-Sync) |
| `SEQ_SERVER_URL` | *(Optional)* Seq-Server URL für zentrales Logging |
| `SEQ_API_KEY` | *(Optional)* Seq-API-Key |

#### Nützliche Docker-Befehle

```bash
# Status prüfen
docker compose ps

# Logs anzeigen
docker compose logs -f feuerprofi

# Stoppen
docker compose down

# Neustart nach Code-Änderungen
docker compose up -d --build

# Health-Check (wird automatisch vom Container ausgeführt)
curl http://localhost:8501/_stcore/health
```

#### 🛡️ Daten-Persistenz

Alle Daten werden im `./data/`-Verzeichnis gespeichert und per Docker-Volume gemountet:

| Datei | Beschreibung |
|---|---|
| `data/local_cache.db` | SQLite-Datenbank mit allen Stamm- & Ausbildungsdaten |
| `data/app.log` | Anwendungs-Log (rotierend, max. 3 Dateien × 5 MB) |
| `data/error.log` | Fehler-Log |
| `data/last_assignment.json` | Letzte Gruppen-Einteilung |
| `data/backup_*.db.gz` | Automatische tägliche Backups (GZIP, letzte 14 Tage) |

> **Tipp:** Bei einem Umzug auf einen neuen Server reicht es, das gesamte `data/`-Verzeichnis mitzunehmen.

---

## ⚙️ Konfiguration

### Umgebungsvariablen

| Variable | Standard | Beschreibung |
|---|---|---|
| `TZ` | `Europe/Berlin` | Zeitzone für Scheduler |
| `SEQ_SERVER_URL` | *(leer)* | Seq-Logging-Server URL |
| `SEQ_API_KEY` | *(leer)* | Seq-API-Key |

### Streamlit-Konfiguration

Die Datei `.streamlit/config.toml` enthält das Theme und Server-Einstellungen:

```toml
[theme]
primaryColor = "#d32f2f"          # Feuerwehr-Rot
backgroundColor = "#121212"       # Dark Mode
secondaryBackgroundColor = "#1E1E1E"
textColor = "#FFFFFF"

[server]
maxUploadSize = 1000              # Max. 1 GB Upload

[global]
dataFrameSerialization = "arrow"
```

---

## 📂 Projektstruktur

```
feuerprofi/
├── 1_🏠_Startseite.py          # Haupt-Einstiegspunkt (Login, Navigation, Scheduler)
├── pages/
│   └── 2_📊_MGLA_Dashboard.py  # MGLA-Dashboard & öffentliche Teilnehmer-Ansicht
├── views/
│   ├── dashboard.py             # Startseite mit KPIs & Charts
│   ├── personal.py              # Personalverwaltung & Stundennachweis-Import
│   ├── gruppen.py               # Automatische Gruppen-Einteilung
│   ├── einsatzbericht.py        # Einsatzbericht-Formular
│   ├── einsatz_historie.py      # Einsatz-Archiv
│   └── settings.py              # Admin-Einstellungen
├── src/
│   ├── database.py              # SQLite-Datenbanklogik (CRUD, Backup/Restore)
│   ├── parser.py                # PDF- & Excel-Parser
│   ├── feueron_downloader.py    # FeuerOn Auto-Downloader (Playwright)
│   ├── mailer.py                # E-Mail-Versand (SMTP)
│   └── data.py                  # Datenzugriffs-Hilfsfunktionen
├── data/                        # Persistente Daten (DB, Logs, Backups)
├── .streamlit/config.toml       # Streamlit-Theme & Server-Konfiguration
├── Dockerfile                   # Docker-Image-Definition
├── docker-compose.yml           # Docker Compose Konfiguration
├── requirements.txt             # Python-Abhängigkeiten
└── README.md
```

---

## 💾 Datenbank & Backup

### Automatisches Backup

- **Jeden Tag um 00:00 Uhr** wird automatisch ein GZIP-komprimiertes Backup der SQLite-Datenbank erstellt
- Die **letzten 14 Backups** werden vorgehalten, ältere automatisch gelöscht
- Backups werden im `data/`-Verzeichnis abgelegt

### Manuelles Backup & Restore

- Unter **Einstellungen → Backup** kann jederzeit ein manuelles Backup erstellt werden
- Export/Import der gesamten Datenbank als GZIP-komprimierte JSON-Datei
- Optional: `module_history`-Tabelle beim Export ausschließen (für kleinere Backups)

### Daten-Reset

- Einzelne Personen, „Unknown"-Einträge oder alle Personen einer Einheit können über die Wartungsseite gelöscht werden
- Inaktive Teilnehmer (>360 Tage ohne Aktualisierung) werden automatisch entfernt

---

## 🛠 Technologie-Stack

| Komponente | Technologie |
|---|---|
| **Frontend** | [Streamlit](https://streamlit.io) mit Custom CSS (Dark Theme) |
| **Backend** | Python 3.11 |
| **Datenbank** | SQLite (lokal, dateibasiert) |
| **PDF-Parsing** | pypdf, pdfplumber, PyMuPDF (fitz) |
| **Excel-Parsing** | openpyxl, pandas |
| **FeuerOn-Sync** | Playwright (Headless Chromium) |
| **E-Mail** | smtplib (SMTP mit TLS) |
| **Scheduler** | APScheduler (Hintergrund-Jobs) |
| **Auth** | bcrypt + Cookie-Manager |
| **QR-Codes** | qrcode + Pillow |
| **Logging** | Python logging + seqlog (optional) |
| **Container** | Docker + Docker Compose |

---

## 📄 Lizenz

Dieses Projekt ist derzeit nicht unter einer offenen Lizenz veröffentlicht. Alle Rechte vorbehalten.

---

Erstellt mit ❤️ und 🚒 für die Freiwillige Feuerwehr
