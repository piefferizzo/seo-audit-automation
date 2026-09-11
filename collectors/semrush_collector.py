import requests
import os
from typing import Dict, Any, List
from collectors.base_collector import BaseCollector


# ---------------------------------------------------------------------------
# COSTANTI — Configurazione Semrush API
# ---------------------------------------------------------------------------
SEMRUSH_API_URL = "https://api.semrush.com/"
DEFAULT_TIMEOUT = 30


# ---------------------------------------------------------------------------
# HELPER 1 — Parsing risposta Semrush (formato CSV-like)
# ---------------------------------------------------------------------------
def parse_semrush_response(response_text: str) -> List[Dict[str, str]]:
    """Parsa risposta Semrush (formato CSV con separatore ;)."""
    lines = response_text.strip().split('\n')
    if len(lines) < 2:
        return []
    
    headers = lines[0].split(';')
    results = []
    
    for line in lines[1:]:
        values = line.split(';')
        results.append(dict(zip(headers, values)))
    
    return results


class SemrushCollector(BaseCollector):
    """Raccoglie dati da Semrush API."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = os.getenv('SEMRUSH_API_KEY') or config.get("SEMRUSH_API_KEY", "")
    
    def is_available(self) -> bool:
        """Verifica se l'API key è configurata."""
        return bool(self.api_key)
    
    def collect(self, domain: str) -> Dict[str, Any]:
        """Raccoglie dati Semrush per il dominio."""
        if not self.is_available():
            self.logger.warning("API key Semrush non configurata. Skip.")
            return {}
        
        self.logger.info(f"🔍 Raccolta dati Semrush per {domain}...")
        
        try:
            # Domain overview
            overview = self._get_domain_overview(domain)
            
            # Organic keywords
            keywords = self._get_organic_keywords(domain)
            
            # Backlinks
            backlinks = self._get_backlinks(domain)
            
            return {
                'overview': overview,
                'keywords': keywords,
                'backlinks': backlinks
            }
            
        except Exception as e:
            self.logger.error(f"Errore raccolta dati Semrush: {e}")
            return {}
    
    def _get_domain_overview(self, domain: str) -> Dict[str, Any]:
        """Ottiene overview del dominio."""
        try:
            params = {
                'key': self.api_key,
                'type': 'domain_rank',
                'domain': domain,
                'export_columns': 'Dm,Rk,Or,Ot,Tr,Kw,Se,Do,At'
            }
            
            response = requests.get(SEMRUSH_API_URL, params=params, timeout=DEFAULT_TIMEOUT)
            if response.status_code == 200:
                data = parse_semrush_response(response.text)
                return data[0] if data else {}
            return {}
        except Exception as e:
            self.logger.warning(f"Errore domain overview: {e}")
            return {}
    
    def _get_organic_keywords(self, domain: str) -> List[Dict[str, str]]:
        """Ottiene keyword organiche."""
        try:
            params = {
                'key': self.api_key,
                'type': 'domain_organic',
                'domain': domain,
                'export_columns': 'Ph,Nq,Kd,Po,Tr',
                'limit': 10
            }
            
            response = requests.get(SEMRUSH_API_URL, params=params, timeout=DEFAULT_TIMEOUT)
            if response.status_code == 200:
                return parse_semrush_response(response.text)
            return []
        except Exception as e:
            self.logger.warning(f"Errore organic keywords: {e}")
            return []
    
    def _get_backlinks(self, domain: str) -> Dict[str, Any]:
        """Ottiene dati backlink."""
        try:
            params = {
                'key': self.api_key,
                'type': 'backlinks',
                'domain': domain,
                'export_columns': 'Source,Target,Anchor,Tld'
            }
            
            response = requests.get(SEMRUSH_API_URL, params=params, timeout=DEFAULT_TIMEOUT)
            if response.status_code == 200:
                lines = response.text.strip().split('\n')
                return {
                    'total': len(lines) - 1 if len(lines) > 1 else 0,
                    'sample': lines[1:6] if len(lines) > 1 else []
                }
            return {'total': 0, 'sample': []}
        except Exception as e:
            self.logger.warning(f"Errore backlinks: {e}")
            return {'total': 0, 'sample': []}