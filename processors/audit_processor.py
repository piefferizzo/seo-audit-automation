"""
AuditProcessor - versione refattorizzata.

Cambiamenti rispetto all'originale (stessa identica logica di business,
stessi ID Audit, stesse soglie, stessi testi):
1. make_audit_row() elimina la duplicazione dello scaffolding a 8 chiavi
   ripetuta in ~70 check.
2. classify_threshold() centralizza il pattern ricorrente
   "> soglia critica -> FAIL, > soglia warning -> WARN, else OK".
3. La checklist (_generate_checklist) usa una tabella dichiarativa di
   regole (CHECKLIST_RULES) invece di ~35 tuple con lambda inline.
4. I log di DEBUG (self.logger.info) sono diventati self.logger.debug,
   così non inquinano più l'output in produzione ma restano disponibili
   per il debug del bug dei fogli drill-down.
"""

from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import yaml
import re
from utils.logger import setup_logger


# ---------------------------------------------------------------------------
# HELPER 1 — costruzione riga di audit (elimina lo scaffolding ripetuto)
# ---------------------------------------------------------------------------
def make_audit_row(
    audit_id: str,
    categoria: str,
    elemento: str,
    stato: str,
    severita: int,
    risultato: str,
    url: str = "",
    note: str = "",
) -> Dict[str, Any]:
    """Costruisce una riga di audit con lo schema standard a 8 chiavi."""
    return {
        "ID Audit": audit_id,
        "Categoria": categoria,
        "Elemento Analizzato": elemento,
        "Stato": stato,
        "Severità": severita,
        "Risultato / Evidenza": risultato,
        "URL / Link Evidenza": url,
        "Note Tecniche": note,
    }


# ---------------------------------------------------------------------------
# HELPER 2 — classificazione a soglie (FAIL/WARN/OK)
# ---------------------------------------------------------------------------
def classify_threshold(
    value: float, critical: float, warning: float, higher_is_worse: bool = True
) -> Tuple[str, int]:
    """Restituisce (stato, severità) confrontando value con due soglie."""
    if higher_is_worse:
        if value > critical:
            return "FAIL", 1
        elif value > warning:
            return "WARN", 2
        return "OK", 0
    else:
        if value < critical:
            return "FAIL", 1
        elif value < warning:
            return "WARN", 2
        return "OK", 0


