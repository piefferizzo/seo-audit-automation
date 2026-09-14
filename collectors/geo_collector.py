import json
import re
from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup
from collectors.base_collector import BaseCollector

import requests


# ---------------------------------------------------------------------------
# COSTANTI — Configurazione GEO/AEO
# ---------------------------------------------------------------------------
# Tipi di schema raccomandati per GEO/AEO con campi obbligatori
RECOMMENDED_SCHEMAS = {
    'Organization': ['name', 'url', 'logo', 'contactPoint'],
    'Article': ['headline', 'author', 'datePublished', 'description'],
    'FAQPage': ['mainEntity'],
    'Product': ['name', 'description', 'brand', 'offers'],
    'LocalBusiness': ['name', 'address', 'telephone', 'openingHours'],
    'BreadcrumbList': ['itemListElement'],
    'WebSite': ['name', 'url', 'potentialAction'],
    'HowTo': ['name', 'step'],
    'Review': ['itemReviewed', 'reviewRating', 'author'],
}

# Requisiti per snippet AI (ChatGPT, Perplexity, AI Overviews)
AI_SNIPPET_REQUIREMENTS = {
    'direct_answer': {
        'min_words': 40,
        'max_words': 60,
        'position': 'first_paragraph',
    },
    'faq_format': {
        'question_pattern': r'^(chi|cosa|come|perché|quando|dove|quanto|quale)',
        'answer_min_words': 30,
    },
    'list_format': {
        'min_items': 3,
        'max_items': 10,
    }
}

# Pattern per rilevare risposte dirette
DIRECT_ANSWER_PATTERNS = [
    r'(in breve|riassumendo|per riassumere|conclusione)',
    r'(la risposta è|il risultato è|la soluzione è)',
    r'(ecco come|ecco perché|ecco cosa)',
    r'(il segreto è|la chiave è)',
]

# Pattern per rilevare formato FAQ
FAQ_PATTERNS = [
    r'(domande frequenti|faq)',
    r'(chi|cosa|come|perché|quando|dove|quanto|quale)\s+\w+\s+\w+\?',
]

# Pattern per rilevare liste
LIST_INDICATORS = ['•', '-', '1.', '2.', '3.', '4.', '5.']


# ---------------------------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------------------------
def extract_structured_data(soup: BeautifulSoup) -> List[Dict]:
    """Estrae tutti i dati strutturati JSON-LD dalla pagina.

    FIX: gestisce esplicitamente il wrapper '@graph' usato da Yoast SEO,
    RankMath e altri plugin WordPress. Senza questo fix, l'intero wrapper
    veniva trattato come un singolo schema senza @type, e la completezza
    risultava sempre 0.
    """
    schemas: List[Dict] = []

    for script in soup.find_all('script', type='application/ld+json'):
        raw = script.string or ''
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue

        # Normalizza in una lista di schemi
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    schemas.append(item)
        elif isinstance(data, dict):
            # Wrapper @graph (Yoast, RankMath)
            graph = data.get('@graph')
            if isinstance(graph, list):
                for item in graph:
                    if isinstance(item, dict):
                        schemas.append(item)
            else:
                schemas.append(data)

    return schemas


def extract_main_content(soup: BeautifulSoup) -> str:
    """Estrae il contenuto principale della pagina."""
    # Rimuovi elementi non rilevanti
    content_soup = BeautifulSoup(str(soup), 'html.parser')
    for elem in content_soup(['script', 'style', 'nav', 'footer', 'header', 'aside']):
        elem.decompose()

    # Prova a trovare il contenuto principale
    main_content = content_soup.find('main') or content_soup.find('article') or content_soup.find('body')
    if main_content:
        return main_content.get_text(separator=' ', strip=True)
    return content_soup.get_text(separator=' ', strip=True)


def count_list_items(content: str) -> int:
    """Conta gli elementi di lista nel contenuto."""
    count = 0
    for indicator in LIST_INDICATORS:
        count += content.count(indicator)
    return count


def calculate_sentence_stats(content: str) -> Dict[str, float]:
    """Calcola statistiche sulle frasi del contenuto."""
    sentences = re.split(r'[.!?]', content)
    sentences = [s for s in sentences if s.strip()]

    if not sentences:
        return {
            'count': 0,
            'avg_length': 0,
            'min_length': 0,
            'max_length': 0,
        }

    lengths = [len(s.split()) for s in sentences]

    return {
        'count': len(sentences),
        'avg_length': sum(lengths) / len(lengths),
        'min_length': min(lengths),
        'max_length': max(lengths),
    }


