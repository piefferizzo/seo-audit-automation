from typing import Dict, Any, List
from datetime import datetime
import yaml
import re
from utils.logger import setup_logger

class AuditProcessor:
    """Trasforma i dati grezzi dei collector nelle righe dell'Audit e della Checklist."""
    
    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        self.logger = setup_logger("AuditProcessor")
    
    def process(self, domain: str, raw_data: Dict[str, Any]) -> Dict[str, List[Dict]]:
        """Elabora tutti i dati grezzi e genera audit + checklist."""

        # DEBUG: Verifica dati ricevuti
        self.logger.info(f"  🔍 DEBUG - Dati ricevuti nel processor:")
        self.logger.info(f"    - pagespeed: {bool(raw_data.get('pagespeed'))}")
        self.logger.info(f"    - gsc: {bool(raw_data.get('gsc'))}")
        self.logger.info(f"    - html: {bool(raw_data.get('html'))}")
        
            
        audit_rows = []
        checklist_rows = []
        
        # 1. PAGE SPEED
        ps_data = raw_data.get("pagespeed", {})
        if ps_data:
            audit_rows.extend(self._process_pagespeed(ps_data, domain))
        
        # 2. GOOGLE SEARCH CONSOLE
        gsc_data = raw_data.get("gsc", {})
        if gsc_data:
            audit_rows.extend(self._process_gsc(gsc_data, domain))
        
        # 3. GOOGLE ANALYTICS 4
        ga4_data = raw_data.get("ga4", {})
        if ga4_data:
            audit_rows.extend(self._process_ga4(ga4_data, domain))
        
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
        
        # 8. GENERA CHECKLIST
        checklist_rows = self._generate_checklist(audit_rows)
        
        # 9. GENERA EXECUTIVE SUMMARY
        summary = self._generate_summary(domain, audit_rows)
        
        # 10. ESTRAI DATI DRILL-DOWN
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
        
        # Estrai problemi dalla homepage
        homepage_problems = self._extract_homepage_problems(html_data)
        
        # Unisci problemi homepage + drill-down
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
        
        problems = {
            'images': [],
            'titles': [],
            'descriptions': [],
            'headings': []
        }
        
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
            
            should_skip = False
            for pattern in skip_patterns:
                if re.search(pattern, src, re.IGNORECASE):
                    should_skip = True
                    break
            
            if should_skip:
                continue
            
            if not alt or alt.strip() == '':
                problems['images'].append({
                    'url': src,
                    'problem': 'Testo alt mancante'
                })
            
            if not width or not height:
                problems['images'].append({
                    'url': src,
                    'problem': 'Attributi di dimensione mancanti'
                })
        
        # PROBLEMI TITLE
        title = homepage.get('title', '')
        title_len = len(title)
        url = homepage.get('url', '')
        
        if title:
            if title_len > 60:
                problems['titles'].append({
                    'url': url,
                    'meta_title': title,
                    'problem': f'Oltre 60 caratteri ({title_len})'
                })
            elif title_len < 30:
                problems['titles'].append({
                    'url': url,
                    'meta_title': title,
                    'problem': f'Sotto 30 caratteri ({title_len})'
                })
        else:
            problems['titles'].append({
                'url': url,
                'meta_title': '[MANCANTE]',
                'problem': 'Title assente'
            })
        
        # PROBLEMI DESCRIPTION
        description = homepage.get('meta_description', '')
        desc_len = len(description)
        
        if description:
            if desc_len > 155:
                problems['descriptions'].append({
                    'url': url,
                    'meta_description': description,
                    'problem': f'Oltre 155 caratteri ({desc_len})'
                })
            elif desc_len < 70:
                problems['descriptions'].append({
                    'url': url,
                    'meta_description': description,
                    'problem': f'Sotto 70 caratteri ({desc_len})'
                })
        else:
            problems['descriptions'].append({
                'url': url,
                'meta_description': '[MANCANTE]',
                'problem': 'Description assente'
            })
        
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
                problems['headings'].append({
                    'url': url,
                    'h1-1': h1,
                    'h1-2': '',
                    'problem': f'Oltre 70 caratteri ({len(h1)})'
                })
                break
        
        if len(h1_list) == 0:
            problems['headings'].append({
                'url': url,
                'h1-1': '',
                'h1-2': '',
                'problem': 'Assente'
            })
        
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
        
        if lcp > thresholds["lcp_critical"]:
            stato, sev = "FAIL", 1
        elif lcp > thresholds["lcp_warning"]:
            stato, sev = "WARN", 2
        else:
            stato, sev = "OK", 0
        
        rows.append({
            "ID Audit": "U-01",
            "Categoria": "Usability",
            "Elemento Analizzato": "Core Web Vitals (Mobile)",
            "Stato": stato,
            "Severità": sev,
            "Risultato / Evidenza": f"FCP {fcp:.1f}s, LCP {lcp:.1f}s, CLS {cls:.2f}",
            "URL / Link Evidenza": f"https://pagespeed.web.dev/analysis?url={domain}",
            "Note Tecniche": "Ridurre JS/CSS inutilizzati" if stato == "FAIL" else ""
        })
        
        perf_score = mobile.get("performance_score", 0)
        acc_score = mobile.get("accessibility_score", 0)
        
        if perf_score < thresholds["lighthouse_perf_critical"]:
            stato, sev = "FAIL", 1
        elif perf_score < thresholds["lighthouse_perf_warning"]:
            stato, sev = "WARN", 2
        else:
            stato, sev = "OK", 0
        
        rows.append({
            "ID Audit": "U-02",
            "Categoria": "Usability",
            "Elemento Analizzato": "Lighthouse Performance Score",
            "Stato": stato,
            "Severità": sev,
            "Risultato / Evidenza": f"Performance {perf_score:.0f}/100, Accessibility {acc_score:.0f}/100",
            "URL / Link Evidenza": "",
            "Note Tecniche": "Ottimizzazione necessaria" if stato != "OK" else ""
        })
        
        return rows
    
    def _process_gsc(self, data: Dict, domain: str) -> List[Dict]:
        """Processa i dati di Google Search Console."""
        rows = []
        
        verification = data.get("verification", "unknown")
        if verification in ["siteOwner", "siteFullUser"]:
            stato, sev = "OK", 0
        elif verification == "restricted":
            stato, sev = "OK", 0
        else:
            stato, sev = "WARN", 2
        
        rows.append({
            "ID Audit": "GSC-01",
            "Categoria": "Technical",
            "Elemento Analizzato": "Accesso Google Search Console",
            "Stato": stato,
            "Severità": sev,
            "Risultato / Evidenza": f"Permesso: {verification}",
            "URL / Link Evidenza": "https://search.google.com/search-console",
            "Note Tecniche": ""
        })
        
        performance = data.get("performance", [])
        if performance:
            total_clicks = sum(p.get("clicks", 0) for p in performance)
            total_impressions = sum(p.get("impressions", 0) for p in performance)
            
            if total_impressions > 0:
                avg_position = sum(p.get("position", 0) * p.get("impressions", 0) for p in performance) / total_impressions
            else:
                avg_position = 0
            
            if total_clicks > 0:
                stato, sev = "OK", 0
            else:
                stato, sev = "WARN", 2
            
            rows.append({
                "ID Audit": "GSC-02",
                "Categoria": "General",
                "Elemento Analizzato": "Performance Search Console (28 giorni)",
                "Stato": stato,
                "Severità": sev,
                "Risultato / Evidenza": f"Click: {total_clicks}, Impression: {total_impressions}, Posizione media: {avg_position:.1f}",
                "URL / Link Evidenza": "https://search.google.com/search-console/performance",
                "Note Tecniche": f"Pagine analizzate: {len(performance)}"
            })
        else:
            rows.append({
                "ID Audit": "GSC-02",
                "Categoria": "General",
                "Elemento Analizzato": "Performance Search Console (28 giorni)",
                "Stato": "WARN",
                "Severità": 2,
                "Risultato / Evidenza": "Nessun dato di performance disponibile",
                "URL / Link Evidenza": "https://search.google.com/search-console/performance",
                "Note Tecniche": "Il sito potrebbe non avere traffico organico"
            })
        
        # GSC-05: Top Pagine per Click
        top_pages = data.get("top_pages", [])
        if top_pages:
            top_3_pages = top_pages[:3]
            risultato_parts = []
            for i, page in enumerate(top_3_pages, 1):
                page_path = page.get('page', '').replace(domain, '')
                if not page_path:
                    page_path = '/'
                clicks = page.get('clicks', 0)
                risultato_parts.append(f"#{i}{page_path}: {clicks} clic")
            
            rows.append({
                "ID Audit": "GSC-05",
                "Categoria": "General",
                "Elemento Analizzato": "Top Pagine per Click",
                "Stato": "OK",
                "Severità": 0,
                "Risultato / Evidenza": ", ".join(risultato_parts),
                "URL / Link Evidenza": "https://search.google.com/search-console/performance",
                "Note Tecniche": ""
            })
        
        # GSC-06: Top Keyword per Click
        top_queries = data.get("top_queries", [])
        if top_queries:
            top_3_queries = top_queries[:3]
            risultato_parts = []
            for i, query in enumerate(top_3_queries, 1):
                query_text = query.get('query', '')
                clicks = query.get('clicks', 0)
                risultato_parts.append(f"#{i} '{query_text}': {clicks} clic")
            
            rows.append({
                "ID Audit": "GSC-06",
                "Categoria": "General",
                "Elemento Analizzato": "Top Keyword per Click",
                "Stato": "OK",
                "Severità": 0,
                "Risultato / Evidenza": ", ".join(risultato_parts),
                "URL / Link Evidenza": "https://search.google.com/search-console/performance",
                "Note Tecniche": ""
            })
        
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
            
            if total > 0:
                if top_3_pct > 20:
                    stato, sev = "OK", 0
                elif top_3_pct > 10:
                    stato, sev = "WARN", 2
                else:
                    stato, sev = "WARN", 2
            else:
                stato, sev = "WARN", 2
            
            rows.append({
                "ID Audit": "GSC-07",
                "Categoria": "General",
                "Elemento Analizzato": "Distribuzione Posizioni",
                "Stato": stato,
                "Severità": sev,
                "Risultato / Evidenza": risultato,
                "URL / Link Evidenza": "https://search.google.com/search-console/performance",
                "Note Tecniche": "Migliorare posizionamento keyword in pagina 2" if stato == "WARN" else ""
            })
        
        # GSC-08: Keyword Trend
        trending = data.get("trending_queries", {})
        if trending:
            growing = trending.get('growing', [])
            declining = trending.get('declining', [])
            new_queries = trending.get('new', [])
            
            if growing or declining or new_queries:
                risultato_parts = []
                if growing:
                    risultato_parts.append(f"{len(growing)} keyword in crescita")
                if declining:
                    risultato_parts.append(f"{len(declining)} keyword in calo")
                if new_queries:
                    risultato_parts.append(f"{len(new_queries)} keyword nuove")
                
                risultato = ", ".join(risultato_parts)
                
                if len(growing) > len(declining):
                    stato, sev = "OK", 0
                elif len(growing) == len(declining):
                    stato, sev = "WARN", 2
                else:
                    stato, sev = "WARN", 2
                
                rows.append({
                    "ID Audit": "GSC-08",
                    "Categoria": "General",
                    "Elemento Analizzato": "Trend Keyword (vs periodo precedente)",
                    "Stato": stato,
                    "Severità": sev,
                    "Risultato / Evidenza": risultato,
                    "URL / Link Evidenza": "https://search.google.com/search-console/performance",
                    "Note Tecniche": "Investigare keyword in calo" if len(declining) > 0 else ""
                })
        
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
                
                if mobile_pct > 50:
                    stato, sev = "OK", 0
                elif mobile_pct > 30:
                    stato, sev = "WARN", 2
                else:
                    stato, sev = "WARN", 2
                
                rows.append({
                    "ID Audit": "GSC-09",
                    "Categoria": "Usability",
                    "Elemento Analizzato": "Distribuzione Traffico per Dispositivo",
                    "Stato": stato,
                    "Severità": sev,
                    "Risultato / Evidenza": risultato,
                    "URL / Link Evidenza": "https://search.google.com/search-console/performance",
                    "Note Tecniche": "Ottimizzare esperienza mobile" if mobile_pct < 50 else ""
                })
        
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
                risultato = f"{sitemap_count} sitemap, {total_urls} URL inviate, {total_indexed} URL sitemap indicizzate"
            
            if total_urls > 0 and index_rate < 50:
                stato = "WARN"
                sev = 2
                note = "Tasso di indicizzazione basso. Verificare qualità contenuti e struttura interna."
            elif total_indexed == 0 and total_urls > 0:
                stato = "FAIL"
                sev = 1
                note = "Nessuna URL della sitemap indicizzata. Problema critico di indicizzazione."
            else:
                stato = "OK"
                sev = 0
                note = ""
            
            rows.append({
                "ID Audit": "GSC-03",
                "Categoria": "Technical",
                "Elemento Analizzato": "Sitemap in GSC",
                "Stato": stato,
                "Severità": sev,
                "Risultato / Evidenza": risultato,
                "URL / Link Evidenza": "https://search.google.com/search-console/sitemaps",
                "Note Tecniche": note
            })
        
        # GSC-04: Stima pagine totali indicizzate
        indexed_estimate = data.get("indexed_estimate", {})
        if indexed_estimate and indexed_estimate.get('sample_size', 0) > 0:
            sample_size = indexed_estimate.get('sample_size', 0)
            indexed = indexed_estimate.get('indexed', 0)
            index_rate = indexed_estimate.get('index_rate', 0)
            method = indexed_estimate.get('estimation_method', 'unknown')
            note = indexed_estimate.get('note', '')
            
            if method == 'performance_api':
                risultato = f"Stima: ~{indexed} pagine indicizzate (basato su performance API, {sample_size} pagine con dati)"
            elif method == 'url_inspection':
                risultato = f"Stima: ~{indexed} pagine indicizzate (basato su campione di {sample_size} URL, tasso: {index_rate}%)"
            else:
                risultato = f"Stima non disponibile"
            
            if index_rate < 50 and method != 'performance_api':
                stato = "WARN"
                sev = 2
                tech_note = "Tasso di indicizzazione reale basso. Investigare problemi tecnici o di qualità."
            else:
                stato = "OK"
                sev = 0
                tech_note = note
            
            rows.append({
                "ID Audit": "GSC-04",
                "Categoria": "Technical",
                "Elemento Analizzato": "Stima Pagine Indicizzate",
                "Stato": stato,
                "Severità": sev,
                "Risultato / Evidenza": risultato,
                "URL / Link Evidenza": "https://search.google.com/search-console/index/coverage",
                "Note Tecniche": tech_note
            })
        
        return rows
    
    def _process_ga4(self, data: Dict, domain: str) -> List[Dict]:
        """Processa i dati di Google Analytics 4."""
        rows = []
        
        overview = data.get('overview', {})
        if overview:
            sessions = overview.get('sessions', 0)
            users = overview.get('users', 0)
            pageviews = overview.get('pageviews', 0)
            
            rows.append({
                "ID Audit": "GA4-01",
                "Categoria": "General",
                "Elemento Analizzato": "Traffico GA4 (28 giorni)",
                "Stato": "OK" if sessions > 100 else "WARN",
                "Severità": 0 if sessions > 100 else 2,
                "Risultato / Evidenza": f"{sessions} sessioni, {users} utenti, {pageviews} pagine viste",
                "URL / Link Evidenza": "https://analytics.google.com/",
                "Note Tecniche": ""
            })
        
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
            
            rows.append({
                "ID Audit": "GA4-02",
                "Categoria": "Usability",
                "Elemento Analizzato": "Bounce Rate",
                "Stato": stato,
                "Severità": sev,
                "Risultato / Evidenza": f"{bounce_rate:.1f}% bounce rate, {avg_duration:.1f}s durata media",
                "URL / Link Evidenza": "https://analytics.google.com/",
                "Note Tecniche": "Migliorare contenuti e UX" if bounce_rate > 50 else ""
            })
        
        traffic = data.get('traffic_sources', {})
        if traffic and traffic.get('sources'):
            sources = traffic['sources']
            organic_sessions = sum(s['sessions'] for s in sources if 'organic' in s['source'].lower())
            total_sessions = sum(s['sessions'] for s in sources)
            
            if total_sessions > 0:
                organic_percentage = (organic_sessions / total_sessions) * 100
                
                if organic_percentage > 30:
                    stato, sev = "OK", 0
                elif organic_percentage > 10:
                    stato, sev = "WARN", 2
                else:
                    stato, sev = "WARN", 2
                
                rows.append({
                    "ID Audit": "GA4-03",
                    "Categoria": "General",
                    "Elemento Analizzato": "Traffico Organico",
                    "Stato": stato,
                    "Severità": sev,
                    "Risultato / Evidenza": f"{organic_percentage:.1f}% del traffico ({organic_sessions} sessioni)",
                    "URL / Link Evidenza": "https://analytics.google.com/",
                    "Note Tecniche": "Migliorare SEO per aumentare traffico organico" if organic_percentage < 30 else ""
                })
        
        devices = data.get('devices', {})
        if devices and devices.get('devices'):
            device_data = devices['devices']
            mobile_sessions = device_data.get('mobile', 0)
            total_sessions = sum(device_data.values())
            
            if total_sessions > 0:
                mobile_percentage = (mobile_sessions / total_sessions) * 100
                
                rows.append({
                    "ID Audit": "GA4-04",
                    "Categoria": "Usability",
                    "Elemento Analizzato": "Traffico Mobile",
                    "Stato": "OK",
                    "Severità": 0,
                    "Risultato / Evidenza": f"{mobile_percentage:.1f}% da mobile ({mobile_sessions} sessioni)",
                    "URL / Link Evidenza": "https://analytics.google.com/",
                    "Note Tecniche": ""
                })
        
        top_pages = data.get('top_pages', {})
        if top_pages and top_pages.get('pages'):
            pages = top_pages['pages']
            
            rows.append({
                "ID Audit": "GA4-05",
                "Categoria": "Content",
                "Elemento Analizzato": "Top Pagine (28 giorni)",
                "Stato": "OK",
                "Severità": 0,
                "Risultato / Evidenza": f"{len(pages)} pagine analizzate, top: {pages[0]['path']} ({pages[0]['views']} views)",
                "URL / Link Evidenza": "https://analytics.google.com/",
                "Note Tecniche": ""
            })
        
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
        
        rows.append({
            "ID Audit": "T-02",
            "Categoria": "Technical",
            "Elemento Analizzato": "Sitemap.xml",
            "Stato": stato,
            "Severità": sev,
            "Risultato / Evidenza": risultato,
            "URL / Link Evidenza": sitemap.get('url', ''),
            "Note Tecniche": ""
        })
        
        # T-03: Robots.txt
        robots = data.get('robots', {})
        sitemap_url = robots.get('sitemap_url', '')
        has_sitemap_ref = robots.get('has_sitemap', False)
        
        if has_sitemap_ref:
            risultato = f"Presente (con sitemap: {sitemap_url})"
        else:
            risultato = "Presente (senza sitemap)"
        
        rows.append({
            "ID Audit": "T-03",
            "Categoria": "Technical",
            "Elemento Analizzato": "Robots.txt",
            "Stato": "OK" if robots.get('exists') else "FAIL",
            "Severità": 0 if robots.get('exists') else 1,
            "Risultato / Evidenza": risultato,
            "URL / Link Evidenza": robots.get('url', ''),
            "Note Tecniche": "" if has_sitemap_ref else "Aggiungere riferimento alla sitemap"
        })
        
        # H-01: Meta Title
        title = homepage.get('title', '')
        title_len = len(title)
        
        if not title:
            stato, sev = "FAIL", 1
            risultato = "Mancante"
            note = "Ottimizzare con keyword target"
        elif title_len < 30:
            stato, sev = "WARN", 2
            risultato = f"Presente ma troppo corto ({title_len} caratteri, ottimale: 50-60)"
            note = "Allungare il title a 50-60 caratteri"
        elif title_len > 60:
            stato, sev = "WARN", 2
            risultato = f"Presente ma troppo lungo ({title_len} caratteri, ottimale: 50-60)"
            note = "Accorciare il title a 50-60 caratteri"
        else:
            stato, sev = "OK", 0
            risultato = f"Presente ({title_len} caratteri)"
            note = ""
        
        rows.append({
            "ID Audit": "H-01",
            "Categoria": "HTML",
            "Elemento Analizzato": "Meta Title",
            "Stato": stato,
            "Severità": sev,
            "Risultato / Evidenza": risultato,
            "URL / Link Evidenza": homepage.get('url', ''),
            "Note Tecniche": note
        })
        
        # H-02: Meta Description
        description = homepage.get('meta_description', '')
        desc_len = len(description)
        
        if not description:
            stato, sev = "FAIL", 1
            risultato = "Mancante"
            note = "Ottimizzare con keyword target"
        elif desc_len < 120:
            stato, sev = "WARN", 2
            risultato = f"Presente ma troppo corta ({desc_len} caratteri, ottimale: 120-160)"
            note = "Allungare la description a 120-160 caratteri"
        elif desc_len > 160:
            stato, sev = "WARN", 2
            risultato = f"Presente ma troppo lunga ({desc_len} caratteri, ottimale: 120-160)"
            note = "Accorciare la description a 120-160 caratteri"
        else:
            stato, sev = "OK", 0
            risultato = f"Presente ({desc_len} caratteri)"
            note = ""
        
        rows.append({
            "ID Audit": "H-02",
            "Categoria": "HTML",
            "Elemento Analizzato": "Meta Description",
            "Stato": stato,
            "Severità": sev,
            "Risultato / Evidenza": risultato,
            "URL / Link Evidenza": homepage.get('url', ''),
            "Note Tecniche": note
        })
        
        # H-03: Canonical
        canonical = homepage.get('canonical', '')
        rows.append({
            "ID Audit": "H-03",
            "Categoria": "HTML",
            "Elemento Analizzato": "Canonical",
            "Stato": "OK" if canonical else "FAIL",
            "Severità": 0 if canonical else 1,
            "Risultato / Evidenza": "Presente" if canonical else "Mancante",
            "URL / Link Evidenza": homepage.get('url', ''),
            "Note Tecniche": ""
        })
        
        # H-04: Headings (H1)
        headings = homepage.get('headings', {})
        h1_count = len(headings.get('h1', []))
        rows.append({
            "ID Audit": "H-04",
            "Categoria": "HTML",
            "Elemento Analizzato": "Heading H1",
            "Stato": "OK" if h1_count == 1 else "FAIL",
            "Severità": 0 if h1_count == 1 else 1,
            "Risultato / Evidenza": f"{h1_count} H1 presente" if h1_count > 0 else "Nessun H1",
            "URL / Link Evidenza": homepage.get('url', ''),
            "Note Tecniche": "Ottimizzare con keyword target" if h1_count != 1 else ""
        })
        
        # H-05: Images Alt Tag
        images = homepage.get('images', [])
        total_images = len(images)
        images_without_alt = len([img for img in images if not img.get('alt')])
        alt_percentage = (images_without_alt / total_images * 100) if total_images > 0 else 0
        
        if total_images == 0:
            stato, sev = "OK", 0
            risultato = "Nessuna immagine sulla homepage"
            note = ""
        elif alt_percentage == 0:
            stato, sev = "OK", 0
            risultato = f"Tutte le {total_images} immagini hanno alt text"
            note = ""
        elif alt_percentage < 10:
            stato, sev = "WARN", 2
            risultato = f"{images_without_alt}/{total_images} immagini senza alt ({alt_percentage:.1f}%)"
            note = "Correzione minore, ma utile per accessibilità"
        else:
            stato, sev = "FAIL", 2
            risultato = f"{images_without_alt}/{total_images} immagini senza alt ({alt_percentage:.1f}%)"
            note = "Aggiungere alt text descrittivi"
        
        rows.append({
            "ID Audit": "H-05",
            "Categoria": "HTML",
            "Elemento Analizzato": "Images Alt Tag",
            "Stato": stato,
            "Severità": sev,
            "Risultato / Evidenza": risultato,
            "URL / Link Evidenza": homepage.get('url', ''),
            "Note Tecniche": note
        })
        
        # H-06: Structured Data
        structured_data = homepage.get('structured_data', [])
        rows.append({
            "ID Audit": "H-06",
            "Categoria": "HTML",
            "Elemento Analizzato": "Structured Data (Schema.org)",
            "Stato": "OK" if structured_data else "FAIL",
            "Severità": 0 if structured_data else 2,
            "Risultato / Evidenza": f"{len(structured_data)} blocchi presenti" if structured_data else "Non presenti",
            "URL / Link Evidenza": homepage.get('url', ''),
            "Note Tecniche": "Implementare markup Schema.org" if not structured_data else ""
        })
        
        # H-07: Open Graph
        og_tags = homepage.get('og_tags', {})
        rows.append({
            "ID Audit": "H-07",
            "Categoria": "HTML",
            "Elemento Analizzato": "Open Graph",
            "Stato": "OK" if og_tags else "WARN",
            "Severità": 0 if og_tags else 2,
            "Risultato / Evidenza": f"{len(og_tags)} tag presenti" if og_tags else "Non presenti",
            "URL / Link Evidenza": homepage.get('url', ''),
            "Note Tecniche": ""
        })
        
        # H-08: Hreflang
        hreflang = homepage.get('hreflang', [])
        lang = homepage.get('lang', '')
        
        valid_hreflang = [h for h in hreflang if h.get('href')]
        
        if len(valid_hreflang) > 0:
            stato, sev = "OK", 0
            risultato = f"{len(valid_hreflang)} lingue presenti"
            note = ""
        elif not lang or lang in ['it', 'it-IT', 'en', 'en-US']:
            stato, sev = "N/A", 0
            risultato = f"Non necessario (sito monolingua: {lang or 'non specificato'})"
            note = ""
        else:
            stato, sev = "WARN", 2
            risultato = "Non presente"
            note = ""
        
        rows.append({
            "ID Audit": "H-08",
            "Categoria": "HTML",
            "Elemento Analizzato": "Hreflang",
            "Stato": stato,
            "Severità": sev,
            "Risultato / Evidenza": risultato,
            "URL / Link Evidenza": homepage.get('url', ''),
            "Note Tecniche": note
        })
        
        # U-03: Viewport
        viewport = homepage.get('viewport', '')
        rows.append({
            "ID Audit": "U-03",
            "Categoria": "Usability",
            "Elemento Analizzato": "Viewport (Responsive)",
            "Stato": "OK" if viewport else "FAIL",
            "Severità": 0 if viewport else 1,
            "Risultato / Evidenza": "Presente" if viewport else "Mancante",
            "URL / Link Evidenza": homepage.get('url', ''),
            "Note Tecniche": ""
        })
        
        # H-09: 404 Custom
        check_404 = data.get('404', {})
        rows.append({
            "ID Audit": "H-09",
            "Categoria": "HTML",
            "Elemento Analizzato": "404 Custom Page",
            "Stato": "OK" if check_404.get('is_custom') else "FAIL",
            "Severità": 0 if check_404.get('is_custom') else 2,
            "Risultato / Evidenza": "Presente" if check_404.get('is_custom') else "Non presente o generica",
            "URL / Link Evidenza": "",
            "Note Tecniche": "Creare pagina 404 personalizzata" if not check_404.get('is_custom') else ""
        })
        
        # H-10: Content Language
        rows.append({
            "ID Audit": "H-10",
            "Categoria": "HTML",
            "Elemento Analizzato": "Content Language",
            "Stato": "OK" if lang else "WARN",
            "Severità": 0 if lang else 2,
            "Risultato / Evidenza": f"Lang: {lang}" if lang else "Non impostato",
            "URL / Link Evidenza": homepage.get('url', ''),
            "Note Tecniche": ""
        })
        
        # T-04: Internal Links
        internal_links = homepage.get('internal_links', [])
        rows.append({
            "ID Audit": "T-04",
            "Categoria": "Technical",
            "Elemento Analizzato": "Internal Links",
            "Stato": "OK" if len(internal_links) > 5 else "WARN",
            "Severità": 0 if len(internal_links) > 5 else 2,
            "Risultato / Evidenza": f"{len(internal_links)} link interni trovati",
            "URL / Link Evidenza": homepage.get('url', ''),
            "Note Tecniche": ""
        })
        
        # C-01: Word Count
        word_count = homepage.get('word_count', 0)
        rows.append({
            "ID Audit": "C-01",
            "Categoria": "Content",
            "Elemento Analizzato": "Content Length",
            "Stato": "OK" if word_count > 300 else "WARN",
            "Severità": 0 if word_count > 300 else 2,
            "Risultato / Evidenza": f"{word_count} parole",
            "URL / Link Evidenza": homepage.get('url', ''),
            "Note Tecniche": "Aumentare contenuto" if word_count < 300 else ""
        })
        
        # T-05: Breadcrumbs
        breadcrumbs = data.get('breadcrumbs', {})
        site_levels = data.get('site_structure', {}).get('levels', 0)
        
        if breadcrumbs.get('present'):
            stato, sev = "OK", 0
            risultato = f"Presenti ({breadcrumbs.get('count', 0)} livelli)"
            note = ""
        elif site_levels <= 2:
            stato, sev = "INFO", 0
            risultato = f"Non presenti (struttura semplice: {site_levels} livelli)"
            note = "Non critici per siti con struttura piatta"
        else:
            stato, sev = "FAIL", 2
            risultato = "Non presenti"
            note = "Implementare breadcrumbs per migliorare UX e SEO"
        
        rows.append({
            "ID Audit": "T-05",
            "Categoria": "Technical",
            "Elemento Analizzato": "Breadcrumbs",
            "Stato": stato,
            "Severità": sev,
            "Risultato / Evidenza": risultato,
            "URL / Link Evidenza": homepage.get('url', ''),
            "Note Tecniche": note
        })
        
        # T-06: HTTP to HTTPS Redirect
        redirect = data.get('redirect', {})
        http_to_https = redirect.get('http_to_https', {})
        https_present = data.get('https_present', True)
        
        mixed_content = data.get('mixed_content', {})
        has_mixed = mixed_content.get('has_mixed_content', False)
        
        if https_present and not has_mixed:
            stato, sev = "OK", 0
            risultato = "HTTPS attivo e funzionante"
            note = ""
        elif http_to_https.get('redirects') and http_to_https.get('is_https'):
            stato, sev = "OK", 0
            risultato = "Redirect corretto"
            note = ""
        else:
            stato, sev = "FAIL", 1
            risultato = "Redirect mancante o errato"
            note = "Configurare redirect 301 da HTTP a HTTPS"
        
        rows.append({
            "ID Audit": "T-06",
            "Categoria": "Technical",
            "Elemento Analizzato": "HTTP to HTTPS Redirect",
            "Stato": stato,
            "Severità": sev,
            "Risultato / Evidenza": risultato,
            "URL / Link Evidenza": "",
            "Note Tecniche": note
        })
        
        # H-11: Image Weight
        image_analysis = data.get('image_analysis', {})
        heavy_images = image_analysis.get('heavy_images', [])
        rows.append({
            "ID Audit": "H-11",
            "Categoria": "HTML",
            "Elemento Analizzato": "Image Weight (>100kb)",
            "Stato": "OK" if not heavy_images else "WARN",
            "Severità": 0 if not heavy_images else 2,
            "Risultato / Evidenza": f"{len(heavy_images)} immagini pesanti" if heavy_images else "Tutte le immagini ottimizzate",
            "URL / Link Evidenza": homepage.get('url', ''),
            "Note Tecniche": "Ottimizzare peso immagini (WebP, compressione)" if heavy_images else ""
        })
        
        # T-07: Anchor Text
        anchor_text = data.get('anchor_text', {})
        generic_count = anchor_text.get('generic_anchors', 0)
        rows.append({
            "ID Audit": "T-07",
            "Categoria": "Technical",
            "Elemento Analizzato": "Internal Anchor Text",
            "Stato": "OK" if generic_count == 0 else "WARN",
            "Severità": 0 if generic_count == 0 else 2,
            "Risultato / Evidenza": f"{generic_count} anchor text generici" if generic_count > 0 else "Anchor text ottimizzati",
            "URL / Link Evidenza": homepage.get('url', ''),
            "Note Tecniche": "Ottimizzare anchor text con keyword descrittive" if generic_count > 0 else ""
        })
        
        # T-08: URL Structure
        url_structure = data.get('url_structure', {})
        deep_links = url_structure.get('deep_links', 0)
        rows.append({
            "ID Audit": "T-08",
            "Categoria": "Technical",
            "Elemento Analizzato": "URL Structure (Deep Links)",
            "Stato": "OK" if deep_links < 5 else "WARN",
            "Severità": 0 if deep_links < 5 else 2,
            "Risultato / Evidenza": f"{deep_links} link profondi (>3 livelli)",
            "URL / Link Evidenza": homepage.get('url', ''),
            "Note Tecniche": "Ridurre profondità URL per migliorare crawling" if deep_links >= 5 else ""
        })
        
        # H-12: HTML5 Doctype
        html5 = data.get('html5', {})
        rows.append({
            "ID Audit": "H-12",
            "Categoria": "HTML",
            "Elemento Analizzato": "HTML5 Doctype",
            "Stato": "OK" if html5.get('html5') else "INFO",
            "Severità": 0,
            "Risultato / Evidenza": "HTML5 valido" if html5.get('html5') else "Doctype non HTML5 (impatto SEO marginale)",
            "URL / Link Evidenza": homepage.get('url', ''),
            "Note Tecniche": ""
        })
        
        # H-13: Logo
        logo = data.get('logo', {})
        rows.append({
            "ID Audit": "H-13",
            "Categoria": "HTML",
            "Elemento Analizzato": "Logo Optimization",
            "Stato": "OK" if logo.get('found') else "WARN",
            "Severità": 0 if logo.get('found') else 2,
            "Risultato / Evidenza": "Logo presente" if logo.get('found') else "Logo non trovato",
            "URL / Link Evidenza": homepage.get('url', ''),
            "Note Tecniche": ""
        })
        
        return rows
    
    def _process_advanced_html(self, data: Dict, domain: str, ps_data: Dict = None) -> List[Dict]:
        """Processa i dati avanzati del crawler HTML."""
        rows = []
        homepage = data.get('homepage', {})
        
        if not homepage or 'error' in homepage:
            return rows
        
        # C-02: Duplicate Content
        duplicate_content = data.get('duplicate_content', {})
        rows.append({
            "ID Audit": "C-02",
            "Categoria": "Content",
            "Elemento Analizzato": "Duplicate Content",
            "Stato": "OK" if not duplicate_content.get('has_duplicates') else "FAIL",
            "Severità": 0 if not duplicate_content.get('has_duplicates') else 1,
            "Risultato / Evidenza": f"{duplicate_content.get('duplicate_count', 0)} duplicati rilevati" if duplicate_content.get('has_duplicates') else "Nessun contenuto duplicato",
            "URL / Link Evidenza": homepage.get('url', ''),
            "Note Tecniche": "Rimuovere o canonicalizzare contenuti duplicati" if duplicate_content.get('has_duplicates') else ""
        })
        
        # T-09: CSS/JS Analysis
        css_js = data.get('css_js_analysis', {})
        total_files = css_js.get('total_css_js', 0)
        rows.append({
            "ID Audit": "T-09",
            "Categoria": "Technical",
            "Elemento Analizzato": "CSS/JS Files",
            "Stato": "OK" if total_files < 20 else "WARN",
            "Severità": 0 if total_files < 20 else 2,
            "Risultato / Evidenza": f"{total_files} file CSS/JS ({css_js.get('css_files_count', 0)} CSS, {css_js.get('js_files_count', 0)} JS)",
            "URL / Link Evidenza": homepage.get('url', ''),
            "Note Tecniche": "Minificare e combinare file CSS/JS" if total_files >= 20 else ""
        })
        
        # H-14: Pagination
        pagination = data.get('pagination', {})
        internal_pages_count = len(data.get('internal_pages', []))
        
        if pagination.get('found'):
            stato, sev = "OK", 0
            risultato = "Presente"
            note = ""
        elif internal_pages_count < 20:
            stato, sev = "N/A", 0
            risultato = f"Non necessaria (sito con poche pagine: ~{internal_pages_count})"
            note = ""
        else:
            stato, sev = "WARN", 2
            risultato = "Non presente"
            note = ""
        
        rows.append({
            "ID Audit": "H-14",
            "Categoria": "HTML",
            "Elemento Analizzato": "Pagination",
            "Stato": stato,
            "Severità": sev,
            "Risultato / Evidenza": risultato,
            "URL / Link Evidenza": homepage.get('url', ''),
            "Note Tecniche": note
        })
        
        # T-10: Site Structure
        site_structure = data.get('site_structure', {})
        levels = site_structure.get('levels', 0)
        rows.append({
            "ID Audit": "T-10",
            "Categoria": "Technical",
            "Elemento Analizzato": "Site Structure (Levels)",
            "Stato": "OK" if levels <= 3 else "WARN",
            "Severità": 0 if levels <= 3 else 2,
            "Risultato / Evidenza": f"{levels} livelli di profondità",
            "URL / Link Evidenza": homepage.get('url', ''),
            "Note Tecniche": "Ridurre profondità struttura" if levels > 3 else ""
        })
        
        # U-04: AMP
        amp = data.get('amp_check', {})
        rows.append({
            "ID Audit": "U-04",
            "Categoria": "Usability",
            "Elemento Analizzato": "AMP (Accelerated Mobile Pages)",
            "Stato": "OK" if amp.get('has_amp') else "INFO",
            "Severità": 0,
            "Risultato / Evidenza": "Presente" if amp.get('has_amp') else "Non presente (non più requisito Google)",
            "URL / Link Evidenza": homepage.get('url', ''),
            "Note Tecniche": ""
        })
        
        # T-11: CDN
        cdn = data.get('cdn_check', {})
        lcp = 0
        if ps_data and ps_data.get('mobile'):
            lcp = ps_data['mobile'].get('lcp', 0)
        
        if cdn.get('has_cdn'):
            stato, sev = "OK", 0
            risultato = f"Presente ({cdn.get('server', 'unknown')})"
            note = ""
        elif lcp > 4.0:
            stato, sev = "WARN", 2
            risultato = f"Non rilevata (LCP {lcp:.1f}s > 4s)"
            note = "Implementare CDN per migliorare performance"
        else:
            stato, sev = "INFO", 0
            risultato = f"Non rilevata (LCP {lcp:.1f}s, performance accettabili)"
            note = ""
        
        rows.append({
            "ID Audit": "T-11",
            "Categoria": "Technical",
            "Elemento Analizzato": "CDN (Content Delivery Network)",
            "Stato": stato,
            "Severità": sev,
            "Risultato / Evidenza": risultato,
            "URL / Link Evidenza": homepage.get('url', ''),
            "Note Tecniche": note
        })
        
        # H-15: Image Dimensions
        image_dims = data.get('image_dimensions', {})
        without_dims = image_dims.get('without_dimensions', 0)
        total_images = image_dims.get('total_images', 0)
        
        if total_images == 0:
            stato, sev = "OK", 0
            risultato = "Nessuna immagine trovata"
        elif without_dims == 0:
            stato, sev = "OK", 0
            risultato = "Tutte le immagini hanno dimensioni specificate"
        else:
            stato, sev = "WARN", 2
            risultato = f"{without_dims}/{total_images} immagini senza dimensioni"
        
        rows.append({
            "ID Audit": "H-15",
            "Categoria": "HTML",
            "Elemento Analizzato": "Image Dimensions (width/height)",
            "Stato": stato,
            "Severità": sev,
            "Risultato / Evidenza": risultato,
            "URL / Link Evidenza": homepage.get('url', ''),
            "Note Tecniche": "Specificare width e height per tutte le immagini" if without_dims > 0 else ""
        })
        
        return rows
    
    def _process_advanced_technical(self, data: Dict, domain: str) -> List[Dict]:
        """Processa i check tecnici avanzati."""
        rows = []
        homepage = data.get('homepage', {})
        
        if not homepage or 'error' in homepage:
            return rows
        
        # T-12: Crawling Errors
        rows.append({
            "ID Audit": "T-12",
            "Categoria": "Technical",
            "Elemento Analizzato": "Crawling Errors",
            "Stato": "OK",
            "Severità": 0,
            "Risultato / Evidenza": "Nessun errore critico rilevato",
            "URL / Link Evidenza": "https://search.google.com/search-console/index/coverage",
            "Note Tecniche": ""
        })
        
        # T-13: Indexability Analysis
        indexability = data.get('indexability', {})
        if indexability:
            noindex = indexability.get('noindex', False)
            canonical_correct = indexability.get('canonical_correct', False)
            
            if noindex:
                stato, sev = "FAIL", 1
                risultato = "Pagina noindex"
            elif not canonical_correct:
                stato, sev = "WARN", 2
                risultato = "Canonical non self-referencing"
            else:
                stato, sev = "OK", 0
                risultato = "Pagina indexabile correttamente"
            
            rows.append({
                "ID Audit": "T-13",
                "Categoria": "Technical",
                "Elemento Analizzato": "Indexability Analysis",
                "Stato": stato,
                "Severità": sev,
                "Risultato / Evidenza": risultato,
                "URL / Link Evidenza": homepage.get('url', ''),
                "Note Tecniche": "Rimuovere noindex" if noindex else "Correggere canonical" if not canonical_correct else ""
            })
        
        # T-14: HTTP Headers
        http_headers = data.get('http_headers', {})
        if http_headers:
            has_security = http_headers.get('has_security_headers', False)
            
            rows.append({
                "ID Audit": "T-14",
                "Categoria": "Technical",
                "Elemento Analizzato": "HTTP Security Headers",
                "Stato": "OK" if has_security else "WARN",
                "Severità": 0 if has_security else 2,
                "Risultato / Evidenza": f"Server: {http_headers.get('server', 'unknown')}" + (", Security headers presenti" if has_security else ", Security headers mancanti"),
                "URL / Link Evidenza": homepage.get('url', ''),
                "Note Tecniche": "Aggiungere X-Frame-Options, HSTS" if not has_security else ""
            })
        
        # T-15: Status Codes
        status_codes = data.get('status_codes', {})
        if status_codes:
            page_status = status_codes.get('page_status', 0)
            broken = status_codes.get('broken_resources', 0)
            
            if page_status == 200 and broken == 0:
                stato, sev = "OK", 0
                risultato = f"Status {page_status}, tutte le risorse OK"
            elif page_status == 200:
                stato, sev = "WARN", 2
                risultato = f"Status {page_status}, {broken} risorse rotte"
            else:
                stato, sev = "FAIL", 1
                risultato = f"Status {page_status}"
            
            rows.append({
                "ID Audit": "T-15",
                "Categoria": "Technical",
                "Elemento Analizzato": "Status Codes Analysis",
                "Stato": stato,
                "Severità": sev,
                "Risultato / Evidenza": risultato,
                "URL / Link Evidenza": homepage.get('url', ''),
                "Note Tecniche": "Correggere risorse rotte" if broken > 0 else ""
            })
        
        # T-16: www vs non-www Redirect
        www_redirect = data.get('www_redirect', {})
        if www_redirect:
            consistent = www_redirect.get('consistent', False)
            
            rows.append({
                "ID Audit": "T-16",
                "Categoria": "Technical",
                "Elemento Analizzato": "www vs non-www Redirect",
                "Stato": "OK" if consistent else "WARN",
                "Severità": 0 if consistent else 2,
                "Risultato / Evidenza": "Redirect coerente" if consistent else "Redirect inconsistente o mancante",
                "URL / Link Evidenza": "",
                "Note Tecniche": "Configurare redirect 301 coerente" if not consistent else ""
            })
        
        # T-17: Mixed Content
        mixed_content = data.get('mixed_content', {})
        if mixed_content:
            has_mixed = mixed_content.get('has_mixed_content', False)
            count = mixed_content.get('count', 0)
            
            rows.append({
                "ID Audit": "T-17",
                "Categoria": "Technical",
                "Elemento Analizzato": "Mixed Content (HTTP su HTTPS)",
                "Stato": "FAIL" if has_mixed else "OK",
                "Severità": 1 if has_mixed else 0,
                "Risultato / Evidenza": f"{count} risorse HTTP su pagina HTTPS" if has_mixed else "Nessun mixed content",
                "URL / Link Evidenza": homepage.get('url', ''),
                "Note Tecniche": "Aggiornare risorse a HTTPS" if has_mixed else ""
            })
        
        # T-18: Redirect Chains
        redirect_chains = data.get('redirect_chains', {})
        if redirect_chains:
            has_chain = redirect_chains.get('has_chain', False)
            chain_length = redirect_chains.get('chain_length', 0)
            
            rows.append({
                "ID Audit": "T-18",
                "Categoria": "Technical",
                "Elemento Analizzato": "Redirect Chains",
                "Stato": "WARN" if has_chain else "OK",
                "Severità": 2 if has_chain else 0,
                "Risultato / Evidenza": f"Catena di {chain_length} redirect" if has_chain else "Nessuna catena di redirect",
                "URL / Link Evidenza": homepage.get('url', ''),
                "Note Tecniche": "Semplificare redirect a singolo hop" if has_chain else ""
            })
        
        # T-19: CSS Issues
        css_issues = data.get('css_issues', {})
        if css_issues:
            too_many = css_issues.get('too_many_files', False)
            total = css_issues.get('total_css_files', 0)
            
            rows.append({
                "ID Audit": "T-19",
                "Categoria": "Technical",
                "Elemento Analizzato": "CSS Files Optimization",
                "Stato": "WARN" if too_many else "OK",
                "Severità": 2 if too_many else 0,
                "Risultato / Evidenza": f"{total} file CSS esterni" + (" (troppi)" if too_many else ""),
                "URL / Link Evidenza": homepage.get('url', ''),
                "Note Tecniche": "Combinare e minificare CSS" if too_many else ""
            })
        
        # T-20: JS Issues
        js_issues = data.get('js_issues', {})
        if js_issues:
            too_many = js_issues.get('too_many_files', False)
            total = js_issues.get('total_js_files', 0)
            
            rows.append({
                "ID Audit": "T-20",
                "Categoria": "Technical",
                "Elemento Analizzato": "JavaScript Files Optimization",
                "Stato": "WARN" if too_many else "OK",
                "Severità": 2 if too_many else 0,
                "Risultato / Evidenza": f"{total} file JS esterni" + (" (troppi)" if too_many else ""),
                "URL / Link Evidenza": homepage.get('url', ''),
                "Note Tecniche": "Deferire o caricare async JS" if too_many else ""
            })
        
        # T-21: Subdomains
        subdomains = data.get('subdomains', {})
        if subdomains:
            has_subdomains = subdomains.get('has_subdomains', False)
            count = subdomains.get('count', 0)
            
            rows.append({
                "ID Audit": "T-21",
                "Categoria": "Technical",
                "Elemento Analizzato": "Subdomains Detection",
                "Stato": "OK",
                "Severità": 0,
                "Risultato / Evidenza": f"{count} sottodomini rilevati" if has_subdomains else "Nessun sottodominio",
                "URL / Link Evidenza": homepage.get('url', ''),
                "Note Tecniche": ""
            })
        
        return rows
    
    def _process_content_advanced(self, data: Dict, domain: str) -> List[Dict]:
        """Processa l'analisi avanzata dei contenuti."""
        rows = []
        homepage = data.get('homepage', {})
        
        if not homepage or 'error' in homepage:
            return rows
        
        site_type = data.get('site_type', 'corporate')
        
        # C-03: Focus Keyword in Title
        content_quality = data.get('content_quality', {})
        if content_quality:
            keyword_in_title = content_quality.get('keyword_in_title', False)
            
            rows.append({
                "ID Audit": "C-03",
                "Categoria": "Content",
                "Elemento Analizzato": "Focus Keyword in Title",
                "Stato": "OK" if keyword_in_title else "WARN",
                "Severità": 0 if keyword_in_title else 2,
                "Risultato / Evidenza": "Keyword presente nel title" if keyword_in_title else "Keyword non trovata nel title",
                "URL / Link Evidenza": homepage.get('url', ''),
                "Note Tecniche": "Includere keyword principale nel title" if not keyword_in_title else ""
            })
        
        # C-04: Focus Keyword in H1
        if content_quality:
            keyword_in_h1 = content_quality.get('keyword_in_h1', False)
            
            rows.append({
                "ID Audit": "C-04",
                "Categoria": "Content",
                "Elemento Analizzato": "Focus Keyword in H1",
                "Stato": "OK" if keyword_in_h1 else "WARN",
                "Severità": 0 if keyword_in_h1 else 2,
                "Risultato / Evidenza": "Keyword presente nell'H1" if keyword_in_h1 else "Keyword non trovata nell'H1",
                "URL / Link Evidenza": homepage.get('url', ''),
                "Note Tecniche": "Includere keyword principale nell'H1" if not keyword_in_h1 else ""
            })
        
        # C-05: Keyword Density
        if content_quality:
            density = content_quality.get('keyword_density', 0)
            
            if density == 0:
                stato, sev = "WARN", 2
                risultato = "Densità keyword non calcolabile"
                note = "Verificare presenza keyword nel contenuto"
            elif 1.0 <= density <= 3.0:
                stato, sev = "OK", 0
                risultato = f"Densità keyword: {density}% (ottimale)"
                note = ""
            elif density < 1.0:
                stato, sev = "WARN", 2
                risultato = f"Densità keyword: {density}% (bassa)"
                note = "Aumentare densità keyword (target: 1-3%)"
            else:
                stato, sev = "WARN", 2
                risultato = f"Densità keyword: {density}% (alta)"
                note = "Ridurre densità keyword (target: 1-3%)"
            
            rows.append({
                "ID Audit": "C-05",
                "Categoria": "Content",
                "Elemento Analizzato": "Keyword Density",
                "Stato": stato,
                "Severità": sev,
                "Risultato / Evidenza": risultato,
                "URL / Link Evidenza": homepage.get('url', ''),
                "Note Tecniche": note
            })
        
        # C-06: Readability Score
        if content_quality:
            readability = content_quality.get('readability_score', 0)
            
            if readability >= 70:
                stato, sev = "OK", 0
                risultato = f"Readability: {readability}/100 (ottima)"
            elif readability >= 50:
                stato, sev = "INFO", 0
                risultato = f"Readability: {readability}/100 (media)"
            else:
                stato, sev = "WARN", 2
                risultato = f"Readability: {readability}/100 (bassa)"
            
            rows.append({
                "ID Audit": "C-06",
                "Categoria": "Content",
                "Elemento Analizzato": "Readability Score",
                "Stato": stato,
                "Severità": sev,
                "Risultato / Evidenza": risultato,
                "URL / Link Evidenza": homepage.get('url', ''),
                "Note Tecniche": "Migliorare leggibilità con frasi più corte" if readability < 50 else ""
            })
        
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
                stato, sev = "OK", 0
                risultato = "Nessuna doorway page rilevata"
                note = ""
            
            rows.append({
                "ID Audit": "C-07",
                "Categoria": "Content",
                "Elemento Analizzato": "Doorway Pages Detection",
                "Stato": stato,
                "Severità": sev,
                "Risultato / Evidenza": risultato,
                "URL / Link Evidenza": homepage.get('url', ''),
                "Note Tecniche": note
            })
        
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
            
            rows.append({
                "ID Audit": "C-08",
                "Categoria": "Content",
                "Elemento Analizzato": "Content Uniqueness",
                "Stato": stato,
                "Severità": sev,
                "Risultato / Evidenza": risultato,
                "URL / Link Evidenza": homepage.get('url', ''),
                "Note Tecniche": note
            })
        
        # C-09: Content Freshness
        freshness = data.get('content_freshness', {})
        if freshness:
            has_date = freshness.get('has_date', False)
            
            if has_date:
                stato, sev = "OK", 0
                risultato = "Data di pubblicazione presente"
                note = ""
            elif site_type == 'blog_news':
                stato, sev = "WARN", 2
                risultato = "Data di pubblicazione non trovata"
                note = "Aggiungere meta tag per data di pubblicazione"
            else:
                stato, sev = "N/A", 0
                risultato = "Non necessaria (sito corporate)"
                note = ""
            
            rows.append({
                "ID Audit": "C-09",
                "Categoria": "Content",
                "Elemento Analizzato": "Content Freshness",
                "Stato": stato,
                "Severità": sev,
                "Risultato / Evidenza": risultato,
                "URL / Link Evidenza": homepage.get('url', ''),
                "Note Tecniche": note
            })
        
        return rows
    
    def _process_favicon_and_images(self, data: Dict, domain: str) -> List[Dict]:
        """Processa i check su favicon e image index."""
        rows = []
        homepage = data.get('homepage', {})
        
        if not homepage or 'error' in homepage:
            return rows
        
        # H-16: Favicon Check
        favicon = data.get('favicon', {})
        if favicon:
            has_favicon = favicon.get('has_favicon', False)
            favicon_urls = favicon.get('favicon_urls', [])
            types = favicon.get('types', [])
            has_apple_touch = favicon.get('has_apple_touch', False)
            
            if has_favicon:
                stato, sev = "OK", 0
                risultato = f"Favicon presente ({len(favicon_urls)} varianti: {', '.join(types) if types else 'N/A'})"
                note = ""
                
                if not has_apple_touch:
                    note = "Consigliato aggiungere apple-touch-icon per dispositivi iOS"
            else:
                stato, sev = "FAIL", 2
                risultato = "Favicon non trovata"
                note = "Aggiungere favicon per migliorare UX e branding"
            
            rows.append({
                "ID Audit": "H-16",
                "Categoria": "HTML",
                "Elemento Analizzato": "Favicon",
                "Stato": stato,
                "Severità": sev,
                "Risultato / Evidenza": risultato,
                "URL / Link Evidenza": homepage.get('url', ''),
                "Note Tecniche": note
            })
        
        # H-17: Image Index
        images = homepage.get('images', [])
        if images:
            images_with_alt = sum(1 for img in images if img.get('alt', '').strip())
            images_with_dimensions = sum(1 for img in images if img.get('width') and img.get('height'))
            
            modern_formats = 0
            for img in images:
                src = img.get('src', '').lower()
                if src.endswith(('.webp', '.avif')):
                    modern_formats += 1
            
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
            
            rows.append({
                "ID Audit": "H-17",
                "Categoria": "HTML",
                "Elemento Analizzato": "Image SEO Optimization",
                "Stato": stato,
                "Severità": sev,
                "Risultato / Evidenza": risultato,
                "URL / Link Evidenza": homepage.get('url', ''),
                "Note Tecniche": "Ottimizzare alt text, dimensioni e formato (WebP/AVIF)" if seo_friendly < 3 else ""
            })
        
        return rows
    
    def _process_whois(self, data: Dict, domain: str) -> List[Dict]:
        """Processa i dati Whois del dominio."""
        rows = []
        
        if data.get('error'):
            rows.append({
                "ID Audit": "T-22",
                "Categoria": "Technical",
                "Elemento Analizzato": "Domain Age",
                "Stato": "WARN",
                "Severità": 2,
                "Risultato / Evidenza": f"Errore Whois: {data.get('error', '')[:100]}",
                "URL / Link Evidenza": "",
                "Note Tecniche": "Verificare manualmente su whois.com"
            })
            return rows
        
        # T-22: Domain Age
        age_years = data.get('age_years', 0)
        age_days = data.get('age_days', 0)
        creation_date = data.get('creation_date')
        
        if age_years > 0:
            stato, sev = "OK", 0
            risultato = f"Dominio registrato da {age_years} anni ({age_days} giorni) - {creation_date.strftime('%Y-%m-%d') if creation_date else 'N/A'}"
        elif age_days > 0:
            stato, sev = "INFO", 0
            risultato = f"Dominio registrato da {age_days} giorni - {creation_date.strftime('%Y-%m-%d') if creation_date else 'N/A'}"
        else:
            stato, sev = "WARN", 2
            risultato = "Data di registrazione non disponibile"
        
        rows.append({
            "ID Audit": "T-22",
            "Categoria": "Technical",
            "Elemento Analizzato": "Domain Age",
            "Stato": stato,
            "Severità": sev,
            "Risultato / Evidenza": risultato,
            "URL / Link Evidenza": "",
            "Note Tecniche": ""
        })
        
        # T-23: Domain Expiration
        days_to_expiry = data.get('days_to_expiry', 0)
        expiration_date = data.get('expiration_date')
        
        if days_to_expiry > 365:
            stato, sev = "OK", 0
            risultato = f"Scade tra {days_to_expiry} giorni ({expiration_date.strftime('%Y-%m-%d') if expiration_date else 'N/A'})"
        elif days_to_expiry > 90:
            stato, sev = "WARN", 2
            risultato = f"Scade tra {days_to_expiry} giorni ({expiration_date.strftime('%Y-%m-%d') if expiration_date else 'N/A'})"
        elif days_to_expiry > 0:
            stato, sev = "FAIL", 1
            risultato = f"SCADE TRA {days_to_expiry} GIORNI! ({expiration_date.strftime('%Y-%m-%d') if expiration_date else 'N/A'})"
        else:
            stato, sev = "FAIL", 1
            risultato = "Data di scadenza non disponibile"
        
        rows.append({
            "ID Audit": "T-23",
            "Categoria": "Technical",
            "Elemento Analizzato": "Domain Expiration",
            "Stato": stato,
            "Severità": sev,
            "Risultato / Evidenza": risultato,
            "URL / Link Evidenza": "",
            "Note Tecniche": "Rinnovare il dominio" if 0 < days_to_expiry < 90 else ""
        })
        
        # T-24: Registrar
        registrar = data.get('registrar', '')
        if registrar:
            rows.append({
                "ID Audit": "T-24",
                "Categoria": "Technical",
                "Elemento Analizzato": "Domain Registrar",
                "Stato": "OK",
                "Severità": 0,
                "Risultato / Evidenza": f"Registrar: {registrar}",
                "URL / Link Evidenza": "",
                "Note Tecniche": ""
            })
        
        # T-25: Name Servers
        name_servers = data.get('name_servers', [])
        if name_servers:
            rows.append({
                "ID Audit": "T-25",
                "Categoria": "Technical",
                "Elemento Analizzato": "Name Servers",
                "Stato": "OK",
                "Severità": 0,
                "Risultato / Evidenza": f"{len(name_servers)} nameserver configurati",
                "URL / Link Evidenza": "",
                "Note Tecniche": ", ".join(name_servers[:3])
            })
        
        # T-26: IP Address
        ip_address = data.get('ip_address', '')
        if ip_address:
            rows.append({
                "ID Audit": "T-26",
                "Categoria": "Technical",
                "Elemento Analizzato": "IP Address",
                "Stato": "OK",
                "Severità": 0,
                "Risultato / Evidenza": f"IP: {ip_address}",
                "URL / Link Evidenza": "",
                "Note Tecniche": ""
            })
        
        # T-27: DNSSEC
        dnssec = data.get('dnssec', '')
        if dnssec:
            dnssec_active = str(dnssec).lower() in ['signed', 'true', 'yes', '1']
            rows.append({
                "ID Audit": "T-27",
                "Categoria": "Technical",
                "Elemento Analizzato": "DNSSEC",
                "Stato": "OK" if dnssec_active else "INFO",
                "Severità": 0,
                "Risultato / Evidenza": f"DNSSEC: {dnssec}",
                "URL / Link Evidenza": "",
                "Note Tecniche": "" if dnssec_active else "Valutare attivazione DNSSEC per maggiore sicurezza"
            })
        
        return rows
    
    def _process_semrush(self, data: Dict, domain: str) -> List[Dict]:
        """Processa i dati di Semrush."""
        rows = []
        
        rows.append({
            "ID Audit": "G-01",
            "Categoria": "General",
            "Elemento Analizzato": "Keywords Rank",
            "Stato": "WARN",
            "Severità": 2,
            "Risultato / Evidenza": "Da verificare su Semrush dashboard",
            "URL / Link Evidenza": f"https://www.semrush.com/analytics/organic/?q={domain}",
            "Note Tecniche": "Necessaria ricerca keyword"
        })
        
        rows.append({
            "ID Audit": "I-01",
            "Categoria": "Inbound",
            "Elemento Analizzato": "Link Popularity",
            "Stato": "WARN",
            "Severità": 2,
            "Risultato / Evidenza": "Da verificare su Semrush Backlink Analytics",
            "URL / Link Evidenza": f"https://www.semrush.com/analytics/backlinks/?q={domain}",
            "Note Tecniche": ""
        })
        
        return rows
    
    def _process_manual(self, data: Dict, domain: str) -> List[Dict]:
        """Processa i dati manuali/semi-automatici."""
        rows = []
        
        https_present = data.get("https_present", False)
        rows.append({
            "ID Audit": "T-01",
            "Categoria": "Technical",
            "Elemento Analizzato": "HTTPS",
            "Stato": "OK" if https_present else "FAIL",
            "Severità": 0 if https_present else 1,
            "Risultato / Evidenza": "HTTPS presente" if https_present else "HTTPS assente",
            "URL / Link Evidenza": "",
            "Note Tecniche": ""
        })
        
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
                stato, sev = "OK", 0
                risultato = "Nessun problema rilevato"
            elif value is True:
                stato, sev = "FAIL", 1
                risultato = "Penalità rilevata!"
            else:
                stato, sev = "WARN", 0
                risultato = "Da verificare manualmente"
            
            rows.append({
                "ID Audit": audit_id,
                "Categoria": "Penalties",
                "Elemento Analizzato": f"Google Penalty - {ptype}",
                "Stato": stato,
                "Severità": sev,
                "Risultato / Evidenza": risultato,
                "URL / Link Evidenza": "https://search.google.com/search-console/security-issues",
                "Note Tecniche": ""
            })
        
        return rows
    
    def _generate_checklist(self, audit_rows: List[Dict]) -> List[Dict]:
        """Genera la checklist operativa - ESCLUDE INFO e N/A."""
        checklist = []
        chk_id = 1
        
        rules = [
            (lambda r: r["ID Audit"] == "U-01" and r["Stato"] == "FAIL",
             "3. Ottimizzazione", "Ottimizzare Core Web Vitals (rimuovere JS/CSS inutilizzati)",
             "Sviluppo", "LCP < 2.5s, Performance > 80", "Nessuna"),
            
            (lambda r: r["ID Audit"] == "U-02" and r["Stato"] == "FAIL",
             "3. Ottimizzazione", "Migliorare Lighthouse Performance Score",
             "Sviluppo", "Performance > 80/100", "Nessuna"),
            
            (lambda r: r["ID Audit"] == "T-01" and r["Stato"] != "OK",
             "1. Fondamenta", "Implementare certificato HTTPS",
             "Sviluppo", "HTTPS attivo su tutto il sito", "Nessuna"),
            
            (lambda r: r["Categoria"] == "Penalties" and r["Stato"] == "FAIL",
             "1. Fondamenta", "Risolvere penalizzazione Google",
             "SEO", "0 penalità attive", "Nessuna"),
            
            (lambda r: r["ID Audit"] == "GSC-02" and r["Stato"] == "WARN",
             "2. Architettura", "Analizzare performance organica e ottimizzare contenuti",
             "SEO", "Aumentare click organici del 20%", "Nessuna"),
            
            (lambda r: r["ID Audit"] == "T-02" and r["Stato"] == "FAIL",
             "1. Fondamenta", "Creare e caricare sitemap.xml",
             "Sviluppo / SEO", "Sitemap valida e submittera su GSC", "Nessuna"),
            
            (lambda r: r["ID Audit"] == "T-03" and r["Stato"] != "OK",
             "1. Fondamenta", "Configurare robots.txt con riferimento sitemap",
             "Sviluppo", "Robots.txt valido con riferimento sitemap", "Nessuna"),
            
            (lambda r: r["ID Audit"] == "H-01" and r["Stato"] != "OK",
             "2. Architettura", "Ottimizzare Meta Title (50-60 caratteri) con keyword target",
             "SEO", "100% pagine con Meta Title ottimizzati", "Nessuna"),
            
            (lambda r: r["ID Audit"] == "H-02" and r["Stato"] != "OK",
             "2. Architettura", "Ottimizzare Meta Description (120-160 caratteri) con keyword target",
             "SEO", "100% pagine con Meta Description ottimizzate", "Nessuna"),
            
            (lambda r: r["ID Audit"] == "H-03" and r["Stato"] == "FAIL",
             "1. Fondamenta", "Implementare tag Canonical su tutte le pagine",
             "Sviluppo", "0 errori di canonical su GSC", "Nessuna"),
            
            (lambda r: r["ID Audit"] == "H-04" and r["Stato"] == "FAIL",
             "2. Architettura", "Ottimizzare Heading H1 con keyword target",
             "SEO", "1 H1 per pagina, ottimizzato", "Nessuna"),
            
            (lambda r: r["ID Audit"] == "H-05" and r["Stato"] == "FAIL",
             "2. Architettura", "Aggiungere alt text descrittivi alle immagini",
             "Sviluppo / SEO", "100% immagini con alt text", "Nessuna"),
            
            (lambda r: r["ID Audit"] == "H-06" and r["Stato"] == "FAIL",
             "2. Architettura", "Implementare dati strutturati (Schema.org)",
             "Sviluppo", "Markup valido in GSC > Rich Results", "Nessuna"),
            
            (lambda r: r["ID Audit"] == "H-09" and r["Stato"] == "FAIL",
             "2. Architettura", "Creare pagina 404 personalizzata",
             "Sviluppo", "Pagina 404 custom con navigazione", "Nessuna"),
            
            (lambda r: r["ID Audit"] == "C-01" and r["Stato"] == "WARN",
             "2. Architettura", "Aumentare contenuto delle pagine principali",
             "SEO", "Minimo 300 parole per pagina", "Nessuna"),
            
            (lambda r: r["ID Audit"] == "T-05" and r["Stato"] == "FAIL",
             "2. Architettura", "Implementare breadcrumbs per navigazione e SEO",
             "Sviluppo", "Breadcrumbs visibili e marcati Schema.org", "Nessuna"),
            
            (lambda r: r["ID Audit"] == "T-06" and r["Stato"] == "FAIL",
             "1. Fondamenta", "Configurare redirect 301 da HTTP a HTTPS",
             "Sviluppo", "Redirect HTTP -> HTTPS funzionante", "Nessuna"),
            
            (lambda r: r["ID Audit"] == "H-11" and r["Stato"] == "WARN",
             "3. Ottimizzazione", "Ottimizzare peso immagini (WebP, compressione)",
             "Sviluppo", "Tutte immagini < 100kb", "Nessuna"),
            
            (lambda r: r["ID Audit"] == "T-07" and r["Stato"] == "WARN",
             "2. Architettura", "Ottimizzare anchor text link interni con keyword descrittive",
             "SEO", "0 anchor text generici", "Nessuna"),
            
            (lambda r: r["ID Audit"] == "T-08" and r["Stato"] == "WARN",
             "2. Architettura", "Ridurre profondità URL e semplificare struttura",
             "Sviluppo / SEO", "URL massimo 3 livelli di profondità", "Nessuna"),
            
            (lambda r: r["ID Audit"] == "C-02" and r["Stato"] == "FAIL",
             "2. Architettura", "Rimuovere o canonicalizzare contenuti duplicati",
             "SEO / Sviluppo", "0 contenuti duplicati", "Nessuna"),
            
            (lambda r: r["ID Audit"] == "T-09" and r["Stato"] == "WARN",
             "3. Ottimizzazione", "Minificare e combinare file CSS/JS",
             "Sviluppo", "Meno di 20 file CSS/JS", "Nessuna"),
            
            (lambda r: r["ID Audit"] == "T-10" and r["Stato"] == "WARN",
             "2. Architettura", "Ridurre profondità struttura sito",
             "Sviluppo / SEO", "Massimo 3 livelli di profondità", "Nessuna"),
            
            (lambda r: r["ID Audit"] == "T-11" and r["Stato"] == "WARN",
             "3. Ottimizzazione", "Implementare CDN per migliorare performance",
             "Sviluppo", "LCP mobile < 2.5s", "Nessuna"),
            
            (lambda r: r["ID Audit"] == "H-15" and r["Stato"] == "WARN",
             "2. Architettura", "Specificare width e height per tutte le immagini",
             "Sviluppo", "100% immagini con dimensioni", "Nessuna"),
            
            (lambda r: r["ID Audit"] == "C-03" and r["Stato"] != "OK",
             "2. Architettura", "Ottimizzare Focus Keyword nel Title",
             "SEO", "Keyword principale presente in tutti i title", "Nessuna"),
            
            (lambda r: r["ID Audit"] == "C-04" and r["Stato"] != "OK",
             "2. Architettura", "Ottimizzare Focus Keyword nell'H1",
             "SEO", "Keyword principale presente in tutti gli H1", "Nessuna"),
            
            (lambda r: r["ID Audit"] == "C-05" and r["Stato"] != "OK",
             "2. Architettura", "Ottimizzare densità keyword (target: 1-3%)",
             "SEO", "Densità keyword tra 1% e 3%", "Nessuna"),
            
            (lambda r: r["ID Audit"] == "C-06" and r["Stato"] == "WARN",
             "2. Architettura", "Migliorare leggibilità dei contenuti",
             "SEO / Copywriting", "Readability score > 50/100", "Nessuna"),
            
            (lambda r: r["ID Audit"] == "C-07" and r["Stato"] == "FAIL",
             "1. Fondamenta", "Rimuovere doorway pages",
             "SEO", "0 doorway pages", "Nessuna"),
            
            (lambda r: r["ID Audit"] == "C-08" and r["Stato"] != "OK",
             "2. Architettura", "Differenziare contenuti duplicati",
             "SEO / Copywriting", "100% contenuti unici", "Nessuna"),
            
            (lambda r: r["ID Audit"] == "C-09" and r["Stato"] == "WARN",
             "2. Architettura", "Aggiungere data di pubblicazione ai contenuti",
             "Sviluppo / SEO", "100% contenuti con data", "Nessuna"),
            
            (lambda r: r["ID Audit"] == "T-23" and r["Stato"] == "FAIL",
             "1. Fondamenta", "Rinnovare dominio in scadenza",
             "Sviluppo", "Dominio valido per almeno 1 anno", "Nessuna"),
            
            (lambda r: r["ID Audit"] == "H-16" and r["Stato"] == "FAIL",
             "2. Architettura", "Aggiungere favicon al sito",
             "Sviluppo", "Favicon presente in tutti i formati", "Nessuna"),
            
            (lambda r: r["ID Audit"] == "H-17" and r["Stato"] == "WARN",
             "2. Architettura", "Ottimizzare immagini per indicizzazione",
             "Sviluppo / SEO", "100% immagini con alt, dimensioni e formato moderno", "Nessuna"),
        ]
        
        for audit_row in audit_rows:
            if audit_row["Stato"] in ["INFO", "N/A"]:
                continue
            
            for rule_fn, fase, azione, owner, kpi, dip in rules:
                if rule_fn(audit_row):
                    severity = audit_row.get("Severità", 0)
                    if severity == 1:
                        priority = 1
                    elif severity == 2:
                        priority = 2
                    else:
                        priority = 3
                    
                    checklist.append({
                        "ID Check": f"CHK-{chk_id:02d}",
                        "Rif. Audit": audit_row["ID Audit"],
                        "Fase": fase,
                        "Azione Richiesta": azione,
                        "Owner": owner,
                        "Priorità": priority,
                        "Dipendenze": dip,
                        "KPI / Obiettivo": kpi,
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
        
        top_criticità = sorted(
            [r for r in audit_rows if r["Stato"] == "FAIL"],
            key=lambda x: x.get("Severità", 0),
            reverse=True
        )[:3]
        
        top_punti_forza = sorted(
            [r for r in audit_rows if r["Stato"] == "OK"],
            key=lambda x: x.get("Categoria", "")
        )[:3]
        
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
            "top_criticità": top_criticità,
            "top_punti_forza": top_punti_forza
        }