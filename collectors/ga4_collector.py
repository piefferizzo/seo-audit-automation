import os
import yaml
from collections import defaultdict
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from collectors.base_collector import BaseCollector


# ---------------------------------------------------------------------------
# COSTANTI — Configurazione query GA4
# ---------------------------------------------------------------------------
GA4_SCOPES = ['https://www.googleapis.com/auth/analytics.readonly']
DEFAULT_DATE_RANGE_DAYS = 28

# Metriche predefinite per tipo di report
GA4_METRICS = {
    'overview': ['sessions', 'totalUsers', 'screenPageViews'],
    'engagement': ['bounceRate', 'averageSessionDuration'],
    'sources': ['sessions'],
    'devices': ['sessions'],
    'pages': ['screenPageViews'],
    # Landing pages: metriche session-scoped. Niente screenPageViews
    # (gonfierebbe i numeri perché è page-level e non session-level).
    'landing_pages': [
        'sessions',
        'totalUsers',
        'engagedSessions',
        'bounceRate',
        'averageSessionDuration',
    ],
    # Exit pages: 'exits' NON esiste in GA4 Data API v1beta.
    # Si stima con screenPageViews × bounceRate (come da logica originale).
    'exit_pages': ['screenPageViews', 'sessions', 'bounceRate'],
    'geo': ['sessions'],
    'new_vs_returning': ['sessions'],
    'trend': ['sessions'],
    'comparison': ['sessions', 'totalUsers', 'bounceRate'],
    'engaged': ['engagedSessions', 'engagementRate', 'averageSessionDuration'],
}

# Dimensioni predefinite per tipo di report
GA4_DIMENSIONS = {
    'sources': 'sessionDefaultChannelGroup',
    'devices': 'deviceCategory',
    'pages': 'pagePath',
    # 'landingPagePlusQueryString' è session-scoped: ogni sessione è
    # associata a UNA sola landing page. I duplicati che ne derivano
    # (path uguali con query string diverse) vengono aggregati dopo.
    'landing_pages': 'landingPagePlusQueryString',
    'exit_pages': 'unifiedPagePathScreen',
    'geo': 'country',
    'new_vs_returning': 'newVsReturning',
    'trend': 'date',
}


# ---------------------------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------------------------
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


def strip_query_string(path: str) -> str:
    """Rimuove la query string da un path (es. '/?utm_source=x' → '/')."""
    return path.split('?', 1)[0] if path else ''


