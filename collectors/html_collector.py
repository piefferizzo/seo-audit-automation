import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import Dict, Any, List, Optional, Tuple, Callable
from collections import defaultdict
import re
import json
import time
from collectors.base_collector import BaseCollector
from utils.focus_keywords import FocusKeywordsManager


# ---------------------------------------------------------------------------
# COSTANTI — Configurazione crawler
# ---------------------------------------------------------------------------
DEFAULT_TIMEOUT = 45
MAX_RETRIES = 3
DEFAULT_MAX_PAGES = 50
DEFAULT_SLEEP_BETWEEN_PAGES = 0.5

USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

IMAGE_SKIP_PATTERNS = [
    r'^data:',
    r'linkedin\.com/collect',
    r'facebook\.com/tr',
    r'google-analytics\.com',
    r'googletagmanager\.com',
    r'px\.ads\.linkedin\.com',
    r'connect\.facebook\.net',
    r'analytics\.google\.com',
    r'secure\.gravatar\.com',
    r'www\.gravatar\.com',
    r'^https?://0[a-z]',
    r'pixel\.',
    r'tracking\.',
    r'beacon\.',
    r'placeholder\.',
    r'dummyimage\.com',
    r'via\.placeholder',
]

ITALIAN_STOP_WORDS = {
    'il', 'lo', 'la', 'i', 'gli', 'le', 'un', 'uno', 'una',
    'di', 'a', 'da', 'in', 'con', 'su', 'per', 'tra', 'fra',
    'e', 'o', 'ma', 'che', 'non', 'è', 'sono', 'ha', 'hanno',
    'del', 'della', 'dei', 'delle', 'degli', 'al', 'alla', 'ai',
    'alle', 'agli', 'dal', 'dalla', 'dai', 'dalle', 'dagli',
    'nel', 'nella', 'nei', 'nelle', 'negli', 'sul', 'sulla',
    'sui', 'sulle', 'sugli', 'come', 'più', 'meno', 'anche',
    'questo', 'questa', 'questi', 'queste', 'quello', 'quella',
    'si', 'ci', 'ne', 'mi', 'ti', 'vi', 'li',
    'essere', 'avere', 'fare', 'può', 'puo', 'sia',
    'the', 'and', 'or', 'of', 'to', 'in', 'is', 'it',
}


# ---------------------------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------------------------
def should_skip_image(url: str) -> bool:
    return any(re.search(p, url, re.IGNORECASE) for p in IMAGE_SKIP_PATTERNS)


def estimate_pixel_width(text: str, is_title: bool = True) -> int:
    if not text:
        return 0
    px_per_char = 8.5 if is_title else 6.8
    return int(len(text) * px_per_char)


def tokenize_keyword(keyword: str) -> List[str]:
    """Estrae i termini 'puliti' da una keyword.

    Esempi:
        "musei dell'olio italia" → ["musei", "dell", "olio", "italia"]
        "olive oil tourism"      → ["olive", "oil", "tourism"]
        "caffè letterario"       → ["caffè", "letterario"]
    """
    if not keyword:
        return []
    return re.findall(r'\w+', keyword.lower())


def soft_match_count(keyword_terms: List[str], text: str) -> int:
    """Conta quante occorrenze minime di TUTTI i termini della keyword
    sono presenti nel testo (soft match, ordine irrilevante).

    Esempio:
        keyword_terms = ["oleoturismo", "liguria"]
        text = "l'oleoturismo in Liguria è ... oleoturismo diffuso in Liguria"
        → ogni termine compare 2 volte → ritorna 2

    Ritorna 0 se almeno uno dei termini non è presente.
    """
    if not keyword_terms:
        return 0

    text_lower = text.lower()
    counts = []
    for term in keyword_terms:
        # Conteggio come parola intera (word boundary)
        c = len(re.findall(r'\b' + re.escape(term) + r'\b', text_lower))
        counts.append(c)

    if not counts:
        return 0

    return min(counts)


def compute_density(
    keyword: str,
    content_text: str,
    word_count: int = None,
) -> Tuple[float, int]:
    """Calcola density con approccio ibrido.

    Ritorna (density, keyword_word_count).

    Modalità:
      - keyword singola: conta parole che contengono il termine (substring)
      - keyword multi-parola:
          - prova prima match esatto (substring contigua)
          - poi soft match (tutti i termini presenti, ordine irrilevante)
          - usa il massimo

    La density è in percentuale e rappresenta la proporzione di "parole
    occupate" dalla keyword nel contenuto.
    """
    if not keyword or not content_text:
        return 0.0, 0

    if word_count is None:
        word_count = len(content_text.split())

    if word_count == 0:
        return 0.0, 0

    keyword_lower = keyword.lower()

    # --- Match esatto (substring contigua) ---
    if ' ' in keyword_lower:
        hard_count = content_text.lower().count(keyword_lower)
        hard_words = hard_count * len(keyword_lower.split())
    else:
        hard_words = sum(1 for w in content_text.lower().split() if keyword_lower in w)
        hard_count = hard_words

    # --- Soft match (tutti i termini presenti) ---
    terms = tokenize_keyword(keyword_lower)
    soft_count = soft_match_count(terms, content_text)
    soft_words = soft_count * len(terms) if terms else 0

    # Usa il massimo tra i due
    effective_words = max(hard_words, soft_words)
    density = (effective_words / word_count) * 100

    return round(density, 2), effective_words