class GEOCollector(BaseCollector):
    """Collector per Generative Engine Optimization (GEO) e Answer Engine Optimization (AEO)."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.timeout = config.get('CRAWLER_TIMEOUT', 30)

    def is_available(self) -> bool:
        """Il collector GEO è sempre disponibile."""
        return True

    def collect(self, domain: str) -> Dict[str, Any]:
        """Raccoglie dati GEO/AEO per il dominio."""
        self.logger.info(f"🔍 Analisi GEO/AEO per {domain}...")

        # Crawla la homepage
        html_data = self._crawl_homepage(domain)
        if not html_data:
            self.logger.warning(f"  ⚠️  Impossibile crawlare {domain}")
            return {}

        results = {
            'schema_validation': self._validate_schema_markup(html_data),
            'ai_readability': self._analyze_ai_readability(html_data),
            'citation_potential': self._evaluate_citation_potential(html_data),
            'content_structure': self._analyze_content_structure(html_data),
        }

        self.logger.info(f"  ✓ Analisi GEO/AEO completata")

        return results

    def _crawl_homepage(self, domain: str) -> Optional[Dict[str, Any]]:
        """Crawla la homepage per l'analisi GEO."""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            }

            response = requests.get(domain, headers=headers, timeout=self.timeout)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            return {
                'url': domain,
                'html': response.text,
                'soup': soup,
                'structured_data': extract_structured_data(soup),
                'content': extract_main_content(soup),
                'title': self._get_text(soup.find('title')),
                'h1_list': [h.get_text().strip() for h in soup.find_all('h1') if h.get_text().strip()],
            }
        except Exception as e:
            self.logger.error(f"Errore crawling homepage: {e}")
            return None

    def _get_text(self, tag) -> str:
        """Estrae testo da un tag BeautifulSoup."""
        return tag.get_text().strip() if tag else ""

    def _validate_schema_markup(self, html_data: Dict) -> Dict[str, Any]:
        """Valida la completezza dei dati strutturati."""
        schemas = html_data.get('structured_data', [])

        validation_results = {
            'total_schemas': len(schemas),
            'schema_types': [],
            'completeness_score': 0,
            'missing_fields': [],
            'recommendations': [],
        }

        if not schemas:
            validation_results['recommendations'].append(
                "Nessun dato strutturato trovato. Implementare JSON-LD per Organization, Article, FAQPage."
            )
            return validation_results

        # Analizza ogni schema
        total_required_fields = 0
        total_present_fields = 0

        for schema in schemas:
            schema_type = schema.get('@type', '')
            # @type può essere una lista (raro ma valido)
            if isinstance(schema_type, list):
                types_list = [t for t in schema_type if isinstance(t, str)]
            elif isinstance(schema_type, str) and schema_type:
                types_list = [schema_type]
            else:
                types_list = []

            validation_results['schema_types'].extend(types_list)

            for stype in types_list:
                if stype in RECOMMENDED_SCHEMAS:
                    required_fields = RECOMMENDED_SCHEMAS[stype]
                    total_required_fields += len(required_fields)

                    for field in required_fields:
                        if field in schema:
                            total_present_fields += 1
                        else:
                            validation_results['missing_fields'].append({
                                'schema': stype,
                                'field': field
                            })

        # Calcola score di completezza
        if total_required_fields > 0:
            validation_results['completeness_score'] = round(
                (total_present_fields / total_required_fields) * 100, 1
            )

        # Genera raccomandazioni
        if validation_results['completeness_score'] < 50:
            missing_fields = set(f['field'] for f in validation_results['missing_fields'][:5])
            validation_results['recommendations'].append(
                f"Completezza schema bassa ({validation_results['completeness_score']}%). "
                f"Aggiungere campi mancanti: {', '.join(missing_fields)}"
            )

        if 'FAQPage' not in validation_results['schema_types']:
            validation_results['recommendations'].append(
                "Implementare FAQPage schema per migliorare visibilità in AI Overviews e featured snippets."
            )

        if 'Organization' not in validation_results['schema_types']:
            validation_results['recommendations'].append(
                "Implementare Organization schema per migliorare identificazione brand nei motori AI."
            )

        return validation_results

    def _analyze_ai_readability(self, html_data: Dict) -> Dict[str, Any]:
        """Analizza la leggibilità del contenuto per motori AI."""
        content = html_data.get('content', '')
        words = content.split()

        analysis = {
            'total_words': len(words),
            'first_150_words': ' '.join(words[:150]),
            'has_direct_answer': False,
            'has_faq_format': False,
            'has_list_format': False,
            'readability_score': 0,
            'recommendations': [],
        }

        # Verifica presenza di risposta diretta nelle prime 150 parole
        first_150 = analysis['first_150_words'].lower()

        for pattern in DIRECT_ANSWER_PATTERNS:
            if re.search(pattern, first_150):
                analysis['has_direct_answer'] = True
                break

        # Verifica formato FAQ
        content_lower = content.lower()
        for pattern in FAQ_PATTERNS:
            if re.search(pattern, content_lower):
                analysis['has_faq_format'] = True
                break

        # Verifica formato lista
        list_items = count_list_items(content)
        if list_items >= 3:
            analysis['has_list_format'] = True

        # Calcola score di leggibilità AI
        score = 0
        if analysis['has_direct_answer']:
            score += 30
        if analysis['has_faq_format']:
            score += 30
        if analysis['has_list_format']:
            score += 20
        if 300 <= analysis['total_words'] <= 1500:
            score += 20

        analysis['readability_score'] = score

        # Genera raccomandazioni
        if not analysis['has_direct_answer']:
            analysis['recommendations'].append(
                "Aggiungere una risposta diretta nelle prime 150 parole per migliorare visibilità in AI Overviews."
            )

        if not analysis['has_faq_format']:
            analysis['recommendations'].append(
                "Implementare sezione FAQ con schema FAQPage per featured snippets."
            )

        if not analysis['has_list_format']:
            analysis['recommendations'].append(
                "Utilizzare elenchi puntati/numerati per migliorare leggibilità e citation potential."
            )

        if analysis['total_words'] < 300:
            analysis['recommendations'].append(
                f"Contenuto troppo breve ({analysis['total_words']} parole). Target: 300-1500 parole."
            )

        return analysis

    def _evaluate_citation_potential(self, html_data: Dict) -> Dict[str, Any]:
        """Valuta il potenziale di citazione da parte di motori AI."""
        content = html_data.get('content', '')
        schemas = html_data.get('structured_data', [])

        evaluation = {
            'citation_score': 0,
            'factors': {},
            'recommendations': [],
        }

        # Fattore 1: Dati strutturati (peso: 30%)
        schema_score = min(len(schemas) * 10, 30)
        evaluation['factors']['structured_data'] = schema_score

        # Fattore 2: Autorevolezza contenuto (peso: 25%)
        authority_indicators = 0
        if re.search(r'(autore|author|scritto da)', content.lower()):
            authority_indicators += 1
        if re.search(r'(\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2})', content):
            authority_indicators += 1
        if re.search(r'(fonte|secondo|studio|ricerca)', content.lower()):
            authority_indicators += 1

        authority_score = min(authority_indicators * 8, 25)
        evaluation['factors']['authority'] = authority_score

        # Fattore 3: Chiarezza espositiva (peso: 25%)
        sentence_stats = calculate_sentence_stats(content)
        avg_sentence_length = sentence_stats['avg_length']

        clarity_score = 0
        if avg_sentence_length < 20 and avg_sentence_length > 0:
            clarity_score = 25
        elif avg_sentence_length < 25 and avg_sentence_length > 0:
            clarity_score = 15
        evaluation['factors']['clarity'] = clarity_score

        # Fattore 4: Unicità contenuto (peso: 20%)
        originality_indicators = 0
        if re.search(r'(\d+%|\d+\.\d+)', content):
            originality_indicators += 1
        if re.search(r'(statistica|dato|ricerca|studio)', content.lower()):
            originality_indicators += 1

        originality_score = min(originality_indicators * 10, 20)
        evaluation['factors']['originality'] = originality_score

        # Calcola score totale
        evaluation['citation_score'] = sum(evaluation['factors'].values())

        # Genera raccomandazioni
        if evaluation['citation_score'] < 50:
            evaluation['recommendations'].append(
                f"Citation potential basso ({evaluation['citation_score']}/100). "
                "Migliorare autorevolezza, chiarezza e unicità del contenuto."
            )

        if evaluation['factors']['authority'] < 15:
            evaluation['recommendations'].append(
                "Aggiungere autore, data di pubblicazione e fonti per migliorare autorevolezza."
            )

        if evaluation['factors']['clarity'] < 15:
            evaluation['recommendations'].append(
                "Migliorare chiarezza espositiva con frasi più brevi e paragrafi strutturati."
            )

        return evaluation

    def _analyze_content_structure(self, html_data: Dict) -> Dict[str, Any]:
        """Analizza la struttura del contenuto per GEO."""
        soup = html_data.get('soup')

        if not soup:
            return {}

        analysis = {
            'h1_count': len(soup.find_all('h1')),
            'h2_count': len(soup.find_all('h2')),
            'h3_count': len(soup.find_all('h3')),
            'paragraphs_count': len(soup.find_all('p')),
            'lists_count': len(soup.find_all('ul')) + len(soup.find_all('ol')),
            'tables_count': len(soup.find_all('table')),
            'images_count': len(soup.find_all('img')),
            'recommendations': [],
        }

        # Verifica struttura ottimale per GEO
        if analysis['h1_count'] == 0:
            analysis['recommendations'].append("Aggiungere almeno un H1 per definire il topic principale.")

        if analysis['h2_count'] < 3:
            analysis['recommendations'].append(
                "Aumentare il numero di H2 per migliorare struttura e leggibilità per motori AI."
            )

        if analysis['paragraphs_count'] < 5:
            analysis['recommendations'].append(
                "Contenuto troppo breve. Aggiungere più paragrafi per migliorare citation potential."
            )

        if analysis['lists_count'] == 0:
            analysis['recommendations'].append(
                "Aggiungere elenchi puntati o numerati per migliorare leggibilità."
            )

        return analysis