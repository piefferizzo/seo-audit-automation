import os
import yaml
from typing import Dict, Any
from collectors.base_collector import BaseCollector

class GA4Collector(BaseCollector):
    """Raccoglie dati da Google Analytics 4 API con lookup ibrido (file YAML + fallback automatico)."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.service_account_file = config.get("GA4_SERVICE_ACCOUNT_FILE", "credentials/service-account.json")
        self.property_cache = {}
        
        # Carica la mappatura dal file YAML
        self.properties_map = self._load_properties_map()
    
    def _load_properties_map(self) -> Dict[str, str]:
        """Carica la mappatura dominio → Property ID dal file YAML."""
        yaml_path = "ga4_properties.yaml"
        if not os.path.exists(yaml_path):
            self.logger.warning(f"⚠️  File {yaml_path} non trovato. Creo template vuoto.")
            # Crea un template vuoto
            with open(yaml_path, 'w', encoding='utf-8') as f:
                f.write("# Mappatura domini → Property ID GA4\n")
                f.write("# Aggiungi qui tutti i clienti con il loro Property ID\n\n")
                f.write("properties:\n")
                f.write("  # esempio.com: \"123456789\"\n")
            return {}
        
        try:
            with open(yaml_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
                properties = data.get('properties', {})
                self.logger.info(f"  ✓ Caricati {len(properties)} domini da ga4_properties.yaml")
                return properties
        except Exception as e:
            self.logger.error(f"Errore lettura ga4_properties.yaml: {e}")
            return {}
    
    def is_available(self) -> bool:
        return bool(self.service_account_file and os.path.exists(self.service_account_file))
    
    def _get_data_client(self):
        """Crea il client per i dati analytics."""
        try:
            from google.analytics.data_v1beta import BetaAnalyticsDataClient
            from google.oauth2 import service_account
            
            credentials = service_account.Credentials.from_service_account_file(
                self.service_account_file
            )
            return BetaAnalyticsDataClient(credentials=credentials)
        except Exception as e:
            self.logger.error(f"Errore autenticazione GA4 Data: {e}")
            return None
    
    def _find_property_for_domain(self, domain: str) -> str:
        """Trova il Property ID per un dominio (lookup ibrido)."""
        
        # Pulisci il dominio
        clean_domain = domain.replace('https://', '').replace('http://', '').replace('www.', '').split('/')[0]
        
        # 1. Controlla la cache
        if clean_domain in self.property_cache:
            self.logger.info(f"  ✓ Property ID trovato in cache per {clean_domain}")
            return self.property_cache[clean_domain]
        
        # 2. Cerca nel file YAML (metodo principale)
        if clean_domain in self.properties_map:
            property_id = self.properties_map[clean_domain]
            self.logger.info(f"  ✓ Property ID trovato in ga4_properties.yaml: {property_id}")
            self.property_cache[clean_domain] = property_id
            return property_id
        
        # 3. Fallback: prova varianti del dominio
        variants = [
            clean_domain,
            clean_domain.replace('www.', ''),
            f"www.{clean_domain}",
        ]
        
        for variant in variants:
            if variant in self.properties_map:
                property_id = self.properties_map[variant]
                self.logger.info(f"  ✓ Property ID trovato per variante '{variant}': {property_id}")
                self.property_cache[clean_domain] = property_id
                return property_id
        
        # 4. Nessun Property ID trovato
        self.logger.warning(f"  ⚠️  Nessun Property ID configurato per {clean_domain}")
        self.logger.info(f"  ℹ️  Aggiungi '{clean_domain}' al file ga4_properties.yaml")
        
        if self.properties_map:
            self.logger.info(f"  ℹ️  Domini configurati:")
            for d, pid in self.properties_map.items():
                self.logger.info(f"    → {d}: {pid}")
        
        return ""
    
    def collect(self, domain: str) -> Dict[str, Any]:
        if not self.is_available():
            self.logger.warning("GA4 non configurato. Skip.")
            return {}
        
        self.logger.info(f"🔍 Raccolta dati GA4 per {domain}...")
        
        # Trova il Property ID per questo dominio
        property_id = self._find_property_for_domain(domain)
        
        if not property_id:
            return {}
        
        # Usa il data client per raccogliere i dati
        data_client = self._get_data_client()
        if not data_client:
            return {}
        
        try:
            results = {}
            
            # 1. Overview
            results['overview'] = self._get_overview(data_client, property_id)
            
            # 2. Top Pagine
            results['top_pages'] = self._get_top_pages(data_client, property_id)
            
            # 3. Sorgenti di Traffico
            results['traffic_sources'] = self._get_traffic_sources(data_client, property_id)
            
            # 4. Dispositivi
            results['devices'] = self._get_devices(data_client, property_id)
            
            # 5. Engagement
            results['engagement'] = self._get_engagement(data_client, property_id)
            
            self.logger.info(f"  ✓ Dati GA4 raccolti per property {property_id}")
            
        except Exception as e:
            self.logger.error(f"  ✗ Errore raccolta dati GA4: {e}")
        
        return results
    
    def _get_overview(self, client, property_id: str) -> Dict[str, Any]:
        """Recupera sessioni, utenti e pagine viste."""
        try:
            from google.analytics.data_v1beta.types import DateRange, Metric, RunReportRequest
            from datetime import datetime, timedelta
            
            request = RunReportRequest(
                property=f"properties/{property_id}",
                date_ranges=[DateRange(
                    start_date=(datetime.now() - timedelta(days=28)).strftime('%Y-%m-%d'),
                    end_date=datetime.now().strftime('%Y-%m-%d')
                )],
                metrics=[
                    Metric(name="sessions"),
                    Metric(name="totalUsers"),
                    Metric(name="screenPageViews"),
                    Metric(name="sessionsPerUser"),
                ]
            )
            
            response = client.run_report(request)
            
            if response.rows:
                row = response.rows[0]
                return {
                    'sessions': int(row.metric_values[0].value),
                    'users': int(row.metric_values[1].value),
                    'pageviews': int(row.metric_values[2].value),
                    'sessions_per_user': float(row.metric_values[3].value),
                }
            return {}
            
        except Exception as e:
            self.logger.warning(f"Errore overview GA4: {e}")
            return {}
    
    def _get_top_pages(self, client, property_id: str) -> Dict[str, Any]:
        """Recupera le top 10 pagine più visitate."""
        try:
            from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, RunReportRequest, OrderBy
            from datetime import datetime, timedelta
            
            request = RunReportRequest(
                property=f"properties/{property_id}",
                date_ranges=[DateRange(
                    start_date=(datetime.now() - timedelta(days=28)).strftime('%Y-%m-%d'),
                    end_date=datetime.now().strftime('%Y-%m-%d')
                )],
                dimensions=[Dimension(name="pagePath")],
                metrics=[Metric(name="screenPageViews")],
                order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="screenPageViews"), desc=True)],
                limit=10
            )
            
            response = client.run_report(request)
            
            pages = []
            for row in response.rows:
                pages.append({
                    'path': row.dimension_values[0].value,
                    'views': int(row.metric_values[0].value)
                })
            
            return {'pages': pages}
            
        except Exception as e:
            self.logger.warning(f"Errore top pages GA4: {e}")
            return {'pages': []}
    
    def _get_traffic_sources(self, client, property_id: str) -> Dict[str, Any]:
        """Recupera le sorgenti di traffico."""
        try:
            from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, RunReportRequest
            from datetime import datetime, timedelta
            
            request = RunReportRequest(
                property=f"properties/{property_id}",
                date_ranges=[DateRange(
                    start_date=(datetime.now() - timedelta(days=28)).strftime('%Y-%m-%d'),
                    end_date=datetime.now().strftime('%Y-%m-%d')
                )],
                dimensions=[Dimension(name="sessionDefaultChannelGroup")],
                metrics=[Metric(name="sessions")],
                limit=10
            )
            
            response = client.run_report(request)
            
            sources = []
            for row in response.rows:
                sources.append({
                    'source': row.dimension_values[0].value,
                    'sessions': int(row.metric_values[0].value)
                })
            
            return {'sources': sources}
            
        except Exception as e:
            self.logger.warning(f"Errore traffic sources GA4: {e}")
            return {'sources': []}
    
    def _get_devices(self, client, property_id: str) -> Dict[str, Any]:
        """Recupera la distribuzione per dispositivo."""
        try:
            from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, RunReportRequest
            from datetime import datetime, timedelta
            
            request = RunReportRequest(
                property=f"properties/{property_id}",
                date_ranges=[DateRange(
                    start_date=(datetime.now() - timedelta(days=28)).strftime('%Y-%m-%d'),
                    end_date=datetime.now().strftime('%Y-%m-%d')
                )],
                dimensions=[Dimension(name="deviceCategory")],
                metrics=[Metric(name="sessions")],
            )
            
            response = client.run_report(request)
            
            devices = {}
            for row in response.rows:
                device = row.dimension_values[0].value
                sessions = int(row.metric_values[0].value)
                devices[device] = sessions
            
            return {'devices': devices}
            
        except Exception as e:
            self.logger.warning(f"Errore devices GA4: {e}")
            return {'devices': {}}
    
    def _get_engagement(self, client, property_id: str) -> Dict[str, Any]:
        """Recupera metriche di engagement."""
        try:
            from google.analytics.data_v1beta.types import DateRange, Metric, RunReportRequest
            from datetime import datetime, timedelta
            
            request = RunReportRequest(
                property=f"properties/{property_id}",
                date_ranges=[DateRange(
                    start_date=(datetime.now() - timedelta(days=28)).strftime('%Y-%m-%d'),
                    end_date=datetime.now().strftime('%Y-%m-%d')
                )],
                metrics=[
                    Metric(name="averageSessionDuration"),
                    Metric(name="bounceRate"),
                    Metric(name="engagedSessions"),
                ]
            )
            
            response = client.run_report(request)
            
            if response.rows:
                row = response.rows[0]
                return {
                    'avg_session_duration': float(row.metric_values[0].value),
                    'bounce_rate': float(row.metric_values[1].value),
                    'engaged_sessions': int(row.metric_values[2].value),
                }
            return {}
            
        except Exception as e:
            self.logger.warning(f"Errore engagement GA4: {e}")
            return {}