import os
import io
import gzip
import json
import time
import hashlib
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from collectors.base_collector import BaseCollector

import requests


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

# ---------------------------------------------------------------------------
# URL Inspection API — tuning per evitare blocchi e crash (v2.3.4)
# ---------------------------------------------------------------------------
# IMPORTANTE (thread-safety):
#   google-auth NON è thread-safe. Condividere lo stesso oggetto credenziali
#   tra più thread causa refresh concorrente del token OAuth che corrompe
#   lo stato SSL in libssl e fa crashare il processo (SIGABRT).
#   Soluzione: ogni worker costruisce il PROPRIO client GSC con credenziali
#   separate (vedi _build_fresh_service + worker in _inspect_urls_batch).
URL_INSPECTION_SLEEP_SECONDS = 0.3               # tra chiamate OK
URL_INSPECTION_MAX_URLS = 150                    # cap ragionevole per stima solida
URL_INSPECTION_CACHE_TTL_HOURS = 24
URL_INSPECTION_CACHE_DIR = 'cache'
URL_INSPECTION_CACHE_FILE = 'url_inspection_cache.json'
URL_INSPECTION_MAX_RETRIES = 4
URL_INSPECTION_BACKOFF_SECONDS = [3, 10, 30, 60] # backoff corto (non 60/120/180)
URL_INSPECTION_CALL_TIMEOUT = 15                 # timeout per singola chiamata
URL_INSPECTION_CACHE_SAVE_EVERY = 10             # salva cache ogni N URL
URL_INSPECTION_ABORT_AFTER_CONSECUTIVE_ERRORS = 5  # soglia per abort (fallback)
URL_INSPECTION_MAX_WORKERS = 5                   # 5 worker paralleli

# Namespace XML sitemap
SITEMAP_NS = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}


# ---------------------------------------------------------------------------
# ECCEZIONI CUSTOM
# ---------------------------------------------------------------------------
class RateLimitError(Exception):
    """Sollevata quando troppi 429 consecutivi indicano un blocco temporaneo."""
    pass


