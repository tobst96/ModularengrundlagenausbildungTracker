import re
import logging
from typing import List, Dict, Any, Optional, Callable
from pypdf import PdfReader

logger = logging.getLogger(__name__)

def parse_time(time_str: str) -> float:
    """Converts a time string like '1:30' or '0:45' to float hours."""
    if not time_str or time_str == "0:00":
        return 0.0
    try:
        hours, minutes = map(int, time_str.split(':'))
        return hours + minutes / 60.0
    except ValueError:
        return 0.0

def extract_data_from_pdf(pdf_path: Any, progress_callback: Optional[Callable[[float], None]] = None) -> List[Dict[str, Any]]:
    """
    Extracts training modules and additional metadata from the Given PDF.
    Supports multiple persons and reports progress via callback.
    """
    logger.info(f"Starting PDF extraction for file: {pdf_path}")
    modules = []
    
    # Identify the start of a module line. 
    module_start_pattern = re.compile(r"MGA - (\S+) (.+)")
    # Matches T:, P:, or K: blocks
    hours_unit_pattern = re.compile(r"([TPK]):\s*(\d+:\d+)/(\d+:\d+)")
    # Matches completion status
    status_pattern = re.compile(r"(Absolviert|In Arbeit|Nicht absolviert)")
    
    # Regex for QS Headers
    qs_pattern = re.compile(r"MGA - (QS\d+|Ergänzungsmodule)(?:\s*-\s*.+)?")

    # Patterns for metadata lines
    meta_patterns = {
        "Erste Hilfe": re.compile(r"(Erste-Hilfe|Ausbildung in Erster Hilfe).*"),
        "Einsatzfähigkeit": re.compile(r"Qualifikationsstufe Einsatzfähigkeit.*"),
        "Truppmitglied": re.compile(r"Qualifikationsstufe Truppmitglied.*"),
        "Truppführer": re.compile(r"Qualifikationsstufe Truppführende.*"),
        "Atemschutz": re.compile(r"Atemschutzgeräteträger.*"),
        "Sprechfunk": re.compile(r"Sprechfunker Digitalfunk.*")
    }

    current_person = "Unknown"
    current_full_candidate = "Unknown"
    current_birthday = "Unknown"
    current_qs = "Sonstige"
    current_meta = {}

    reader = PdfReader(pdf_path)
    total_pages = len(reader.pages)
    
    # Regex to extract birth dates like "29.05.1995"
    bday_pattern = re.compile(r"\b(\d{2}\.\d{2}\.\d{4})\b")
    # Repeated inline regex patterns for optimization
    modul_num_pattern = re.compile(r"Modul (\d+)")
    leading_dash_pattern = re.compile(r"^[-\s]+")
    
    for page_idx, page in enumerate(reader.pages):
        text = page.extract_text()
        if text:
            lines = text.split('\n')
            i = 0
            while i < len(lines):
                line = lines[i].strip()
                if not line:
                    i += 1
                    continue

                # 1. New Person
                if "Ziel der modularen Grundlagenausbildung" in line or "Ziel der modularen\nGrundlagenausbildung" in text:
                    for prev_idx in range(i - 1, max(-1, i-10), -1):
                        candidate = lines[prev_idx].strip()
                        if candidate and not any(p.search(candidate) for p in meta_patterns.values()):
                            if "Der Ausbilder versichert" not in candidate and "Feuerwehrdienstvorschriften" not in candidate and "UVV-Feuerwehr" not in candidate:
                                next_person = candidate.split(',')[0].strip()
                                if next_person != current_person:
                                    current_person = next_person
                                    current_full_candidate = candidate
                                    current_birthday = "Unknown"
                                    bday_match = bday_pattern.search(candidate)
                                    if bday_match:
                                        current_birthday = bday_match.group(1)
                                        
                                    current_qs = "Sonstige"
                                    current_meta = {}
                                else:
                                    # Same person on a new page
                                    if len(candidate) > len(current_full_candidate):
                                        current_full_candidate = candidate
                                    if current_birthday == "Unknown":
                                        bday_match = bday_pattern.search(candidate)
                                        if bday_match:
                                            current_birthday = bday_match.group(1)
                                break
                    i += 1
                    continue

                # 2. Metadata
                is_meta = False
                for key, pattern in meta_patterns.items():
                    if pattern.search(line):
                        current_meta[key] = line
                        
                        # Extrahiere QS Abschluss Status direkt
                        if key == "Einsatzfähigkeit":
                            current_meta['qs1_done'] = "Nicht absolviert" not in line
                        elif key == "Truppmitglied":
                            current_meta['qs2_done'] = "Nicht absolviert" not in line
                        elif key == "Truppführer":
                            current_meta['qs3_done'] = "Nicht absolviert" not in line
                            
                        is_meta = True
                        break
                if is_meta:
                    i += 1
                    continue

                # 3. QS Header
                qs_match = qs_pattern.search(line)
                if qs_match:
                    current_qs = qs_match.group(1).strip()
                    i += 1
                    continue

                # 4. Module
                start_match = module_start_pattern.search(line)
                vorb_match = line.startswith("Vorbereitungsmodul Gruppenführer")
                estabk_match = line.startswith("KatS - EStabK")
                if start_match or vorb_match or estabk_match:
                    if start_match:
                        mod_id = start_match.group(1)
                    elif estabk_match:
                        # e.g. "KatS - EStabK - Modul 1" -> "EStabK_1"
                        m_match = modul_num_pattern.search(line)
                        m_num = m_match.group(1) if m_match else "X"
                        mod_id = f"EStabK_{m_num}"
                        current_qs = "EStabK"
                    else:
                        mod_id = "VorbGF"
                        # If it's the Vorbereitungsmodul, ensure we map it to QS3
                        current_qs = "QS3 - Truppführende/r"

                    block_lines = [line]
                    lookahead = i + 1
                    while lookahead < len(lines):
                        next_line = lines[lookahead].strip()
                        if module_start_pattern.search(next_line) or next_line.startswith("Vorbereitungsmodul Gruppenführer") or next_line.startswith("KatS - EStabK") or qs_pattern.search(next_line) or "Ziel der modularen Grundlagenausbildung" in next_line:
                            break
                        if any(p.search(next_line) for p in meta_patterns.values()):
                            break
                        block_lines.append(next_line)
                        lookahead += 1
                    
                    block_content = " ".join(block_lines)
                    status_match = status_pattern.search(block_content)
                    if status_match:
                        status = status_match.group(1)
                        first_poi = status_match.start()
                        h_first = hours_unit_pattern.search(block_content)
                        if h_first and h_first.start() < first_poi:
                            first_poi = h_first.start()
                        
                        if start_match:
                            title_str = block_content[start_match.end(1):first_poi].strip()
                            title_str = leading_dash_pattern.sub("", title_str)
                        elif estabk_match:
                            m_match = modul_num_pattern.search(line)
                            m_num = m_match.group(1) if m_match else "X"
                            title_str = f"KatS - EStabK - Modul {m_num}"
                        else:
                            title_str = "Vorbereitungsmodul Gruppenführer"

                        hours_data = {
                            "T_Ist": 0.0, "T_Soll": 0.0,
                            "P_Ist": 0.0, "P_Soll": 0.0,
                            "K_Ist": 0.0, "K_Soll": 0.0
                        }
                        for h_match in hours_unit_pattern.finditer(block_content):
                            type_code = h_match.group(1)
                            hours_data[f"{type_code}_Ist"] = parse_time(h_match.group(2))
                            hours_data[f"{type_code}_Soll"] = parse_time(h_match.group(3))

                        meta_fields = {f"meta_{k}": v for k, v in current_meta.items()}
                        modules.append({
                            "person_name": current_full_candidate,
                            "person_birthday": current_birthday,
                            "id": mod_id,
                            "title": title_str,
                            "status": status,
                            "qs_level": current_qs,
                            **hours_data,
                            **meta_fields
                        })
                        i = lookahead - 1
                i += 1
        
        # Report progress
        if progress_callback:
            progress_callback(min(1.0, (page_idx + 1) / total_pages))
                
    logger.info(f"Finished parsing PDF. Extracted {len(modules)} modules across {total_pages} pages.")
    return modules


