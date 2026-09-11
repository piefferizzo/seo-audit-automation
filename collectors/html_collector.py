import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import Dict, Any, List
from collections import defaultdict
import re
import json
import time
import xml.etree.ElementTree as ET
from collectors.base_collector import BaseCollector

class HTMLCollector(BaseCollector):
    """Crawler HTML avanzato con analisi multi-pagina per drill-down."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.timeout = 30
        self.max_retries = 2
        self.max_pages = config.get("MAX_PAGES_TO_CRAWL", 50)
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate',
        }
        
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
        self.playwright_available = self._check_playwright()
        self.playwright_browser = None
        self.playwright_context = None
        self.playwright_p = None
    
    def is_available(self) -> bool:
        """Il crawler HTML è sempre disponibile (non richiede credenziali)."""
        return True

    def _check_playwright(self) -> bool:
        try:
            import playwright
            return True
        except ImportError:
            return False
    
    def _init_playwright(self):
        if not self.playwright_available:
            return False
        try:
            from playwright.sync_api import sync_playwright
            self.playwright_p = sync_playwright().start()
            self.playwright_browser = self.playwright_p.chromium.launch(headless=True)
            self.playwright_context = self.playwright_browser.new_context(
                user_agent=self.headers['User-Agent'],
                viewport={'width': 1920, 'height': 1080}
            )
            return True
        except Exception as e:
            self.logger.error(f"Errore inizializzazione Playwright: {e}")
            return False
    
    def _close_playwright(self):
        try:
            if self.playwright_browser:
                self.playwright_browser.close()
            if self.playwright_p:
                self.playwright_p.stop()
        except:
            pass
    
    def collect(self, domain: str) -> Dict[str, Any]:
        """Esegue il crawling del dominio con analisi multi-pagina."""
        self.logger.info(f"🔍 Crawling HTML avanzato per {domain}...")
        
        if not domain.startswith('http'):
            domain = f"https://{domain}"
        
        results = {}
        
        try:
            # 1. Crawling homepage
            homepage_data = self._crawl_page(domain)
            
            if homepage_data.get('error') and self.playwright_available:
                self.logger.info(f"🔄 Uso Playwright per homepage...")
                homepage_data = self._crawl_page_with_playwright(domain)
            
            results['homepage'] = homepage_data
            
            # 2. Verifiche base
            results['robots'] = self._check_robots(domain)
            results['sitemap'] = {'exists': False, 'url': f"{domain}/sitemap.xml"}
            results['404'] = self._check_404(domain)
            results['redirect'] = self._check_redirect(domain)
            
            # 3. Check tecnici avanzati
            results['www_redirect'] = self._check_www_redirect(domain)
            results['mixed_content'] = self._check_mixed_content(homepage_data)
            results['redirect_chains'] = self._check_redirect_chains(domain)
            results['indexability'] = self._analyze_indexability(homepage_data)
            results['http_headers'] = self._analyze_http_headers(homepage_data)
            results['status_codes'] = self._check_status_codes(homepage_data)
            results['css_issues'] = self._analyze_css_issues(homepage_data)
            results['js_issues'] = self._analyze_js_issues(homepage_data)
            results['pagination_advanced'] = self._check_pagination_advanced(homepage_data)
            results['subdomains'] = self._detect_subdomains(homepage_data, domain)
            
            # 4. Raccolta URL da sitemap per analisi multi-pagina
            self.logger.info(f"  📋 Raccolta URL per drill-down...")
            all_urls = self._collect_urls_from_sitemap(domain, homepage_data, results['robots'])
            
            # DEBUG: Log dettagliato
            self.logger.info(f"  📊 URL totali trovate: {len(all_urls)}")
            if len(all_urls) > 0:
                self.logger.info(f"  📝 Prime 5 URL: {all_urls[:5]}")
            
            # Limita al massimo configurato
            urls_to_crawl = all_urls[:self.max_pages]
            self.logger.info(f"  🎯 URL da analizzare (limite {self.max_pages}): {len(urls_to_crawl)}")
            
            # 5. Crawling profondo di tutte le pagine per drill-down
            if len(urls_to_crawl) > 0:
                self.logger.info(f"  🔍 Avvio crawling drill-down...")
                drilldown_data = self._crawl_pages_for_drilldown(urls_to_crawl)
                results['drilldown'] = drilldown_data
                
                # DEBUG: Log risultati drill-down
                self.logger.info(f"  ✅ Drill-down completato:")
                self.logger.info(f"    - Pagine analizzate: {len(drilldown_data.get('pages_analyzed', []))}")
                self.logger.info(f"    - Problemi immagini: {len(drilldown_data.get('images_problems', []))}")
                self.logger.info(f"    - Problemi title: {len(drilldown_data.get('title_problems', []))}")
                self.logger.info(f"    - Problemi description: {len(drilldown_data.get('description_problems', []))}")
                self.logger.info(f"    - Problemi headings: {len(drilldown_data.get('headings_problems', []))}")
            else:
                self.logger.warning(f"  ⚠️  Nessuna URL trovata per drill-down!")
                results['drilldown'] = {
                    'pages_analyzed': [],
                    'images_problems': [],
                    'title_problems': [],
                    'description_problems': [],
                    'headings_problems': []
                }
            
            # 6. Crawling pagine interne (per analisi standard)
            if homepage_data.get('internal_links'):
                internal_pages = homepage_data['internal_links'][:5]
                results['internal_pages'] = []
                for page_url in internal_pages:
                    try:
                        page_data = self._crawl_page(page_url)
                        if page_data.get('error') and self.playwright_available:
                            page_data = self._crawl_page_with_playwright(page_url)
                        results['internal_pages'].append(page_data)
                        time.sleep(0.5)
                    except Exception as e:
                        self.logger.warning(f"Errore crawling {page_url}: {e}")
            
            # 7. Analisi standard
            results['breadcrumbs'] = self._detect_breadcrumbs(homepage_data)
            results['anchor_text'] = self._analyze_anchor_text(homepage_data)
            results['url_structure'] = self._analyze_url_structure(homepage_data)
            results['logo'] = self._analyze_logo(homepage_data)
            results['duplicate_content'] = self._check_duplicate_content(results.get('internal_pages', []))
            results['css_js_analysis'] = self._analyze_css_js(homepage_data)
            results['site_structure'] = self._analyze_site_structure(results.get('internal_pages', []))
            results['cdn_check'] = self._check_cdn(homepage_data)
            results['image_dimensions'] = self._analyze_image_dimensions(homepage_data)
            
            # 8. Favicon check
            results['favicon'] = self._check_favicon(homepage_data, domain)
            
            # 9. Analisi contenuti
            results['site_type'] = self._detect_site_type(homepage_data)
            results['content_quality'] = self._analyze_content_quality(homepage_data)
            results['doorway_pages'] = self._detect_doorway_pages(homepage_data)
            results['content_uniqueness'] = self._analyze_content_uniqueness(results.get('internal_pages', []))
            results['content_freshness'] = self._check_content_freshness(homepage_data)
            
            pages_analyzed = len(results.get('drilldown', {}).get('pages_analyzed', []))
            self.logger.info(f"  ✓ Crawling completato: {pages_analyzed} pagine analizzate in profondità")
            
        except Exception as e:
            self.logger.error(f"Errore crawling HTML: {e}")
        finally:
            self._close_playwright()
        
        return results
    
    # ============================================
    # METODI DI CRAWLING BASE
    # ============================================
    
    def _crawl_page_with_playwright(self, url: str) -> Dict[str, Any]:
        """Crawling con Playwright."""
        try:
            if not self.playwright_browser and not self._init_playwright():
                return {'url': url, 'error': 'Playwright non disponibile'}
            
            page = self.playwright_context.new_page()
            page.goto(url, wait_until='networkidle', timeout=60000)
            time.sleep(2)
            
            html_content = page.content()
            final_url = page.url
            page.close()
            
            soup = BeautifulSoup(html_content, 'html.parser')
            return self._extract_page_data(soup, url, final_url, {})
            
        except Exception as e:
            self.logger.error(f"Errore Playwright per {url}: {e}")
            return {'url': url, 'error': str(e)[:100]}
    
    def _crawl_page(self, url: str) -> Dict[str, Any]:
        """Crawling con requests."""
        for attempt in range(self.max_retries):
            try:
                response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
                
                if response.status_code == 403:
                    return {'url': url, 'error': '403 Forbidden'}
                
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
                
                return self._extract_page_data(soup, url, response.url, dict(response.headers))
                
            except Exception as e:
                if attempt < self.max_retries - 1:
                    time.sleep(1)
                    continue
                return {'url': url, 'error': str(e)[:100]}
    
    def _extract_page_data(self, soup: BeautifulSoup, url: str, final_url: str, headers: Dict) -> Dict[str, Any]:
        """Estrae tutti i dati dalla pagina."""
        content_soup = BeautifulSoup(str(soup), 'html.parser')
        for elem in content_soup(['script', 'style', 'nav', 'footer', 'header']):
            elem.decompose()
        content_text = content_soup.get_text(separator=' ', strip=True)
        
        return {
            'url': url,
            'status_code': 200,
            'final_url': final_url,
            'redirected': final_url != url,
            'response_headers': headers,
            'title': self._get_text(soup.find('title')),
            'meta_description': self._get_meta(soup, 'description'),
            'canonical': self._get_canonical(soup),
            'viewport': self._get_meta(soup, 'viewport'),
            'robots_meta': self._get_robots_meta(soup),
            'og_tags': self._get_og_tags(soup),
            'hreflang': self._get_hreflang(soup),
            'headings': self._get_headings(soup),
            'images': self._get_images(soup, url),
            'internal_links': self._get_internal_links(soup, url),
            'internal_links_with_text': self._get_internal_links_with_text(soup, url),
            'structured_data': self._get_structured_data(soup),
            'lang': self._get_lang(soup),
            'word_count': self._get_word_count(soup),
            'breadcrumbs': self._find_breadcrumbs(soup),
            'logo': self._find_logo(soup, url),
            'css_files': self._get_css_files(soup, url),
            'js_files': self._get_js_files(soup, url),
            'favicon_links': self._get_favicon_links(soup, url),
            'content_text': content_text,
        }
    
    # ============================================
    # METODI DI ESTRAZIONE DATI
    # ============================================
    
    def _get_text(self, tag):
        return tag.get_text().strip() if tag else ""
    
    def _get_meta(self, soup, name):
        meta = soup.find('meta', attrs={'name': name})
        return meta.get('content', '').strip() if meta else ""
    
    def _get_robots_meta(self, soup):
        robots = soup.find('meta', attrs={'name': 'robots'})
        return robots.get('content', '') if robots else ""
    
    def _get_canonical(self, soup):
        canonical = soup.find('link', rel='canonical')
        return canonical.get('href', '') if canonical else ""
    
    def _get_og_tags(self, soup):
        og_tags = {}
        for meta in soup.find_all('meta', attrs={'property': re.compile('^og:')}):
            prop = meta.get('property', '').replace('og:', '')
            og_tags[prop] = meta.get('content', '')
        return og_tags
    
    def _get_hreflang(self, soup):
        hreflangs = []
        for link in soup.find_all('link', rel='alternate'):
            hreflang = link.get('hreflang')
            href = link.get('href')
            if hreflang and href:
                hreflangs.append({'lang': hreflang, 'href': href})
        return hreflangs
    
    def _get_headings(self, soup):
        headings = defaultdict(list)
        for i in range(1, 7):
            for h in soup.find_all(f'h{i}'):
                headings[f'h{i}'].append(h.get_text().strip())
        return dict(headings)
    
    def _get_images(self, soup, base_url):
        images = []
        for img in soup.find_all('img'):
            src = img.get('src', '')
            if src:
                images.append({
                    'src': urljoin(base_url, src),
                    'alt': img.get('alt', ''),
                    'width': img.get('width'),
                    'height': img.get('height')
                })
        return images
    
    def _get_internal_links(self, soup, base_url):
        base_domain = urlparse(base_url).netloc
        links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            if not href or href.startswith(('javascript:', 'mailto:', 'tel:', '#')):
                continue
            full_url = urljoin(base_url, href).split('#')[0]
            if urlparse(full_url).netloc == base_domain and full_url.startswith('http'):
                if full_url not in links:
                    links.append(full_url)
        return links[:30]
    
    def _get_internal_links_with_text(self, soup, base_url):
        base_domain = urlparse(base_url).netloc
        links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            if not href or href.startswith(('javascript:', 'mailto:', 'tel:', '#')):
                continue
            full_url = urljoin(base_url, href).split('#')[0]
            if urlparse(full_url).netloc == base_domain and full_url.startswith('http'):
                text = a.get_text().strip()
                if text:
                    links.append({'url': full_url, 'anchor': text})
        return links[:30]
    
    def _get_structured_data(self, soup):
        data = []
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data.append(json.loads(script.string))
            except:
                pass
        return data
    
    def _get_lang(self, soup):
        html = soup.find('html')
        return html.get('lang', '') if html else ''
    
    def _get_word_count(self, soup):
        for elem in soup(['script', 'style', 'nav', 'footer']):
            elem.decompose()
        return len(soup.get_text().split())
    
    def _find_breadcrumbs(self, soup):
        breadcrumbs = []
        for cls in ['breadcrumb', 'breadcrumbs', 'crumbs']:
            for elem in soup.find_all(class_=re.compile(cls, re.I)):
                for link in elem.find_all('a'):
                    breadcrumbs.append(link.get_text().strip())
        return breadcrumbs
    
    def _find_logo(self, soup, base_url):
        for cls in ['logo', 'site-logo', 'brand']:
            elem = soup.find(class_=re.compile(cls, re.I))
            if elem:
                img = elem.find('img')
                if img and img.get('src'):
                    return {'found': True, 'src': urljoin(base_url, img.get('src'))}
        return {'found': False}
    
    def _get_css_files(self, soup, base_url):
        """Rileva file CSS con metodi multipli."""
        css_files = []
        
        # Metodo 1: tag <link rel="stylesheet">
        for link in soup.find_all('link', rel='stylesheet'):
            href = link.get('href')
            if href:
                css_files.append(urljoin(base_url, href))
        
        # Metodo 2: tag <link> con type="text/css"
        for link in soup.find_all('link', type='text/css'):
            href = link.get('href')
            if href and href not in css_files:
                css_files.append(urljoin(base_url, href))
        
        # Metodo 3: tag <style> con src (raro ma possibile)
        for style in soup.find_all('style', src=True):
            src = style.get('src')
            if src and src not in css_files:
                css_files.append(urljoin(base_url, src))
        
        return css_files
    
    def _get_js_files(self, soup, base_url):
        """Rileva file JavaScript con metodi multipli."""
        js_files = []
        
        # Metodo 1: tag <script src="...">
        for script in soup.find_all('script', src=True):
            src = script.get('src')
            if src:
                js_files.append(urljoin(base_url, src))
        
        # Metodo 2: tag <script type="text/javascript"> con src
        for script in soup.find_all('script', type='text/javascript'):
            src = script.get('src')
            if src and src not in js_files:
                js_files.append(urljoin(base_url, src))
        
        # Metodo 3: tag <script type="module"> con src
        for script in soup.find_all('script', type='module'):
            src = script.get('src')
            if src and src not in js_files:
                js_files.append(urljoin(base_url, src))
        
        return js_files
    
    def _get_favicon_links(self, soup, base_url):
        """Estrae tutti i link favicon dalla pagina."""
        favicons = []
        
        # Cerca tutti i link rel="icon" o rel="shortcut icon"
        for link in soup.find_all('link', rel=lambda r: r and ('icon' in r.lower())):
            href = link.get('href', '')
            if href:
                favicons.append({
                    'href': urljoin(base_url, href),
                    'rel': link.get('rel', ['icon'])[0] if link.get('rel') else 'icon',
                    'type': link.get('type', ''),
                    'sizes': link.get('sizes', '')
                })
        
        return favicons
    
    # ============================================
    # METODI DI VERIFICA BASE
    # ============================================
    
    def _check_robots(self, domain):
        """Verifica robots.txt con tentativi multipli."""
        try:
            # Tentativo 1: User-agent standard
            response = self.session.get(f"{domain}/robots.txt", timeout=10)
            
            # Se fallisce, prova con user-agent Googlebot
            if response.status_code != 200:
                self.logger.info(f"  🔄 robots.txt status {response.status_code}, provo con Googlebot UA...")
                headers = {
                    'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'
                }
                response = self.session.get(f"{domain}/robots.txt", headers=headers, timeout=10)
            
            content = response.text if response.status_code == 200 else ""
            
            sitemap_url = ''
            for line in content.split('\n'):
                if line.strip().lower().startswith('sitemap:'):
                    sitemap_url = line.split(':', 1)[1].strip()
                    break
            
            self.logger.info(f"  ✓ robots.txt trovato, sitemap dichiarata: {sitemap_url if sitemap_url else 'N/A'}")
            
            return {
                'exists': bool(content),
                'content': content,
                'has_sitemap': bool(sitemap_url),
                'sitemap_url': sitemap_url,
                'status_code': response.status_code
            }
        except Exception as e:
            self.logger.warning(f"  ⚠️  Errore robots.txt: {e}")
            return {'exists': False, 'content': '', 'has_sitemap': False, 'sitemap_url': '', 'status_code': 0}
    
    def _check_404(self, domain):
        try:
            response = self.session.get(f"{domain}/test-404-page", timeout=10, allow_redirects=False)
            return {'is_custom': response.status_code == 404 and len(response.content) > 500}
        except:
            return {'is_custom': False}
    
    def _check_redirect(self, domain):
        clean_domain = domain.replace('https://', '').replace('http://', '').replace('www.', '')
        try:
            response = self.session.get(f"http://{clean_domain}", timeout=10, allow_redirects=False)
            if response.status_code in [301, 302]:
                location = response.headers.get('Location', '')
                return {'redirects': True, 'is_https': location.startswith('https://')}
        except:
            pass
        return {'redirects': False, 'is_https': False}
    
    # ============================================
    # METODI DI ANALISI SITEMAP AVANZATA
    # ============================================
    
    def _collect_urls_from_sitemap(self, domain: str, homepage_data: Dict, robots_data: Dict) -> List[str]:
        """Raccoglie tutte le URL dalla sitemap con tentativi multipli."""
        urls = set()
        
        # 1. Aggiungi homepage
        urls.add(domain.rstrip('/'))
        self.logger.info(f"  ✓ Homepage aggiunta: {domain}")
        
        # 2. Prova a leggere la sitemap dal robots.txt
        sitemap_url = robots_data.get('sitemap_url', '')
        
        if sitemap_url:
            self.logger.info(f"  📖 Tentativo download sitemap da robots.txt: {sitemap_url}")
            sitemap_urls = self._download_and_parse_sitemap(sitemap_url)
            if sitemap_urls:
                self.logger.info(f"  ✓ Trovate {len(sitemap_urls)} URL dalla sitemap (robots.txt)")
                urls.update(sitemap_urls)
            else:
                self.logger.warning(f"  ⚠️  Sitemap da robots.txt non parsabile, provo URL comuni...")
        
        # 3. Se non funziona, prova URL comuni
        if not sitemap_url or not urls:
            self.logger.info(f"  🔍 Provo URL sitemap comuni...")
            for candidate in [
                f"{domain}/sitemap.xml",
                f"{domain}/sitemap_index.xml",
                f"{domain}/wp-sitemap.xml",
                f"{domain}/sitemap/sitemap.xml",
                f"{domain}/sitemap-index.xml"
            ]:
                self.logger.info(f"    → Provo: {candidate}")
                sitemap_urls = self._download_and_parse_sitemap(candidate)
                if sitemap_urls:
                    self.logger.info(f"    ✓ Trovate {len(sitemap_urls)} URL da {candidate}")
                    urls.update(sitemap_urls)
                    break
                else:
                    self.logger.info(f"    ✗ Non trovata o non parsabile")
        
        # 4. Aggiungi link interni dalla homepage
        internal_links = homepage_data.get('internal_links', [])
        self.logger.info(f"  🔗 Link interni dalla homepage: {len(internal_links)}")
        
        for link in internal_links:
            clean_link = link.split('#')[0]
            if clean_link:
                urls.add(clean_link)
        
        self.logger.info(f"  📊 Totale URL uniche raccolte: {len(urls)}")
        
        return list(urls)
    
    def _download_and_parse_sitemap(self, sitemap_url: str) -> List[str]:
        """Scarica e parsifica una sitemap con tentativi multipli."""
        urls = []
        
        # Tentativo 1: User-agent standard
        try:
            self.logger.info(f"    📥 Download (UA standard): {sitemap_url}")
            response = self.session.get(sitemap_url, timeout=15)
            
            if response.status_code == 200:
                content = response.text
                self.logger.info(f"    📄 Scaricata: {len(content)} bytes")
                
                # Parsa la sitemap
                parsed_urls = self._parse_sitemap_content(content, sitemap_url)
                if parsed_urls:
                    return parsed_urls
            else:
                self.logger.info(f"    ⚠️  Status code: {response.status_code}")
        except Exception as e:
            self.logger.warning(f"    ⚠️  Errore UA standard: {e}")
        
        # Tentativo 2: User-agent Googlebot
        try:
            self.logger.info(f"    📥 Download (UA Googlebot): {sitemap_url}")
            headers = {
                'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'
            }
            response = self.session.get(sitemap_url, headers=headers, timeout=15)
            
            if response.status_code == 200:
                content = response.text
                self.logger.info(f"    📄 Scaricata: {len(content)} bytes")
                
                # Parsa la sitemap
                parsed_urls = self._parse_sitemap_content(content, sitemap_url)
                if parsed_urls:
                    return parsed_urls
            else:
                self.logger.info(f"    ⚠️  Status code: {response.status_code}")
        except Exception as e:
            self.logger.warning(f"    ⚠️  Errore UA Googlebot: {e}")
        
        # Tentativo 3: User-agent browser completo
        try:
            self.logger.info(f"    📥 Download (UA browser): {sitemap_url}")
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
            }
            response = self.session.get(sitemap_url, headers=headers, timeout=15)
            
            if response.status_code == 200:
                content = response.text
                self.logger.info(f"    📄 Scaricata: {len(content)} bytes")
                
                # Parsa la sitemap
                parsed_urls = self._parse_sitemap_content(content, sitemap_url)
                if parsed_urls:
                    return parsed_urls
            else:
                self.logger.info(f"    ⚠️  Status code: {response.status_code}")
        except Exception as e:
            self.logger.warning(f"    ⚠️  Errore UA browser: {e}")
        
        return []
    
    def _parse_sitemap_content(self, content: str, base_url: str) -> List[str]:
        """Parsa il contenuto di una sitemap (anche sitemap index)."""
        urls = []
        
        try:
            # Controlla se è un sitemap index
            if '<sitemapindex' in content:
                self.logger.info(f"    🗂️  Sitemap index rilevato")
                # Estrai URL delle sotto-sitemap
                sub_sitemaps = re.findall(r'<loc>(.*?)</loc>', content)
                self.logger.info(f"    📋 Trovate {len(sub_sitemaps)} sotto-sitemap")
                
                for sub_url in sub_sitemaps:
                    sub_url = sub_url.strip()
                    self.logger.info(f"      → Parsing sotto-sitemap: {sub_url}")
                    sub_urls = self._download_and_parse_sitemap(sub_url)
                    urls.extend(sub_urls)
                    self.logger.info(f"      ✓ {len(sub_urls)} URL dalla sotto-sitemap")
            elif '<urlset' in content:
                # Sitemap normale
                self.logger.info(f"    📄 Sitemap normale, parsing URL...")
                found_urls = re.findall(r'<loc>(.*?)</loc>', content)
                urls.extend([u.strip() for u in found_urls])
                self.logger.info(f"    ✓ {len(urls)} URL trovate")
            else:
                # Prova a parsare come XML generico
                self.logger.info(f"    ⚠️  Formato non standard, provo parsing XML generico...")
                found_urls = re.findall(r'<loc>(.*?)</loc>', content)
                if found_urls:
                    urls.extend([u.strip() for u in found_urls])
                    self.logger.info(f"    ✓ {len(urls)} URL trovate (parsing generico)")
                else:
                    self.logger.warning(f"    ✗ Nessun URL trovato nel contenuto")
        
        except Exception as e:
            self.logger.error(f"    ✗ Errore parsing sitemap: {e}")
        
        return urls
    
    # ============================================
    # METODI DI CRAWLING DRILL-DOWN
    # ============================================
    
    def _crawl_pages_for_drilldown(self, urls: List[str]) -> Dict[str, Any]:
        """Crawla tutte le URL e raccoglie dati per drill-down."""
        drilldown = {
            'pages_analyzed': [],
            'images_problems': [],
            'title_problems': [],
            'description_problems': [],
            'headings_problems': [],
        }
        
        total = len(urls)
        success_count = 0
        error_count = 0
        
        for i, url in enumerate(urls, 1):
            if i % 10 == 0 or i == 1:
                self.logger.info(f"  📊 Analisi drill-down: {i}/{total} pagine...")
            
            try:
                page_info = self._analyze_page_deep(url)
                if page_info:
                    drilldown['pages_analyzed'].append(page_info)
                    success_count += 1
                    
                    # Raccogli problemi
                    drilldown['images_problems'].extend(page_info.get('image_problems', []))
                    drilldown['title_problems'].extend(page_info.get('title_problems', []))
                    drilldown['description_problems'].extend(page_info.get('description_problems', []))
                    drilldown['headings_problems'].extend(page_info.get('headings_problems', []))
                else:
                    error_count += 1
                
                time.sleep(0.3)  # Pausa per non sovraccaricare il server
            except Exception as e:
                self.logger.warning(f"  ⚠️  Errore analisi {url}: {e}")
                error_count += 1
        
        self.logger.info(f"  ✅ Drill-down completato: {success_count} successi, {error_count} errori")
        
        return drilldown
    
    def _analyze_page_deep(self, url: str) -> Dict[str, Any]:
        """Analizza una pagina in profondità per estrarre dati drill-down."""
        try:
            response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            if response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            page_info = {
                'url': url,
                'status_code': response.status_code,
            }
            
            # Analizza TITLE
            page_info['title_problems'] = self._analyze_title_deep(soup, url)
            
            # Analizza DESCRIPTION
            page_info['description_problems'] = self._analyze_description_deep(soup, url)
            
            # Analizza HEADINGS
            page_info['headings_problems'] = self._analyze_headings_deep(soup, url)
            
            # Analizza IMMAGINI
            page_info['image_problems'] = self._analyze_images_deep(soup, url)
            
            return page_info
            
        except Exception as e:
            self.logger.warning(f"Errore analisi profonda {url}: {e}")
            return None
    
    def _analyze_title_deep(self, soup: BeautifulSoup, url: str) -> List[Dict]:
        """Analizza il meta title e rileva problemi."""
        problems = []
        title_tag = soup.find('title')
        
        if not title_tag:
            problems.append({
                'url': url,
                'meta_title': '[MANCANTE]',
                'problem': 'Title assente'
            })
            return problems
        
        title_text = title_tag.get_text().strip()
        char_count = len(title_text)
        pixel_width = self._estimate_pixel_width(title_text, is_title=True)
        
        # Controlla problemi
        if char_count > 60:
            problems.append({
                'url': url,
                'meta_title': title_text,
                'problem': f'Oltre 60 caratteri ({char_count})'
            })
        elif char_count < 30:
            problems.append({
                'url': url,
                'meta_title': title_text,
                'problem': f'Sotto 30 caratteri ({char_count})'
            })
        
        if pixel_width > 561:
            problems.append({
                'url': url,
                'meta_title': title_text,
                'problem': f'Oltre 561px ({pixel_width}px)'
            })
        elif pixel_width < 200 and char_count > 0:
            problems.append({
                'url': url,
                'meta_title': title_text,
                'problem': f'Sotto 200px ({pixel_width}px)'
            })
        
        return problems
    
    def _analyze_description_deep(self, soup: BeautifulSoup, url: str) -> List[Dict]:
        """Analizza la meta description e rileva problemi."""
        problems = []
        meta = soup.find('meta', attrs={'name': 'description'})
        
        if not meta or not meta.get('content'):
            problems.append({
                'url': url,
                'meta_description': '[MANCANTE]',
                'problem': 'Description assente'
            })
            return problems
        
        desc_text = meta.get('content', '').strip()
        char_count = len(desc_text)
        pixel_width = self._estimate_pixel_width(desc_text, is_title=False)
        
        if char_count > 155:
            problems.append({
                'url': url,
                'meta_description': desc_text,
                'problem': f'Oltre 155 caratteri ({char_count})'
            })
        elif char_count < 70:
            problems.append({
                'url': url,
                'meta_description': desc_text,
                'problem': f'Sotto 70 caratteri ({char_count})'
            })
        
        if pixel_width > 995:
            problems.append({
                'url': url,
                'meta_description': desc_text,
                'problem': f'Oltre 995px ({pixel_width}px)'
            })
        elif pixel_width < 40 and char_count > 0:
            problems.append({
                'url': url,
                'meta_description': desc_text,
                'problem': f'Sotto 40 caratteri ({pixel_width}px)'
            })
        
        return problems
    
    def _analyze_headings_deep(self, soup: BeautifulSoup, url: str) -> List[Dict]:
        """Analizza gli headings H1 e rileva problemi."""
        problems = []
        h1_tags = soup.find_all('h1')
        h1_list = [h.get_text().strip() for h in h1_tags if h.get_text().strip()]
        
        h1_1 = h1_list[0] if len(h1_list) > 0 else ''
        h1_2 = h1_list[1] if len(h1_list) > 1 else ''
        
        problem_list = []
        
        # H1 assente
        if len(h1_list) == 0:
            problem_list.append('Assente')
        
        # H1 multiplo
        if len(h1_list) > 1:
            problem_list.append('Multiplo')
        
        # H1 troppo lungo
        for h1 in h1_list:
            if len(h1) > 70:
                problem_list.append(f'Oltre 70 caratteri ({len(h1)})')
                break
        
        # H1 duplicato (stesso testo in più H1)
        if len(h1_list) > 1 and len(set(h1_list)) < len(h1_list):
            problem_list.append('Duplicato')
        
        if problem_list:
            problems.append({
                'url': url,
                'h1-1': h1_1,
                'h1-2': h1_2,
                'problem': ' | '.join(problem_list)
            })
        
        return problems
    
    def _analyze_images_deep(self, soup: BeautifulSoup, url: str) -> List[Dict]:
        """Analizza le immagini e rileva problemi (alt, dimensioni, peso).
        Filtra automaticamente: SVG inline, tracking pixel, Gravatar, URL non validi."""
        problems = []
        seen_urls = set()
        skipped_count = 0
        
        # Pattern da filtrare (rumore noto)
        skip_patterns = [
            # Data URI (SVG inline, base64)
            r'^data:',
            # Tracking pixel
            r'linkedin\.com/collect',
            r'facebook\.com/tr',
            r'google-analytics\.com',
            r'googletagmanager\.com',
            r'px\.ads\.linkedin\.com',
            r'connect\.facebook\.net',
            r'analytics\.google\.com',
            # Gravatar (avatar WordPress)
            r'secure\.gravatar\.com',
            r'www\.gravatar\.com',
            # URL con typo evidenti (es. "0arkys" invece di "arkys")
            r'^https?://0[a-z]',
            # Pixel di monitoraggio comuni
            r'pixel\.',
            r'tracking\.',
            r'beacon\.',
            # Placeholder images
            r'placeholder\.',
            r'dummyimage\.com',
            r'via\.placeholder',
        ]
        
        domain_base = urlparse(url).netloc
        
        for img in soup.find_all('img'):
            src = img.get('src', '')
            if not src:
                continue
            
            full_src = urljoin(url, src)
            
            # 1. Evita duplicati
            if full_src in seen_urls:
                continue
            seen_urls.add(full_src)
            
            # 2. Applica filtri anti-rumore
            should_skip = False
            for pattern in skip_patterns:
                if re.search(pattern, full_src, re.IGNORECASE):
                    should_skip = True
                    skipped_count += 1
                    break
            
            if should_skip:
                continue
            
            # 3. Filtra immagini esterne non pertinenti (opzionale)
            img_domain = urlparse(full_src).netloc
            if img_domain and img_domain != domain_base:
                # Permetti solo CDN noti o domini correlati
                if not any(cdn in img_domain for cdn in ['cdn', 'media', 'static', 'images', 'img']):
                    # Se è un dominio completamente esterno, skip
                    if not img_domain.endswith(domain_base.replace('www.', '')):
                        skipped_count += 1
                        continue
            
            # 4. Analizza l'immagine (alt, dimensioni, peso)
            alt = img.get('alt', '')
            width = img.get('width')
            height = img.get('height')
            
            # Problema: alt mancante
            if not alt or alt.strip() == '':
                problems.append({
                    'url': full_src,
                    'problem': 'Testo alt mancante'
                })
            
            # Problema: dimensioni mancanti
            if not width or not height:
                problems.append({
                    'url': full_src,
                    'problem': 'Attributi di dimensione mancanti'
                })
            
            # Problema: peso > 100kb
            img_size_kb = self._get_image_size_kb(full_src)
            if img_size_kb is not None and img_size_kb > 100:
                problems.append({
                    'url': full_src,
                    'problem': f'Oltre 100 kb ({img_size_kb:.1f} kb)'
                })
        
        if skipped_count > 0:
            self.logger.info(f"  🎯 Filtrate {skipped_count} immagini non pertinenti (tracking/SVG/Gravatar)")
        
        return problems
    
    def _get_image_size_kb(self, image_url: str) -> float:
        """Ottiene la dimensione di un'immagine in KB (HEAD request)."""
        try:
            response = self.session.head(image_url, timeout=5, allow_redirects=True)
            if response.status_code == 200:
                content_length = response.headers.get('content-length')
                if content_length:
                    return int(content_length) / 1024
        except:
            pass
        return None
    
    def _estimate_pixel_width(self, text: str, is_title: bool = True) -> int:
        """Stima la larghezza in pixel di un testo nelle SERP Google."""
        if not text:
            return 0
        
        # Fattore pixel per carattere (stima)
        if is_title:
            px_per_char = 8.5
        else:
            px_per_char = 6.8
        
        return int(len(text) * px_per_char)
    
    # ============================================
    # METODI DI ANALISI TECNICA AVANZATA
    # ============================================
    
    def _check_www_redirect(self, domain: str) -> Dict[str, Any]:
        """Verifica redirect www vs non-www."""
        clean_domain = domain.replace('https://', '').replace('http://', '').replace('www.', '')
        
        results = {
            'www_to_non_www': None,
            'non_www_to_www': None,
            'consistent': False
        }
        
        try:
            response = self.session.get(f"https://www.{clean_domain}", timeout=10, allow_redirects=False)
            if response.status_code in [301, 302]:
                location = response.headers.get('Location', '')
                results['www_to_non_www'] = {
                    'redirects': True,
                    'status': response.status_code,
                    'location': location,
                    'correct': not location.startswith('https://www.')
                }
            
            response = self.session.get(f"https://{clean_domain}", timeout=10, allow_redirects=False)
            if response.status_code in [301, 302]:
                location = response.headers.get('Location', '')
                results['non_www_to_www'] = {
                    'redirects': True,
                    'status': response.status_code,
                    'location': location,
                    'correct': location.startswith('https://www.')
                }
            
            if results['www_to_non_www'] or results['non_www_to_www']:
                results['consistent'] = True
            
        except Exception as e:
            self.logger.warning(f"Errore check www redirect: {e}")
        
        return results
    
    def _check_mixed_content(self, homepage_data: Dict) -> Dict[str, Any]:
        """Rileva mixed content (HTTP su HTTPS)."""
        mixed_content = []
        
        for img in homepage_data.get('images', []):
            src = img.get('src', '')
            if src.startswith('http://'):
                mixed_content.append({'type': 'image', 'url': src})
        
        for css in homepage_data.get('css_files', []):
            if css.startswith('http://'):
                mixed_content.append({'type': 'css', 'url': css})
        
        for js in homepage_data.get('js_files', []):
            if js.startswith('http://'):
                mixed_content.append({'type': 'js', 'url': js})
        
        return {
            'has_mixed_content': len(mixed_content) > 0,
            'count': len(mixed_content),
            'items': mixed_content[:5]
        }
    
    def _check_redirect_chains(self, domain: str) -> Dict[str, Any]:
        """Verifica catene di redirect."""
        try:
            response = self.session.get(domain, timeout=10, allow_redirects=True)
            
            redirect_chain = []
            if response.history:
                for resp in response.history:
                    redirect_chain.append({
                        'url': resp.url,
                        'status': resp.status_code,
                        'location': resp.headers.get('Location', '')
                    })
            
            return {
                'has_chain': len(redirect_chain) > 1,
                'chain_length': len(redirect_chain),
                'chain': redirect_chain,
                'final_url': response.url
            }
            
        except Exception as e:
            return {'has_chain': False, 'chain_length': 0, 'chain': [], 'error': str(e)}
    
    def _analyze_indexability(self, homepage_data: Dict) -> Dict[str, Any]:
        """Analizza l'indexabilità della pagina."""
        robots_meta = homepage_data.get('robots_meta', '').lower()
        canonical = homepage_data.get('canonical', '')
        
        noindex = 'noindex' in robots_meta
        nofollow = 'nofollow' in robots_meta
        
        url = homepage_data.get('url', '')
        canonical_correct = canonical and url and canonical.rstrip('/') == url.rstrip('/')
        
        return {
            'indexable': not noindex,
            'noindex': noindex,
            'nofollow': nofollow,
            'has_canonical': bool(canonical),
            'canonical_correct': canonical_correct,
            'robots_meta': robots_meta
        }
    
    def _analyze_http_headers(self, homepage_data: Dict) -> Dict[str, Any]:
        """Analizza gli HTTP headers per SEO e sicurezza."""
        headers = homepage_data.get('response_headers', {})
        
        return {
            'server': headers.get('Server', ''),
            'x_powered_by': headers.get('X-Powered-By', ''),
            'content_type': headers.get('Content-Type', ''),
            'cache_control': headers.get('Cache-Control', ''),
            'x_frame_options': headers.get('X-Frame-Options', ''),
            'strict_transport_security': headers.get('Strict-Transport-Security', ''),
            'content_security_policy': headers.get('Content-Security-Policy', ''),
            'x_content_type_options': headers.get('X-Content-Type-Options', ''),
            'has_security_headers': bool(headers.get('X-Frame-Options') or headers.get('Strict-Transport-Security'))
        }
    
    def _check_status_codes(self, homepage_data: Dict) -> Dict[str, Any]:
        """Verifica gli status code delle risorse."""
        status_codes = {
            'page_status': homepage_data.get('status_code', 0),
            'resources_checked': 0,
            'broken_resources': 0
        }
        
        critical_resources = []
        
        if homepage_data.get('url'):
            base_url = homepage_data['url'].rsplit('/', 1)[0]
            critical_resources.append(f"{base_url}/sitemap.xml")
            critical_resources.append(f"{base_url}/robots.txt")
        
        for resource in critical_resources[:3]:
            try:
                response = self.session.head(resource, timeout=5, allow_redirects=True)
                status_codes['resources_checked'] += 1
                if response.status_code >= 400:
                    status_codes['broken_resources'] += 1
            except:
                pass
        
        return status_codes
    
    def _analyze_css_issues(self, homepage_data: Dict) -> Dict[str, Any]:
        """Analizza problemi CSS."""
        css_files = homepage_data.get('css_files', [])
        
        return {
            'total_css_files': len(css_files),
            'external_css': len(css_files),
            'inline_css': 0,
            'too_many_files': len(css_files) > 10,
            'recommendation': 'Combinare e minificare CSS' if len(css_files) > 5 else 'OK'
        }
    
    def _analyze_js_issues(self, homepage_data: Dict) -> Dict[str, Any]:
        """Analizza problemi JavaScript."""
        js_files = homepage_data.get('js_files', [])
        
        return {
            'total_js_files': len(js_files),
            'external_js': len(js_files),
            'inline_js': 0,
            'too_many_files': len(js_files) > 10,
            'recommendation': 'Deferire o async JS' if len(js_files) > 5 else 'OK'
        }
    
    def _check_pagination_advanced(self, homepage_data: Dict) -> Dict[str, Any]:
        """Verifica pagination avanzata (rel next/prev)."""
        return {
            'has_pagination': False,
            'has_rel_next': False,
            'has_rel_prev': False,
            'note': 'Analisi pagination avanzata richiede crawling completo'
        }
    
    def _detect_subdomains(self, homepage_data: Dict, domain: str) -> Dict[str, Any]:
        """Rileva sottodomini nei link interni."""
        base_domain = urlparse(domain).netloc
        subdomains = set()
        
        for link in homepage_data.get('internal_links', []):
            link_domain = urlparse(link).netloc
            if link_domain != base_domain and link_domain.endswith(base_domain):
                subdomains.add(link_domain)
        
        return {
            'has_subdomains': len(subdomains) > 0,
            'subdomains': list(subdomains),
            'count': len(subdomains)
        }
    
    def _analyze_image_dimensions(self, homepage_data: Dict) -> Dict[str, Any]:
        """Analizza le dimensioni delle immagini."""
        images = homepage_data.get('images', [])
        images_without_dimensions = []
        
        for img in images:
            width = img.get('width')
            height = img.get('height')
            if not width or not height:
                images_without_dimensions.append(img.get('src', ''))
        
        return {
            'total_images': len(images),
            'without_dimensions': len(images_without_dimensions),
            'sample': images_without_dimensions[:5]
        }
    
    def _check_favicon(self, homepage_data: Dict, domain: str) -> Dict[str, Any]:
        """Verifica la presenza e qualità della favicon."""
        favicon_links = homepage_data.get('favicon_links', [])
        
        result = {
            'has_favicon': False,
            'favicon_urls': [],
            'types': [],
            'has_apple_touch': False,
            'has_manifest': False,
            'default_favicon_exists': False
        }
        
        # Analizza i favicon link trovati
        for fav in favicon_links:
            href = fav.get('href', '')
            rel = fav.get('rel', '').lower()
            fav_type = fav.get('type', '').lower()
            sizes = fav.get('sizes', '')
            
            result['favicon_urls'].append(href)
            
            # Identifica il tipo
            if 'apple-touch' in rel:
                result['has_apple_touch'] = True
            if 'manifest' in rel:
                result['has_manifest'] = True
            
            if 'svg' in fav_type:
                result['types'].append('svg')
            elif 'png' in fav_type:
                result['types'].append('png')
            elif 'ico' in fav_type:
                result['types'].append('ico')
            elif href.endswith('.svg'):
                result['types'].append('svg')
            elif href.endswith('.png'):
                result['types'].append('png')
            elif href.endswith('.ico'):
                result['types'].append('ico')
        
        # Verifica favicon di default (/favicon.ico)
        try:
            default_url = f"{domain.rstrip('/')}/favicon.ico"
            response = self.session.head(default_url, timeout=5, allow_redirects=True)
            if response.status_code == 200:
                result['default_favicon_exists'] = True
                if default_url not in result['favicon_urls']:
                    result['favicon_urls'].append(default_url)
        except:
            pass
        
        # Determina se ha una favicon valida
        result['has_favicon'] = len(result['favicon_urls']) > 0 or result['default_favicon_exists']
        result['types'] = list(set(result['types']))  # Rimuovi duplicati
        
        return result
    
    # ============================================
    # METODI DI ANALISI CONTENUTI
    # ============================================
    
    def _detect_site_type(self, homepage_data: Dict) -> str:
        """Rileva automaticamente il tipo di sito (blog/news vs corporate)."""
        blog_signals = 0
        
        content_text = homepage_data.get('content_text', '').lower()
        if '<article' in content_text:
            blog_signals += 2
        
        blog_patterns = ['posted on', 'published', 'by', 'categories:', 'tags:', 
                         'leave a comment', 'related posts', 'recent posts']
        for pattern in blog_patterns:
            if pattern in content_text:
                blog_signals += 1
        
        if 'article:published_time' in content_text or 'datepublished' in content_text:
            blog_signals += 2
        
        url = homepage_data.get('url', '')
        if any(x in url for x in ['/blog/', '/news/', '/articles/', '/post/']):
            blog_signals += 2
        
        site_type = 'blog_news' if blog_signals >= 3 else 'corporate'
        
        self.logger.info(f"  📝 Tipo sito rilevato: {site_type} (segnali: {blog_signals})")
        
        return site_type
    
    def _analyze_content_quality(self, homepage_data: Dict) -> Dict[str, Any]:
        """Analizza la qualità del contenuto."""
        word_count = homepage_data.get('word_count', 0)
        title = homepage_data.get('title', '')
        h1_list = homepage_data.get('headings', {}).get('h1', [])
        meta_desc = homepage_data.get('meta_description', '')
        url = homepage_data.get('url', '')
        content_text = homepage_data.get('content_text', '')
        
        title_words = set(title.lower().split())
        h1_words = set()
        for h1 in h1_list:
            h1_words.update(h1.lower().split())
        
        keyword_in_title = len(title_words) > 0
        keyword_in_h1 = len(h1_words) > 0
        keyword_in_url = any(word in url.lower() for word in title_words) if title_words else False
        
        keyword_density = 0.0
        if content_text and title_words:
            stop_words = {'il', 'lo', 'la', 'i', 'gli', 'le', 'un', 'uno', 'una', 'di', 'a', 'da', 'in', 'con', 'su', 'per', 'tra', 'fra', 'e', 'o', 'ma', 'che', 'non', 'è', 'sono', 'ha', 'hanno'}
            meaningful_words = [w for w in title_words if w not in stop_words and len(w) > 3]
            if meaningful_words:
                main_keyword = meaningful_words[0]
                content_words = content_text.lower().split()
                if content_words:
                    keyword_count = sum(1 for w in content_words if main_keyword in w)
                    keyword_density = (keyword_count / len(content_words)) * 100
        
        readability_score = 0
        if content_text:
            sentences = content_text.count('.') + content_text.count('!') + content_text.count('?')
            if sentences > 0:
                avg_sentence_length = word_count / sentences
                readability_score = max(0, min(100, 100 - (avg_sentence_length - 10) * 5))
        
        return {
            'word_count': word_count,
            'keyword_in_title': keyword_in_title,
            'keyword_in_h1': keyword_in_h1,
            'keyword_in_url': keyword_in_url,
            'keyword_density': round(keyword_density, 2),
            'readability_score': round(readability_score, 1),
            'title': title,
            'h1_count': len(h1_list),
            'meta_desc_length': len(meta_desc)
        }
    
    def _detect_doorway_pages(self, homepage_data: Dict) -> Dict[str, Any]:
        """Rileva potenziali doorway pages."""
        word_count = homepage_data.get('word_count', 0)
        robots_meta = homepage_data.get('robots_meta', '').lower()
        
        has_meta_refresh = 'refresh' in robots_meta or 'redirect' in robots_meta
        is_thin_content = word_count < 50
        
        doorway_signals = []
        if is_thin_content:
            doorway_signals.append('Contenuto molto breve')
        if has_meta_refresh:
            doorway_signals.append('Meta refresh/redirect')
        
        return {
            'is_doorway': len(doorway_signals) >= 2,
            'signals': doorway_signals,
            'word_count': word_count,
            'has_meta_refresh': has_meta_refresh
        }
    
    def _analyze_content_uniqueness(self, pages: List[Dict]) -> Dict[str, Any]:
        """Analizza l'unicità del contenuto tra pagine."""
        if not pages:
            return {'unique': True, 'duplicates': 0, 'total_pages': 0}
        
        contents = []
        for page in pages:
            word_count = page.get('word_count', 0)
            title = page.get('title', '')
            meta_desc = page.get('meta_description', '')
            
            fingerprint = f"{title}|{meta_desc}|{word_count}"
            contents.append({
                'url': page.get('url', ''),
                'fingerprint': fingerprint,
                'word_count': word_count
            })
        
        seen = {}
        duplicates = []
        for content in contents:
            fp = content['fingerprint']
            if fp in seen:
                duplicates.append({
                    'url1': seen[fp],
                    'url2': content['url'],
                    'type': 'similar_content'
                })
            else:
                seen[fp] = content['url']
        
        return {
            'unique': len(duplicates) == 0,
            'duplicates': len(duplicates),
            'total_pages': len(pages),
            'duplicate_list': duplicates[:5]
        }
    
    def _check_content_freshness(self, homepage_data: Dict) -> Dict[str, Any]:
        """Verifica quanto è aggiornato il contenuto."""
        return {
            'has_date': False,
            'publish_date': '',
            'modified_date': '',
            'note': 'Data non trovata'
        }
    
    # ============================================
    # METODI DI ANALISI STRUTTURA
    # ============================================
    
    def _detect_breadcrumbs(self, homepage_data):
        breadcrumbs = homepage_data.get('breadcrumbs', [])
        return {'present': len(breadcrumbs) > 0, 'count': len(breadcrumbs)}
    
    def _analyze_anchor_text(self, homepage_data):
        links = homepage_data.get('internal_links_with_text', [])
        generic = ['clicca qui', 'leggi di più', 'scopri', 'qui', 'link']
        generic_count = sum(1 for l in links if any(g in l.get('anchor', '').lower() for g in generic))
        return {'total_links': len(links), 'generic_anchors': generic_count}
    
    def _analyze_url_structure(self, homepage_data):
        links = homepage_data.get('internal_links', [])
        deep = sum(1 for l in links if len([p for p in urlparse(l).path.split('/') if p]) > 3)
        return {'total_links': len(links), 'deep_links': deep}
    
    def _analyze_logo(self, homepage_data):
        return homepage_data.get('logo', {'found': False})
    
    def _check_duplicate_content(self, pages):
        titles = {}
        duplicates = []
        for page in pages:
            title = page.get('title', '')
            url = page.get('url', '')
            if title:
                if title in titles:
                    duplicates.append({'type': 'title', 'value': title})
                else:
                    titles[title] = url
        return {'has_duplicates': len(duplicates) > 0, 'duplicate_count': len(duplicates)}
    
    def _analyze_css_js(self, homepage_data):
        return {
            'css_files_count': len(homepage_data.get('css_files', [])),
            'js_files_count': len(homepage_data.get('js_files', [])),
            'total_css_js': len(homepage_data.get('css_files', [])) + len(homepage_data.get('js_files', []))
        }
    
    def _analyze_site_structure(self, pages):
        if not pages:
            return {'levels': 0}
        depths = [len([p for p in urlparse(page.get('url', '')).path.split('/') if p]) for page in pages]
        return {'levels': max(depths) if depths else 0}
    
    def _check_cdn(self, homepage_data):
        server = homepage_data.get('response_headers', {}).get('Server', '').lower()
        cdn_providers = ['cloudflare', 'akamai', 'fastly', 'cdn']
        return {'has_cdn': any(p in server for p in cdn_providers), 'server': server}