import json
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from utils.logger import setup_logger

class CacheManager:
    """Gestisce la cache per i dati PageSpeed e altre API."""
    
    def __init__(self, cache_dir: str = "cache", default_ttl_hours: int = 24):
        self.cache_dir = Path(cache_dir)
        self.default_ttl_hours = default_ttl_hours
        self.logger = setup_logger("CacheManager")
        
        # Crea directory cache se non esiste
        self.cache_dir.mkdir(exist_ok=True)
        
        # File statistiche cache
        self.stats_file = self.cache_dir / "cache_stats.json"
        
        # Carica statistiche esistenti
        self.stats = self._load_stats()
    
    def _load_stats(self) -> Dict[str, int]:
        """Carica le statistiche della cache."""
        if self.stats_file.exists():
            try:
                with open(self.stats_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {'hits': 0, 'misses': 0}
    
    def _save_stats(self):
        """Salva le statistiche della cache."""
        try:
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                json.dump(self.stats, f, indent=2)
        except Exception as e:
            self.logger.warning(f"Errore salvataggio statistiche cache: {e}")
    
    def get_pagespeed(self, url: str, strategy: str) -> Optional[Dict[str, Any]]:
        """Ottiene dati PageSpeed dalla cache se disponibili e non scaduti."""
        cache_key = f"pagespeed_{url.replace('https://', '').replace('http://', '').replace('/', '_')}_{strategy}"
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        if not cache_file.exists():
            self.stats['misses'] += 1
            self._save_stats()
            return None
        
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # Verifica età
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
        cache_key = f"pagespeed_{url.replace('https://', '').replace('http://', '').replace('/', '_')}_{strategy}"
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        cache_data = {
            'url': url,
            'strategy': strategy,
            'timestamp': datetime.now().isoformat(),
            'data': data
        }
        
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2)
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
                    if cache_file.name != "cache_stats.json":
                        cache_file.unlink()
                self.logger.info("Tutta la cache è stata pulita")
            
            # Reset statistiche
            self.stats = {'hits': 0, 'misses': 0}
            self._save_stats()
            
        except Exception as e:
            self.logger.error(f"Errore nella pulizia della cache: {e}")