def extract_all_person_pdfs(pdf_path_or_bytes: Any, progress_callback: Optional[Callable[[float], None]] = None) -> Dict[str, bytes]:
    """
    Bulk-extracts isolated PDF certificates for ALL persons in a single pass over the document.
    Returns: A dictionary mapping 'Person Name' -> PDF byte blob.
    """
    import fitz
    import io
    
    logger.info("Starting single-pass bulk PDF isolation for all persons using PyMuPDF (Vector-perfect)...")
    persons_pdfs = {}
    
    # Check if we were passed bytes or a path
    if isinstance(pdf_path_or_bytes, bytes):
        doc = fitz.open(stream=pdf_path_or_bytes, filetype="pdf")
    elif hasattr(pdf_path_or_bytes, 'read'):
        doc = fitz.open(stream=pdf_path_or_bytes.read(), filetype="pdf")
    else:
        doc = fitz.open(pdf_path_or_bytes)
        
    total_pages = len(doc)
    
    # Format: { 'Person Name': [page_idx_1, page_idx_2, ...] }
    person_pages: Dict[str, List[int]] = {}
    current_person = None
    
    for i, page in enumerate(doc):
        # Look for the start of a new person's record on this page
        # Usually formatted like: "Max Mustermann, geb. 01.01.1990..."
        text_instances = page.search_for("geb.")
        page_rect = page.rect
        new_person_found = False
        
        if text_instances:
            # Sort by Y-coordinate to get the first one on the page
            first_inst = sorted(text_instances, key=lambda r: r.y0)[0]
            y = first_inst.y0
            
            # Extract text around "geb." to get the name
            line_rect = fitz.Rect(0, max(0, y - 5), page_rect.width, y + 15)
            line_text = page.get_text("text", clip=line_rect)
            
            if "geb." in line_text:
                name_part = line_text.split("geb.")[0]
                name = name_part.replace(',', '').replace('\n', ' ').strip()
                
                if name:
                    current_person = name
                    new_person_found = True
                    if current_person not in person_pages:
                        person_pages[current_person] = []
        
        # Assign the entire current page to the current person
        if current_person:
            # If current_person was just found or carried over from previous page
            if i not in person_pages[current_person]:
                person_pages[current_person].append(i)
                        
        if progress_callback:
            progress_callback(min(0.5, (i + 1) / total_pages * 0.5))

    logger.info(f"Isolation calculated for {len(person_pages)} persons. Saving Full Page Vector PDFs...")
    
    # Save the full pages directly into a new PDF
    processed = 0
    for name, page_indices in person_pages.items():
        out_doc = fitz.open()
        
        for page_idx in page_indices:
            out_doc.insert_pdf(doc, from_page=page_idx, to_page=page_idx)
            
        if len(out_doc) > 0:
            pdf_bytes = out_doc.write()
            persons_pdfs[name] = pdf_bytes
            
        out_doc.close()
            
        processed += 1
        if progress_callback:
            progress_callback(min(1.0, 0.5 + (processed / len(person_pages)) * 0.5))

    logger.info(f"Bulk isolation complete. Generated {len(persons_pdfs)} individual PDFs.")
    return persons_pdfs

