import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
from utils.logger import setup_logger


# ---------------------------------------------------------------------------
# COSTANTI — Configurazione cache
# ---------------------------------------------------------------------------
DEFAULT_CACHE_DIR = "cache"
DEFAULT_TTL_HOURS = 24
STATS_FILE = "cache_stats.json"


# ---------------------------------------------------------------------------
# HELPER 1 — Generazione cache key
# ---------------------------------------------------------------------------
def generate_cache_key(prefix: str, url: str, strategy: str = "") -> str:
    """Genera una cache key standardizzata."""
    url_clean = url.replace('https://', '').replace('http://', '').replace('/', '_')
    if strategy:
        return f"{prefix}_{url_clean}_{strategy}"
    return f"{prefix}_{url_clean}"


# ---------------------------------------------------------------------------
# HELPER 2 — Lettura/scrittura JSON sicura
# ---------------------------------------------------------------------------
def read_json_file(file_path: Path) -> Optional[Dict[str, Any]]:
    """Legge un file JSON in modo sicuro."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def write_json_file(file_path: Path, data: Dict[str, Any]):
    """Scrive un file JSON in modo sicuro."""
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        raise Exception(f"Errore scrittura file {file_path}: {e}")


class CacheManager:
    """Gestisce la cache per i dati PageSpeed e altre API."""
    
    def __init__(self, cache_dir: str = DEFAULT_CACHE_DIR, default_ttl_hours: int = DEFAULT_TTL_HOURS):
        self.cache_dir = Path(cache_dir)
        self.default_ttl_hours = default_ttl_hours
        self.logger = setup_logger("CacheManager")
        
        # Crea directory cache se non esiste
        self.cache_dir.mkdir(exist_ok=True)
        
        # File statistiche cache
        self.stats_file = self.cache_dir / STATS_FILE
        
        # Carica statistiche esistenti
        self.stats = self._load_stats()
    
    def _load_stats(self) -> Dict[str, int]:
        """Carica le statistiche della cache."""
        data = read_json_file(self.stats_file)
        return data if data else {'hits': 0, 'misses': 0}
    
    def _save_stats(self):
        """Salva le statistiche della cache."""
        try:
            write_json_file(self.stats_file, self.stats)
        except Exception as e:
            self.logger.warning(f"Errore salvataggio statistiche cache: {e}")
    
    def get_pagespeed(self, url: str, strategy: str) -> Optional[Dict[str, Any]]:
        """Ottiene dati PageSpeed dalla cache se disponibili e non scaduti."""
        cache_key = generate_cache_key("pagespeed", url, strategy)
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        if not cache_file.exists():
            self.stats['misses'] += 1
            self._save_stats()
            return None
        
        cache_data = read_json_file(cache_file)
        if not cache_data:
            self.stats['misses'] += 1
            self._save_stats()
            return None
        
        # Verifica età
        try:
            cached_time = datetime.fromisoformat(cache_data['timestamp'])
            age_hours = (datetime.now() - cached_time).total_seconds() / 3600
            
            if age_hours > self.default_ttl_hours:
                self.logger.debug(f"Cache scaduta per {url} ({strategy}) - età: {age_hours:.1f}h")
                self.stats['misses'] += 1
                self._save_stats()
                return None
            
            self.stats['hits'] += 1
            self._save_stats()
            self.logger.debug(f"Cache HIT per {url} ({strategy}) - età: {age_hours:.1f}h")
            
            return cache_data['data']
            
        except Exception as e:
            self.logger.warning(f"Errore lettura cache per {url}: {e}")
            self.stats['misses'] += 1
            self._save_stats()
            return None
    
    def save_pagespeed(self, url: str, strategy: str, data: Dict[str, Any]):
        """Salva dati PageSpeed nella cache."""
        cache_key = generate_cache_key("pagespeed", url, strategy)
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        cache_data = {
            'url': url,
            'strategy': strategy,
            'timestamp': datetime.now().isoformat(),
            'data': data
        }
        
        try:
            write_json_file(cache_file, cache_data)
            self.logger.debug(f"Dati PageSpeed salvati in cache per {url} ({strategy})")
        except Exception as e:
            self.logger.warning(f"Errore salvataggio cache per {url}: {e}")
    
    def get_stats(self) -> Dict[str, int]:
        """Restituisce le statistiche della cache."""
        return self.stats
    
    def clear(self, domain: str = None):
        """Pulisce la cache.
        
        Args:
            domain: Se specificato, pulisce solo la cache per quel dominio.
                   Altrimenti pulisce tutta la cache.
        """
        try:
            if domain:
                # Pulisci solo cache per questo dominio
                domain_clean = domain.replace('https://', '').replace('http://', '').replace('/', '_')
                for cache_file in self.cache_dir.glob(f"*{domain_clean}*"):
                    cache_file.unlink()
                self.logger.info(f"Cache pulita per {domain}")
            else:
                # Pulisci tutta la cache
                for cache_file in self.cache_dir.glob("*.json"):
                    if cache_file.name != STATS_FILE:
                        cache_file.unlink()
                self.logger.info("Tutta la cache è stata pulita")
            
            # Reset statistiche
            self.stats = {'hits': 0, 'misses': 0}
            self._save_stats()
            
        except Exception as e:
            self.logger.error(f"Errore nella pulizia della cache: {e}")