class AuditProcessor:
    """Trasforma i dati grezzi dei collector nelle righe dell'Audit e della Checklist."""

    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        self.logger = setup_logger("AuditProcessor")

    def process(self, domain: str, raw_data: Dict[str, Any]) -> Dict[str, List[Dict]]:
        """Elabora tutti i dati grezzi e genera audit + checklist."""
        self.logger.debug(f"  🔍 DEBUG - Dati ricevuti nel processore:")
        self.logger.debug(f"    - pagespeed: {bool(raw_data.get('pagespeed'))}")
        self.logger.debug(f"    - gsc: {bool(raw_data.get('gsc'))}")
        self.logger.debug(f"    - ga4: {bool(raw_data.get('ga4'))}")
        self.logger.debug(f"    - html: {bool(raw_data.get('html'))}")
        self.logger.debug(f"    - geo: {bool(raw_data.get('geo'))}")

        audit_rows = []

        # 1. PAGE SPEED
        ps_data = raw_data.get("pagespeed", {})
        if ps_data:
            audit_rows.extend(self._process_pagespeed(ps_data, domain))

        # 2. GOOGLE SEARCH CONSOLE
        gsc_data = raw_data.get("gsc", {})
        if gsc_data:
            audit_rows.extend(self._process_gsc(gsc_data, domain))

        # 3. GOOGLE ANALYTICS 4 (base + avanzati)
        ga4_data = raw_data.get("ga4", {})
        if ga4_data:
            audit_rows.extend(self._process_ga4(ga4_data, domain))
            audit_rows.extend(self._process_ga4_advanced(ga4_data, domain))

        # 4. HTML CRAWLER
        html_data = raw_data.get("html", {})
        if html_data:
            audit_rows.extend(self._process_html(html_data, domain, gsc_data=gsc_data, ps_data=ps_data))
            audit_rows.extend(self._process_advanced_html(html_data, domain, ps_data=ps_data))
            audit_rows.extend(self._process_advanced_technical(html_data, domain))
            audit_rows.extend(self._process_content_advanced(html_data, domain))
            audit_rows.extend(self._process_favicon_and_images(html_data, domain))

        # 5. WHOIS
        whois_data = raw_data.get("whois", {})
        if whois_data:
            audit_rows.extend(self._process_whois(whois_data, domain))

        # 6. SEMRUSH
        semrush_data = raw_data.get("semrush", {})
        if semrush_data:
            audit_rows.extend(self._process_semrush(semrush_data, domain))

        # 7. MANUAL DATA
        manual_data = raw_data.get("manual", {})
        if manual_data:
            audit_rows.extend(self._process_manual(manual_data, domain))

        # 8. GEO/AEO DATA ← AGGIUNTO!
        geo_data = raw_data.get("geo", {})
        if geo_data:
            audit_rows.extend(self._process_geo(geo_data, domain))

        # 9. GENERA CHECKLIST
        checklist_rows = self._generate_checklist(audit_rows)

        # 10. GENERA EXECUTIVE SUMMARY
        summary = self._generate_summary(domain, audit_rows)

        # 11. ESTRAI DATI DRILL-DOWN
        drilldown_data = self._extract_drilldown_data(html_data)

        return {
            "audit": audit_rows,
            "checklist": checklist_rows,
            "summary": summary,
            "drilldown": drilldown_data
        }
    def _extract_drilldown_data(self, html_data: Dict) -> Dict[str, List[Dict]]:
        """Estrae i dati drill-down dal crawler HTML, includendo anche la homepage."""
        drilldown = html_data.get('drilldown', {}) if html_data else {}

        homepage_problems = self._extract_homepage_problems(html_data)

        images_problems = homepage_problems.get('images', []) + drilldown.get('images_problems', [])
        title_problems = homepage_problems.get('titles', []) + drilldown.get('title_problems', [])
        description_problems = homepage_problems.get('descriptions', []) + drilldown.get('description_problems', [])
        headings_problems = homepage_problems.get('headings', []) + drilldown.get('headings_problems', [])

        return {
            'images': images_problems,
            'titles': title_problems,
            'descriptions': description_problems,
            'headings': headings_problems,
            'pages_analyzed': len(drilldown.get('pages_analyzed', []))
        }

    def _extract_homepage_problems(self, html_data: Dict) -> Dict[str, List[Dict]]:
        """Estrae i problemi dalla homepage per popolare i fogli drill-down."""
        homepage = html_data.get('homepage', {}) if html_data else {}
        if not homepage or 'error' in homepage:
            return {'images': [], 'titles': [], 'descriptions': [], 'headings': []}

        problems = {'images': [], 'titles': [], 'descriptions': [], 'headings': []}

        # PROBLEMI IMMAGINI
        images = homepage.get('images', [])
        for img in images:
            src = img.get('src', '')
            alt = img.get('alt', '')
            width = img.get('width')
            height = img.get('height')

            if not src or src.startswith('data:'):
                continue

            skip_patterns = [
                r'linkedin\.com/collect',
                r'facebook\.com/tr',
                r'google-analytics\.com',
                r'googletagmanager\.com',
                r'secure\.gravatar\.com',
                r'www\.gravatar\.com',
            ]
            should_skip = any(re.search(p, src, re.IGNORECASE) for p in skip_patterns)
            if should_skip:
                continue

            if not alt or alt.strip() == '':
                problems['images'].append({'url': src, 'problem': 'Testo alt mancante'})

            if not width or not height:
                problems['images'].append({'url': src, 'problem': 'Attributi di dimensione mancanti'})

        # PROBLEMI TITLE
        title = homepage.get('title', '')
        title_len = len(title)
        url = homepage.get('url', '')

        if title:
            if title_len > 60:
                problems['titles'].append({'url': url, 'meta_title': title, 'problem': f'Oltre 60 caratteri ({title_len})'})
            elif title_len < 30:
                problems['titles'].append({'url': url, 'meta_title': title, 'problem': f'Sotto 30 caratteri ({title_len})'})
        else:
            problems['titles'].append({'url': url, 'meta_title': '[MANCANTE]', 'problem': 'Title assente'})

        # PROBLEMI DESCRIPTION
        description = homepage.get('meta_description', '')
        desc_len = len(description)

        if description:
            if desc_len > 155:
                problems['descriptions'].append({'url': url, 'meta_description': description, 'problem': f'Oltre 155 caratteri ({desc_len})'})
            elif desc_len < 70:
                problems['descriptions'].append({'url': url, 'meta_description': description, 'problem': f'Sotto 70 caratteri ({desc_len})'})
        else:
            problems['descriptions'].append({'url': url, 'meta_description': '[MANCANTE]', 'problem': 'Description assente'})

        # PROBLEMI HEADINGS
        headings = homepage.get('headings', {})
        h1_list = headings.get('h1', [])

        if len(h1_list) > 1:
            problems['headings'].append({
                'url': url,
                'h1-1': h1_list[0] if len(h1_list) > 0 else '',
                'h1-2': h1_list[1] if len(h1_list) > 1 else '',
                'problem': 'Multiplo'
            })

        for h1 in h1_list:
            if len(h1) > 70:
                problems['headings'].append({'url': url, 'h1-1': h1, 'h1-2': '', 'problem': f'Oltre 70 caratteri ({len(h1)})'})
                break

        if len(h1_list) == 0:
            problems['headings'].append({'url': url, 'h1-1': '', 'h1-2': '', 'problem': 'Assente'})

        return problems

    def _process_pagespeed(self, data: Dict, domain: str) -> List[Dict]:
        """Processa i dati di Google PageSpeed Insights."""
        rows = []
        mobile = data.get("mobile", {})
        thresholds = self.config["thresholds"]

        if not mobile:
            return rows

        lcp = mobile.get("lcp", 0)
        fcp = mobile.get("fcp", 0)
        cls = mobile.get("cls", 0)

        stato, sev = classify_threshold(lcp, thresholds["lcp_critical"], thresholds["lcp_warning"])
        rows.append(make_audit_row(
            "U-01", "Usability", "Core Web Vitals (Mobile)", stato, sev,
            f"FCP {fcp:.1f}s, LCP {lcp:.1f}s, CLS {cls:.2f}",
            f"https://pagespeed.web.dev/analysis?url={domain}",
            "Ridurre JS/CSS inutilizzati" if stato == "FAIL" else "",
        ))

        perf_score = mobile.get("performance_score", 0)
        acc_score = mobile.get("accessibility_score", 0)
        stato, sev = classify_threshold(
            perf_score, thresholds["lighthouse_perf_critical"], thresholds["lighthouse_perf_warning"],
            higher_is_worse=False,
        )
        rows.append(make_audit_row(
            "U-02", "Usability", "Lighthouse Performance Score", stato, sev,
            f"Performance {perf_score:.0f}/100, Accessibility {acc_score:.0f}/100",
            note="Ottimizzazione necessaria" if stato != "OK" else "",
        ))

        return rows

    def _process_gsc(self, data: Dict, domain: str) -> List[Dict]:
        """Processa i dati di Google Search Console."""
        rows = []

        verification = data.get("verification", "unknown")
        if verification in ["siteOwner", "siteFullUser", "restricted"]:
            stato, sev = "OK", 0
        else:
            stato, sev = "WARN", 2

        rows.append(make_audit_row(
            "GSC-01", "Technical", "Accesso Google Search Console", stato, sev,
            f"Permesso: {verification}",
            "https://search.google.com/search-console",
        ))

        performance = data.get("performance", [])
        if performance:
            total_clicks = sum(p.get("clicks", 0) for p in performance)
            total_impressions = sum(p.get("impressions", 0) for p in performance)

            if total_impressions > 0:
                avg_position = sum(p.get("position", 0) * p.get("impressions", 0) for p in performance) / total_impressions
            else:
                avg_position = 0

            stato, sev = ("OK", 0) if total_clicks > 0 else ("WARN", 2)

            rows.append(make_audit_row(
                "GSC-02", "General", "Performance Search Console (28 giorni)", stato, sev,
                f"Click: {total_clicks}, Impression: {total_impressions}, Posizione media: {avg_position:.1f}",
                "https://search.google.com/search-console/performance",
                f"Pagine analizzate: {len(performance)}",
            ))
        else:
            rows.append(make_audit_row(
                "GSC-02", "General", "Performance Search Console (28 giorni)", "WARN", 2,
                "Nessun dato di performance disponibile",
                "https://search.google.com/search-console/performance",
                "Il sito potrebbe non avere traffico organico",
            ))

        # GSC-05: Top Pagine per Click
        top_pages = data.get("top_pages", [])
        if top_pages:
            top_3_pages = top_pages[:3]
            parts = []
            for i, page in enumerate(top_3_pages, 1):
                page_path = page.get('page', '').replace(domain, '') or '/'
                clicks = page.get('clicks', 0)
                parts.append(f"#{i}{page_path}: {clicks} clic")

            rows.append(make_audit_row(
                "GSC-05", "General", "Top Pagine per Click", "OK", 0,
                ", ".join(parts),
                "https://search.google.com/search-console/performance",
            ))

        # GSC-06: Top Keyword per Click
        top_queries = data.get("top_queries", [])
        if top_queries:
            top_3_queries = top_queries[:3]
            parts = []
            for i, query in enumerate(top_3_queries, 1):
                query_text = query.get('query', '')
                clicks = query.get('clicks', 0)
                parts.append(f"#{i} '{query_text}': {clicks} clic")

            rows.append(make_audit_row(
                "GSC-06", "General", "Top Keyword per Click", "OK", 0,
                ", ".join(parts),
                "https://search.google.com/search-console/performance",
            ))

        # GSC-07: Distribuzione Posizioni
        position_dist = data.get("position_distribution", {})
        if position_dist and position_dist.get('distribution'):
            dist = position_dist['distribution']
            total = position_dist.get('total_queries', 0)

            top_3_count = dist.get('top_3', {}).get('count', 0)
            page_1_count = dist.get('page_1', {}).get('count', 0)
            page_2_count = dist.get('page_2', {}).get('count', 0)

            top_3_pct = (top_3_count / total * 100) if total > 0 else 0
            risultato = f"Top 3: {top_3_count} keyword ({top_3_pct:.1f}%), Pagina 1: {page_1_count}, Pagina 2: {page_2_count} su {total} totali"

            if total > 0 and top_3_pct > 20:
                stato, sev = "OK", 0
            else:
                stato, sev = "WARN", 2

            rows.append(make_audit_row(
                "GSC-07", "General", "Distribuzione Posizioni", stato, sev, risultato,
                "https://search.google.com/search-console/performance",
                "Migliorare posizionamento keyword in pagina 2" if stato == "WARN" else "",
            ))

        # GSC-08: Keyword Trend
        trending = data.get("trending_queries", {})
        if trending:
            growing = trending.get('growing', [])
            declining = trending.get('declining', [])
            new_queries = trending.get('new', [])

            if growing or declining or new_queries:
                parts = []
                if growing:
                    parts.append(f"{len(growing)} keyword in crescita")
                if declining:
                    parts.append(f"{len(declining)} keyword in calo")
                if new_queries:
                    parts.append(f"{len(new_queries)} keyword nuove")

                risultato = ", ".join(parts)
                stato, sev = ("OK", 0) if len(growing) > len(declining) else ("WARN", 2)

                rows.append(make_audit_row(
                    "GSC-08", "General", "Trend Keyword (vs periodo precedente)", stato, sev, risultato,
                    "https://search.google.com/search-console/performance",
                    "Investigare keyword in calo" if len(declining) > 0 else "",
                ))

        # GSC-09: Dati per Dispositivo
        devices = data.get("devices", {})
        if devices:
            desktop_data = devices.get('DESKTOP', {})
            mobile_data = devices.get('MOBILE', {})
            desktop_clicks = desktop_data.get('clicks', 0)
            mobile_clicks = mobile_data.get('clicks', 0)
            total_clicks = desktop_clicks + mobile_clicks

            if total_clicks > 0:
                mobile_pct = (mobile_clicks / total_clicks) * 100
                desktop_pct = (desktop_clicks / total_clicks) * 100
                risultato = f"Desktop: {desktop_clicks} clic ({desktop_pct:.1f}%), Mobile: {mobile_clicks} clic ({mobile_pct:.1f}%)"
                stato, sev = ("OK", 0) if mobile_pct > 50 else ("WARN", 2)

                rows.append(make_audit_row(
                    "GSC-09", "Usability", "Distribuzione Traffico per Dispositivo", stato, sev, risultato,
                    "https://search.google.com/search-console/performance",
                    "Ottimizzare esperienza mobile" if mobile_pct < 50 else "",
                ))

        # GSC-03: Sitemaps info
        sitemaps_info = data.get("sitemaps", {})
        if sitemaps_info and sitemaps_info.get('found'):
            sitemap_count = sitemaps_info.get('count', 0)
            total_urls = sitemaps_info.get('total_urls', 0)
            total_indexed = sitemaps_info.get('total_indexed', 0)

            if total_urls > 0:
                index_rate = (total_indexed / total_urls) * 100
                risultato = f"{sitemap_count} sitemap, {total_urls} URL inviate, {total_indexed} URL sitemap indicizzate ({index_rate:.1f}%)"
            else:
                index_rate = 0
                risultato = f"{sitemap_count} sitemap, {total_urls} URL inviate, {total_indexed} URL sitemap indicizzate"

            if total_urls > 0 and index_rate < 50:
                stato, sev, note = "WARN", 2, "Tasso di indicizzazione basso. Verificare qualità contenuti e struttura interna."
            elif total_indexed == 0 and total_urls > 0:
                stato, sev, note = "FAIL", 1, "Nessuna URL della sitemap indicizzata. Problema critico di indicizzazione."
            else:
                stato, sev, note = "OK", 0, ""

            rows.append(make_audit_row(
                "GSC-03", "Technical", "Sitemap in GSC", stato, sev, risultato,
                "https://search.google.com/search-console/sitemaps", note,
            ))

        # GSC-04: Stima pagine totali indicizzate
        indexed_estimate = data.get("indexed_estimate", {})
        if indexed_estimate and indexed_estimate.get('sample_size', 0) > 0:
            sample_size = indexed_estimate.get('sample_size', 0)
            indexed = indexed_estimate.get('indexed', 0)
            index_rate = indexed_estimate.get('index_rate', 0)
            method = indexed_estimate.get('estimation_method', 'unknown')
            note_base = indexed_estimate.get('note', '')

            if method == 'performance_api':
                risultato = f"Stima: ~{indexed} pagine indicizzate (basato su performance API, {sample_size} pagine con dati)"
            elif method == 'url_inspection':
                risultato = f"Stima: ~{indexed} pagine indicizzate (basato su campione di {sample_size} URL, tasso: {index_rate}%)"
            else:
                risultato = "Stima non disponibile"

            if index_rate < 50 and method != 'performance_api':
                stato, sev = "WARN", 2
                tech_note = "Tasso di indicizzazione reale basso. Investigare problemi tecnici o di qualità."
            else:
                stato, sev = "OK", 0
                tech_note = note_base

            rows.append(make_audit_row(
                "GSC-04", "Technical", "Stima Pagine Indicizzate", stato, sev, risultato,
                "https://search.google.com/search-console/index/coverage", tech_note,
            ))

        return rows
    def _process_ga4(self, data: Dict, domain: str) -> List[Dict]:
        """Processa i dati di Google Analytics 4."""
        rows = []

        overview = data.get('overview', {})
        if overview:
            sessions = overview.get('sessions', 0)
            users = overview.get('users', 0)
            pageviews = overview.get('pageviews', 0)
            stato, sev = ("OK", 0) if sessions > 100 else ("WARN", 2)

            rows.append(make_audit_row(
                "GA4-01", "General", "Traffico GA4 (28 giorni)", stato, sev,
                f"{sessions} sessioni, {users} utenti, {pageviews} pagine viste",
                "https://analytics.google.com/",
            ))

        engagement = data.get('engagement', {})
        if engagement:
            bounce_rate = engagement.get('bounce_rate', 0) * 100
            avg_duration = engagement.get('avg_session_duration', 0)

            if bounce_rate > 70:
                stato, sev = "FAIL", 2
            elif bounce_rate > 50:
                stato, sev = "WARN", 2
            else:
                stato, sev = "OK", 0

            rows.append(make_audit_row(
                "GA4-02", "Usability", "Bounce Rate", stato, sev,
                f"{bounce_rate:.1f}% bounce rate, {avg_duration:.1f}s durata media",
                "https://analytics.google.com/",
                "Migliorare contenuti e UX" if bounce_rate > 50 else "",
            ))

        traffic = data.get('traffic_sources', {})
        if traffic and traffic.get('sources'):
            sources = traffic['sources']
            organic_sessions = sum(s['sessions'] for s in sources if 'organic' in s['source'].lower())
            total_sessions = sum(s['sessions'] for s in sources)

            if total_sessions > 0:
                organic_pct = (organic_sessions / total_sessions) * 100
                stato, sev = ("OK", 0) if organic_pct > 30 else ("WARN", 2)

                rows.append(make_audit_row(
                    "GA4-03", "General", "Traffico Organico", stato, sev,
                    f"{organic_pct:.1f}% del traffico ({organic_sessions} sessioni)",
                    "https://analytics.google.com/",
                    "Migliorare SEO per aumentare traffico organico" if organic_pct < 30 else "",
                ))

        devices = data.get('devices', {})
        if devices and devices.get('devices'):
            device_data = devices['devices']
            mobile_sessions = device_data.get('mobile', 0)
            total_sessions = sum(device_data.values())

            if total_sessions > 0:
                mobile_pct = (mobile_sessions / total_sessions) * 100
                rows.append(make_audit_row(
                    "GA4-04", "Usability", "Traffico Mobile", "OK", 0,
                    f"{mobile_pct:.1f}% da mobile ({mobile_sessions} sessioni)",
                    "https://analytics.google.com/",
                ))

        top_pages = data.get('top_pages', {})
        if top_pages and top_pages.get('pages'):
            pages = top_pages['pages']
            rows.append(make_audit_row(
                "GA4-05", "Content", "Top Pagine (28 giorni)", "OK", 0,
                f"{len(pages)} pagine analizzate, top: {pages[0]['path']} ({pages[0]['views']} views)",
                "https://analytics.google.com/",
            ))

        return rows

    def _process_ga4_advanced(self, data: Dict, domain: str) -> List[Dict]:
        """Processa i dati GA4 avanzati (SEOZoom-like)."""
        rows = []
        
        # GA4-06: Top Landing Pages
        landing_pages = data.get('landing_pages', {})
        if landing_pages and landing_pages.get('landing_pages'):
            top_landing = landing_pages['landing_pages'][0]
            rows.append(make_audit_row(
                "GA4-06", "Content", "Top Landing Page", "OK", 0,
                f"{top_landing['page']} ({top_landing['sessions']} sessioni, {top_landing['bounce_rate']*100:.1f}% bounce)",
                "https://analytics.google.com/"
            ))
        
        # GA4-07: Top Exit Pages
        exit_pages = data.get('exit_pages', {})
        if exit_pages and exit_pages.get('exit_pages'):
            top_exit = exit_pages['exit_pages'][0]
            rows.append(make_audit_row(
                "GA4-07", "Content", "Top Exit Page", "OK", 0,
                f"{top_exit['page']} ({top_exit['estimated_exits']} exit stimati)",
                "https://analytics.google.com/"
            ))
        
        # GA4-08: Trend Traffico
        trend = data.get('traffic_trend', {})
        if trend and trend.get('trend'):
            trend_data = trend['trend']
            if len(trend_data) >= 7:
                recent_sessions = sum(d['sessions'] for d in trend_data[-7:])
                previous_sessions = sum(d['sessions'] for d in trend_data[-14:-7]) if len(trend_data) >= 14 else 0
                
                if previous_sessions > 0:
                    change = ((recent_sessions - previous_sessions) / previous_sessions) * 100
                    if change > 10:
                        stato, sev = "OK", 0
                        risultato = f"Trend positivo: +{change:.1f}% ultimi 7 giorni"
                    elif change < -10:
                        stato, sev = "WARN", 2
                        risultato = f"Trend negativo: {change:.1f}% ultimi 7 giorni"
                    else:
                        stato, sev = "OK", 0
                        risultato = f"Trend stabile: {change:.1f}% ultimi 7 giorni"
                    
                    rows.append(make_audit_row(
                        "GA4-08", "General", "Trend Traffico Organico", stato, sev,
                        risultato, "https://analytics.google.com/"
                    ))
        
        # GA4-09: Variazione Sessioni
        comparison = data.get('period_comparison', {})
        if comparison and comparison.get('sessions'):
            sessions_data = comparison['sessions']
            change = sessions_data.get('change_percent', 0)
            
            if change > 10:
                stato, sev = "OK", 0
            elif change > 0:
                stato, sev = "INFO", 0
            else:
                stato, sev = "WARN", 2
            
            rows.append(make_audit_row(
                "GA4-09", "General", "Variazione Sessioni (vs periodo precedente)", stato, sev,
                f"{sessions_data['current']} sessioni ({change:+.1f}%)",
                "https://analytics.google.com/"
            ))
        
        # GA4-10: Nuovi vs Ritorno
        new_returning = data.get('new_vs_returning', {})
        if new_returning and new_returning.get('new_vs_returning'):
            nr_data = new_returning['new_vs_returning']
            new_sessions = nr_data.get('new', 0)
            returning_sessions = nr_data.get('returning', 0)
            total = new_sessions + returning_sessions
            
            if total > 0:
                new_pct = (new_sessions / total) * 100
                returning_pct = (returning_sessions / total) * 100
                
                rows.append(make_audit_row(
                    "GA4-10", "Content", "Nuovi vs Utenti di Ritorno", "OK", 0,
                    f"Nuovi: {new_pct:.1f}%, Ritorno: {returning_pct:.1f}%",
                    "https://analytics.google.com/"
                ))
        
        # GA4-11: Distribuzione Geografica
        geo = data.get('geo_distribution', {})
        if geo and geo.get('geo_distribution'):
            top_country = geo['geo_distribution'][0]
            rows.append(make_audit_row(
                "GA4-11", "Content", "Top Paese per Traffico", "OK", 0,
                f"{top_country['country']} ({top_country['sessions']} sessioni)",
                "https://analytics.google.com/"
            ))
        
        # GA4-12: Engaged Sessions
        engaged = data.get('engaged_sessions', {})
        if engaged:
            engaged_sessions = engaged.get('engaged_sessions', 0)
            engagement_rate = engaged.get('engagement_rate', 0) * 100
            
            if engagement_rate > 50:
                stato, sev = "OK", 0
            elif engagement_rate > 30:
                stato, sev = "INFO", 0
            else:
                stato, sev = "WARN", 2
            
            rows.append(make_audit_row(
                "GA4-12", "Usability", "Engaged Sessions", stato, sev,
                f"{engaged_sessions} sessioni engage ({engagement_rate:.1f}%)",
                "https://analytics.google.com/"
            ))
        
        return rows

    def _process_html(self, data: Dict, domain: str, gsc_data: Dict = None, ps_data: Dict = None) -> List[Dict]:
        """Processa i dati del crawler HTML."""
        rows = []
        homepage = data.get('homepage', {})

        if not homepage or 'error' in homepage:
            return rows

        # T-02: Sitemap
        sitemap = data.get('sitemap', {})

        if not sitemap.get('exists') and gsc_data and gsc_data.get('sitemaps', {}).get('found'):
            gsc_sitemaps = gsc_data['sitemaps']
            if gsc_sitemaps['sitemaps']:
                first_sitemap = gsc_sitemaps['sitemaps'][0]
                sitemap = {
                    'exists': True,
                    'url': first_sitemap['path'],
                    'status_code': 200,
                    'is_valid_xml': True,
                    'url_count': gsc_sitemaps.get('total_urls', 0),
                    'found_via': 'gsc',
                    'indexed_count': gsc_sitemaps.get('total_indexed', 0),
                    'sitemap_count': gsc_sitemaps.get('count', 1)
                }

        if sitemap.get('exists'):
            url_count = sitemap.get('url_count', 0)
            found_via = sitemap.get('found_via', 'discovery')
            indexed_count = sitemap.get('indexed_count', 0)
            sitemap_count = sitemap.get('sitemap_count', 1)

            if found_via == 'gsc':
                risultato = f"Presente in GSC ({url_count} URL, {indexed_count} indicizzate, {sitemap_count} sitemap)"
            else:
                risultato = f"Presente ({url_count} URL, trovata via {found_via})"
            stato, sev = "OK", 0
        else:
            risultato = "Non presente"
            stato, sev = "FAIL", 1

        rows.append(make_audit_row(
            "T-02", "Technical", "Sitemap.xml", stato, sev, risultato, sitemap.get('url', ''),
        ))

        # T-03: Robots.txt
        robots = data.get('robots', {})
        sitemap_url = robots.get('sitemap_url', '')
        has_sitemap_ref = robots.get('has_sitemap', False)

        risultato = f"Presente (con sitemap: {sitemap_url})" if has_sitemap_ref else "Presente (senza sitemap)"

        rows.append(make_audit_row(
            "T-03", "Technical", "Robots.txt",
            "OK" if robots.get('exists') else "FAIL",
            0 if robots.get('exists') else 1,
            risultato, robots.get('url', ''),
            "" if has_sitemap_ref else "Aggiungere riferimento alla sitemap",
        ))

        # H-01: Meta Title
        title = homepage.get('title', '')
        title_len = len(title)

        if not title:
            stato, sev, risultato, note = "FAIL", 1, "Mancante", "Ottimizzare con keyword target"
        elif title_len < 30:
            stato, sev = "WARN", 2
            risultato = f"Presente ma troppo corto ({title_len} caratteri, ottimale: 50-60)"
            note = "Allungare il title a 50-60 caratteri"
        elif title_len > 60:
            stato, sev = "WARN", 2
            risultato = f"Presente ma troppo lungo ({title_len} caratteri, ottimale: 50-60)"
            note = "Accorciare il title a 50-60 caratteri"
        else:
            stato, sev, note = "OK", 0, ""
            risultato = f"Presente ({title_len} caratteri)"

        rows.append(make_audit_row("H-01", "HTML", "Meta Title", stato, sev, risultato, homepage.get('url', ''), note))

        # H-02: Meta Description
        description = homepage.get('meta_description', '')
        desc_len = len(description)

        if not description:
            stato, sev, risultato, note = "FAIL", 1, "Mancante", "Ottimizzare con keyword target"
        elif desc_len < 120:
            stato, sev = "WARN", 2
            risultato = f"Presente ma troppo corta ({desc_len} caratteri, ottimale: 120-160)"
            note = "Allungare la description a 120-160 caratteri"
        elif desc_len > 160:
            stato, sev = "WARN", 2
            risultato = f"Presente ma troppo lunga ({desc_len} caratteri, ottimale: 120-160)"
            note = "Accorciare la description a 120-160 caratteri"
        else:
            stato, sev, note = "OK", 0, ""
            risultato = f"Presente ({desc_len} caratteri)"

        rows.append(make_audit_row("H-02", "HTML", "Meta Description", stato, sev, risultato, homepage.get('url', ''), note))

        # H-03: Canonical
        canonical = homepage.get('canonical', '')
        rows.append(make_audit_row(
            "H-03", "HTML", "Canonical",
            "OK" if canonical else "FAIL", 0 if canonical else 1,
            "Presente" if canonical else "Mancante", homepage.get('url', ''),
        ))

        # H-04: Headings (H1)
        headings = homepage.get('headings', {})
        h1_count = len(headings.get('h1', []))
        rows.append(make_audit_row(
            "H-04", "HTML", "Heading H1",
            "OK" if h1_count == 1 else "FAIL", 0 if h1_count == 1 else 1,
            f"{h1_count} H1 presente" if h1_count > 0 else "Nessun H1",
            homepage.get('url', ''),
            "Ottimizzare con keyword target" if h1_count != 1 else "",
        ))

        # H-05: Images Alt Tag
        images = homepage.get('images', [])
        total_images = len(images)
        images_without_alt = len([img for img in images if not img.get('alt')])
        alt_percentage = (images_without_alt / total_images * 100) if total_images > 0 else 0

        if total_images == 0:
            stato, sev, risultato, note = "OK", 0, "Nessuna immagine sulla homepage", ""
        elif alt_percentage == 0:
            stato, sev, risultato, note = "OK", 0, f"Tutte le {total_images} immagini hanno alt text", ""
        elif alt_percentage < 10:
            stato, sev = "WARN", 2
            risultato = f"{images_without_alt}/{total_images} immagini senza alt ({alt_percentage:.1f}%)"
            note = "Correzione minore, ma utile per accessibilità"
        else:
            stato, sev = "FAIL", 2
            risultato = f"{images_without_alt}/{total_images} immagini senza alt ({alt_percentage:.1f}%)"
            note = "Aggiungere alt text descrittivi"

        rows.append(make_audit_row("H-05", "HTML", "Images Alt Tag", stato, sev, risultato, homepage.get('url', ''), note))

        # H-06: Structured Data
        structured_data = homepage.get('structured_data', [])
        rows.append(make_audit_row(
            "H-06", "HTML", "Structured Data (Schema.org)",
            "OK" if structured_data else "FAIL", 0 if structured_data else 2,
            f"{len(structured_data)} blocchi presenti" if structured_data else "Non presenti",
            homepage.get('url', ''),
            "Implementare markup Schema.org" if not structured_data else "",
        ))

        # H-07: Open Graph
        og_tags = homepage.get('og_tags', {})
        rows.append(make_audit_row(
            "H-07", "HTML", "Open Graph",
            "OK" if og_tags else "WARN", 0 if og_tags else 2,
            f"{len(og_tags)} tag presenti" if og_tags else "Non presenti",
            homepage.get('url', ''),
        ))

        # H-08: Hreflang
        hreflang = homepage.get('hreflang', [])
        lang = homepage.get('lang', '')
        valid_hreflang = [h for h in hreflang if h.get('href')]

        if len(valid_hreflang) > 0:
            stato, sev, risultato, note = "OK", 0, f"{len(valid_hreflang)} lingue presenti", ""
        elif not lang or lang in ['it', 'it-IT', 'en', 'en-US']:
            stato, sev = "N/A", 0
            risultato = f"Non necessario (sito monolingua: {lang or 'non specificato'})"
            note = ""
        else:
            stato, sev, risultato, note = "WARN", 2, "Non presente", ""

        rows.append(make_audit_row("H-08", "HTML", "Hreflang", stato, sev, risultato, homepage.get('url', ''), note))

        # U-03: Viewport
        viewport = homepage.get('viewport', '')
        rows.append(make_audit_row(
            "U-03", "Usability", "Viewport (Responsive)",
            "OK" if viewport else "FAIL", 0 if viewport else 1,
            "Presente" if viewport else "Mancante", homepage.get('url', ''),
        ))

        # H-09: 404 Custom
        check_404 = data.get('404', {})
        rows.append(make_audit_row(
            "H-09", "HTML", "404 Custom Page",
            "OK" if check_404.get('is_custom') else "FAIL", 0 if check_404.get('is_custom') else 2,
            "Presente" if check_404.get('is_custom') else "Non presente o generica", "",
            "Creare pagina 404 personalizzata" if not check_404.get('is_custom') else "",
        ))

        # H-10: Content Language
        rows.append(make_audit_row(
            "H-10", "HTML", "Content Language",
            "OK" if lang else "WARN", 0 if lang else 2,
            f"Lang: {lang}" if lang else "Non impostato", homepage.get('url', ''),
        ))

        # T-04: Internal Links
        internal_links = homepage.get('internal_links', [])
        rows.append(make_audit_row(
            "T-04", "Technical", "Internal Links",
            "OK" if len(internal_links) > 5 else "WARN", 0 if len(internal_links) > 5 else 2,
            f"{len(internal_links)} link interni trovati", homepage.get('url', ''),
        ))

        # C-01: Word Count
        word_count = homepage.get('word_count', 0)
        rows.append(make_audit_row(
            "C-01", "Content", "Content Length",
            "OK" if word_count > 300 else "WARN", 0 if word_count > 300 else 2,
            f"{word_count} parole", homepage.get('url', ''),
            "Aumentare contenuto" if word_count < 300 else "",
        ))

        # T-05: Breadcrumbs
        breadcrumbs = data.get('breadcrumbs', {})
        site_levels = data.get('site_structure', {}).get('levels', 0)

        if breadcrumbs.get('present'):
            stato, sev, risultato, note = "OK", 0, f"Presenti ({breadcrumbs.get('count', 0)} livelli)", ""
        elif site_levels <= 2:
            stato, sev = "INFO", 0
            risultato = f"Non presenti (struttura semplice: {site_levels} livelli)"
            note = "Non critici per siti con struttura piatta"
        else:
            stato, sev, risultato = "FAIL", 2, "Non presenti"
            note = "Implementare breadcrumbs per migliorare UX e SEO"

        rows.append(make_audit_row("T-05", "Technical", "Breadcrumbs", stato, sev, risultato, homepage.get('url', ''), note))

        # T-06: HTTP to HTTPS Redirect
        redirect = data.get('redirect', {})
        http_to_https = redirect.get('http_to_https', {})
        https_present = data.get('https_present', True)
        mixed_content = data.get('mixed_content', {})
        has_mixed = mixed_content.get('has_mixed_content', False)

        if https_present and not has_mixed:
            stato, sev, risultato, note = "OK", 0, "HTTPS attivo e funzionante", ""
        elif http_to_https.get('redirects') and http_to_https.get('is_https'):
            stato, sev, risultato, note = "OK", 0, "Redirect corretto", ""
        else:
            stato, sev, risultato = "FAIL", 1, "Redirect mancante o errato"
            note = "Configurare redirect 301 da HTTP a HTTPS"

        rows.append(make_audit_row("T-06", "Technical", "HTTP to HTTPS Redirect", stato, sev, risultato, "", note))

        # H-11: Image Weight
        image_analysis = data.get('image_analysis', {})
        heavy_images = image_analysis.get('heavy_images', [])
        rows.append(make_audit_row(
            "H-11", "HTML", "Image Weight (>100kb)",
            "OK" if not heavy_images else "WARN", 0 if not heavy_images else 2,
            f"{len(heavy_images)} immagini pesanti" if heavy_images else "Tutte le immagini ottimizzate",
            homepage.get('url', ''),
            "Ottimizzare peso immagini (WebP, compressione)" if heavy_images else "",
        ))

        # T-07: Anchor Text
        anchor_text = data.get('anchor_text', {})
        generic_count = anchor_text.get('generic_anchors', 0)
        rows.append(make_audit_row(
            "T-07", "Technical", "Internal Anchor Text",
            "OK" if generic_count == 0 else "WARN", 0 if generic_count == 0 else 2,
            f"{generic_count} anchor text generici" if generic_count > 0 else "Anchor text ottimizzati",
            homepage.get('url', ''),
            "Ottimizzare anchor text con keyword descrittive" if generic_count > 0 else "",
        ))

        # T-08: URL Structure
        url_structure = data.get('url_structure', {})
        deep_links = url_structure.get('deep_links', 0)
        rows.append(make_audit_row(
            "T-08", "Technical", "URL Structure (Deep Links)",
            "OK" if deep_links < 5 else "WARN", 0 if deep_links < 5 else 2,
            f"{deep_links} link profondi (>3 livelli)", homepage.get('url', ''),
            "Ridurre profondità URL per migliorare crawling" if deep_links >= 5 else "",
        ))

        # H-12: HTML5 Doctype
        html5 = data.get('html5', {})
        rows.append(make_audit_row(
            "H-12", "HTML", "HTML5 Doctype",
            "OK" if html5.get('html5') else "INFO", 0,
            "HTML5 valido" if html5.get('html5') else "Doctype non HTML5 (impatto SEO marginale)",
            homepage.get('url', ''),
        ))

        # H-13: Logo
        logo = data.get('logo', {})
        rows.append(make_audit_row(
            "H-13", "HTML", "Logo Optimization",
            "OK" if logo.get('found') else "WARN", 0 if logo.get('found') else 2,
            "Logo presente" if logo.get('found') else "Logo non trovato", homepage.get('url', ''),
        ))

        return rows

    def _process_advanced_html(self, data: Dict, domain: str, ps_data: Dict = None) -> List[Dict]:
        """Processa i dati avanzati del crawler HTML."""
        rows = []
        homepage = data.get('homepage', {})

        if not homepage or 'error' in homepage:
            return rows

        # C-02: Duplicate Content
        duplicate_content = data.get('duplicate_content', {})
        rows.append(make_audit_row(
            "C-02", "Content", "Duplicate Content",
            "OK" if not duplicate_content.get('has_duplicates') else "FAIL",
            0 if not duplicate_content.get('has_duplicates') else 1,
            f"{duplicate_content.get('duplicate_count', 0)} duplicati rilevati" if duplicate_content.get('has_duplicates') else "Nessun contenuto duplicato",
            homepage.get('url', ''),
            "Rimuovere o canonicalizzare contenuti duplicati" if duplicate_content.get('has_duplicates') else "",
        ))

        # T-09: CSS/JS Analysis
        css_js = data.get('css_js_analysis', {})
        total_files = css_js.get('total_css_js', 0)
        rows.append(make_audit_row(
            "T-09", "Technical", "CSS/JS Files",
            "OK" if total_files < 20 else "WARN", 0 if total_files < 20 else 2,
            f"{total_files} file CSS/JS ({css_js.get('css_files_count', 0)} CSS, {css_js.get('js_files_count', 0)} JS)",
            homepage.get('url', ''),
            "Minificare e combinare file CSS/JS" if total_files >= 20 else "",
        ))

        # H-14: Pagination
        pagination = data.get('pagination', {})
        internal_pages_count = len(data.get('internal_pages', []))

        if pagination.get('found'):
            stato, sev, risultato, note = "OK", 0, "Presente", ""
        elif internal_pages_count < 20:
            stato, sev = "N/A", 0
            risultato = f"Non necessaria (sito con poche pagine: ~{internal_pages_count})"
            note = ""
        else:
            stato, sev, risultato, note = "WARN", 2, "Non presente", ""

        rows.append(make_audit_row("H-14", "HTML", "Pagination", stato, sev, risultato, homepage.get('url', ''), note))

        # T-10: Site Structure
        site_structure = data.get('site_structure', {})
        levels = site_structure.get('levels', 0)
        rows.append(make_audit_row(
            "T-10", "Technical", "Site Structure (Levels)",
            "OK" if levels <= 3 else "WARN", 0 if levels <= 3 else 2,
            f"{levels} livelli di profondità", homepage.get('url', ''),
            "Ridurre profondità struttura" if levels > 3 else "",
        ))

        # U-04: AMP
        amp = data.get('amp_check', {})
        rows.append(make_audit_row(
            "U-04", "Usability", "AMP (Accelerated Mobile Pages)",
            "OK" if amp.get('has_amp') else "INFO", 0,
            "Presente" if amp.get('has_amp') else "Non presente (non più requisito Google)",
            homepage.get('url', ''),
        ))

        # T-11: CDN
        cdn = data.get('cdn_check', {})
        lcp = 0
        if ps_data and ps_data.get('mobile'):
            lcp = ps_data['mobile'].get('lcp', 0)

        if cdn.get('has_cdn'):
            stato, sev, risultato, note = "OK", 0, f"Presente ({cdn.get('server', 'unknown')})", ""
        elif lcp > 4.0:
            stato, sev = "WARN", 2
            risultato = f"Non rilevata (LCP {lcp:.1f}s > 4s)"
            note = "Implementare CDN per migliorare performance"
        else:
            stato, sev = "INFO", 0
            risultato = f"Non rilevata (LCP {lcp:.1f}s, performance accettabili)"
            note = ""

        rows.append(make_audit_row("T-11", "Technical", "CDN (Content Delivery Network)", stato, sev, risultato, homepage.get('url', ''), note))

        # H-15: Image Dimensions
        image_dims = data.get('image_dimensions', {})
        without_dims = image_dims.get('without_dimensions', 0)
        total_images = image_dims.get('total_images', 0)

        if total_images == 0:
            stato, sev, risultato = "OK", 0, "Nessuna immagine trovata"
        elif without_dims == 0:
            stato, sev, risultato = "OK", 0, "Tutte le immagini hanno dimensioni specificate"
        else:
            stato, sev = "WARN", 2
            risultato = f"{without_dims}/{total_images} immagini senza dimensioni"

        rows.append(make_audit_row(
            "H-15", "HTML", "Image Dimensions (width/height)", stato, sev, risultato, homepage.get('url', ''),
            "Specificare width e height per tutte le immagini" if without_dims > 0 else "",
        ))

        return rows

    def _process_advanced_technical(self, data: Dict, domain: str) -> List[Dict]:
        """Processa i check tecnici avanzati."""
        rows = []
        homepage = data.get('homepage', {})

        if not homepage or 'error' in homepage:
            return rows

        # T-12: Crawling Errors
        rows.append(make_audit_row(
            "T-12", "Technical", "Crawling Errors", "OK", 0,
            "Nessun errore critico rilevato",
            "https://search.google.com/search-console/index/coverage",
        ))

        # T-13: Indexability Analysis
        indexability = data.get('indexability', {})
        if indexability:
            noindex = indexability.get('noindex', False)
            canonical_correct = indexability.get('canonical_correct', False)

            if noindex:
                stato, sev, risultato = "FAIL", 1, "Pagina noindex"
            elif not canonical_correct:
                stato, sev, risultato = "WARN", 2, "Canonical non self-referencing"
            else:
                stato, sev, risultato = "OK", 0, "Pagina indexabile correttamente"

            rows.append(make_audit_row(
                "T-13", "Technical", "Indexability Analysis", stato, sev, risultato, homepage.get('url', ''),
                "Rimuovere noindex" if noindex else ("Correggere canonical" if not canonical_correct else ""),
            ))

        # T-14: HTTP Headers
        http_headers = data.get('http_headers', {})
        if http_headers:
            has_security = http_headers.get('has_security_headers', False)
            rows.append(make_audit_row(
                "T-14", "Technical", "HTTP Security Headers",
                "OK" if has_security else "WARN", 0 if has_security else 2,
                f"Server: {http_headers.get('server', 'unknown')}" + (", Security headers presenti" if has_security else ", Security headers mancanti"),
                homepage.get('url', ''),
                "Aggiungere X-Frame-Options, HSTS" if not has_security else "",
            ))

        # T-15: Status Codes
        status_codes = data.get('status_codes', {})
        if status_codes:
            page_status = status_codes.get('page_status', 0)
            broken = status_codes.get('broken_resources', 0)

            if page_status == 200 and broken == 0:
                stato, sev, risultato = "OK", 0, f"Status {page_status}, tutte le risorse OK"
            elif page_status == 200:
                stato, sev, risultato = "WARN", 2, f"Status {page_status}, {broken} risorse rotte"
            else:
                stato, sev, risultato = "FAIL", 1, f"Status {page_status}"

            rows.append(make_audit_row(
                "T-15", "Technical", "Status Codes Analysis", stato, sev, risultato, homepage.get('url', ''),
                "Correggere risorse rotte" if broken > 0 else "",
            ))

        # T-16: www vs non-www Redirect
        www_redirect = data.get('www_redirect', {})
        if www_redirect:
            consistent = www_redirect.get('consistent', False)
            rows.append(make_audit_row(
                "T-16", "Technical", "www vs non-www Redirect",
                "OK" if consistent else "WARN", 0 if consistent else 2,
                "Redirect coerente" if consistent else "Redirect inconsistente o mancante", "",
                "Configurare redirect 301 coerente" if not consistent else "",
            ))

        # T-17: Mixed Content
        mixed_content = data.get('mixed_content', {})
        if mixed_content:
            has_mixed = mixed_content.get('has_mixed_content', False)
            count = mixed_content.get('count', 0)
            rows.append(make_audit_row(
                "T-17", "Technical", "Mixed Content (HTTP su HTTPS)",
                "FAIL" if has_mixed else "OK", 1 if has_mixed else 0,
                f"{count} risorse HTTP su pagina HTTPS" if has_mixed else "Nessun mixed content",
                homepage.get('url', ''),
                "Aggiornare risorse a HTTPS" if has_mixed else "",
            ))

        # T-18: Redirect Chains
        redirect_chains = data.get('redirect_chains', {})
        if redirect_chains:
            has_chain = redirect_chains.get('has_chain', False)
            chain_length = redirect_chains.get('chain_length', 0)
            rows.append(make_audit_row(
                "T-18", "Technical", "Redirect Chains",
                "WARN" if has_chain else "OK", 2 if has_chain else 0,
                f"Catena di {chain_length} redirect" if has_chain else "Nessuna catena di redirect",
                homepage.get('url', ''),
                "Semplificare redirect a singolo hop" if has_chain else "",
            ))

        # T-19: CSS Issues
        css_issues = data.get('css_issues', {})
        if css_issues:
            too_many = css_issues.get('too_many_files', False)
            total = css_issues.get('total_css_files', 0)
            rows.append(make_audit_row(
                "T-19", "Technical", "CSS Files Optimization",
                "WARN" if too_many else "OK", 2 if too_many else 0,
                f"{total} file CSS esterni" + (" (troppi)" if too_many else ""),
                homepage.get('url', ''),
                "Combinare e minificare CSS" if too_many else "",
            ))

        # T-20: JS Issues
        js_issues = data.get('js_issues', {})
        if js_issues:
            too_many = js_issues.get('too_many_files', False)
            total = js_issues.get('total_js_files', 0)
            rows.append(make_audit_row(
                "T-20", "Technical", "JavaScript Files Optimization",
                "WARN" if too_many else "OK", 2 if too_many else 0,
                f"{total} file JS esterni" + (" (troppi)" if too_many else ""),
                homepage.get('url', ''),
                "Deferire o caricare async JS" if too_many else "",
            ))

        # T-21: Subdomains
        subdomains = data.get('subdomains', {})
        if subdomains:
            has_subdomains = subdomains.get('has_subdomains', False)
            count = subdomains.get('count', 0)
            rows.append(make_audit_row(
                "T-21", "Technical", "Subdomains Detection", "OK", 0,
                f"{count} sottodomini rilevati" if has_subdomains else "Nessun sottodominio",
                homepage.get('url', ''),
            ))

        return rows

    def _process_content_advanced(self, data: Dict, domain: str) -> List[Dict]:
        """Processa l'analisi avanzata dei contenuti."""
        rows = []
        homepage = data.get('homepage', {})

        if not homepage or 'error' in homepage:
            return rows

        site_type = data.get('site_type', 'corporate')
        content_quality = data.get('content_quality', {})

        # C-03: Focus Keyword in Title
        if content_quality:
            keyword_in_title = content_quality.get('keyword_in_title', False)
            rows.append(make_audit_row(
                "C-03", "Content", "Focus Keyword in Title",
                "OK" if keyword_in_title else "WARN", 0 if keyword_in_title else 2,
                "Keyword presente nel title" if keyword_in_title else "Keyword non trovata nel title",
                homepage.get('url', ''),
                "Includere keyword principale nel title" if not keyword_in_title else "",
            ))

            # C-04: Focus Keyword in H1
            keyword_in_h1 = content_quality.get('keyword_in_h1', False)
            rows.append(make_audit_row(
                "C-04", "Content", "Focus Keyword in H1",
                "OK" if keyword_in_h1 else "WARN", 0 if keyword_in_h1 else 2,
                "Keyword presente nell'H1" if keyword_in_h1 else "Keyword non trovata nell'H1",
                homepage.get('url', ''),
                "Includere keyword principale nell'H1" if not keyword_in_h1 else "",
            ))

            # C-05: Keyword Density
            density = content_quality.get('keyword_density', 0)
            if density == 0:
                stato, sev, risultato, note = "WARN", 2, "Densità keyword non calcolabile", "Verificare presenza keyword nel contenuto"
            elif 1.0 <= density <= 3.0:
                stato, sev, risultato, note = "OK", 0, f"Densità keyword: {density}% (ottimale)", ""
            elif density < 1.0:
                stato, sev = "WARN", 2
                risultato = f"Densità keyword: {density}% (bassa)"
                note = "Aumentare densità keyword (target: 1-3%)"
            else:
                stato, sev = "WARN", 2
                risultato = f"Densità keyword: {density}% (alta)"
                note = "Ridurre densità keyword (target: 1-3%)"

            rows.append(make_audit_row("C-05", "Content", "Keyword Density", stato, sev, risultato, homepage.get('url', ''), note))

            # C-06: Readability Score
            readability = content_quality.get('readability_score', 0)
            if readability >= 70:
                stato, sev, risultato = "OK", 0, f"Readability: {readability}/100 (ottima)"
            elif readability >= 50:
                stato, sev, risultato = "INFO", 0, f"Readability: {readability}/100 (media)"
            else:
                stato, sev, risultato = "WARN", 2, f"Readability: {readability}/100 (bassa)"

            rows.append(make_audit_row(
                "C-06", "Content", "Readability Score", stato, sev, risultato, homepage.get('url', ''),
                "Migliorare leggibilità con frasi più corte" if readability < 50 else "",
            ))

        # C-07: Doorway Pages Detection
        doorway = data.get('doorway_pages', {})
        if doorway:
            is_doorway = doorway.get('is_doorway', False)
            signals = doorway.get('signals', [])

            if is_doorway:
                stato, sev = "FAIL", 1
                risultato = f"Potenziale doorway page rilevata ({len(signals)} segnali)"
                note = "Rimuovere o migliorare la pagina"
            else:
                stato, sev, risultato, note = "OK", 0, "Nessuna doorway page rilevata", ""

            rows.append(make_audit_row("C-07", "Content", "Doorway Pages Detection", stato, sev, risultato, homepage.get('url', ''), note))

        # C-08: Content Uniqueness
        uniqueness = data.get('content_uniqueness', {})
        if uniqueness:
            is_unique = uniqueness.get('unique', True)
            duplicates = uniqueness.get('duplicates', 0)
            total_pages = uniqueness.get('total_pages', 0)

            if is_unique:
                stato, sev = "OK", 0
                risultato = f"Contenuto unico ({total_pages} pagine analizzate)"
                note = ""
            else:
                stato, sev = "WARN", 2
                risultato = f"{duplicates} pagine con contenuto duplicato su {total_pages}"
                note = "Differenziare i contenuti delle pagine"

            rows.append(make_audit_row("C-08", "Content", "Content Uniqueness", stato, sev, risultato, homepage.get('url', ''), note))

        # C-09: Content Freshness
        freshness = data.get('content_freshness', {})
        if freshness:
            has_date = freshness.get('has_date', False)

            if has_date:
                stato, sev, risultato, note = "OK", 0, "Data di pubblicazione presente", ""
            elif site_type == 'blog_news':
                stato, sev = "WARN", 2
                risultato = "Data di pubblicazione non trovata"
                note = "Aggiungere meta tag per data di pubblicazione"
            else:
                stato, sev, risultato, note = "N/A", 0, "Non necessaria (sito corporate)", ""

            rows.append(make_audit_row("C-09", "Content", "Content Freshness", stato, sev, risultato, homepage.get('url', ''), note))

        return rows

    def _process_favicon_and_images(self, data: Dict, domain: str) -> List[Dict]:
        """Processa i check su favicon e image SEO."""
        rows = []
        homepage = data.get('homepage', {})

        if not homepage or 'error' in homepage:
            return rows

        # H-16: Favicon
        favicon = data.get('favicon', {})
        if favicon:
            has_favicon = favicon.get('has_favicon', False)
            favicon_urls = favicon.get('favicon_urls', [])
            types = favicon.get('types', [])
            has_apple_touch = favicon.get('has_apple_touch', False)

            if has_favicon:
                stato, sev = "OK", 0
                risultato = f"Favicon presente ({len(favicon_urls)} varianti: {', '.join(types) if types else 'N/A'})"
                note = "" if has_apple_touch else "Consigliato aggiungere apple-touch-icon per dispositivi iOS"
            else:
                stato, sev, risultato = "FAIL", 2, "Favicon non trovata"
                note = "Aggiungere favicon per migliorare UX e branding"

            rows.append(make_audit_row("H-16", "HTML", "Favicon", stato, sev, risultato, homepage.get('url', ''), note))

        # H-17: Image Index (SEO Optimization)
        images = homepage.get('images', [])
        if images:
            images_with_alt = sum(1 for img in images if img.get('alt', '').strip())
            images_with_dimensions = sum(1 for img in images if img.get('width') and img.get('height'))

            modern_formats = sum(1 for img in images if img.get('src', '').lower().endswith(('.webp', '.avif')))

            total = len(images)
            seo_friendly = sum([
                images_with_alt == total,
                images_with_dimensions == total,
                modern_formats > 0
            ])

            if seo_friendly == 3:
                stato, sev = "OK", 0
                risultato = f"Immagini ottimizzate per indicizzazione ({total} immagini, {modern_formats} in formato moderno)"
            elif seo_friendly >= 1:
                stato, sev = "WARN", 2
                risultato = f"{total} immagini: {images_with_alt} con alt, {images_with_dimensions} con dimensioni, {modern_formats} formato moderno"
            else:
                stato, sev = "WARN", 2
                risultato = f"{total} immagini non ottimizzate per indicizzazione"

            rows.append(make_audit_row(
                "H-17", "HTML", "Image SEO Optimization", stato, sev, risultato, homepage.get('url', ''),
                "Ottimizzare alt text, dimensioni e formato (WebP/AVIF)" if seo_friendly < 3 else "",
            ))

        return rows

    def _process_whois(self, data: Dict, domain: str) -> List[Dict]:
        """Processa i dati Whois del dominio."""
        rows = []

        if data.get('error'):
            rows.append(make_audit_row(
                "T-22", "Technical", "Domain Age", "WARN", 2,
                f"Errore Whois: {data.get('error', '')[:100]}", "",
                "Verificare manualmente su whois.com",
            ))
            return rows

        # T-22: Domain Age
        age_years = data.get('age_years', 0)
        age_days = data.get('age_days', 0)
        creation_date = data.get('creation_date')

        creation_str = creation_date.strftime('%Y-%m-%d') if creation_date else 'N/A'
        if age_years > 0:
            stato, sev = "OK", 0
            risultato = f"Dominio registrato da {age_years} anni ({age_days} giorni) - {creation_str}"
        elif age_days > 0:
            stato, sev = "INFO", 0
            risultato = f"Dominio registrato da {age_days} giorni - {creation_str}"
        else:
            stato, sev, risultato = "WARN", 2, "Data di registrazione non disponibile"

        rows.append(make_audit_row("T-22", "Technical", "Domain Age", stato, sev, risultato))

        # T-23: Domain Expiration
        days_to_expiry = data.get('days_to_expiry', 0)
        expiration_date = data.get('expiration_date')
        expiry_str = expiration_date.strftime('%Y-%m-%d') if expiration_date else 'N/A'

        if days_to_expiry > 365:
            stato, sev, risultato = "OK", 0, f"Scade tra {days_to_expiry} giorni ({expiry_str})"
        elif days_to_expiry > 90:
            stato, sev, risultato = "WARN", 2, f"Scade tra {days_to_expiry} giorni ({expiry_str})"
        elif days_to_expiry > 0:
            stato, sev, risultato = "FAIL", 1, f"SCADE TRA {days_to_expiry} GIORNI! ({expiry_str})"
        else:
            stato, sev, risultato = "FAIL", 1, "Data di scadenza non disponibile"

        rows.append(make_audit_row(
            "T-23", "Technical", "Domain Expiration", stato, sev, risultato, "",
            "Rinnovare il dominio" if 0 < days_to_expiry < 90 else "",
        ))

        # T-24: Registrar
        registrar = data.get('registrar', '')
        if registrar:
            rows.append(make_audit_row("T-24", "Technical", "Domain Registrar", "OK", 0, f"Registrar: {registrar}"))

        # T-25: Name Servers
        name_servers = data.get('name_servers', [])
        if name_servers:
            rows.append(make_audit_row(
                "T-25", "Technical", "Name Servers", "OK", 0,
                f"{len(name_servers)} nameserver configurati", note=", ".join(name_servers[:3]),
            ))

        # T-26: IP Address
        ip_address = data.get('ip_address', '')
        if ip_address:
            rows.append(make_audit_row("T-26", "Technical", "IP Address", "OK", 0, f"IP: {ip_address}"))

        # T-27: DNSSEC
        dnssec = data.get('dnssec', '')
        if dnssec:
            dnssec_active = str(dnssec).lower() in ['signed', 'true', 'yes', '1']
            rows.append(make_audit_row(
                "T-27", "Technical", "DNSSEC",
                "OK" if dnssec_active else "INFO", 0,
                f"DNSSEC: {dnssec}", note="" if dnssec_active else "Valutare attivazione DNSSEC per maggiore sicurezza",
            ))

        return rows

    def _process_semrush(self, data: Dict, domain: str) -> List[Dict]:
        """Processa i dati di Semrush."""
        rows = []

        rows.append(make_audit_row(
            "G-01", "General", "Keywords Rank", "WARN", 2,
            "Da verificare su Semrush dashboard",
            f"https://www.semrush.com/analytics/organic/?q={domain}",
            "Necessaria ricerca keyword",
        ))

        rows.append(make_audit_row(
            "I-01", "Inbound", "Link Popularity", "WARN", 2,
            "Da verificare su Semrush Backlink Analytics",
            f"https://www.semrush.com/analytics/backlinks/?q={domain}",
        ))

        return rows

    def _process_manual(self, data: Dict, domain: str) -> List[Dict]:
        """Processa i dati manuali/semi-automatici."""
        rows = []

        https_present = data.get("https_present", False)
        rows.append(make_audit_row(
            "T-01", "Technical", "HTTPS",
            "OK" if https_present else "FAIL", 0 if https_present else 1,
            "HTTPS presente" if https_present else "HTTPS assente",
        ))

        penalties = data.get("penalties", {})
        penalty_mapping = {
            "internal": "P-INT",
            "external": "P-EXT",
            "autogenerated": "P-AUT",
            "low_quality": "P-LOW"
        }

        for ptype, value in penalties.items():
            audit_id = penalty_mapping.get(ptype, f"P-{ptype[:3].upper()}")

            if value is False:
                stato, sev, risultato = "OK", 0, "Nessun problema rilevato"
            elif value is True:
                stato, sev, risultato = "FAIL", 1, "Penalità rilevata!"
            else:
                stato, sev, risultato = "WARN", 0, "Da verificare manualmente"

            rows.append(make_audit_row(
                audit_id, "Penalties", f"Google Penalty - {ptype}", stato, sev, risultato,
                "https://search.google.com/search-console/security-issues",
            ))

        return rows

    def _process_geo(self, data: Dict, domain: str) -> List[Dict]:
        """Processa i dati GEO/AEO."""
        rows = []
        
        # GEO-01: Schema Markup Validation
        schema_validation = data.get('schema_validation', {})
        if schema_validation:
            completeness = schema_validation.get('completeness_score', 0)
            total_schemas = schema_validation.get('total_schemas', 0)
            
            if completeness >= 70:
                stato, sev = "OK", 0
            elif completeness >= 40:
                stato, sev = "WARN", 2
            else:
                stato, sev = "FAIL", 1
            
            rows.append(make_audit_row(
                "GEO-01", "GEO", "Schema Markup Completeness", stato, sev,
                f"{completeness}% completo ({total_schemas} schemi trovati)",
                domain,
                "Implementare JSON-LD per Organization, Article, FAQPage" if completeness < 70 else ""
            ))
        
        # GEO-02: AI Readability Score
        ai_readability = data.get('ai_readability', {})
        if ai_readability:
            score = ai_readability.get('readability_score', 0)
            
            if score >= 70:
                stato, sev = "OK", 0
            elif score >= 40:
                stato, sev = "WARN", 2
            else:
                stato, sev = "FAIL", 1
            
            rows.append(make_audit_row(
                "GEO-02", "GEO", "AI Readability Score", stato, sev,
                f"{score}/100 (Direct answer: {'✓' if ai_readability.get('has_direct_answer') else '✗'}, "
                f"FAQ: {'✓' if ai_readability.get('has_faq_format') else '✗'}, "
                f"List: {'✓' if ai_readability.get('has_list_format') else '✗'})",
                domain,
                "Migliorare struttura per AI Overviews e featured snippets" if score < 70 else ""
            ))
        
        # GEO-03: Citation Potential
        citation = data.get('citation_potential', {})
        if citation:
            score = citation.get('citation_score', 0)
            
            if score >= 70:
                stato, sev = "OK", 0
            elif score >= 40:
                stato, sev = "WARN", 2
            else:
                stato, sev = "FAIL", 1
            
            factors = citation.get('factors', {})
            rows.append(make_audit_row(
                "GEO-03", "GEO", "Citation Potential", stato, sev,
                f"{score}/100 (Structured data: {factors.get('structured_data', 0)}/30, "
                f"Authority: {factors.get('authority', 0)}/25, "
                f"Clarity: {factors.get('clarity', 0)}/25, "
                f"Originality: {factors.get('originality', 0)}/20)",
                domain,
                "Migliorare autorevolezza e unicità del contenuto" if score < 70 else ""
            ))
        
        # GEO-04: Content Structure
        structure = data.get('content_structure', {})
        if structure:
            h1_count = structure.get('h1_count', 0)
            h2_count = structure.get('h2_count', 0)
            
            if h1_count == 1 and h2_count >= 3:
                stato, sev = "OK", 0
            elif h1_count >= 1 and h2_count >= 2:
                stato, sev = "WARN", 2
            else:
                stato, sev = "FAIL", 1
            
            rows.append(make_audit_row(
                "GEO-04", "GEO", "Content Structure for GEO", stato, sev,
                f"H1: {h1_count}, H2: {h2_count}, H3: {structure.get('h3_count', 0)}, "
                f"Paragrafi: {structure.get('paragraphs_count', 0)}",
                domain,
                "Ottimizzare struttura headings per motori AI" if stato != "OK" else ""
            ))
        
        return rows

    # ------------------------------------------------------------------
    # CHECKLIST — tabella dichiarativa invece di ~35 tuple con lambda
    # ------------------------------------------------------------------
    # Ogni regola: quando l'ID Audit vale audit_id E lo Stato è tra
    # trigger_stati, genera questa azione in checklist. Stessa logica
    # dell'originale, ma leggibile e modificabile senza toccare codice.
    CHECKLIST_RULES: List[Dict[str, Any]] = [
        {"audit_id": "U-01", "trigger_stati": ["FAIL"], "fase": "3. Ottimizzazione", "azione": "Ottimizzare Core Web Vitals (rimuovere JS/CSS inutilizzati)", "owner": "Sviluppo", "kpi": "LCP < 2.5s, Performance > 80"},
        {"audit_id": "U-02", "trigger_stati": ["FAIL"], "fase": "3. Ottimizzazione", "azione": "Migliorare Lighthouse Performance Score", "owner": "Sviluppo", "kpi": "Performance > 80/100"},
        {"audit_id": "T-01", "trigger_stati": ["WARN", "FAIL"], "fase": "1. Fondamenta", "azione": "Implementare certificato HTTPS", "owner": "Sviluppo", "kpi": "HTTPS attivo su tutto il sito"},
        {"audit_id": None, "categoria": "Penalties", "trigger_stati": ["FAIL"], "fase": "1. Fondamenta", "azione": "Risolvere penalizzazione Google", "owner": "SEO", "kpi": "0 penalità attive"},
        {"audit_id": "GSC-02", "trigger_stati": ["WARN"], "fase": "2. Architettura", "azione": "Analizzare performance organica e ottimizzare contenuti", "owner": "SEO", "kpi": "Aumentare click organici del 20%"},
        {"audit_id": "T-02", "trigger_stati": ["FAIL"], "fase": "1. Fondamenta", "azione": "Creare e caricare sitemap.xml", "owner": "Sviluppo / SEO", "kpi": "Sitemap valida e submittera su GSC"},
        {"audit_id": "T-03", "trigger_stati": ["WARN", "FAIL"], "fase": "1. Fondamenta", "azione": "Configurare robots.txt con riferimento sitemap", "owner": "Sviluppo", "kpi": "Robots.txt valido con riferimento sitemap"},
        {"audit_id": "H-01", "trigger_stati": ["WARN", "FAIL"], "fase": "2. Architettura", "azione": "Ottimizzare Meta Title (50-60 caratteri) con keyword target", "owner": "SEO", "kpi": "100% pagine con Meta Title ottimizzati"},
        {"audit_id": "H-02", "trigger_stati": ["WARN", "FAIL"], "fase": "2. Architettura", "azione": "Ottimizzare Meta Description (120-160 caratteri) con keyword target", "owner": "SEO", "kpi": "100% pagine con Meta Description ottimizzate"},
        {"audit_id": "H-03", "trigger_stati": ["FAIL"], "fase": "1. Fondamenta", "azione": "Implementare tag Canonical su tutte le pagine", "owner": "Sviluppo", "kpi": "0 errori di canonical su GSC"},
        {"audit_id": "H-04", "trigger_stati": ["FAIL"], "fase": "2. Architettura", "azione": "Ottimizzare Heading H1 con keyword target", "owner": "SEO", "kpi": "1 H1 per pagina, ottimizzato"},
        {"audit_id": "H-05", "trigger_stati": ["FAIL"], "fase": "2. Architettura", "azione": "Aggiungere alt text descrittivi alle immagini", "owner": "Sviluppo / SEO", "kpi": "100% immagini con alt text"},
        {"audit_id": "H-06", "trigger_stati": ["FAIL"], "fase": "2. Architettura", "azione": "Implementare dati strutturati (Schema.org)", "owner": "Sviluppo", "kpi": "Markup valido in GSC > Rich Results"},
        {"audit_id": "H-09", "trigger_stati": ["FAIL"], "fase": "2. Architettura", "azione": "Creare pagina 404 personalizzata", "owner": "Sviluppo", "kpi": "Pagina 404 custom con navigazione"},
        {"audit_id": "C-01", "trigger_stati": ["WARN"], "fase": "2. Architettura", "azione": "Aumentare contenuto delle pagine principali", "owner": "SEO", "kpi": "Minimo 300 parole per pagina"},
        {"audit_id": "T-05", "trigger_stati": ["FAIL"], "fase": "2. Architettura", "azione": "Implementare breadcrumbs per navigazione e SEO", "owner": "Sviluppo", "kpi": "Breadcrumbs visibili e marcati Schema.org"},
        {"audit_id": "T-06", "trigger_stati": ["FAIL"], "fase": "1. Fondamenta", "azione": "Configurare redirect 301 da HTTP a HTTPS", "owner": "Sviluppo", "kpi": "Redirect HTTP -> HTTPS funzionante"},
        {"audit_id": "H-11", "trigger_stati": ["WARN"], "fase": "3. Ottimizzazione", "azione": "Ottimizzare peso immagini (WebP, compressione)", "owner": "Sviluppo", "kpi": "Tutte immagini < 100kb"},
        {"audit_id": "T-07", "trigger_stati": ["WARN"], "fase": "2. Architettura", "azione": "Ottimizzare anchor text link interni con keyword descrittive", "owner": "SEO", "kpi": "0 anchor text generici"},
        {"audit_id": "T-08", "trigger_stati": ["WARN"], "fase": "2. Architettura", "azione": "Ridurre profondità URL e semplificare struttura", "owner": "Sviluppo / SEO", "kpi": "URL massimo 3 livelli di profondità"},
        {"audit_id": "C-02", "trigger_stati": ["FAIL"], "fase": "2. Architettura", "azione": "Rimuovere o canonicalizzare contenuti duplicati", "owner": "SEO / Sviluppo", "kpi": "0 contenuti duplicati"},
        {"audit_id": "T-09", "trigger_stati": ["WARN"], "fase": "3. Ottimizzazione", "azione": "Minificare e combinare file CSS/JS", "owner": "Sviluppo", "kpi": "Meno di 20 file CSS/JS"},
        {"audit_id": "T-10", "trigger_stati": ["WARN"], "fase": "2. Architettura", "azione": "Ridurre profondità struttura sito", "owner": "Sviluppo / SEO", "kpi": "Massimo 3 livelli di profondità"},
        {"audit_id": "T-11", "trigger_stati": ["WARN"], "fase": "3. Ottimizzazione", "azione": "Implementare CDN per migliorare performance", "owner": "Sviluppo", "kpi": "LCP mobile < 2.5s"},
        {"audit_id": "H-15", "trigger_stati": ["WARN"], "fase": "2. Architettura", "azione": "Specificare width e height per tutte le immagini", "owner": "Sviluppo", "kpi": "100% immagini con dimensioni"},
        {"audit_id": "C-03", "trigger_stati": ["WARN", "FAIL"], "fase": "2. Architettura", "azione": "Ottimizzare Focus Keyword nel Title", "owner": "SEO", "kpi": "Keyword principale presente in tutti i title"},
        {"audit_id": "C-04", "trigger_stati": ["WARN", "FAIL"], "fase": "2. Architettura", "azione": "Ottimizzare Focus Keyword nell'H1", "owner": "SEO", "kpi": "Keyword principale presente in tutti gli H1"},
        {"audit_id": "C-05", "trigger_stati": ["WARN", "FAIL"], "fase": "2. Architettura", "azione": "Ottimizzare densità keyword (target: 1-3%)", "owner": "SEO", "kpi": "Densità keyword tra 1% e 3%"},
        {"audit_id": "C-06", "trigger_stati": ["WARN"], "fase": "2. Architettura", "azione": "Migliorare leggibilità dei contenuti", "owner": "SEO / Copywriting", "kpi": "Readability score > 50/100"},
        {"audit_id": "C-07", "trigger_stati": ["FAIL"], "fase": "1. Fondamenta", "azione": "Rimuovere doorway pages", "owner": "SEO", "kpi": "0 doorway pages"},
        {"audit_id": "C-08", "trigger_stati": ["WARN", "FAIL"], "fase": "2. Architettura", "azione": "Differenziare contenuti duplicati", "owner": "SEO / Copywriting", "kpi": "100% contenuti unici"},
        {"audit_id": "C-09", "trigger_stati": ["WARN"], "fase": "2. Architettura", "azione": "Aggiungere data di pubblicazione ai contenuti", "owner": "Sviluppo / SEO", "kpi": "100% contenuti con data"},
        {"audit_id": "T-23", "trigger_stati": ["FAIL"], "fase": "1. Fondamenta", "azione": "Rinnovare dominio in scadenza", "owner": "Sviluppo", "kpi": "Dominio valido per almeno 1 anno"},
        {"audit_id": "H-16", "trigger_stati": ["FAIL"], "fase": "2. Architettura", "azione": "Aggiungere favicon al sito", "owner": "Sviluppo", "kpi": "Favicon presente in tutti i formati"},
        {"audit_id": "H-17", "trigger_stati": ["WARN"], "fase": "2. Architettura", "azione": "Ottimizzare immagini per indicizzazione", "owner": "Sviluppo / SEO", "kpi": "100% immagini con alt, dimensioni e formato moderno"},
    ]

    def _generate_checklist(self, audit_rows: List[Dict]) -> List[Dict]:
        """Genera la checklist operativa - ESCLUDE INFO e N/A."""
        checklist = []
        chk_id = 1

        # Indicizza le regole per ID Audit per un lookup O(1) invece di
        # scorrere tutte le regole per ogni riga (l'originale scorreva
        # linearmente ~35 regole per ognuna delle ~70 righe di audit).
        rules_by_audit_id: Dict[str, List[Dict]] = {}
        category_rules: List[Dict] = []
        for rule in self.CHECKLIST_RULES:
            if rule.get("audit_id"):
                rules_by_audit_id.setdefault(rule["audit_id"], []).append(rule)
            else:
                category_rules.append(rule)

        for audit_row in audit_rows:
            if audit_row["Stato"] in ["INFO", "N/A"]:
                continue

            applicable_rules = list(rules_by_audit_id.get(audit_row["ID Audit"], []))
            applicable_rules += [
                r for r in category_rules
                if r.get("categoria") == audit_row.get("Categoria")
            ]

            for rule in applicable_rules:
                if audit_row["Stato"] not in rule["trigger_stati"]:
                    continue

                severity = audit_row.get("Severità", 0)
                priority = {1: 1, 2: 2}.get(severity, 3)

                checklist.append({
                    "ID Check": f"CHK-{chk_id:02d}",
                    "Rif. Audit": audit_row["ID Audit"],
                    "Fase": rule["fase"],
                    "Azione Richiesta": rule["azione"],
                    "Owner": rule["owner"],
                    "Priorità": priority,
                    "Dipendenze": rule.get("dipendenze", "Nessuna"),
                    "KPI / Obiettivo": rule["kpi"],
                    "Sprint / Deadline": "Mese 1",
                    "Status": "To-Do"
                })
                chk_id += 1

        return checklist


    def _generate_summary(self, domain: str, audit_rows: List[Dict]) -> Dict:
        """Genera l'Executive Summary."""
        total = len(audit_rows)
        fails = sum(1 for r in audit_rows if r["Stato"] == "FAIL")
        warns = sum(1 for r in audit_rows if r["Stato"] == "WARN")
        oks = sum(1 for r in audit_rows if r["Stato"] == "OK")
        infos = sum(1 for r in audit_rows if r["Stato"] == "INFO")
        nas = sum(1 for r in audit_rows if r["Stato"] == "N/A")

        relevant_checks = oks + warns + fails

        if relevant_checks == 0:
            health_score = 0
        else:
            weighted_score = (oks * 1.0 + warns * 0.5 + fails * 0.0) / relevant_checks
            health_score = round(weighted_score * 100)

        # Top criticità - evita duplicati per elemento
        seen_crit = set()
        top_criticita = []
        for r in sorted(
            [r for r in audit_rows if r["Stato"] == "FAIL"],
            key=lambda x: x.get("Severità", 0),
            reverse=True
        ):
            element = r.get("Elemento Analizzato", "")
            if element not in seen_crit:
                seen_crit.add(element)
                top_criticita.append(r)
                if len(top_criticita) >= 3:
                    break

        # Top punti di forza - evita duplicati per elemento
        seen_pf = set()
        top_punti_forza = []
        for r in audit_rows:
            if r["Stato"] == "OK":
                element = r.get("Elemento Analizzato", "")
                if element not in seen_pf:
                    seen_pf.add(element)
                    top_punti_forza.append(r)
                    if len(top_punti_forza) >= 3:
                        break

        return {
            "domain": domain,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "version": "2.3 Indexed Pages Estimate",
            "health_score": health_score,
            "total_checks": total,
            "fails": fails,
            "warnings": warns,
            "oks": oks,
            "infos": infos,
            "na": nas,
            "top_criticita": top_criticita,
            "top_punti_forza": top_punti_forza
        }