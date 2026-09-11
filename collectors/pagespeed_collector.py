import requests
import json
import os
from typing import Dict, Any, Optional
from collectors.base_collector import BaseCollector
from utils.cache import CacheManager


# ---------------------------------------------------------------------------
# COSTANTI — Configurazione PageSpeed API
# ---------------------------------------------------------------------------
PAGESPEED_API_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
DEFAULT_TIMEOUT = 120
CATEGORIES = ["PERFORMANCE", "ACCESSIBILITY"]


# ---------------------------------------------------------------------------
# HELPER 1 — Estrazione metriche da risposta PageSpeed
# ---------------------------------------------------------------------------
def extract_pagespeed_metrics(data: Dict[str, Any]) -> Dict[str, Any]:
    """Estrae metriche dalla risposta PageSpeed Insights API."""
    lighthouse = data.get("lighthouseResult", {})
    audits = lighthouse.get("audits", {})
    
    return {
        "performance_score": lighthouse.get("categories", {}).get("performance", {}).get("score", 0) * 100,
        "accessibility_score": lighthouse.get("categories", {}).get("accessibility", {}).get("score", 0) * 100,
        "lcp": float(audits.get("largest-contentful-paint", {}).get("numericValue", 0)) / 1000,
        "fcp": float(audits.get("first-contentful-paint", {}).get("numericValue", 0)) / 1000,
        "cls": float(audits.get("cumulative-layout-shift", {}).get("numericValue", 0)),
        "tti": float(audits.get("interactive", {}).get("numericValue", 0)) / 1000,
        "tbt": float(audits.get("total-blocking-time", {}).get("numericValue", 0)),
        "si": float(audits.get("speed-index", {}).get("numericValue", 0)) / 1000,
    }


class PageSpeedCollector(BaseCollector):
    """Raccoglie dati da Google PageSpeed Insights API."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = os.getenv('GOOGLE_PAGESPEED_API_KEY') or config.get("PAGE_SPEED_API_KEY", "")
        self.cache = CacheManager(cache_dir="cache")
    
    def is_available(self) -> bool:
        """Verifica se l'API key è configurata."""
        return bool(self.api_key)
    
    def collect(self, domain: str) -> Dict[str, Any]:
        """Raccoglie dati PageSpeed per mobile e desktop."""
        if not self.is_available():
            self.logger.warning("API key PageSpeed non configurata. Skip.")
            return {}
        
        self.logger.info(f"🔍 Raccolta dati PageSpeed per {domain}...")
        
        results = {}
        
        # Mobile
        mobile_data = self._analyze_url(domain, "mobile")
        if mobile_data:
            results["mobile"] = mobile_data
        
        # Desktop
        desktop_data = self._analyze_url(domain, "desktop")
        if desktop_data:
            results["desktop"] = desktop_data
        
        return results
    
    def _analyze_url(self, url: str, strategy: str) -> Optional[Dict[str, Any]]:
        """Analizza una URL con PageSpeed Insights."""
        # Controlla cache
        cached = self.cache.get_pagespeed(url, strategy)
        if cached:
            self.logger.info(f"✅ Cache HIT per {url} ({strategy})")
            return cached
        
        self.logger.info(f"🌐 Analisi {strategy} per {url}...")
        
        params = {
            "url": url,
            "strategy": strategy,
            "category": CATEGORIES,
            "key": self.api_key
        }
        
        try:
            response = requests.get(PAGESPEED_API_URL, params=params, timeout=DEFAULT_TIMEOUT)
            response.raise_for_status()
            data = response.json()
            
            # Estrai metriche usando helper
            result = extract_pagespeed_metrics(data)
            
            # Salva in cache
            self.cache.save_pagespeed(url, strategy, result)
            
            return result
            
        except Exception as e:
            self.logger.error(f"Errore PageSpeed per {url} ({strategy}): {e}")
            return None
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Restituisce le statistiche della cache."""
        return self.cache.get_stats()