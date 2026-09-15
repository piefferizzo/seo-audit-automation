"""
Regole meta HTML.

v2.4.0 — quarta estrazione: H-01 (Meta Title), H-02 (Meta Description),
H-03 (Canonical), H-04 (H1).

Questi 5 check leggono solo `homepage` (nessuna dipendenza da GSC,
PageSpeed o altri blocchi raw_data).
"""
from typing import Dict, Any, List

from processors.rules.base_rule import BaseRule
from processors.models.finding import make_audit_row


class HtmlMetaRules(BaseRule):
    """Regole H-01, H-02, H-03, H-04 basate su meta della homepage."""

    category = "HTML"
    audit_ids = ["H-01", "H-02", "H-03", "H-04"]

    def is_applicable(self, raw_data: Dict[str, Any]) -> bool:
        """Applicabile se c'è una homepage valida."""
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
        # H-01 — Meta Title
        # --------------------------------------------------------------
        title = homepage.get("title", "")
        title_len = len(title)

        if not title:
            stato, sev, risultato, note = "FAIL", 1, "Mancante", "Ottimizzare con keyword target"
        elif title_len < 30:
            stato, sev = "WARN", 2
            risultato = f"Presente ma troppo corto ({title_len} caratteri, ottimale: 50-60)"
            note = "Allungare il title a 50-60 caratteri"
        elif title_len > 60:
            stato, sev = "WARN", 2
            risultato = f"Presente ma troppo lungo ({title_len} caratteri, ottimale: 50-60)"
            note = "Accorciare il title a 50-60 caratteri"
        else:
            stato, sev, note = "OK", 0, ""
            risultato = f"Presente ({title_len} caratteri)"

        rows.append(make_audit_row("H-01", "HTML", "Meta Title", stato, sev, risultato, url, note))

        # --------------------------------------------------------------
        # H-02 — Meta Description
        # --------------------------------------------------------------
        description = homepage.get("meta_description", "")
        desc_len = len(description)

        if not description:
            stato, sev, risultato, note = "FAIL", 1, "Mancante", "Ottimizzare con keyword target"
        elif desc_len < 120:
            stato, sev = "WARN", 2
            risultato = f"Presente ma troppo corta ({desc_len} caratteri, ottimale: 120-160)"
            note = "Allungare la description a 120-160 caratteri"
        elif desc_len > 160:
            stato, sev = "WARN", 2
            risultato = f"Presente ma troppo lunga ({desc_len} caratteri, ottimale: 120-160)"
            note = "Accorciare la description a 120-160 caratteri"
        else:
            stato, sev, note = "OK", 0, ""
            risultato = f"Presente ({desc_len} caratteri)"

        rows.append(make_audit_row("H-02", "HTML", "Meta Description", stato, sev, risultato, url, note))

        # --------------------------------------------------------------
        # H-03 — Canonical
        # --------------------------------------------------------------
        canonical = homepage.get("canonical", "")
        rows.append(make_audit_row(
            "H-03", "HTML", "Canonical",
            "OK" if canonical else "FAIL", 0 if canonical else 1,
            "Presente" if canonical else "Mancante", url,
        ))

        # --------------------------------------------------------------
        # H-04 — Heading H1
        # --------------------------------------------------------------
        headings = homepage.get("headings", {})
        h1_count = len(headings.get("h1", []))
        rows.append(make_audit_row(
            "H-04", "HTML", "Heading H1",
            "OK" if h1_count == 1 else "FAIL",
            0 if h1_count == 1 else 1,
            f"{h1_count} H1 presente" if h1_count > 0 else "Nessun H1",
            url,
            "Ottimizzare con keyword target" if h1_count != 1 else "",
        ))

        # --------------------------------------------------------------
        return rows