class GA4Collector(BaseCollector):
    """Raccoglie dati da Google Analytics 4."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.credentials_file = config.get("GA4_CREDENTIALS_FILE", "credentials/ga4-credentials.json")
        self.properties_file = "ga4_properties.yaml"
        self._client = None

    def is_available(self) -> bool:
        """Verifica se le credenziali GA4 sono configurate."""
        if not self.credentials_file:
            self.logger.debug("GA4_CREDENTIALS_FILE non configurato")
            return False

        if not os.path.exists(self.credentials_file):
            self.logger.debug(f"File credenziali GA4 non esiste: {self.credentials_file}")
            return False

        return True

    def _get_property_id(self, domain: str) -> Optional[str]:
        """Ottiene il Property ID per il dominio dal file di configurazione."""
        try:
            if not os.path.exists(self.properties_file):
                self.logger.debug(f"File {self.properties_file} non trovato")
                return None

            with open(self.properties_file, 'r', encoding='utf-8') as f:
                properties = yaml.safe_load(f)

            if not properties:
                return None

            clean_domain = domain.replace('https://', '').replace('http://', '').replace('www.', '')

            # STRUTTURA 1: File con chiave "properties" (nuovo formato)
            if 'properties' in properties:
                props = properties['properties']

                if clean_domain in props:
                    prop_id = props[clean_domain]
                    if isinstance(prop_id, str):
                        self.logger.debug(f"  ✓ Property ID trovato (nuovo formato): {prop_id}")
                        return prop_id
                    elif isinstance(prop_id, dict):
                        prop_id = prop_id.get('property_id')
                        self.logger.debug(f"  ✓ Property ID trovato (nuovo formato complesso): {prop_id}")
                        return prop_id

                for d, prop_id in props.items():
                    if clean_domain in d or d in clean_domain:
                        if isinstance(prop_id, str):
                            self.logger.debug(f"  ✓ Property ID trovato (match parziale): {prop_id}")
                            return prop_id
                        elif isinstance(prop_id, dict):
                            prop_id = prop_id.get('property_id')
                            self.logger.debug(f"  ✓ Property ID trovato (match parziale complesso): {prop_id}")
                            return prop_id

            # STRUTTURA 2: File senza chiave "properties" (vecchio formato)
            else:
                if clean_domain in properties:
                    prop_data = properties[clean_domain]
                    if isinstance(prop_data, str):
                        self.logger.debug(f"  ✓ Property ID trovato (vecchio formato): {prop_data}")
                        return prop_data
                    elif isinstance(prop_data, dict):
                        prop_id = prop_data.get('property_id')
                        self.logger.debug(f"  ✓ Property ID trovato (vecchio formato complesso): {prop_id}")
                        return prop_id

                for d, prop_data in properties.items():
                    if clean_domain in d or d in clean_domain:
                        if isinstance(prop_data, str):
                            self.logger.debug(f"  ✓ Property ID trovato (match parziale): {prop_data}")
                            return prop_data
                        elif isinstance(prop_data, dict):
                            prop_id = prop_data.get('property_id')
                            self.logger.debug(f"  ✓ Property ID trovato (match parziale complesso): {prop_id}")
                            return prop_id

            self.logger.warning(f"  ⚠️  {clean_domain} non trovato in {self.properties_file}")
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
        """Esegue una query GA4 standardizzata."""
        try:
            from google.analytics.data_v1beta.types import (
                DateRange, Dimension, Metric, RunReportRequest, OrderBy
            )

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

            results = []
            for row in response.rows:
                row_data = {}

                if dimensions:
                    for i, dim in enumerate(dimensions):
                        row_data[dim] = row.dimension_values[i].value

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

        dates = get_date_range()

        results = {}

        # Metriche base
        results['overview'] = self._get_overview(client, property_id, dates)
        results['engagement'] = self._get_engagement(client, property_id, dates)
        results['traffic_sources'] = self._get_traffic_sources(client, property_id, dates)
        results['devices'] = self._get_devices(client, property_id, dates)
        results['top_pages'] = self._get_top_pages(client, property_id, dates)

        # Metriche avanzate (SEOZoom-like)
        results['landing_pages'] = self._get_landing_pages(client, property_id, dates)
        results['exit_pages'] = self._get_exit_pages(client, property_id, dates)
        results['new_vs_returning'] = self._get_new_vs_returning(client, property_id, dates)
        results['geo_distribution'] = self._get_geo_distribution(client, property_id, dates)
        results['traffic_trend'] = self._get_traffic_trend(client, property_id, dates)
        results['period_comparison'] = self._get_period_comparison(client, property_id, dates)
        results['engaged_sessions'] = self._get_engaged_sessions(client, property_id, dates)

        self.logger.info(f"  ✓ Dati GA4 raccolti per property {property_id}")

        return results

    # ---------------------------------------------------------------------------
    # METRICHE BASE
    # ---------------------------------------------------------------------------

    def _get_overview(self, client, property_id: str, dates: Dict[str, str]) -> Dict[str, Any]:
        """Ottiene overview generale."""
        rows = self._run_query(client, property_id, dates, metrics=GA4_METRICS['overview'])

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
        rows = self._run_query(client, property_id, dates, metrics=GA4_METRICS['engagement'])

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

    # ---------------------------------------------------------------------------
    # METRICHE AVANZATE (SEOZoom-like)
    # ---------------------------------------------------------------------------

    def _get_landing_pages(self, client, property_id: str, dates: Dict[str, str]) -> Dict[str, Any]:
        """Ottiene le top landing pages.

        Usa 'landingPagePlusQueryString' (session-scoped, una sola landing
        per sessione) e AGGREGA i path dopo aver rimosso la query string,
        per evitare righe duplicate tipo '/' + '/?utm=x' + '/?ref=y'.

        Fetch di 100 righe grezze per avere materiale sufficiente dopo
        l'aggregazione, poi si restituiscono le top 15 per sessioni.
        """
        rows = self._run_query(
            client, property_id, dates,
            metrics=GA4_METRICS['landing_pages'],
            dimensions=[GA4_DIMENSIONS['landing_pages']],
            order_by='sessions',
            limit=100
        )

        # Aggrega per path pulito
        aggregated = defaultdict(lambda: {
            'sessions': 0,
            'users': 0,
            'engaged_sessions': 0,
            'bounce_rate_sum': 0.0,
            'avg_duration_sum': 0.0,
            'count': 0,
        })

        for row in rows:
            raw_page = row.get('landingPagePlusQueryString', '') or ''
            page = strip_query_string(raw_page)
            if not page:
                continue

            agg = aggregated[page]
            agg['sessions'] += safe_int(row.get('sessions', 0))
            agg['users'] += safe_int(row.get('totalUsers', 0))
            agg['engaged_sessions'] += safe_int(row.get('engagedSessions', 0))
            agg['bounce_rate_sum'] += safe_float(row.get('bounceRate', 0))
            agg['avg_duration_sum'] += safe_float(row.get('averageSessionDuration', 0))
            agg['count'] += 1

        landing_pages = []
        for page, agg in aggregated.items():
            landing_pages.append({
                'page': page,
                'sessions': agg['sessions'],
                'users': agg['users'],
                'engaged_sessions': agg['engaged_sessions'],
                'bounce_rate': agg['bounce_rate_sum'] / agg['count'] if agg['count'] else 0.0,
                'avg_duration': agg['avg_duration_sum'] / agg['count'] if agg['count'] else 0.0,
            })

        # Ordina per sessioni decrescenti e prendi le top 15
        landing_pages.sort(key=lambda x: x['sessions'], reverse=True)
        landing_pages = landing_pages[:15]

        return {'landing_pages': landing_pages}

    def _get_exit_pages(self, client, property_id: str, dates: Dict[str, str]) -> Dict[str, Any]:
        """Ottiene le top exit pages.

        NOTA: la metrica 'exits' NON è disponibile in GA4 Data API v1beta
        (l'avevo erroneamente introdotta in una versione precedente e
        causava l'errore 400 'Field exits is not a valid metric').
        Si torna alla stima views × bounceRate, che è l'approssimazione
        standard finché GA4 non esporrà la metrica nativa.
        """
        rows = self._run_query(
            client, property_id, dates,
            metrics=GA4_METRICS['exit_pages'],
            dimensions=[GA4_DIMENSIONS['exit_pages']],
            order_by='screenPageViews',
            limit=15
        )

        exit_pages = []
        for row in rows:
            raw_page = row.get('unifiedPagePathScreen', '') or ''
            views = safe_int(row.get('screenPageViews', 0))
            bounce_rate = safe_float(row.get('bounceRate', 0))
            estimated_exits = int(views * bounce_rate)

            exit_pages.append({
                'page': strip_query_string(raw_page),
                'views': views,
                'sessions': safe_int(row.get('sessions', 0)),
                'bounce_rate': bounce_rate,
                'estimated_exits': estimated_exits,
            })

        return {'exit_pages': exit_pages}

    def _get_new_vs_returning(self, client, property_id: str, dates: Dict[str, str]) -> Dict[str, Any]:
        """Ottiene distribuzione nuovi vs utenti di ritorno."""
        rows = self._run_query(
            client, property_id, dates,
            metrics=GA4_METRICS['new_vs_returning'],
            dimensions=[GA4_DIMENSIONS['new_vs_returning']]
        )

        new_returning = {}
        for row in rows:
            user_type = row.get('newVsReturning', '')
            sessions = safe_int(row.get('sessions', 0))
            new_returning[user_type] = sessions

        return {'new_vs_returning': new_returning}

    def _get_geo_distribution(self, client, property_id: str, dates: Dict[str, str]) -> Dict[str, Any]:
        """Ottiene distribuzione geografica del traffico."""
        rows = self._run_query(
            client, property_id, dates,
            metrics=GA4_METRICS['geo'],
            dimensions=[GA4_DIMENSIONS['geo']],
            order_by='sessions',
            limit=10
        )

        geo_data = []
        for row in rows:
            geo_data.append({
                'country': row.get('country', ''),
                'sessions': safe_int(row.get('sessions', 0))
            })

        return {'geo_distribution': geo_data}

    def _get_traffic_trend(self, client, property_id: str, dates: Dict[str, str]) -> Dict[str, Any]:
        """Ottiene trend traffico giornaliero."""
        rows = self._run_query(
            client, property_id, dates,
            metrics=GA4_METRICS['trend'],
            dimensions=[GA4_DIMENSIONS['trend']],
            limit=30
        )

        trend_data = []
        for row in rows:
            trend_data.append({
                'date': row.get('date', ''),
                'sessions': safe_int(row.get('sessions', 0))
            })

        return {'trend': trend_data}

    def _get_period_comparison(self, client, property_id: str, dates: Dict[str, str]) -> Dict[str, Any]:
        """Confronta metriche tra periodo attuale e precedente."""
        try:
            # Calcola periodo precedente
            start_date = datetime.strptime(dates['start'], '%Y-%m-%d')
            end_date = datetime.strptime(dates['end'], '%Y-%m-%d')
            days_diff = (end_date - start_date).days

            prev_end = start_date - timedelta(days=1)
            prev_start = prev_end - timedelta(days=days_diff)

            # Query periodo attuale
            current_rows = self._run_query(
                client, property_id, dates,
                metrics=GA4_METRICS['comparison']
            )

            # Query periodo precedente
            prev_dates = {
                'start': prev_start.strftime('%Y-%m-%d'),
                'end': prev_end.strftime('%Y-%m-%d')
            }
            prev_rows = self._run_query(
                client, property_id, prev_dates,
                metrics=GA4_METRICS['comparison']
            )

            if current_rows and prev_rows:
                current = current_rows[0]
                previous = prev_rows[0]

                current_sessions = safe_int(current.get('sessions', 0))
                prev_sessions = safe_int(previous.get('sessions', 0))
                sessions_change = ((current_sessions - prev_sessions) / prev_sessions * 100) if prev_sessions > 0 else 0

                current_users = safe_int(current.get('totalUsers', 0))
                prev_users = safe_int(previous.get('totalUsers', 0))
                users_change = ((current_users - prev_users) / prev_users * 100) if prev_users > 0 else 0

                return {
                    'sessions': {
                        'current': current_sessions,
                        'previous': prev_sessions,
                        'change_percent': round(sessions_change, 1)
                    },
                    'users': {
                        'current': current_users,
                        'previous': prev_users,
                        'change_percent': round(users_change, 1)
                    }
                }

            return {}

        except Exception as e:
            self.logger.warning(f"Errore confronto periodi: {e}")
            return {}

    def _get_engaged_sessions(self, client, property_id: str, dates: Dict[str, str]) -> Dict[str, Any]:
        """Ottiene metriche engaged sessions."""
        rows = self._run_query(
            client, property_id, dates,
            metrics=GA4_METRICS['engaged']
        )

        if not rows:
            return {}

        row = rows[0]
        return {
            'engaged_sessions': safe_int(row.get('engagedSessions', 0)),
            'engagement_rate': safe_float(row.get('engagementRate', 0)),
            'avg_session_duration': safe_float(row.get('averageSessionDuration', 0)),
        }