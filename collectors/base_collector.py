from abc import ABC, abstractmethod
from typing import Dict, Any
from utils.logger import setup_logger


class BaseCollector(ABC):
    """Classe base per tutti i collector."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = setup_logger(self.__class__.__name__)
    
    @abstractmethod
    def collect(self, domain: str) -> Dict[str, Any]:
        """Raccoglie dati per il dominio specificato."""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Verifica se il collector è disponibile (credenziali, API key, ecc.)."""
        pass