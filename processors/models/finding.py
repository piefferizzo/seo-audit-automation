"""
Modello Finding — rappresenta un singolo risultato di audit.

Questo modello è il cuore della futura SEO Intelligence: permette di
separare i dati (finding) dalle regole (come li calcoliamo) e
dall'output (come li rappresentiamo).

Attualmente il processor usa ancora i dict a 8 chiavi per retrocompatibilità.
La funzione `make_audit_row` in `audit_processor.py` è un wrapper che
restituisce il dict classico costruito a partire da un Finding.

Uso diretto (nuovo):
    from processors.models.finding import Finding, make_finding
    f = make_finding("U-01", "Usability", "CWV", "FAIL", 1, "LCP 4.8s")
    f.status           # "FAIL"
    f.is_fail()        # True
    f.to_audit_dict()  # dict a 8 chiavi per il processor
    f.to_dict()        # dict completo per JSON output futuro
"""
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any


# ---------------------------------------------------------------------------
# Costanti di stato
# ---------------------------------------------------------------------------
STATUS_OK = "OK"
STATUS_WARN = "WARN"
STATUS_FAIL = "FAIL"
STATUS_INFO = "INFO"
STATUS_NA = "N/A"

VALID_STATUSES = {STATUS_OK, STATUS_WARN, STATUS_FAIL, STATUS_INFO, STATUS_NA}

# ---------------------------------------------------------------------------
# Costanti di severità
# ---------------------------------------------------------------------------
SEVERITY_NONE = 0       # nessun problema
SEVERITY_HIGH = 1       # critico
SEVERITY_MEDIUM = 2     # da migliorare

VALID_SEVERITIES = {SEVERITY_NONE, SEVERITY_HIGH, SEVERITY_MEDIUM}


# ---------------------------------------------------------------------------
# Modello
# ---------------------------------------------------------------------------
@dataclass
class Finding:
    """Rappresenta un singolo risultato di audit.

    Campi core (obbligatori) — corrispondono ai primi 6 del dict a 8 chiavi:
        audit_id, category, element, status, severity, result

    Campi opzionali:
        url, notes

    Campi estesi (opzionali, per la SEO Intelligence futura):
        source, metric, value, threshold, recommendation,
        estimated_effort, business_impact
    """

    # --- Campi core ---
    audit_id: str
    category: str
    element: str
    status: str
    severity: int
    result: str

    # --- Campi di evidenza ---
    url: str = ""
    notes: str = ""

    # --- Campi estesi (futuri) ---
    source: str = ""
    metric: str = ""
    value: Optional[float] = None
    threshold: str = ""
    recommendation: str = ""
    estimated_effort: str = ""      # "low" | "medium" | "high"
    business_impact: str = ""       # "low" | "medium" | "high"

    def __post_init__(self):
        if self.status not in VALID_STATUSES:
            raise ValueError(
                f"Status non valido: '{self.status}'. "
                f"Valori ammessi: {sorted(VALID_STATUSES)}"
            )
        if self.severity not in VALID_SEVERITIES:
            raise ValueError(
                f"Severity non valida: {self.severity}. "
                f"Valori ammessi: {sorted(VALID_SEVERITIES)}"
            )

    # ------------------------------------------------------------------
    # Conversioni
    # ------------------------------------------------------------------
    def to_audit_dict(self) -> Dict[str, Any]:
        """Restituisce il dict a 8 chiavi usato dal processor e dal generator.

        Retrocompatibile con il vecchio `make_audit_row`.
        """
        return {
            "ID Audit": self.audit_id,
            "Categoria": self.category,
            "Elemento Analizzato": self.element,
            "Stato": self.status,
            "Severità": self.severity,
            "Risultato / Evidenza": self.result,
            "URL / Link Evidenza": self.url,
            "Note Tecniche": self.notes,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serializzazione completa (per JSON output futuro)."""
        return asdict(self)

    # ------------------------------------------------------------------
    # Helper di stato
    # ------------------------------------------------------------------
    def is_fail(self) -> bool:
        return self.status == STATUS_FAIL

    def is_warn(self) -> bool:
        return self.status == STATUS_WARN

    def is_ok(self) -> bool:
        return self.status == STATUS_OK

    def is_info(self) -> bool:
        return self.status == STATUS_INFO

    def is_na(self) -> bool:
        return self.status == STATUS_NA


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
def make_finding(
    audit_id: str,
    categoria: str,
    elemento: str,
    stato: str,
    severita: int,
    risultato: str,
    url: str = "",
    note: str = "",
    **kwargs,
) -> Finding:
    """Costruisce un Finding con nomi italiani per compatibilità col processor.

    I nomi italiani ricalcano quelli usati da `make_audit_row` così che il
    passaggio da dict a Finding sia meccanico.

    Argomenti extra (**kwargs) vengono passati al costruttore e possono
    essere usati per source, metric, value, threshold, recommendation,
    estimated_effort, business_impact.
    """
    return Finding(
        audit_id=audit_id,
        category=categoria,
        element=elemento,
        status=stato,
        severity=severita,
        result=risultato,
        url=url,
        notes=note,
        **kwargs,
    )