import pdfplumber
import re
from typing import List, Dict, Any

def parse_time(time_str: str) -> float:
    """Converts a time string like '1:30' or '0:45' to float hours."""
    if not time_str or time_str == "0:00":
        return 0.0
    try:
        hours, minutes = map(int, time_str.split(':'))
        return hours + minutes / 60.0
    except ValueError:
        return 0.0

def extract_data_from_pdf(pdf_path: Any) -> List[Dict[str, Any]]:
    """
    Extracts training modules and additional metadata from the Given PDF.
    Supports multiple persons.
    """
    modules = []
    
    # Regex for Modules
    module_pattern = re.compile(r"MGA - (\S+) (.+?) ((?:[TPK]: \d+:\d+/\d+:\d+\s*)+) (Absolviert|In Arbeit|Nicht absolviert)")
    hours_pattern = re.compile(r"([TPK]): (\d+:\d+)/(\d+:\d+)")
    
    # Regex for QS Headers
    qs_pattern = re.compile(r"MGA - (QS\d+|Ergänzungsmodule)(?: - .+)?")

    # Patterns for metadata lines (appear before modules)
    # We store the whole line content after the keyword match as the value.
    meta_patterns = {
        "Erste Hilfe": re.compile(r"(Erste-Hilfe|Ausbildung in Erster Hilfe).*"),
        "Einsatzfähigkeit": re.compile(r"Qualifikationsstufe Einsatzfähigkeit.*"),
        "Truppmitglied": re.compile(r"Qualifikationsstufe Truppmitglied.*"),
        "Truppführer": re.compile(r"Qualifikationsstufe Truppführende.*"),
        "Atemschutz": re.compile(r"Atemschutzgeräteträger.*"),
        "Sprechfunk": re.compile(r"Sprechfunker Digitalfunk.*")
    }

    current_person = "Unknown"
    current_qs = "Sonstige"
    current_meta = {} # Dictionary to store metadata for the current person

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            
            lines = text.split('\n')
            for i, line in enumerate(lines):
                line = line.strip()
                if not line:
                    continue

                # 1. Detect New Person Start
                if "Ziel der modularen Grundlagenausbildung" in line:
                    # Look backwards for Name
                    for prev_idx in range(i - 1, -1, -1):
                        candidate = lines[prev_idx].strip()
                        if candidate:
                            current_person = candidate
                            current_qs = "Sonstige"
                            current_meta = {} # Reset metadata for new person
                            break
                    continue

                # 2. Check for Metadata Lines
                # Only check if we haven't seen any modules yet for this person? 
                # Or just check all non-module lines. Safe to check all non-module lines.
                is_meta = False
                for key, pattern in meta_patterns.items():
                    if pattern.search(line):
                        # Store the full line content as the value
                        # e.g. "Atemschutzgeräteträgerlehrgang Bestanden 09.04.2016 -23.04.2016"
                        # We might need to clean it up slightly if needed, but raw is fine.
                        current_meta[key] = line
                        is_meta = True
                        break
                
                if is_meta:
                    continue

                # 3. Check for QS Header
                qs_match = qs_pattern.search(line)
                if qs_match:
                    current_qs = qs_match.group(1).strip()
                    continue

                # 4. Check for Module
                match = module_pattern.search(line)
                if match:
                    mod_id = match.group(1)
                    title = match.group(2)
                    hours_part = match.group(3)
                    status = match.group(4)
                    
                    # Parse hours
                    hours_data = {
                        "T_Ist": 0.0, "T_Soll": 0.0,
                        "P_Ist": 0.0, "P_Soll": 0.0,
                        "K_Ist": 0.0, "K_Soll": 0.0
                    }
                    
                    for h_match in hours_pattern.finditer(hours_part):
                        type_code = h_match.group(1)
                        ist_str = h_match.group(2)
                        soll_str = h_match.group(3)
                        
                        code_map = {"T": "T", "P": "P", "K": "K"}
                        if type_code in code_map:
                            prefix = code_map[type_code]
                            hours_data[f"{prefix}_Ist"] = parse_time(ist_str)
                            hours_data[f"{prefix}_Soll"] = parse_time(soll_str)

                    # Add metadata fields to the module record
                    # Using prefix 'meta_' to distinguish
                    meta_fields = {f"meta_{k}": v for k, v in current_meta.items()}

                    modules.append({
                        "person_name": current_person,
                        "id": mod_id,
                        "title": title.strip(),
                        "status": status,
                        "qs_level": current_qs,
                        **hours_data,
                        **meta_fields
                    })
                    
    return modules
