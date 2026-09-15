"""
Interfaccia base per le regole di audit.

Ogni categoria di regole (PageSpeed, GSC, GA4, HTML, ecc.) estende
BaseRule e implementa is_applicable() + evaluate().
"""
from typing import Dict, Any, List
from abc import ABC, abstractmethod

from utils.logger import setup_logger


class BaseRule(ABC):
    """Classe base per le regole di audit.

    Attributi di classe da sovrascrivere:
        category: nome categoria (es. "Usability", "Technical")
        audit_ids: lista degli ID audit prodotti (es. ["U-01", "U-02"])
    """

    category: str = ""
    audit_ids: List[str] = []

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = setup_logger(self.__class__.__name__)

    @abstractmethod
    def is_applicable(self, raw_data: Dict[str, Any]) -> bool:
        """Ritorna True se ci sono i dati necessari."""
        raise NotImplementedError

    @abstractmethod
    def evaluate(self, raw_data: Dict[str, Any], domain: str) -> List[Dict]:
        """Valuta la regola e ritorna le righe di audit (dict a 8 chiavi)."""
        raise NotImplementedError
