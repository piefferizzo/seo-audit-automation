import requests
from typing import Dict, Any
from collectors.base_collector import BaseCollector

class SemrushCollector(BaseCollector):
    """Raccoglie dati da Semrush API (Site Audit + Backlink + Organic)."""
    
    BASE_URL = "https://api.semrush.com/"
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get("SEMRUSH_API_KEY")
    
    def is_available(self) -> bool:
        return bool(self.api_key)
    
    def _call_api(self, params: Dict[str, Any]) -> Dict[str, Any]:
        params["key"] = self.api_key
        try:
            response = requests.get(self.BASE_URL, params=params, timeout=60)
            response.raise_for_status()
            # Semrush restituisce CSV o JSON a seconda del parametro
            return response.json() if "json" in str(params) else {"raw": response.text}
        except Exception as e:
            self.logger.error(f"Errore Semrush: {e}")
            return {}
    
    def collect(self, domain: str) -> Dict[str, Any]:
        if not self.is_available():
            self.logger.warning("Semrush API key non configurata. Skip.")
            return {}
        
        self.logger.info(f"🔍 Raccolta dati Semrush per {domain}...")
        clean_domain = domain.replace("https://", "").replace("http://", "").rstrip("/")
        
        results = {}
        
        # 1. Site Audit
        self.logger.info("  → Site Audit...")
        audit_params = {
            "type": "domain_audit",
            "domain": clean_domain,
            "export_columns": "Dt,Dn,Rr,Url,Nr,To,Th,Or,Ts",
            "export_escape": 1
        }
        results["site_audit"] = self._call_api(audit_params)
        
        # 2. Backlink Analytics
        self.logger.info("  → Backlink Analytics...")
        backlink_params = {
            "type": "backlinks",
            "domain": clean_domain,
            "export_columns": "Dm,Rk,At,Fi,Fd,Lm,Tl,Fl",
            "export_escape": 1
        }
        results["backlinks"] = self._call_api(backlink_params)
        
        # 3. Organic Research (keyword posizionate)
        self.logger.info("  → Organic Research...")
        organic_params = {
            "type": "domain_rank",
            "domain": clean_domain,
            "export_columns": "Dm,Rk,Or,Ot,Oc,Kd,Nr"
        }
        results["organic"] = self._call_api(organic_params)
        
        self.logger.info("  ✓ Dati Semrush raccolti")
        return results