class HTMLCollector(BaseCollector):
    """Crawler HTML avanzato con analisi multi-pagina per drill-down.

    v2.3.9 — modifiche:
    - Fix label C-05 (in audit_processor): "non calcolabile" → "0.00%".
    - Soft matching per la density: oltre al match esatto (substring),
      conta anche le occorrenze di tutti i termini separatamente
      (ordine irrilevante). Risolve i falsi 0.00% quando la keyword è
      "oleoturismo liguria" e il testo dice "l'oleoturismo in Liguria".
    - Title/H1 check con soft match: la keyword è considerata presente
      se tutti i suoi termini compaiono nel title/H1, indipendentemente
      dall'ordine.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.timeout = config.get('CRAWLER_TIMEOUT', DEFAULT_TIMEOUT)
        self.max_retries = MAX_RETRIES

        raw_max = config.get("MAX_PAGES_TO_CRAWL", DEFAULT_MAX_PAGES)
        if raw_max is None:
            self.max_pages = DEFAULT_MAX_PAGES
        elif raw_max <= 0:
            self.max_pages = None
        else:
            self.max_pages = int(raw_max)

        self.sleep_between_pages = config.get(
            'CRAWLER_SLEEP_BETWEEN_PAGES', DEFAULT_SLEEP_BETWEEN_PAGES
        )

        self.focus_keyword = (config.get('focus_keyword') or '').strip().lower()
        # Il manager viene (ri)istanziato in collect() perché ha bisogno
        # del dominio per selezionare la sezione corretta in file multi-dominio.
        self.focus_keywords_mgr = None
        self._focus_keywords_file = config.get('FOCUS_KEYWORDS_FILE', 'focus_keywords.yaml')

        self.headers = {
            'User-Agent': USER_AGENT,
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
                user_agent=USER_AGENT,
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
        self.logger.info(f"🔍 Crawling HTML avanzato per {domain}...")

        if not domain.startswith('http'):
            domain = f"https://{domain}"

        # Inizializza il FocusKeywordsManager per il dominio corrente
        # (necessario per file multi-dominio)
        self.focus_keywords_mgr = FocusKeywordsManager(
            self._focus_keywords_file,
            domain=domain,
        )
        self.focus_keywords_mgr.load()
        if self.focus_keywords_mgr.count > 0:
            self.logger.info(
                f"  📋 focus_keywords.yaml: {self.focus_keywords_mgr.count} keyword "
                f"mappate per {self.focus_keywords_mgr.domain}"
            )
        else:
            self.logger.debug(
                f"  📋 Nessuna keyword trovata per {self.focus_keywords_mgr.domain} "
                f"in {self._focus_keywords_file}"
            )

        results = {}

        try:
            homepage_data = self._crawl_page(domain)

            if homepage_data.get('error') and self.playwright_available:
                self.logger.info(f"🔄 Uso Playwright per homepage...")
                homepage_data = self._crawl_page_with_playwright(domain)

            results['homepage'] = homepage_data

            results['robots'] = self._check_robots(domain)
            results['sitemap'] = {'exists': False, 'url': f"{domain}/sitemap.xml"}
            results['404'] = self._check_404(domain)
            results['redirect'] = self._check_redirect(domain)

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

            self.logger.info(f"  📋 Raccolta URL per drill-down...")
            all_urls = self._collect_urls_from_sitemap(domain, homepage_data, results['robots'])

            robots_sitemap_url = results['robots'].get('sitemap_url', '')
            urls_from_sitemap = [u for u in all_urls if u.rstrip('/') != domain.rstrip('/')]

            if robots_sitemap_url and urls_from_sitemap:
                results['sitemap'] = {
                    'exists': True,
                    'url': robots_sitemap_url,
                    'found_via': 'robots',
                    'url_count': len(urls_from_sitemap),
                    'status_code': 200,
                    'is_valid_xml': True,
                }
                self.logger.debug(
                    f"  ✓ Sitemap confermata via robots.txt: {robots_sitemap_url} "
                    f"({len(urls_from_sitemap)} URL)"
                )
            elif urls_from_sitemap:
                found_url = f"{domain}/sitemap.xml"
                results['sitemap'] = {
                    'exists': True,
                    'url': found_url,
                    'found_via': 'discovery',
                    'url_count': len(urls_from_sitemap),
                    'status_code': 200,
                    'is_valid_xml': True,
                }
                self.logger.debug(
                    f"  ✓ Sitemap trovata via discovery: {found_url} "
                    f"({len(urls_from_sitemap)} URL)"
                )
            else:
                results['sitemap'] = {
                    'exists': False,
                    'url': f"{domain}/sitemap.xml",
                    'found_via': 'none',
                    'url_count': 0,
                }
                self.logger.debug(f"  ⚠️  Nessuna sitemap trovata")

            self.logger.debug(f"  📊 URL totali trovate: {len(all_urls)}")

            if self.max_pages is None:
                urls_to_crawl = all_urls
                self.logger.info(f"  🎯 URL da analizzare (nessun limite): {len(urls_to_crawl)}")
            else:
                urls_to_crawl = all_urls[:self.max_pages]
                self.logger.info(f"  🎯 URL da analizzare (limite {self.max_pages}): {len(urls_to_crawl)}")

            if urls_to_crawl:
                self.logger.info(f"  🔍 Avvio crawling drill-down...")
                drilldown_data = self._crawl_pages_for_drilldown(urls_to_crawl)
                results['drilldown'] = drilldown_data

                self.logger.debug(f"  ✅ Drill-down completato:")
                self.logger.debug(f"    - Pagine analizzate: {len(drilldown_data.get('pages_analyzed', []))}")
                self.logger.debug(f"    - Problemi immagini: {len(drilldown_data.get('images_problems', []))}")
                self.logger.debug(f"    - Problemi title: {len(drilldown_data.get('title_problems', []))}")
                self.logger.debug(f"    - Problemi description: {len(drilldown_data.get('description_problems', []))}")
                self.logger.debug(f"    - Problemi headings: {len(drilldown_data.get('headings_problems', []))}")
                self.logger.debug(f"    - Problemi focus keyword: {len(drilldown_data.get('focus_keyword_problems', []))}")
            else:
                self.logger.warning(f"  ⚠️  Nessuna URL trovata per drill-down!")
                results['drilldown'] = {
                    'pages_analyzed': [],
                    'images_problems': [],
                    'title_problems': [],
                    'description_problems': [],
                    'headings_problems': [],
                    'focus_keyword_problems': [],
                }

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

            results['breadcrumbs'] = self._detect_breadcrumbs(homepage_data)
            results['anchor_text'] = self._analyze_anchor_text(homepage_data)
            results['url_structure'] = self._analyze_url_structure(homepage_data)
            results['logo'] = self._analyze_logo(homepage_data)
            results['duplicate_content'] = self._check_duplicate_content(results.get('internal_pages', []))
            results['css_js_analysis'] = self._analyze_css_js(homepage_data)
            results['site_structure'] = self._analyze_site_structure(results.get('internal_pages', []))
            results['cdn_check'] = self._check_cdn(homepage_data)
            results['image_dimensions'] = self._analyze_image_dimensions(homepage_data)
            results['favicon'] = self._check_favicon(homepage_data, domain)

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
    # CRAWLING BASE
    # ============================================

    def _crawl_page_with_playwright(self, url: str) -> Dict[str, Any]:
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
                    self.logger.debug(f"  ↻ Retry {attempt + 2}/{self.max_retries} per {url}: {str(e)[:80]}")
                    time.sleep(1.5)
                    continue
                return {'url': url, 'error': str(e)[:100]}

    def _extract_page_data(self, soup: BeautifulSoup, url: str, final_url: str, headers: Dict) -> Dict[str, Any]:
        css_files = self._get_css_files(soup, url)
        js_files = self._get_js_files(soup, url)

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
            'css_files': css_files,
            'js_files': js_files,
            'favicon_links': self._get_favicon_links(soup, url),
            'content_text': content_text,
            'raw_html': str(soup)[:200000],
        }

    # ============================================
    # ESTRAZIONE DATI
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
        css_files = []
        for link in soup.find_all('link', rel='stylesheet'):
            href = link.get('href')
            if href:
                full_url = urljoin(base_url, href)
                if full_url not in css_files:
                    css_files.append(full_url)
        for link in soup.find_all('link', type='text/css'):
            href = link.get('href')
            if href:
                full_url = urljoin(base_url, href)
                if full_url not in css_files:
                    css_files.append(full_url)
        for link in soup.find_all('link'):
            rel = link.get('rel', [])
            rel_str = ' '.join(rel).lower() if isinstance(rel, list) else str(rel).lower()
            if 'stylesheet' in rel_str:
                href = link.get('href')
                if href:
                    full_url = urljoin(base_url, href)
                    if full_url not in css_files:
                        css_files.append(full_url)
        for style in soup.find_all('style', src=True):
            src = style.get('src')
            if src:
                full_url = urljoin(base_url, src)
                if full_url not in css_files:
                    css_files.append(full_url)
        for link in soup.find_all('link'):
            href = link.get('href', '')
            if href and href.lower().endswith('.css'):
                full_url = urljoin(base_url, href)
                if full_url not in css_files:
                    css_files.append(full_url)
        self.logger.debug(f"  🎨 CSS files trovati: {len(css_files)}")
        return css_files

    def _get_js_files(self, soup, base_url):
        js_files = []
        for script in soup.find_all('script', src=True):
            src = script.get('src')
            if src:
                full_url = urljoin(base_url, src)
                if full_url not in js_files:
                    js_files.append(full_url)
        for script in soup.find_all('script', type='text/javascript'):
            src = script.get('src')
            if src:
                full_url = urljoin(base_url, src)
                if full_url not in js_files:
                    js_files.append(full_url)
        for script in soup.find_all('script', type='module'):
            src = script.get('src')
            if src:
                full_url = urljoin(base_url, src)
                if full_url not in js_files:
                    js_files.append(full_url)
        for script in soup.find_all('script'):
            src = script.get('src', '')
            if src and src.lower().endswith('.js'):
                full_url = urljoin(base_url, src)
                if full_url not in js_files:
                    js_files.append(full_url)
        for script in soup.find_all('script', type='application/javascript'):
            src = script.get('src')
            if src:
                full_url = urljoin(base_url, src)
                if full_url not in js_files:
                    js_files.append(full_url)
        self.logger.debug(f"  📜 JS files trovati: {len(js_files)}")
        return js_files

    def _get_favicon_links(self, soup, base_url):
        favicons = []
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
    # VERIFICA BASE
    # ============================================

    def _check_robots(self, domain):
        try:
            response = self.session.get(f"{domain}/robots.txt", timeout=10)
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
            response = self.session.get(f"{domain}/test-404-page-xyz123", timeout=10, allow_redirects=False)
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
    # SITEMAP
    # ============================================

    def _collect_urls_from_sitemap(self, domain: str, homepage_data: Dict, robots_data: Dict) -> List[str]:
        urls = set()
        urls.add(domain.rstrip('/'))

        sitemap_url = robots_data.get('sitemap_url', '')

        if sitemap_url:
            self.logger.info(f"  📖 Tentativo download sitemap da robots.txt: {sitemap_url}")
            sitemap_urls = self._download_and_parse_sitemap(sitemap_url)
            if sitemap_urls:
                self.logger.info(f"  ✓ Trovate {len(sitemap_urls)} URL dalla sitemap (robots.txt)")
                urls.update(sitemap_urls)
            else:
                self.logger.warning(f"  ⚠️  Sitemap da robots.txt non parsabile, provo URL comuni...")

        if not sitemap_url or len(urls) <= 1:
            self.logger.info(f"  🔍 Provo URL sitemap comuni...")
            for candidate in [
                f"{domain}/sitemap.xml",
                f"{domain}/sitemap_index.xml",
                f"{domain}/wp-sitemap.xml",
                f"{domain}/sitemap/sitemap.xml",
                f"{domain}/sitemap-index.xml"
            ]:
                sitemap_urls = self._download_and_parse_sitemap(candidate)
                if sitemap_urls:
                    self.logger.info(f"    ✓ Trovate {len(sitemap_urls)} URL da {candidate}")
                    urls.update(sitemap_urls)
                    break

        internal_links = homepage_data.get('internal_links', [])
        for link in internal_links:
            clean_link = link.split('#')[0]
            if clean_link:
                urls.add(clean_link)

        self.logger.debug(f"  📊 Totale URL uniche raccolte: {len(urls)}")
        return list(urls)

    def _download_and_parse_sitemap(self, sitemap_url: str) -> List[str]:
        try:
            response = self.session.get(sitemap_url, timeout=15)
            if response.status_code != 200:
                return []
            return self._parse_sitemap_content(response.text, sitemap_url)
        except Exception as e:
            self.logger.warning(f"  ⚠️  Errore download sitemap: {e}")
            return []

    def _parse_sitemap_content(self, content: str, base_url: str) -> List[str]:
        urls = []
        try:
            if '<sitemapindex' in content:
                sub_sitemaps = re.findall(r'<loc>(.*?)</loc>', content)
                for sub_url in sub_sitemaps:
                    sub_urls = self._download_and_parse_sitemap(sub_url.strip())
                    urls.extend(sub_urls)
            elif '<urlset' in content:
                found_urls = re.findall(r'<loc>(.*?)</loc>', content)
                urls.extend([u.strip() for u in found_urls])
            else:
                found_urls = re.findall(r'<loc>(.*?)</loc>', content)
                if found_urls:
                    urls.extend([u.strip() for u in found_urls])
        except Exception as e:
            self.logger.error(f"    ✗ Errore parsing sitemap: {e}")
        return urls

    # ============================================
    # DRILL-DOWN
    # ============================================

    def _crawl_pages_for_drilldown(self, urls: List[str]) -> Dict[str, Any]:
        drilldown = {
            'pages_analyzed': [],
            'images_problems': [],
            'title_problems': [],
            'description_problems': [],
            'headings_problems': [],
            'focus_keyword_problems': [],
        }

        total = len(urls)
        success_count = 0
        error_count = 0
        start_ts = time.time()

        for i, url in enumerate(urls, 1):
            if i % 10 == 0 or i == 1:
                elapsed = time.time() - start_ts
                rate = i / elapsed if elapsed > 0 else 0
                eta = (total - i) / rate if rate > 0 else 0
                self.logger.info(
                    f"  📊 Analisi drill-down: {i}/{total} pagine "
                    f"({elapsed:.0f}s, ETA {eta:.0f}s)"
                )

            try:
                page_info = self._analyze_page_deep(url)
                if page_info:
                    drilldown['pages_analyzed'].append(page_info)
                    success_count += 1
                    drilldown['images_problems'].extend(page_info.get('image_problems', []))
                    drilldown['title_problems'].extend(page_info.get('title_problems', []))
                    drilldown['description_problems'].extend(page_info.get('description_problems', []))
                    drilldown['headings_problems'].extend(page_info.get('headings_problems', []))
                    drilldown['focus_keyword_problems'].extend(page_info.get('focus_keyword_problems', []))
                else:
                    error_count += 1

                time.sleep(self.sleep_between_pages)
            except Exception as e:
                self.logger.warning(f"  ⚠️  Errore analisi {url}: {e}")
                error_count += 1

        duration = time.time() - start_ts
        self.logger.info(
            f"  ✅ Drill-down completato: {success_count} successi, "
            f"{error_count} errori in {duration:.0f}s"
        )
        return drilldown

    def _analyze_page_deep(self, url: str) -> Dict[str, Any]:
        try:
            response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            if response.status_code != 200:
                return None

            soup = BeautifulSoup(response.text, 'html.parser')

            return {
                'url': url,
                'status_code': response.status_code,
                'title_problems': self._analyze_title_deep(soup, url),
                'description_problems': self._analyze_description_deep(soup, url),
                'headings_problems': self._analyze_headings_deep(soup, url),
                'image_problems': self._analyze_images_deep(soup, url),
                'focus_keyword_problems': self._analyze_focus_keyword_deep(soup, url),
            }
        except Exception as e:
            self.logger.warning(f"Errore analisi profonda {url}: {e}")
            return None

    # ------------------------------------------------------------------
    # Focus keyword per URL (v2.3.9 con soft matching)
    # ------------------------------------------------------------------

    def _analyze_focus_keyword_deep(self, soup: BeautifulSoup, url: str) -> List[Dict]:
        """Verifica che la keyword assegnata all'URL sia ottimizzata.

        v2.3.9 — soft matching:
          - La keyword è considerata "nel title/H1" se TUTTI i suoi termini
            sono presenti (ordine irrilevante).
          - La density usa il massimo tra match esatto e soft match.
        """
        fk_data = self.focus_keywords_mgr.get_for_url(url)
        if not fk_data:
            return []

        primary = (fk_data.get('primary') or '').strip().lower()
        if not primary:
            return []

        problems = []

        # Estrai testo dal contenuto (senza script/style/nav/footer)
        content_soup = BeautifulSoup(str(soup), 'html.parser')
        for elem in content_soup(['script', 'style', 'nav', 'footer', 'header']):
            elem.decompose()
        content_text = content_soup.get_text(separator=' ', strip=True).lower()
        word_count = len(content_text.split())

        # Calcola density con soft matching
        density, _ = compute_density(primary, content_text, word_count)

        # Title e H1 con soft match
        title_tag = soup.find('title')
        title_text = title_tag.get_text().strip().lower() if title_tag else ''

        h1_tags = soup.find_all('h1')
        h1_text = ' '.join(h.get_text().strip().lower() for h in h1_tags)

        # Termini della keyword
        terms = tokenize_keyword(primary)

        # Keyword presente se tutti i termini sono presenti (soft match)
        def is_present(text: str, terms: List[str]) -> bool:
            if not terms:
                return False
            text_lower = text.lower()
            return all(
                re.search(r'\b' + re.escape(t) + r'\b', text_lower) is not None
                for t in terms
            )

        kw_in_title = is_present(title_text, terms)
        kw_in_h1 = is_present(h1_text, terms)

        # ----- Valutazione -----
        opts = self.focus_keywords_mgr.options
        min_d = opts.get('min_density', 0.8)
        max_d = opts.get('max_density', 3.5)
        check_title = opts.get('check_title', True)
        check_h1 = opts.get('check_h1', True)

        if check_title and not kw_in_title:
            problems.append({
                'url': url,
                'focus_keyword': primary,
                'problem': 'Keyword non presente nel title',
            })

        if check_h1 and not kw_in_h1:
            problems.append({
                'url': url,
                'focus_keyword': primary,
                'problem': 'Keyword non presente nell\'H1',
            })

        if density < min_d:
            problems.append({
                'url': url,
                'focus_keyword': primary,
                'problem': f'Density bassa ({density:.2f}%, min {min_d}%)',
            })
        elif density > max_d:
            problems.append({
                'url': url,
                'focus_keyword': primary,
                'problem': f'Density alta ({density:.2f}%, max {max_d}%)',
            })

        return problems

    def _analyze_title_deep(self, soup, url):
        problems = []
        title_tag = soup.find('title')

        if not title_tag:
            problems.append({'url': url, 'meta_title': '[MANCANTE]', 'problem': 'Title assente'})
            return problems

        title_text = title_tag.get_text().strip()
        char_count = len(title_text)
        pixel_width = estimate_pixel_width(title_text, is_title=True)

        if char_count > 60:
            problems.append({'url': url, 'meta_title': title_text, 'problem': f'Oltre 60 caratteri ({char_count})'})
        elif char_count < 30:
            problems.append({'url': url, 'meta_title': title_text, 'problem': f'Sotto 30 caratteri ({char_count})'})

        if pixel_width > 561:
            problems.append({'url': url, 'meta_title': title_text, 'problem': f'Oltre 561px ({pixel_width}px)'})
        elif pixel_width < 200 and char_count > 0:
            problems.append({'url': url, 'meta_title': title_text, 'problem': f'Sotto 200px ({pixel_width}px)'})

        return problems

    def _analyze_description_deep(self, soup, url):
        problems = []
        meta = soup.find('meta', attrs={'name': 'description'})

        if not meta or not meta.get('content'):
            problems.append({'url': url, 'meta_description': '[MANCANTE]', 'problem': 'Description assente'})
            return problems

        desc_text = meta.get('content', '').strip()
        char_count = len(desc_text)
        pixel_width = estimate_pixel_width(desc_text, is_title=False)

        if char_count > 155:
            problems.append({'url': url, 'meta_description': desc_text, 'problem': f'Oltre 155 caratteri ({char_count})'})
        elif char_count < 70:
            problems.append({'url': url, 'meta_description': desc_text, 'problem': f'Sotto 70 caratteri ({char_count})'})

        if pixel_width > 995:
            problems.append({'url': url, 'meta_description': desc_text, 'problem': f'Oltre 995px ({pixel_width}px)'})
        elif pixel_width < 40 and char_count > 0:
            problems.append({'url': url, 'meta_description': desc_text, 'problem': f'Sotto 40 caratteri ({pixel_width}px)'})

        return problems

    def _analyze_headings_deep(self, soup, url):
        problems = []
        h1_tags = soup.find_all('h1')
        h1_list = [h.get_text().strip() for h in h1_tags if h.get_text().strip()]

        h1_1 = h1_list[0] if len(h1_list) > 0 else ''
        h1_2 = h1_list[1] if len(h1_list) > 1 else ''

        problem_list = []

        if len(h1_list) == 0:
            problem_list.append('Assente')
        if len(h1_list) > 1:
            problem_list.append('Multiplo')

        for h1 in h1_list:
            if len(h1) > 70:
                problem_list.append(f'Oltre 70 caratteri ({len(h1)})')
                break

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

    def _analyze_images_deep(self, soup, url):
        problems = []
        seen_urls = set()
        skipped_count = 0

        domain_base = urlparse(url).netloc

        for img in soup.find_all('img'):
            src = img.get('src', '')
            if not src:
                continue

            full_src = urljoin(url, src)

            if full_src in seen_urls:
                continue
            seen_urls.add(full_src)

            if should_skip_image(full_src):
                skipped_count += 1
                continue

            img_domain = urlparse(full_src).netloc
            if img_domain and img_domain != domain_base:
                if not any(cdn in img_domain for cdn in ['cdn', 'media', 'static', 'images', 'img']):
                    if not img_domain.endswith(domain_base.replace('www.', '')):
                        skipped_count += 1
                        continue

            alt = img.get('alt', '')
            width = img.get('width')
            height = img.get('height')

            if not alt or alt.strip() == '':
                problems.append({'url': full_src, 'problem': 'Testo alt mancante'})

            if not width or not height:
                problems.append({'url': full_src, 'problem': 'Attributi di dimensione mancanti'})

            img_size_kb = self._get_image_size_kb(full_src)
            if img_size_kb is not None and img_size_kb > 100:
                problems.append({'url': full_src, 'problem': f'Oltre 100 kb ({img_size_kb:.1f} kb)'})

        if skipped_count > 0:
            self.logger.debug(f"  🎯 Filtrate {skipped_count} immagini non pertinenti")

        return problems

    def _get_image_size_kb(self, image_url: str) -> Optional[float]:
        try:
            response = self.session.head(image_url, timeout=5, allow_redirects=True)
            if response.status_code == 200:
                content_length = response.headers.get('content-length')
                if content_length:
                    return int(content_length) / 1024
        except:
            pass
        return None

    # ============================================
    # ANALISI TECNICA AVANZATA
    # ============================================

    def _check_www_redirect(self, domain: str) -> Dict[str, Any]:
        clean_domain = domain.replace('https://', '').replace('http://', '').replace('www.', '')
        results = {'www_to_non_www': None, 'non_www_to_www': None, 'consistent': False}

        try:
            response = self.session.get(f"https://www.{clean_domain}", timeout=10, allow_redirects=False)
            if response.status_code in [301, 302]:
                location = response.headers.get('Location', '')
                results['www_to_non_www'] = {
                    'redirects': True, 'status': response.status_code,
                    'location': location, 'correct': not location.startswith('https://www.')
                }

            response = self.session.get(f"https://{clean_domain}", timeout=10, allow_redirects=False)
            if response.status_code in [301, 302]:
                location = response.headers.get('Location', '')
                results['non_www_to_www'] = {
                    'redirects': True, 'status': response.status_code,
                    'location': location, 'correct': location.startswith('https://www.')
                }

            if results['www_to_non_www'] or results['non_www_to_www']:
                results['consistent'] = True
        except Exception as e:
            self.logger.warning(f"Errore check www redirect: {e}")

        return results

    def _check_mixed_content(self, homepage_data: Dict) -> Dict[str, Any]:
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
        css_files = homepage_data.get('css_files', [])
        return {
            'total_css_files': len(css_files),
            'external_css': len(css_files),
            'inline_css': 0,
            'too_many_files': len(css_files) > 10,
            'recommendation': 'Combinare e minificare CSS' if len(css_files) > 5 else 'OK'
        }

    def _analyze_js_issues(self, homepage_data: Dict) -> Dict[str, Any]:
        js_files = homepage_data.get('js_files', [])
        return {
            'total_js_files': len(js_files),
            'external_js': len(js_files),
            'inline_js': 0,
            'too_many_files': len(js_files) > 10,
            'recommendation': 'Deferire o async JS' if len(js_files) > 5 else 'OK'
        }

    def _check_pagination_advanced(self, homepage_data: Dict) -> Dict[str, Any]:
        return {
            'has_pagination': False,
            'has_rel_next': False,
            'has_rel_prev': False,
            'note': 'Analisi pagination avanzata richiede crawling completo'
        }

    def _detect_subdomains(self, homepage_data: Dict, domain: str) -> Dict[str, Any]:
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
        favicon_links = homepage_data.get('favicon_links', [])

        result = {
            'has_favicon': False,
            'favicon_urls': [],
            'types': [],
            'has_apple_touch': False,
            'has_manifest': False,
            'default_favicon_exists': False
        }

        for fav in favicon_links:
            href = fav.get('href', '')
            rel = fav.get('rel', '').lower()
            fav_type = fav.get('type', '').lower()

            result['favicon_urls'].append(href)

            if 'apple-touch' in rel:
                result['has_apple_touch'] = True
            if 'manifest' in rel:
                result['has_manifest'] = True

            if 'svg' in fav_type or href.endswith('.svg'):
                result['types'].append('svg')
            elif 'png' in fav_type or href.endswith('.png'):
                result['types'].append('png')
            elif 'ico' in fav_type or href.endswith('.ico'):
                result['types'].append('ico')

        try:
            default_url = f"{domain.rstrip('/')}/favicon.ico"
            response = self.session.head(default_url, timeout=5, allow_redirects=True)
            if response.status_code == 200:
                result['default_favicon_exists'] = True
                if default_url not in result['favicon_urls']:
                    result['favicon_urls'].append(default_url)
        except:
            pass

        result['has_favicon'] = len(result['favicon_urls']) > 0 or result['default_favicon_exists']
        result['types'] = list(set(result['types']))
        return result

    # ============================================
    # ANALISI CONTENUTI
    # ============================================

    def _detect_site_type(self, homepage_data: Dict) -> str:
        blog_signals = 0
        content_text = homepage_data.get('content_text', '').lower()
        raw_html = homepage_data.get('raw_html', '').lower()

        if '<article' in raw_html:
            blog_signals += 2

        blog_patterns = [
            'posted on', 'published', 'by', 'categories:', 'tags:',
            'leave a comment', 'related posts', 'recent posts',
            'pubblicato il', 'categorie:', 'tag:', 'commenti',
        ]
        for pattern in blog_patterns:
            if pattern in content_text:
                blog_signals += 1

        if 'article:published_time' in raw_html or 'datepublished' in raw_html:
            blog_signals += 2

        url = homepage_data.get('url', '')
        if any(x in url for x in ['/blog/', '/news/', '/articles/', '/post/']):
            blog_signals += 2

        site_type = 'blog_news' if blog_signals >= 3 else 'corporate'
        self.logger.debug(f"  📝 Tipo sito rilevato: {site_type} (segnali: {blog_signals})")
        return site_type

    def _analyze_content_quality(self, homepage_data: Dict) -> Dict[str, Any]:
        """Analizza la qualità del contenuto (v2.3.9 con soft matching).

        - La keyword è scelta: focus_keywords.yaml → config → euristica.
        - keyword_in_title / keyword_in_h1 usano soft match (tutti i termini).
        - La density usa il massimo tra match esatto e soft match.
        """
        word_count = homepage_data.get('word_count', 0)
        title = homepage_data.get('title', '')
        h1_list = homepage_data.get('headings', {}).get('h1', [])
        meta_desc = homepage_data.get('meta_description', '')
        url = homepage_data.get('url', '')
        content_text = homepage_data.get('content_text', '')

        # Sceglie la keyword
        main_keyword, is_from_config = self._pick_main_keyword(url, title, h1_list)

        # Termini della keyword per soft match
        terms = tokenize_keyword(main_keyword) if main_keyword else []

        def is_present(text: str, terms: List[str]) -> bool:
            if not terms:
                return False
            text_lower = text.lower()
            return all(
                re.search(r'\b' + re.escape(t) + r'\b', text_lower) is not None
                for t in terms
            )

        # keyword_in_title / keyword_in_h1 con soft match
        if main_keyword:
            keyword_in_title = is_present(title, terms)
            keyword_in_h1 = any(is_present(h, terms) for h in h1_list)
            keyword_in_url = is_present(url, terms)
        else:
            # Fallback: vecchio comportamento (qualche parola del title)
            title_words_set = set(title.lower().split())
            h1_words_set = set()
            for h1 in h1_list:
                h1_words_set.update(h1.lower().split())
            keyword_in_title = len(title_words_set) > 0
            keyword_in_h1 = len(h1_words_set) > 0
            keyword_in_url = any(word in url.lower() for word in title_words_set) if title_words_set else False

        # Density con soft match
        density, _ = compute_density(main_keyword, content_text, word_count)

        # Readability
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
            'focus_keyword': main_keyword,
            'is_from_config': is_from_config,
            'keyword_density': round(density, 2),
            'readability_score': round(readability_score, 1),
            'title': title,
            'h1_count': len(h1_list),
            'meta_desc_length': len(meta_desc)
        }

    def _pick_main_keyword(self, url: str, title: str, h1_list: List[str]) -> Tuple[str, bool]:
        """Sceglie la keyword principale in modo deterministico.

        Ritorna (keyword, is_from_config):
          - is_from_config=True  → keyword da focus_keywords.yaml
          - is_from_config=False → keyword da config globale o euristica
        """
        # Priorità 1: focus_keywords.yaml (per-URL)
        explicit_per_url = self.focus_keywords_mgr.get_primary(url)
        if explicit_per_url:
            self.logger.debug(f"  🎯 Keyword da focus_keywords.yaml per {url}: '{explicit_per_url}'")
            return explicit_per_url.lower(), True

        # Priorità 2: focus_keyword globale da config
        if self.focus_keyword:
            return self.focus_keyword, False

        # Priorità 3: euristica (prima parola meaningful del title)
        if title:
            title_words_list = title.lower().split()
            for w in title_words_list:
                clean = re.sub(r'[^\wàèéìòù]', '', w)
                if clean and len(clean) > 3 and clean not in ITALIAN_STOP_WORDS:
                    self.logger.debug(f"  🎯 Keyword euristica (title): '{clean}'")
                    return clean, False

        # Priorità 4: prima parola meaningful del primo H1
        if h1_list:
            first_h1_words = h1_list[0].lower().split()
            for w in first_h1_words:
                clean = re.sub(r'[^\wàèéìòù]', '', w)
                if clean and len(clean) > 3 and clean not in ITALIAN_STOP_WORDS:
                    self.logger.debug(f"  🎯 Keyword euristica (H1): '{clean}'")
                    return clean, False

        return "", False

    def _detect_doorway_pages(self, homepage_data: Dict) -> Dict[str, Any]:
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
        return {
            'has_date': False,
            'publish_date': '',
            'modified_date': '',
            'note': 'Data non trovata'
        }

    # ============================================
    # ANALISI STRUTTURA
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