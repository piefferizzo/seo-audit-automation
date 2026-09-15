"""
Regole HTML strutturali.

v2.4.0 — quinta estrazione: H-05 (Images Alt Tag), H-06 (Structured Data),
H-07 (Open Graph), H-08 (Hreflang).
"""
from typing import Dict, Any, List

from processors.rules.base_rule import BaseRule
from processors.models.finding import make_audit_row


class HTMLStructureRules(BaseRule):
    """Regole H-05, H-06, H-07, H-08 basate sulla struttura HTML della homepage."""

    category = "HTML"
    audit_ids = ["H-05", "H-06", "H-07", "H-08"]

    def is_applicable(self, raw_data: Dict[str, Any]) -> bool:
        html = raw_data.get("html", {}) or {}
        homepage = html.get("homepage", {}) or {}
        return bool(homepage) and "error" not in homepage

    def evaluate(self, raw_data: Dict[str, Any], domain: str) -> List[Dict]:
        html = raw_data.get("html", {}) or {}
        homepage = html.get("homepage", {}) or {}

        if not homepage or "error" in homepage:
            return []

        rows: List[Dict] = []
        url = homepage.get("url", "")

        # --------------------------------------------------------------
        # H-05 — Images Alt Tag
        # --------------------------------------------------------------
        images = homepage.get("images", [])
        total_images = len(images)
        images_without_alt = len([img for img in images if not img.get("alt")])
        alt_percentage = (images_without_alt / total_images * 100) if total_images > 0 else 0

        if total_images == 0:
            stato, sev, risultato, note = "OK", 0, "Nessuna immagine sulla homepage", ""
        elif alt_percentage == 0:
            stato, sev, risultato, note = "OK", 0, f"Tutte le {total_images} immagini hanno alt text", ""
        elif alt_percentage < 10:
            stato, sev = "WARN", 2
            risultato = f"{images_without_alt}/{total_images} immagini senza alt ({alt_percentage:.1f}%)"
            note = "Correzione minore, ma utile per accessibilità"
        else:
            stato, sev = "FAIL", 1
            risultato = f"{images_without_alt}/{total_images} immagini senza alt ({alt_percentage:.1f}%)"
            note = "Aggiungere alt text descrittivi"

        rows.append(make_audit_row("H-05", "HTML", "Images Alt Tag", stato, sev, risultato, url, note))

        # --------------------------------------------------------------
        # H-06 — Structured Data (Schema.org)
        # --------------------------------------------------------------
        structured_data = homepage.get("structured_data", [])
        rows.append(make_audit_row(
            "H-06", "HTML", "Structured Data (Schema.org)",
            "OK" if structured_data else "FAIL", 0 if structured_data else 1,
            f"{len(structured_data)} blocchi presenti" if structured_data else "Non presenti",
            url,
            "Implementare markup Schema.org" if not structured_data else "",
        ))

        # --------------------------------------------------------------
        # H-07 — Open Graph
        # --------------------------------------------------------------
        og_tags = homepage.get("og_tags", {})
        rows.append(make_audit_row(
            "H-07", "HTML", "Open Graph",
            "OK" if og_tags else "WARN", 0 if og_tags else 2,
            f"{len(og_tags)} tag presenti" if og_tags else "Non presenti",
            url,
        ))

        # --------------------------------------------------------------
        # H-08 — Hreflang
        # --------------------------------------------------------------
        hreflang = homepage.get("hreflang", [])
        lang = homepage.get("lang", "")
        valid_hreflang = [h for h in hreflang if h.get("href")]

        if len(valid_hreflang) > 0:
            stato, sev, risultato, note = "OK", 0, f"{len(valid_hreflang)} lingue presenti", ""
        elif not lang or lang in ["it", "it-IT", "en", "en-US"]:
            stato, sev = "N/A", 0
            risultato = f"Non necessario (sito monolingua: {lang or 'non specificato'})"
            note = ""
        else:
            stato, sev, risultato, note = "WARN", 2, "Non presente", ""

        rows.append(make_audit_row("H-08", "HTML", "Hreflang", stato, sev, risultato, url, note))

        return rows