# ---------------------------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------------------------
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
        # Controllo opzionale dell'URL Inspection (default: attivo)
        self.url_inspection_enabled = config.get(
            "GSC_URL_INSPECTION_ENABLED", True
        )
        self.url_inspection_max_urls = config.get(
            "GSC_URL_INSPECTION_MAX_URLS", URL_INSPECTION_MAX_URLS
        )
        self._service = None
        self._inspection_cache = None  # lazy load

    def is_available(self) -> bool:
        """Verifica se il Service Account è configurato."""
        return bool(self.service_account_file and os.path.exists(self.service_account_file))

    # ------------------------------------------------------------------
    # CLIENT GSC — costruzione (main thread + thread-locale)
    # ------------------------------------------------------------------

    def _get_service(self):
        """Crea il servizio Google Search Console per il main thread (con cache).

        Usato per le chiamate sequenziali (searchanalytics, sitemaps, sites).
        NON usare questo metodo dai worker di _inspect_urls_batch — usa
        invece _build_fresh_service() per evitare crash SSL.
        """
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

            self._service = build(
                'searchconsole', 'v1',
                credentials=credentials,
                cache_discovery=False,
            )
            return self._service

        except ImportError as e:
            self.logger.error(f"Librerie Google non installate: {e}")
            self.logger.error("Esegui: pip install google-api-python-client google-auth")
            return None
        except Exception as e:
            self.logger.error(f"Errore autenticazione Service Account: {e}")
            return None

    def _build_fresh_service(self):
        """Costruisce un NUOVO client GSC con credenziali fresche.

        Necessario per l'uso da più thread: google-auth NON è thread-safe,
        condividere lo stesso oggetto credenziali causa corruzione di
        memoria in libssl (crash SIGABRT in ___BUG_IN_CLIENT_OF_LIBMALLOC).
        Ogni worker chiama questo metodo per avere il proprio client isolato.

        Ritorna il client GSC, oppure None in caso di errore.
        """
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            credentials = service_account.Credentials.from_service_account_file(
                self.service_account_file,
                scopes=GSC_SCOPES
            )
            return build(
                'searchconsole', 'v1',
                credentials=credentials,
                cache_discovery=False,
            )
        except Exception as e:
            self.logger.error(f"Errore costruzione service thread-locale: {e}")
            return None

    # ------------------------------------------------------------------
    # ENTRY POINT
    # ------------------------------------------------------------------

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

        # Raccolta dati (chiamate sequenziali sul main thread)
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

        # Stima pagine indicizzate (con URL Inspection API reale, multithread)
        if results["performance"]:
            sample_urls = [
                row.get('keys', [None])[0]
                for row in results["performance"][:20]
                if row.get('keys')
            ]
            if sample_urls:
                results["indexed_estimate"] = self._estimate_indexed_pages(
                    service, site_url, sample_urls,
                    sitemaps_info=results.get("sitemaps", {}),
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

    # ------------------------------------------------------------------
    # PROPERTY DISCOVERY
    # ------------------------------------------------------------------

    def _find_property(self, service, domain: str) -> Optional[str]:
        """Trova la property GSC corretta per il dominio, interrogando
        direttamente l'API per scoprire il formato esatto (Dominio o
        Prefisso URL) registrato in Search Console.

        Questo evita il bug per cui un mismatch di formato restituisce
        un 403 fuorviante anche quando il Service Account è Owner.
        """
        clean_domain = domain.replace('https://', '').replace('http://', '').replace('www.', '').split('/')[0]

        # 1. Chiedi all'API l'elenco completo delle proprietà accessibili
        try:
            response = service.sites().list().execute()
            site_entries = response.get('siteEntry', [])
        except Exception as e:
            self.logger.error(f"Errore nel recupero della lista delle proprietà GSC: {e}")
            site_entries = []

        # 2. Cerca una corrispondenza esatta (dominio pulito)
        for entry in site_entries:
            site_url = entry.get('siteUrl', '')
            normalized = site_url.replace('sc-domain:', '').rstrip('/')
            normalized_clean = normalized.replace('https://', '').replace('http://', '').replace('www.', '')

            if normalized_clean == clean_domain:
                self.logger.info(f"  ✓ Proprietà trovata per {clean_domain}: {site_url}")
                return site_url

        # 3. Fallback: prova con i formati più comuni
        fallback_urls = [
            f"sc-domain:{clean_domain}",
            f"https://{clean_domain}/",
            f"https://www.{clean_domain}/",
        ]

        for site_url in fallback_urls:
            try:
                service.sites().get(siteUrl=site_url).execute()
                self.logger.info(f"  ✓ Proprietà trovata (fallback) per {clean_domain}: {site_url}")
                return site_url
            except Exception:
                continue

        self.logger.error(f"  ✗ Nessuna proprietà GSC trovata per {clean_domain}.")
        return None

    # ------------------------------------------------------------------
    # SEARCH ANALYTICS
    # ------------------------------------------------------------------

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
            current_rows = self._query_search_analytics(service, site_url, dates, 'query', 100)

            prev_request = {
                'startDate': dates['prev_start'],
                'endDate': dates['prev_end'],
                'dimensions': ['query'],
                'rowLimit': 100,
                'dataState': 'FINAL'
            }
            response_prev = service.searchanalytics().query(siteUrl=site_url, body=prev_request).execute()
            previous_rows = response_prev.get('rows', [])

            current_dict = {row.get('keys', [''])[0]: row for row in current_rows}
            previous_dict = {row.get('keys', [''])[0]: row for row in previous_rows}

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

        distribution = {
            'top_3': {'count': 0, 'clicks': 0, 'impressions': 0},
            'page_1': {'count': 0, 'clicks': 0, 'impressions': 0},
            'page_2': {'count': 0, 'clicks': 0, 'impressions': 0},
            'page_3_5': {'count': 0, 'clicks': 0, 'impressions': 0},
            'beyond_50': {'count': 0, 'clicks': 0, 'impressions': 0}
        }

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

    # ------------------------------------------------------------------
    # SITEMAPS
    # ------------------------------------------------------------------

    def _get_sitemaps_info(self, service, site_url: str) -> Dict[str, Any]:
        """Recupera informazioni sulle sitemap inviate a GSC.

        NOTA: il campo 'indexed' dell'API GSC è deprecato e restituisce
        sempre 0. Marchiamo il dato come non affidabile tramite il flag
        'indexed_available'. Il conteggio reale viene poi ricavato dalla
        URL Inspection API in _estimate_indexed_pages.
        """
        try:
            self.logger.info(f"  🔍 Recupero informazioni sitemap da GSC...")

            response = service.sitemaps().list(siteUrl=site_url).execute()
            sitemaps = response.get('sitemap', [])

            if not sitemaps:
                return {'found': False, 'count': 0, 'sitemaps': [], 'indexed_available': False}

            self.logger.info(f"  ✓ Trovate {len(sitemaps)} sitemap in GSC")

            sitemap_details = []
            total_urls = 0
            total_indexed = 0
            has_nonzero_indexed = False

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

                    if indexed > 0:
                        has_nonzero_indexed = True

                sitemap_details.append(sitemap_info)

            indexed_available = has_nonzero_indexed

            if not indexed_available and total_urls > 0:
                self.logger.debug(
                    "  ℹ️  Campo 'indexed' deprecato (sempre 0). "
                    "Verrà usata la URL Inspection API per il conteggio reale."
                )

            return {
                'found': True,
                'count': len(sitemaps),
                'sitemaps': sitemap_details,
                'total_urls': total_urls,
                'total_indexed': total_indexed,
                'indexed_available': indexed_available,
            }

        except Exception as e:
            self.logger.error(f"  ✗ Errore recupero sitemap da GSC: {e}")
            return {'found': False, 'count': 0, 'sitemaps': [], 'error': str(e), 'indexed_available': False}

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

    # ------------------------------------------------------------------
    # URL INSPECTION — Strada A (v2.3.4: thread-safe)
    # ------------------------------------------------------------------

    def _load_inspection_cache(self) -> Dict[str, Dict]:
        """Carica la cache delle ispezioni URL da file, se valida."""
        if self._inspection_cache is not None:
            return self._inspection_cache

        cache_path = os.path.join(URL_INSPECTION_CACHE_DIR, URL_INSPECTION_CACHE_FILE)
        if not os.path.exists(cache_path):
            self._inspection_cache = {}
            return self._inspection_cache

        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            now = datetime.now()
            ttl = timedelta(hours=URL_INSPECTION_CACHE_TTL_HOURS)

            valid = {}
            for url, entry in data.items():
                try:
                    ts = datetime.fromisoformat(entry.get('ts', ''))
                    if now - ts < ttl:
                        valid[url] = entry
                except Exception:
                    continue

            self._inspection_cache = valid
            if valid:
                self.logger.debug(f"  ✓ Cache ispezioni URL: {len(valid)} voci valide")
            return self._inspection_cache

        except Exception as e:
            self.logger.warning(f"  ⚠️  Errore lettura cache ispezioni: {e}")
            self._inspection_cache = {}
            return self._inspection_cache

    def _save_inspection_cache(self):
        """Salva la cache delle ispezioni URL su file."""
        try:
            os.makedirs(URL_INSPECTION_CACHE_DIR, exist_ok=True)
            cache_path = os.path.join(URL_INSPECTION_CACHE_DIR, URL_INSPECTION_CACHE_FILE)
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(self._inspection_cache or {}, f, ensure_ascii=False)
            self.logger.debug(f"  ✓ Cache ispezioni salvata: {len(self._inspection_cache or {})} voci")
        except Exception as e:
            self.logger.warning(f"  ⚠️  Errore salvataggio cache ispezioni: {e}")

    def _parse_sitemap_xml(self, content: bytes, base_url: str) -> Dict[str, List[str]]:
        """Parsa un XML sitemap (o sitemap index)."""
        result = {'urls': [], 'child_sitemaps': []}
        try:
            root = ET.fromstring(content)
        except ET.ParseError as e:
            self.logger.warning(f"  ⚠️  XML sitemap non valido ({base_url}): {e}")
            return result

        tag = root.tag.split('}')[-1]

        if tag == 'sitemapindex':
            for child in root.findall('sm:sitemap/sm:loc', SITEMAP_NS) or root.findall('sitemap/loc'):
                loc = (child.text or '').strip()
                if loc:
                    result['child_sitemaps'].append(loc)

        elif tag == 'urlset':
            for url_el in root.findall('sm:url/sm:loc', SITEMAP_NS) or root.findall('url/loc'):
                loc = (url_el.text or '').strip()
                if loc:
                    result['urls'].append(loc)

        return result

    def _get_all_urls_from_sitemaps(
        self,
        site_url: str,
        sitemaps_info: Dict[str, Any],
        max_urls: int = URL_INSPECTION_MAX_URLS,
    ) -> List[str]:
        """Scarica le sitemap e ritorna la lista di URL da ispezionare."""
        if not sitemaps_info or not sitemaps_info.get('found'):
            return []

        root_sitemaps = [
            s.get('path', '') for s in sitemaps_info.get('sitemaps', []) if s.get('path')
        ]
        if not root_sitemaps:
            return []

        all_urls: List[str] = []
        visited_sitemaps = set()
        queue = list(root_sitemaps)

        headers = {'User-Agent': 'Mozilla/5.0 (compatible; ArkysSEOAudit/1.0)'}

        while queue and len(all_urls) < max_urls:
            sm_url = queue.pop(0)
            if sm_url in visited_sitemaps:
                continue
            visited_sitemaps.add(sm_url)

            try:
                resp = requests.get(sm_url, headers=headers, timeout=15)
                if resp.status_code != 200:
                    self.logger.debug(f"  ⚠️  Sitemap {sm_url} → HTTP {resp.status_code}")
                    continue

                content = resp.content
                if sm_url.endswith('.gz'):
                    try:
                        content = gzip.decompress(content)
                    except Exception:
                        self.logger.debug(f"  ⚠️  Gzip fallito per {sm_url}")

                parsed = self._parse_sitemap_xml(content, sm_url)
                all_urls.extend(parsed['urls'])
                queue.extend(parsed['child_sitemaps'])

            except Exception as e:
                self.logger.debug(f"  ⚠️  Errore download {sm_url}: {e}")
                continue

        seen = set()
        unique = []
        for u in all_urls:
            if u not in seen:
                seen.add(u)
                unique.append(u)

        if len(unique) > max_urls:
            self.logger.warning(
                f"  ⚠️  Trovati {len(unique)} URL, ne ispezionerò solo i primi {max_urls}."
            )
            unique = unique[:max_urls]

        self.logger.info(f"  ✓ Estratti {len(unique)} URL dalle sitemap")
        return unique

    def _inspect_single_url(self, service, site_url: str, url: str) -> Optional[Dict[str, Any]]:
        """Ispeziona un singolo URL con timeout e retry RAPIDI.

        CRITICO: `.execute(num_retries=0)` disabilita i retry interni di
        googleapiclient (backoff esponenziale lungo), lasciando il controllo
        dei retry a noi con backoff CORTO [3, 10, 30, 60]s.

        Il parametro `service` DEVE essere un client dedicato a questo
        thread (vedi _build_fresh_service).
        """
        body = {'inspectionUrl': url, 'siteUrl': site_url}

        for attempt in range(URL_INSPECTION_MAX_RETRIES):
            try:
                response = (
                    service.urlInspection()
                    .index()
                    .inspect(body=body)
                    .execute(num_retries=0)
                )
                result = response.get('inspectionResult', {}) or {}
                idx = result.get('indexStatusResult', {}) or {}
                return {
                    'verdict': idx.get('verdict', 'VERDICT_UNSPECIFIED'),
                    'coverage_state': idx.get('coverageState', ''),
                    'robots_txt_state': idx.get('robotsTxtState', ''),
                    'indexing_state': idx.get('indexingState', ''),
                    'last_crawl_time': idx.get('lastCrawlTime', ''),
                }

            except Exception as e:
                msg = str(e)

                if '403' in msg or 'PERMISSION_DENIED' in msg:
                    raise PermissionError(msg)

                if '429' in msg or 'rateLimitExceeded' in msg or 'quotaExceeded' in msg:
                    delay = URL_INSPECTION_BACKOFF_SECONDS[
                        min(attempt, len(URL_INSPECTION_BACKOFF_SECONDS) - 1)
                    ]
                    self.logger.warning(
                        f"  ⏸️  Rate limit, attendo {delay}s "
                        f"(tentativo {attempt + 1}/{URL_INSPECTION_MAX_RETRIES})"
                    )
                    time.sleep(delay)
                    continue

                self.logger.debug(f"  ⚠️  Errore inspection {url}: {msg[:120]}")
                return None

        raise RateLimitError(f"Rate limit persistente su {url}")

    def _inspect_urls_batch(self, service, site_url: str, urls: List[str]) -> Dict[str, Any]:
        """Ispeziona in batch con 5 worker e un client GSC dedicato per thread.

        Ogni worker costruisce il proprio client per evitare la
        condivisione di stato SSL di google-auth (che crasha il processo
        con più thread, bug noto di libssl/OpenSSL 3.x).

        Il parametro `service` (client del main thread) NON viene usato
        dai worker, ma mantenuto per compatibilità di firma.
        """
        import threading
        from concurrent.futures import ThreadPoolExecutor, as_completed

        if not urls:
            return {
                'total_inspected': 0, 'indexed': 0, 'not_indexed': 0,
                'errors': 0, 'index_rate': 0, 'coverage_breakdown': {},
            }

        cache = self._load_inspection_cache()
        cache_lock = threading.Lock()
        counters_lock = threading.Lock()

        # Pre-filtra: contiamo subito gli URL in cache
        to_inspect = [u for u in urls if u not in cache]
        cache_hits = len(urls) - len(to_inspect)

        indexed = 0
        not_indexed = 0
        errors = 0
        coverage_breakdown: Dict[str, int] = {}

        for url in urls:
            if url in cache:
                entry = cache[url]
                if entry.get('verdict') == 'PASS':
                    indexed += 1
                else:
                    not_indexed += 1
                cov = entry.get('coverage_state', '')
                if cov:
                    coverage_breakdown[cov] = coverage_breakdown.get(cov, 0) + 1

        total = len(urls)
        inspected_count = [cache_hits]
        start_ts = time.time()

        abort_event = threading.Event()
        rate_limit_event = threading.Event()

        # Finestra scivolosa per abort basato su percentuale
        recent_window_seconds = 30
        recent_attempts: List[tuple] = []

        MAX_WORKERS = URL_INSPECTION_MAX_WORKERS

        def record_attempt(success: bool) -> bool:
            """Registra un tentativo e ritorna True se bisogna abortire."""
            now = time.time()
            with counters_lock:
                recent_attempts.append((now, success))
                cutoff = now - recent_window_seconds
                recent_attempts[:] = [(t, s) for t, s in recent_attempts if t > cutoff]

                if len(recent_attempts) >= 20:
                    fails = sum(1 for _, s in recent_attempts if not s)
                    if fails / len(recent_attempts) > 0.7:
                        return True
            return False

        def worker(url: str, worker_idx: int):
            """Worker thread: costruisce il proprio client e ispeziona un URL."""
            # Stagger iniziale per non partire tutti insieme
            time.sleep(worker_idx * 0.8)

            if abort_event.is_set():
                return (url, None, 'aborted')

            # Se c'è rate limit globale in corso, aspetta
            if rate_limit_event.is_set():
                rate_limit_event.wait(timeout=15)

            if abort_event.is_set():
                return (url, None, 'aborted')

            # CRITICO: ogni thread ha il SUO client GSC con credenziali isolate
            thread_service = self._build_fresh_service()
            if thread_service is None:
                return (url, None, ('error', 'service build failed'))

            try:
                res = self._inspect_single_url(thread_service, site_url, url)
                return (url, res, None)
            except PermissionError as e:
                return (url, None, ('permission', str(e)))
            except RateLimitError as e:
                return (url, None, ('ratelimit', str(e)))
            except Exception as e:
                return (url, None, ('error', str(e)))

        self.logger.info(
            f"    🚀 Ispeziono {len(to_inspect)} URL con {MAX_WORKERS} worker "
            f"({cache_hits} da cache)"
        )

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(worker, url, i % MAX_WORKERS): url
                for i, url in enumerate(to_inspect)
            }

            for future in as_completed(futures):
                if abort_event.is_set():
                    for f in futures:
                        f.cancel()
                    break

                url, res, err = future.result()

                # --- Gestione errori ---
                if err:
                    if isinstance(err, tuple):
                        kind, msg = err

                        if kind == 'permission':
                            self.logger.error(f"  ✗ Permessi insufficienti: {msg[:150]}")
                            abort_event.set()
                            break

                        elif kind == 'ratelimit':
                            self.logger.debug("  ⏸️  Rate limit globale, pausa di 10s")
                            rate_limit_event.set()
                            threading.Timer(10.0, lambda: rate_limit_event.clear()).start()
                            errors += 1
                            if record_attempt(False):
                                self.logger.error(
                                    "  ✗ Tasso errori >70% nella finestra recente. "
                                    "Interrompo. Cache salvata."
                                )
                                abort_event.set()
                            continue

                    if err == 'aborted':
                        continue

                    errors += 1
                    if record_attempt(False):
                        self.logger.error(
                            "  ✗ Tasso errori >70% nella finestra recente. "
                            "Interrompo. Cache salvata."
                        )
                        abort_event.set()
                    continue

                if res is None:
                    errors += 1
                    if record_attempt(False):
                        self.logger.error(
                            "  ✗ Tasso errori >70% nella finestra recente. "
                            "Interrompo. Cache salvata."
                        )
                        abort_event.set()
                    continue

                # --- Successo ---
                record_attempt(True)

                verdict = res.get('verdict', '')
                coverage = res.get('coverage_state', '')

                with cache_lock:
                    cache[url] = {
                        'ts': datetime.now().isoformat(),
                        'verdict': verdict,
                        'coverage_state': coverage,
                    }
                    with counters_lock:
                        if verdict == 'PASS':
                            indexed += 1
                        else:
                            not_indexed += 1
                        if coverage:
                            coverage_breakdown[coverage] = coverage_breakdown.get(coverage, 0) + 1
                        inspected_count[0] += 1
                        done = inspected_count[0]

                # Salva cache ogni N URL (sopravvive a Ctrl+C / crash)
                if done % URL_INSPECTION_CACHE_SAVE_EVERY == 0:
                    with cache_lock:
                        self._inspection_cache = dict(cache)
                        self._save_inspection_cache()

                # Progress ogni 10 URL con ETA
                if done % 10 == 0 or done == total:
                    elapsed = time.time() - start_ts
                    rate = done / elapsed if elapsed > 0 else 0
                    eta = (total - done) / rate if rate > 0 else 0
                    self.logger.info(
                        f"    … {done}/{total} URL ({elapsed:.0f}s, "
                        f"{cache_hits} da cache, ETA {eta:.0f}s)"
                    )

        # Salva cache finale
        with cache_lock:
            self._inspection_cache = dict(cache)
            self._save_inspection_cache()

        total_inspected = indexed + not_indexed
        index_rate = (indexed / total_inspected * 100) if total_inspected > 0 else 0
        duration = time.time() - start_ts

        return {
            'total_inspected': total_inspected,
            'indexed': indexed,
            'not_indexed': not_indexed,
            'errors': errors,
            'index_rate': round(index_rate, 1),
            'coverage_breakdown': coverage_breakdown,
            'cache_hits': cache_hits,
            'duration_seconds': round(duration, 1),
            'aborted': abort_event.is_set(),
        }

    def _estimate_indexed_pages(
        self,
        service,
        site_url: str,
        sample_urls: List[str],
        sitemaps_info: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Stima le pagine indicizzate con URL Inspection API (Strada A)."""
        self.logger.info(f"  🔍 Stima pagine indicizzate (URL Inspection API)...")

        if self.url_inspection_enabled and sitemaps_info:
            try:
                urls = self._get_all_urls_from_sitemaps(
                    site_url=site_url,
                    sitemaps_info=sitemaps_info,
                    max_urls=self.url_inspection_max_urls,
                )

                if urls:
                    batch = self._inspect_urls_batch(service, site_url, urls)

                    if batch.get('aborted') and batch.get('total_inspected', 0) < 10:
                        self.logger.warning(
                            "  ⚠️  Batch abortito con pochi dati. "
                            "Fallback alla Performance API."
                        )
                    else:
                        batch['sample_size'] = batch['total_inspected']
                        batch['estimation_method'] = 'url_inspection_full'
                        self.logger.info(
                            f"  ✅ Ispezione completata: {batch['indexed']} indicizzate, "
                            f"{batch['not_indexed']} non indicizzate, "
                            f"{batch['errors']} errori "
                            f"({batch['duration_seconds']}s, {batch.get('cache_hits', 0)} da cache)"
                        )
                        return batch

            except PermissionError:
                self.logger.warning(
                    "  ⚠️  URL Inspection API non accessibile (Service Account non Owner). "
                    "Fallback alla Performance API."
                )
            except Exception as e:
                self.logger.warning(
                    f"  ⚠️  URL Inspection fallita ({str(e)[:120]}). "
                    f"Fallback alla Performance API."
                )

        # FALLBACK: Performance API
        self.logger.info(f"  📊 Fallback: stima basata su Performance API ({len(sample_urls)} pagine con dati)")
        return {
            'sample_size': len(sample_urls),
            'total_inspected': len(sample_urls),
            'indexed': len(sample_urls),
            'not_indexed': 0,
            'errors': 0,
            'index_rate': 100.0,
            'coverage_breakdown': {},
            'estimation_method': 'performance_api',
            'note': 'Stima basata su pagine con dati performance (URL Inspection API non disponibile)',
        }