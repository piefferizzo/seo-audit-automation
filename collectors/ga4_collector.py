import os
import yaml
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from collectors.base_collector import BaseCollector


# ---------------------------------------------------------------------------
# HELPER 1 — Configurazione query GA4 (elimina duplicazioni)
# ---------------------------------------------------------------------------
GA4_SCOPES = ['https://www.googleapis.com/auth/analytics.readonly']

# Date range standard
DEFAULT_DATE_RANGE_DAYS = 28

# Metriche predefinite per tipo di report
GA4_METRICS = {
    'overview': ['sessions', 'totalUsers', 'screenPageViews'],
    'engagement': ['bounceRate', 'averageSessionDuration'],
    'sources': ['sessions'],
    'devices': ['sessions'],
    'pages': ['screenPageViews'],
}

# Dimensione predefinite per tipo di report
GA4_DIMENSIONS = {
    'sources': 'sessionDefaultChannelGroup',
    'devices': 'deviceCategory',
    'pages': 'pagePath',
}


def get_date_range(days_back: int = DEFAULT_DATE_RANGE_DAYS) -> Dict[str, str]:
    """Calcola date range per query GA4."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)
    
    return {
        'start': start_date.strftime('%Y-%m-%d'),
        'end': end_date.strftime('%Y-%m-%d'),
    }


def safe_float(value: Any, default: float = 0.0) -> float:
    """Converte valore in float in modo sicuro."""
    try:
        return float(value) if value else default
    except (ValueError, TypeError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    """Converte valore in int in modo sicuro."""
    try:
        return int(value) if value else default
    except (ValueError, TypeError):
        return default


class GA4Collector(BaseCollector):
    """Raccoglie dati da Google Analytics 4."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.credentials_file = config.get("GA4_CREDENTIALS_FILE", "credentials/ga4-credentials.json")
        self.properties_file = "ga4_properties.yaml"
        self._client = None
    
    def is_available(self) -> bool:
        """Verifica se le credenziali GA4 sono configurate."""
        return bool(self.credentials_file and os.path.exists(self.credentials_file))
    
    def _get_property_id(self, domain: str) -> Optional[str]:
        """Ottiene il Property ID per il dominio dal file di configurazione."""
        try:
            if not os.path.exists(self.properties_file):
                return None
            
            with open(self.properties_file, 'r', encoding='utf-8') as f:
                properties = yaml.safe_load(f)
            
            clean_domain = domain.replace('https://', '').replace('http://', '').replace('www.', '')
            
            # Match esatto
            if clean_domain in properties:
                return properties[clean_domain].get('property_id')
            
            # Match parziale
            for d, data in properties.items():
                if clean_domain in d or d in clean_domain:
                    return data.get('property_id')
            
            return None
        except Exception as e:
            self.logger.warning(f"Errore lettura property ID: {e}")
            return None
    
    def _get_client(self):
        """Crea il client GA4 (con cache)."""
        if self._client:
            return self._client
        
        try:
            from google.analytics.data_v1beta import BetaAnalyticsDataClient
            from google.oauth2 import service_account
            
            credentials = service_account.Credentials.from_service_account_file(
                self.credentials_file,
                scopes=GA4_SCOPES
            )
            
            self._client = BetaAnalyticsDataClient(credentials=credentials)
            return self._client
            
        except ImportError as e:
            self.logger.error(f"Librerie Google Analytics non installate: {e}")
            self.logger.error("Esegui: pip install google-analytics-data")
            return None
        except Exception as e:
            self.logger.error(f"Errore autenticazione GA4: {e}")
            return None
    
    def _run_query(self, client, property_id: str, dates: Dict[str, str],
                   metrics: List[str], dimensions: Optional[List[str]] = None,
                   order_by: Optional[str] = None, limit: int = 10) -> List[Dict]:
        """Esegue una query GA4 standardizzata.
        
        Args:
            client: Client GA4
            property_id: ID property GA4
            dates: Dict con 'start' e 'end'
            metrics: Lista nomi metriche
            dimensions: Lista nomi dimensioni (opzionale)
            order_by: Nome metrica per ordinamento (opzionale)
            limit: Limite risultati
        
        Returns:
            Lista di dict con risultati
        """
        try:
            from google.analytics.data_v1beta.types import (
                DateRange, Dimension, Metric, RunReportRequest, OrderBy
            )
            
            # Costruisci request
            request_params = {
                'property': f"properties/{property_id}",
                'date_ranges': [DateRange(start_date=dates['start'], end_date=dates['end'])],
                'metrics': [Metric(name=m) for m in metrics],
            }
            
            if dimensions:
                request_params['dimensions'] = [Dimension(name=d) for d in dimensions]
            
            if order_by:
                request_params['order_bys'] = [
                    OrderBy(metric=OrderBy.MetricOrderBy(metric_name=order_by), desc=True)
                ]
            
            if limit:
                request_params['limit'] = limit
            
            request = RunReportRequest(**request_params)
            response = client.run_report(request)
            
            # Estrai risultati
            results = []
            for row in response.rows:
                row_data = {}
                
                # Dimensioni
                if dimensions:
                    for i, dim in enumerate(dimensions):
                        row_data[dim] = row.dimension_values[i].value
                
                # Metriche
                for i, metric in enumerate(metrics):
                    row_data[metric] = row.metric_values[i].value
                
                results.append(row_data)
            
            return results
            
        except Exception as e:
            self.logger.warning(f"Errore query GA4: {e}")
            return []
    
    def collect(self, domain: str) -> Dict[str, Any]:
        """Raccoglie tutti i dati GA4 per il dominio."""
        if not self.is_available():
            self.logger.warning("Credenziali GA4 non configurate. Skip.")
            return {}
        
        property_id = self._get_property_id(domain)
        if not property_id:
            self.logger.warning(f"Nessun Property ID trovato per {domain}")
            return {}
        
        self.logger.info(f"🔍 Raccolta dati GA4 per {domain}...")
        self.logger.debug(f"  ✓ Property ID trovato: {property_id}")
        
        client = self._get_client()
        if not client:
            return {}
        
        # Date range standard
        dates = get_date_range()
        
        results = {}
        
        # 1. Overview
        results['overview'] = self._get_overview(client, property_id, dates)
        
        # 2. Engagement
        results['engagement'] = self._get_engagement(client, property_id, dates)
        
        # 3. Traffic sources
        results['traffic_sources'] = self._get_traffic_sources(client, property_id, dates)
        
        # 4. Devices
        results['devices'] = self._get_devices(client, property_id, dates)
        
        # 5. Top pages
        results['top_pages'] = self._get_top_pages(client, property_id, dates)
        
        self.logger.info(f"  ✓ Dati GA4 raccolti per property {property_id}")
        
        return results
    
    def _get_overview(self, client, property_id: str, dates: Dict[str, str]) -> Dict[str, Any]:
        """Ottiene overview generale."""
        rows = self._run_query(
            client, property_id, dates,
            metrics=GA4_METRICS['overview']
        )
        
        if not rows:
            return {}
        
        row = rows[0]
        return {
            'sessions': safe_int(row.get('sessions', 0)),
            'users': safe_int(row.get('totalUsers', 0)),
            'pageviews': safe_int(row.get('screenPageViews', 0)),
        }
    
    def _get_engagement(self, client, property_id: str, dates: Dict[str, str]) -> Dict[str, Any]:
        """Ottiene metriche di engagement."""
        rows = self._run_query(
            client, property_id, dates,
            metrics=GA4_METRICS['engagement']
        )
        
        if not rows:
            return {}
        
        row = rows[0]
        return {
            'bounce_rate': safe_float(row.get('bounceRate', 0)),
            'avg_session_duration': safe_float(row.get('averageSessionDuration', 0)),
        }
    
    def _get_traffic_sources(self, client, property_id: str, dates: Dict[str, str]) -> Dict[str, Any]:
        """Ottiene dati sulle sorgenti di traffico."""
        rows = self._run_query(
            client, property_id, dates,
            metrics=GA4_METRICS['sources'],
            dimensions=[GA4_DIMENSIONS['sources']],
            order_by='sessions',
            limit=10
        )
        
        sources = []
        for row in rows:
            sources.append({
                'source': row.get('sessionDefaultChannelGroup', ''),
                'sessions': safe_int(row.get('sessions', 0))
            })
        
        return {'sources': sources}
    
    def _get_devices(self, client, property_id: str, dates: Dict[str, str]) -> Dict[str, Any]:
        """Ottiene dati sui dispositivi."""
        rows = self._run_query(
            client, property_id, dates,
            metrics=GA4_METRICS['devices'],
            dimensions=[GA4_DIMENSIONS['devices']]
        )
        
        devices = {}
        for row in rows:
            device = row.get('deviceCategory', '').lower()
            devices[device] = safe_int(row.get('sessions', 0))
        
        return {'devices': devices}
    
    def _get_top_pages(self, client, property_id: str, dates: Dict[str, str]) -> Dict[str, Any]:
        """Ottiene le top pagine."""
        rows = self._run_query(
            client, property_id, dates,
            metrics=GA4_METRICS['pages'],
            dimensions=[GA4_DIMENSIONS['pages']],
            order_by='screenPageViews',
            limit=10
        )
        
        pages = []
        for row in rows:
            pages.append({
                'path': row.get('pagePath', ''),
                'views': safe_int(row.get('screenPageViews', 0))
            })
        
        return {'pages': pages}