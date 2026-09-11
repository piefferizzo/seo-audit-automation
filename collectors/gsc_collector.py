import os
import time
from typing import Dict, Any, List
from datetime import datetime, timedelta
from collectors.base_collector import BaseCollector


class GSCCollector(BaseCollector):
    """Raccoglie dati da Google Search Console API usando Service Account."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.service_account_file = config.get("GSC_SERVICE_ACCOUNT_FILE", "credentials/service-account.json")
    
    def is_available(self) -> bool:
        return bool(self.service_account_file and os.path.exists(self.service_account_file))
    
    def _get_service(self):
        """Crea il servizio Google Search Console con Service Account."""
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
            
            SCOPES = ['https://www.googleapis.com/auth/webmasters.readonly']
            
            if not os.path.exists(self.service_account_file):
                self.logger.error(f"File Service Account non trovato: {self.service_account_file}")
                return None
            
            credentials = service_account.Credentials.from_service_account_file(
                self.service_account_file,
                scopes=SCOPES
            )
            
            return build('searchconsole', 'v1', credentials=credentials)
        
        except ImportError as e:
            self.logger.error(f"Librerie Google non installate: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Errore autenticazione Service Account: {e}")
            return None
    
    def collect(self, domain: str) -> Dict[str, Any]:
        if not self.is_available():
            self.logger.warning("Service Account non configurato. Skip.")
            return {}
        
        self.logger.info(f"🔍 Raccolta dati GSC per {domain}...")
        
        service = self._get_service()
        if not service:
            return {}
        
        clean_domain = domain.replace('https://', '').replace('http://', '').replace('www.', '').split('/')[0]
        
        possible_urls = [
            f"https://{clean_domain}",
            f"sc-domain:{clean_domain}",
            f"https://www.{clean_domain}",
        ]
        
        results = {}
        
        for site_url in possible_urls:
            try:
                site_info = service.sites().get(siteUrl=site_url).execute()
                results["verification"] = site_info.get("permissionLevel", "unknown")
                results["site_url"] = site_url
                self.logger.info(f"  ✓ Accesso GSC confermato per {site_url}: {results['verification']}")
                
                # Date range
                end_date = datetime.now()
                start_date = end_date - timedelta(days=28)
                prev_end_date = start_date - timedelta(days=1)
                prev_start_date = prev_end_date - timedelta(days=28)
                
                end_date_str = end_date.strftime('%Y-%m-%d')
                start_date_str = start_date.strftime('%Y-%m-%d')
                prev_end_date_str = prev_end_date.strftime('%Y-%m-%d')
                prev_start_date_str = prev_start_date.strftime('%Y-%m-%d')
                
                # 1. Performance data base
                request = {
                    'startDate': start_date_str,
                    'endDate': end_date_str,
                    'dimensions': ['page'],
                    'rowLimit': 100
                }
                response = service.searchanalytics().query(siteUrl=site_url, body=request).execute()
                results["performance"] = response.get("rows", [])
                
                # 2. Top pagine per click
                results["top_pages"] = self._get_top_pages(service, site_url, start_date_str, end_date_str)
                
                # 3. Top keyword per click
                results["top_queries"] = self._get_top_queries(service, site_url, start_date_str, end_date_str)
                
                # 4. Dati per dispositivo
                results["devices"] = self._get_device_data(service, site_url, start_date_str, end_date_str)
                
                # 5. Keyword che crescono e calano
                results["trending_queries"] = self._get_trending_queries(
                    service, site_url, 
                    start_date_str, end_date_str,
                    prev_start_date_str, prev_end_date_str
                )
                
                # 6. Distribuzione posizioni
                results["position_distribution"] = self._get_position_distribution(
                    service, site_url, start_date_str, end_date_str
                )
                
                # 7. Sitemaps info
                results["sitemaps"] = self._get_sitemaps_info(service, site_url)
                
                # 8. Crawling errors
                results["crawling_errors"] = self._get_crawling_errors(service, site_url)
                
                # 9. Stima pagine indicizzate (con fallback a Performance API)
                if results["performance"]:
                    sample_urls = [row.get('keys', [None])[0] for row in results["performance"][:20] if row.get('keys')]
                    if sample_urls:
                        results["indexed_estimate"] = self._estimate_indexed_pages(service, site_url, sample_urls)
                
                self.logger.info(f"  ✓ Trovate {len(results['performance'])} pagine con dati performance")
                
                # DEBUG
                self.logger.info(f"  📊 DEBUG - Dati GSC raccolti:")
                self.logger.info(f"    - top_pages: {len(results.get('top_pages', []))} elementi")
                self.logger.info(f"    - top_queries: {len(results.get('top_queries', []))} elementi")
                self.logger.info(f"    - devices: {len(results.get('devices', {}))} dispositivi")
                self.logger.info(f"    - trending_queries: {len(results.get('trending_queries', {}).get('growing', []))} growing, {len(results.get('trending_queries', {}).get('declining', []))} declining")
                
                break
                
            except Exception as e:
                self.logger.warning(f"  ⚠️  Nessun accesso per {site_url}")
                continue
        
        if not results:
            self.logger.error("Nessun accesso a GSC per questo dominio")
        
        return results
    
    def _get_top_pages(self, service, site_url: str, start_date: str, end_date: str) -> List[Dict]:
        """Ottiene le top 10 pagine ordinate per click."""
        try:
            request = {
                'startDate': start_date,
                'endDate': end_date,
                'dimensions': ['page'],
                'rowLimit': 10,
                'dataState': 'FINAL'
            }
            
            response = service.searchanalytics().query(siteUrl=site_url, body=request).execute()
            rows = response.get('rows', [])
            
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
            
        except Exception as e:
            self.logger.warning(f"  ⚠️  Errore estrazione top pagine: {e}")
            return []
    
    def _get_top_queries(self, service, site_url: str, start_date: str, end_date: str) -> List[Dict]:
        """Ottiene le top 10 keyword ordinate per click."""
        try:
            request = {
                'startDate': start_date,
                'endDate': end_date,
                'dimensions': ['query'],
                'rowLimit': 10,
                'dataState': 'FINAL'
            }
            
            response = service.searchanalytics().query(siteUrl=site_url, body=request).execute()
            rows = response.get('rows', [])
            
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
            
        except Exception as e:
            self.logger.warning(f"  ⚠️  Errore estrazione top keyword: {e}")
            return []
    
    def _get_device_data(self, service, site_url: str, start_date: str, end_date: str) -> Dict[str, Any]:
        """Ottiene dati aggregati per dispositivo."""
        try:
            request = {
                'startDate': start_date,
                'endDate': end_date,
                'dimensions': ['device'],
                'rowLimit': 10,
                'dataState': 'FINAL'
            }
            
            response = service.searchanalytics().query(siteUrl=site_url, body=request).execute()
            rows = response.get('rows', [])
            
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
            
        except Exception as e:
            self.logger.warning(f"  ⚠️  Errore estrazione dati dispositivo: {e}")
            return {}
    
    def _get_trending_queries(self, service, site_url: str, 
                              start_date: str, end_date: str,
                              prev_start_date: str, prev_end_date: str) -> Dict[str, Any]:
        """Confronta keyword tra due periodi per identificare trend."""
        try:
            # Periodo corrente
            request_current = {
                'startDate': start_date,
                'endDate': end_date,
                'dimensions': ['query'],
                'rowLimit': 100,
                'dataState': 'FINAL'
            }
            response_current = service.searchanalytics().query(siteUrl=site_url, body=request_current).execute()
            current_rows = response_current.get('rows', [])
            
            # Periodo precedente
            request_previous = {
                'startDate': prev_start_date,
                'endDate': prev_end_date,
                'dimensions': ['query'],
                'rowLimit': 100,
                'dataState': 'FINAL'
            }
            response_previous = service.searchanalytics().query(siteUrl=site_url, body=request_previous).execute()
            previous_rows = response_previous.get('rows', [])
            
            # Crea dizionari per confronto
            current_dict = {row.get('keys', [''])[0]: row for row in current_rows}
            previous_dict = {row.get('keys', [''])[0]: row for row in previous_rows}
            
            # Calcola variazioni
            growing = []
            declining = []
            new_queries = []
            
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
    
    def _get_position_distribution(self, service, site_url: str, start_date: str, end_date: str) -> Dict[str, Any]:
        """Calcola la distribuzione delle keyword per fascia di posizione."""
        try:
            request = {
                'startDate': start_date,
                'endDate': end_date,
                'dimensions': ['query'],
                'rowLimit': 1000,
                'dataState': 'FINAL'
            }
            
            response = service.searchanalytics().query(siteUrl=site_url, body=request).execute()
            rows = response.get('rows', [])
            
            distribution = {
                'top_3': {'count': 0, 'clicks': 0, 'impressions': 0},
                'page_1': {'count': 0, 'clicks': 0, 'impressions': 0},
                'page_2': {'count': 0, 'clicks': 0, 'impressions': 0},
                'page_3_5': {'count': 0, 'clicks': 0, 'impressions': 0},
                'beyond_50': {'count': 0, 'clicks': 0, 'impressions': 0}
            }
            
            for row in rows:
                position = row.get('position', 0)
                clicks = row.get('clicks', 0)
                impressions = row.get('impressions', 0)
                
                if position <= 3:
                    distribution['top_3']['count'] += 1
                    distribution['top_3']['clicks'] += clicks
                    distribution['top_3']['impressions'] += impressions
                elif position <= 10:
                    distribution['page_1']['count'] += 1
                    distribution['page_1']['clicks'] += clicks
                    distribution['page_1']['impressions'] += impressions
                elif position <= 20:
                    distribution['page_2']['count'] += 1
                    distribution['page_2']['clicks'] += clicks
                    distribution['page_2']['impressions'] += impressions
                elif position <= 50:
                    distribution['page_3_5']['count'] += 1
                    distribution['page_3_5']['clicks'] += clicks
                    distribution['page_3_5']['impressions'] += impressions
                else:
                    distribution['beyond_50']['count'] += 1
                    distribution['beyond_50']['clicks'] += clicks
                    distribution['beyond_50']['impressions'] += impressions
            
            total_queries = sum(d['count'] for d in distribution.values())
            
            self.logger.info(f"  ✓ Distribuzione posizioni estratta: {total_queries} keyword totali")
            
            return {
                'distribution': distribution,
                'total_queries': total_queries
            }
            
        except Exception as e:
            self.logger.warning(f"  ⚠️  Errore estrazione distribuzione posizioni: {e}")
            return {'distribution': {}, 'total_queries': 0}
    
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
                    submitted = content.get('submitted', 0)
                    indexed = content.get('indexed', 0)
                    
                    try:
                        submitted_int = int(submitted) if submitted else 0
                    except (ValueError, TypeError):
                        submitted_int = 0
                    
                    try:
                        indexed_int = int(indexed) if indexed else 0
                    except (ValueError, TypeError):
                        indexed_int = 0
                    
                    total_urls += submitted_int
                    total_indexed += indexed_int
                
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
            self.logger.info(f"  🔍 Recupero errori di crawling da GSC...")
            
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
            self.logger.info(f"  📝 Test URL Inspection API con homepage: {homepage_url}")
            
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