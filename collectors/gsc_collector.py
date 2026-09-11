import os
import time
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from collectors.base_collector import BaseCollector


# ---------------------------------------------------------------------------
# HELPER — Configurazione query GSC (elimina duplicazioni)
# ---------------------------------------------------------------------------
GSC_SCOPES = ['https://www.googleapis.com/auth/webmasters.readonly']

# Date range standard per analisi
DEFAULT_DATE_RANGE_DAYS = 28
COMPARISON_DATE_RANGE_DAYS = 28

# Dimension queries predefinite
DIMENSION_QUERIES = {
    'pages': {'dimensions': ['page'], 'rowLimit': 100},
    'queries': {'dimensions': ['query'], 'rowLimit': 1000},
    'devices': {'dimensions': ['device'], 'rowLimit': 10},
}


def get_date_ranges(days_back: int = DEFAULT_DATE_RANGE_DAYS) -> Dict[str, str]:
    """Calcola date range per query GSC."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)
    
    return {
        'start': start_date.strftime('%Y-%m-%d'),
        'end': end_date.strftime('%Y-%m-%d'),
        'prev_start': (start_date - timedelta(days=days_back)).strftime('%Y-%m-%d'),
        'prev_end': (start_date - timedelta(days=1)).strftime('%Y-%m-%d'),
    }


def safe_int(value: Any, default: int = 0) -> int:
    """Converte valore in int in modo sicuro."""
    try:
        return int(value) if value else default
    except (ValueError, TypeError):
        return default


class GSCCollector(BaseCollector):
    """Raccoglie dati da Google Search Console API usando Service Account."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.service_account_file = config.get(
            "GSC_SERVICE_ACCOUNT_FILE", 
            "credentials/service-account.json"
        )
        self._service = None
    
    def is_available(self) -> bool:
        """Verifica se il Service Account è configurato."""
        return bool(self.service_account_file and os.path.exists(self.service_account_file))
    
    def _get_service(self):
        """Crea il servizio Google Search Console (con cache)."""
        if self._service:
            return self._service
        
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
            
            if not os.path.exists(self.service_account_file):
                self.logger.error(f"File Service Account non trovato: {self.service_account_file}")
                return None
            
            credentials = service_account.Credentials.from_service_account_file(
                self.service_account_file,
                scopes=GSC_SCOPES
            )
            
            self._service = build('searchconsole', 'v1', credentials=credentials)
            return self._service
            
        except ImportError as e:
            self.logger.error(f"Librerie Google non installate: {e}")
            self.logger.error("Esegui: pip install google-api-python-client google-auth")
            return None
        except Exception as e:
            self.logger.error(f"Errore autenticazione Service Account: {e}")
            return None
    
    def collect(self, domain: str) -> Dict[str, Any]:
        """Raccoglie tutti i dati GSC per il dominio."""
        if not self.is_available():
            self.logger.warning("Service Account non configurato. Skip.")
            return {}
        
        self.logger.info(f"🔍 Raccolta dati GSC per {domain}...")
        
        service = self._get_service()
        if not service:
            return {}
        
        # Trova la property corretta
        site_url = self._find_property(service, domain)
        if not site_url:
            self.logger.error("Nessun accesso a GSC per questo dominio")
            return {}
        
        # Verifica accesso
        site_info = service.sites().get(siteUrl=site_url).execute()
        results = {
            "verification": site_info.get("permissionLevel", "unknown"),
            "site_url": site_url,
        }
        
        self.logger.info(f"  ✓ Accesso GSC confermato per {site_url}: {results['verification']}")
        
        # Calcola date ranges
        dates = get_date_ranges()
        
        # Raccolta dati
        results.update({
            "performance": self._get_performance_data(service, site_url, dates),
            "top_pages": self._get_top_pages(service, site_url, dates),
            "top_queries": self._get_top_queries(service, site_url, dates),
            "devices": self._get_device_data(service, site_url, dates),
            "trending_queries": self._get_trending_queries(service, site_url, dates),
            "position_distribution": self._get_position_distribution(service, site_url, dates),
            "sitemaps": self._get_sitemaps_info(service, site_url),
            "crawling_errors": self._get_crawling_errors(service, site_url),
        })
        
        # Stima pagine indicizzate (con fallback)
        if results["performance"]:
            sample_urls = [
                row.get('keys', [None])[0] 
                for row in results["performance"][:20] 
                if row.get('keys')
            ]
            if sample_urls:
                results["indexed_estimate"] = self._estimate_indexed_pages(
                    service, site_url, sample_urls
                )
        
        self.logger.info(f"  ✓ Trovate {len(results['performance'])} pagine con dati performance")
        
        # Debug log
        self.logger.debug(f"  📊 DEBUG - Dati GSC raccolti:")
        self.logger.debug(f"    - top_pages: {len(results.get('top_pages', []))} elementi")
        self.logger.debug(f"    - top_queries: {len(results.get('top_queries', []))} elementi")
        self.logger.debug(f"    - devices: {len(results.get('devices', {}))} dispositivi")
        
        trending = results.get('trending_queries', {})
        self.logger.debug(f"    - trending_queries: {len(trending.get('growing', []))} growing, {len(trending.get('declining', []))} declining")
        
        return results
    
    def _find_property(self, service, domain: str) -> Optional[str]:
        """Trova la property GSC corretta per il dominio."""
        clean_domain = domain.replace('https://', '').replace('http://', '').replace('www.', '').split('/')[0]
        
        possible_urls = [
            f"https://{clean_domain}",
            f"sc-domain:{clean_domain}",
            f"https://www.{clean_domain}",
        ]
        
        for site_url in possible_urls:
            try:
                service.sites().get(siteUrl=site_url).execute()
                return site_url
            except Exception:
                continue
        
        return None
    
    def _query_search_analytics(self, service, site_url: str, dates: Dict, 
                                 dimension: str, row_limit: int = 100) -> List[Dict]:
        """Esegue query searchanalytics con parametri standard."""
        request = {
            'startDate': dates['start'],
            'endDate': dates['end'],
            'dimensions': [dimension],
            'rowLimit': row_limit,
            'dataState': 'FINAL'
        }
        
        try:
            response = service.searchanalytics().query(siteUrl=site_url, body=request).execute()
            return response.get("rows", [])
        except Exception as e:
            self.logger.warning(f"  ⚠️  Errore query {dimension}: {e}")
            return []
    
    def _get_performance_data(self, service, site_url: str, dates: Dict) -> List[Dict]:
        """Ottiene dati performance base."""
        return self._query_search_analytics(service, site_url, dates, 'page', 100)
    
    def _get_top_pages(self, service, site_url: str, dates: Dict) -> List[Dict]:
        """Ottiene le top 10 pagine ordinate per click."""
        rows = self._query_search_analytics(service, site_url, dates, 'page', 10)
        
        sorted_rows = sorted(rows, key=lambda x: x.get('clicks', 0), reverse=True)
        
        top_pages = []
        for row in sorted_rows[:10]:
            top_pages.append({
                'page': row.get('keys', [''])[0],
                'clicks': row.get('clicks', 0),
                'impressions': row.get('impressions', 0),
                'ctr': row.get('ctr', 0),
                'position': row.get('position', 0)
            })
        
        self.logger.info(f"  ✓ Top 10 pagine estratte")
        return top_pages
    
    def _get_top_queries(self, service, site_url: str, dates: Dict) -> List[Dict]:
        """Ottiene le top 10 keyword ordinate per click."""
        rows = self._query_search_analytics(service, site_url, dates, 'query', 10)
        
        sorted_rows = sorted(rows, key=lambda x: x.get('clicks', 0), reverse=True)
        
        top_queries = []
        for row in sorted_rows[:10]:
            top_queries.append({
                'query': row.get('keys', [''])[0],
                'clicks': row.get('clicks', 0),
                'impressions': row.get('impressions', 0),
                'ctr': row.get('ctr', 0),
                'position': row.get('position', 0)
            })
        
        self.logger.info(f"  ✓ Top 10 keyword estratte")
        return top_queries
    
    def _get_device_data(self, service, site_url: str, dates: Dict) -> Dict[str, Any]:
        """Ottiene dati aggregati per dispositivo."""
        rows = self._query_search_analytics(service, site_url, dates, 'device', 10)
        
        device_data = {}
        for row in rows:
            device = row.get('keys', [''])[0]
            device_data[device] = {
                'clicks': row.get('clicks', 0),
                'impressions': row.get('impressions', 0),
                'ctr': row.get('ctr', 0),
                'position': row.get('position', 0)
            }
        
        self.logger.info(f"  ✓ Dati dispositivo estratti: {list(device_data.keys())}")
        return device_data
    
    def _get_trending_queries(self, service, site_url: str, dates: Dict) -> Dict[str, Any]:
        """Confronta keyword tra due periodi per identificare trend."""
        try:
            # Periodo corrente
            current_rows = self._query_search_analytics(service, site_url, dates, 'query', 100)
            
            # Periodo precedente
            prev_request = {
                'startDate': dates['prev_start'],
                'endDate': dates['prev_end'],
                'dimensions': ['query'],
                'rowLimit': 100,
                'dataState': 'FINAL'
            }
            response_prev = service.searchanalytics().query(siteUrl=site_url, body=prev_request).execute()
            previous_rows = response_prev.get('rows', [])
            
            # Crea dizionari per confronto
            current_dict = {row.get('keys', [''])[0]: row for row in current_rows}
            previous_dict = {row.get('keys', [''])[0]: row for row in previous_rows}
            
            # Calcola variazioni
            growing, declining, new_queries = [], [], []
            
            for query, current_data in current_dict.items():
                current_clicks = current_data.get('clicks', 0)
                
                if query in previous_dict:
                    previous_clicks = previous_dict[query].get('clicks', 0)
                    change = current_clicks - previous_clicks
                    
                    if change > 0:
                        growing.append({
                            'query': query,
                            'clicks': current_clicks,
                            'change': change,
                            'position': current_data.get('position', 0)
                        })
                    elif change < 0:
                        declining.append({
                            'query': query,
                            'clicks': current_clicks,
                            'change': change,
                            'position': current_data.get('position', 0)
                        })
                else:
                    if current_clicks > 0:
                        new_queries.append({
                            'query': query,
                            'clicks': current_clicks,
                            'position': current_data.get('position', 0)
                        })
            
            # Ordina e limita
            growing = sorted(growing, key=lambda x: x['change'], reverse=True)[:10]
            declining = sorted(declining, key=lambda x: x['change'])[:10]
            new_queries = sorted(new_queries, key=lambda x: x['clicks'], reverse=True)[:10]
            
            self.logger.info(f"  ✓ Trend keyword estratti: {len(growing)} crescono, {len(declining)} calano, {len(new_queries)} nuove")
            
            return {
                'growing': growing,
                'declining': declining,
                'new': new_queries
            }
            
        except Exception as e:
            self.logger.warning(f"  ⚠️  Errore estrazione trend keyword: {e}")
            return {'growing': [], 'declining': [], 'new': []}
    
    def _get_position_distribution(self, service, site_url: str, dates: Dict) -> Dict[str, Any]:
        """Calcola la distribuzione delle keyword per fascia di posizione."""
        rows = self._query_search_analytics(service, site_url, dates, 'query', 1000)
        
        # Inizializza distribuzione
        distribution = {
            'top_3': {'count': 0, 'clicks': 0, 'impressions': 0},
            'page_1': {'count': 0, 'clicks': 0, 'impressions': 0},
            'page_2': {'count': 0, 'clicks': 0, 'impressions': 0},
            'page_3_5': {'count': 0, 'clicks': 0, 'impressions': 0},
            'beyond_50': {'count': 0, 'clicks': 0, 'impressions': 0}
        }
        
        # Definisci fasce di posizione
        position_buckets = [
            (0, 3, 'top_3'),
            (4, 10, 'page_1'),
            (11, 20, 'page_2'),
            (21, 50, 'page_3_5'),
            (51, float('inf'), 'beyond_50')
        ]
        
        for row in rows:
            position = row.get('position', 0)
            clicks = row.get('clicks', 0)
            impressions = row.get('impressions', 0)
            
            for min_pos, max_pos, bucket_name in position_buckets:
                if min_pos <= position <= max_pos:
                    distribution[bucket_name]['count'] += 1
                    distribution[bucket_name]['clicks'] += clicks
                    distribution[bucket_name]['impressions'] += impressions
                    break
        
        total_queries = sum(d['count'] for d in distribution.values())
        
        self.logger.info(f"  ✓ Distribuzione posizioni estratta: {total_queries} keyword totali")
        
        return {
            'distribution': distribution,
            'total_queries': total_queries
        }
    
    def _get_sitemaps_info(self, service, site_url: str) -> Dict[str, Any]:
        """Recupera informazioni sulle sitemap inviate a GSC."""
        try:
            self.logger.info(f"  🔍 Recupero informazioni sitemap da GSC...")
            
            response = service.sitemaps().list(siteUrl=site_url).execute()
            sitemaps = response.get('sitemap', [])
            
            if not sitemaps:
                return {'found': False, 'count': 0, 'sitemaps': []}
            
            self.logger.info(f"  ✓ Trovate {len(sitemaps)} sitemap in GSC")
            
            sitemap_details = []
            total_urls = 0
            total_indexed = 0
            
            for sitemap in sitemaps:
                sitemap_info = {
                    'path': sitemap.get('path', ''),
                    'contents': sitemap.get('contents', []),
                    'errors': sitemap.get('errors', 0),
                    'warnings': sitemap.get('warnings', 0),
                }
                
                for content in sitemap_info['contents']:
                    submitted = safe_int(content.get('submitted', 0))
                    indexed = safe_int(content.get('indexed', 0))
                    
                    total_urls += submitted
                    total_indexed += indexed
                
                sitemap_details.append(sitemap_info)
            
            return {
                'found': True,
                'count': len(sitemaps),
                'sitemaps': sitemap_details,
                'total_urls': total_urls,
                'total_indexed': total_indexed
            }
            
        except Exception as e:
            self.logger.error(f"  ✗ Errore recupero sitemap da GSC: {e}")
            return {'found': False, 'count': 0, 'sitemaps': [], 'error': str(e)}
    
    def _get_crawling_errors(self, service, site_url: str) -> Dict[str, Any]:
        """Recupera gli errori di crawling da GSC (placeholder)."""
        try:
            self.logger.debug(f"  🔍 Recupero errori di crawling da GSC...")
            
            return {
                'found': False,
                'errors': [],
                'note': 'Usare crawler HTML per analisi dettagliata'
            }
            
        except Exception as e:
            self.logger.warning(f"  ⚠️  Errore recupero crawling errors: {e}")
            return {'found': False, 'errors': [], 'error': str(e)}
    
    def _estimate_indexed_pages(self, service, site_url: str, sample_urls: List[str]) -> Dict[str, Any]:
        """Stima il numero di pagine indicizzate usando Performance API come fallback."""
        try:
            self.logger.info(f"  🔍 Stima pagine indicizzate...")
            
            # Prova con URL Inspection API
            homepage_url = site_url.rstrip('/')
            self.logger.debug(f"  📝 Test URL Inspection API con homepage: {homepage_url}")
            
            try:
                request = {
                    'inspectionUrl': homepage_url,
                    'siteUrl': site_url
                }
                
                response = service.urlInspection().index().inspect(body=request).execute()
                self.logger.info(f"  ✅ URL Inspection API disponibile!")
                
                # Se funziona, usa per campione
                indexed_count = 0
                not_indexed_count = 0
                errors = 0
                
                for url in sample_urls[:10]:
                    try:
                        request = {
                            'inspectionUrl': url,
                            'siteUrl': site_url
                        }
                        response = service.urlInspection().index().inspect(body=request).execute()
                        index_status = response.get('indexStatusResult', {}).get('verdict', '')
                        
                        if index_status in ['PASSED', 'NEUTRAL']:
                            indexed_count += 1
                        elif index_status in ['FAILED']:
                            not_indexed_count += 1
                        
                        time.sleep(0.5)
                    except Exception as e:
                        errors += 1
                
                total_inspected = indexed_count + not_indexed_count
                if total_inspected > 0:
                    index_rate = (indexed_count / total_inspected) * 100
                    return {
                        'sample_size': total_inspected,
                        'indexed': indexed_count,
                        'not_indexed': not_indexed_count,
                        'errors': errors,
                        'index_rate': round(index_rate, 1),
                        'estimation_method': 'url_inspection'
                    }
            
            except Exception as e:
                error_msg = str(e)
                if '403' in error_msg or 'PERMISSION_DENIED' in error_msg:
                    self.logger.warning(f"  ⚠️  URL Inspection API: permessi insufficienti")
                    self.logger.info(f"  ℹ️  Uso Performance API come stima alternativa")
                else:
                    self.logger.warning(f"  ⚠️  Errore URL Inspection: {error_msg[:100]}")
            
            # FALLBACK: Performance API
            self.logger.info(f"  📊 Stima basata su Performance API: {len(sample_urls)} pagine con dati")
            
            return {
                'sample_size': len(sample_urls),
                'indexed': len(sample_urls),
                'not_indexed': 0,
                'errors': 0,
                'index_rate': 100.0,
                'estimation_method': 'performance_api',
                'note': 'Stima basata su pagine con dati performance (URL Inspection API non disponibile)'
            }
        
        except Exception as e:
            self.logger.error(f"  ✗ Errore stima pagine indicizzate: {e}")
            return {
                'sample_size': 0,
                'indexed': 0,
                'not_indexed': 0,
                'errors': 0,
                'index_rate': 0,
                'error': str(e),
                'estimation_method': 'error'
            }