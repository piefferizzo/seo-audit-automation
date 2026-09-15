"""
Helper condivisi per la classificazione a soglie.

Estratto da audit_processor.py per essere usato anche dalle regole
in processors/rules/*.py senza creare import circolari.
"""
from typing import Tuple


def classify_threshold(
    value: float,
    critical: float,
    warning: float,
    higher_is_worse: bool = True,
) -> Tuple[str, int]:
    """Classifica un valore in OK/WARN/FAIL confrontandolo con due soglie.

    Ritorna una tupla (stato, severità):
      - stato: "OK", "WARN", "FAIL"
      - severità: 0 (OK), 2 (WARN), 1 (FAIL)
    """
    if higher_is_worse:
        if value > critical:
            return "FAIL", 1
        elif value > warning:
            return "WARN", 2
        return "OK", 0
    else:
        if value < critical:
            return "FAIL", 1
        elif value < warning:
            return "WARN", 2
        return "OK", 0