def parse_stundennachweis_excel(file_bytes: bytes) -> tuple[Optional[str], dict[tuple[str, str], dict]]:
    """
    Parses the "Stundennachweis" excel sheet.
    
    Returns:
        (zeitraum_str, mapping)
        mapping is a dict: (Name, Birthday) -> {"einsatzstunden": float, "dienststunden": float}
    """
    import io
    import pandas as pd
    import logging

    logger = logging.getLogger(__name__)
    
    mapping = {}
    zeitraum = "Unbekannt"
    
    try:
        df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=0, header=None)
        
        # Extract period from rows 4 and 5 (index 4 and 5)
        # Often: Row 4: "Von: 01.01.2023", Row 5: " bis : 31.12.2023"
        zeit_von = str(df.iloc[4, 0]).strip() if len(df) > 4 else ""
        zeit_bis = str(df.iloc[5, 0]).strip() if len(df) > 5 else ""
        
        if zeit_von and zeit_bis and "nan" not in zeit_von and "nan" not in zeit_bis:
            zeitraum = f"{zeit_von} {zeit_bis}".strip()
            
        for r in range(10, len(df) - 1):
            val0 = str(df.iloc[r, 0]).strip()
            if val0 and val0.lower() != 'nan' and val0 != 'Gesamtstunden' and val0 != 'Vor/Nach' and val0 != 'Name, Vorname':
                name = val0
                if ',' in name:
                    parts = name.split(',')
                    if len(parts) >= 2:
                        name = f"{parts[1].strip()} {parts[0].strip()}"
                
                bday = str(df.iloc[r, 1]).strip()
                dienst_val = df.iloc[r, 26] # AA
                
                # Try to parse Dienststunden
                dienststunden = 0.0
                try:
                    if str(dienst_val).lower() != 'nan':
                        dienststunden = float(str(dienst_val).replace(',', '.'))
                except Exception:
                    pass
                
                # Check next row for Gesamtstunden
                next_val0 = str(df.iloc[r+1, 0]).strip()
                gesamtstunden = 0.0
                if next_val0 == 'Gesamtstunden':
                    gesamt_val = df.iloc[r+1, 1] # B
                    try:
                        if str(gesamt_val).lower() != 'nan':
                            gesamtstunden = float(str(gesamt_val).replace(',', '.'))
                    except Exception:
                        pass
                
                einsatzstunden = max(0.0, gesamtstunden - dienststunden)
                mapping[(name, bday)] = {
                    "einsatzstunden": einsatzstunden,
                    "dienststunden": dienststunden
                }
                
        return zeitraum, mapping
    except Exception as e:
        logger.error(f"Error parsing Stundennachweis: {e}")
        return None, {}
