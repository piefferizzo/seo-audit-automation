"""
Genera una bozza di focus_keywords.yaml dai dati GSC.

Per ogni URL con dati GSC, propone:
  - primary = top query per impression su quell'URL
  - secondary = altre top 3-4 query

Merge non distruttivo: se una entry ha già `primary` impostato
manualmente, NON viene sovrascritta.

Utilizzo:
    python3 tools/generate_focus_keywords.py passionevo.com
    python3 tools/generate_focus_keywords.py arkys.agency --output focus_keywords.yaml
    python3 tools/generate_focus_keywords.py passionevo.com --overwrite
"""
import sys
import os
import argparse
import yaml
from datetime import datetime
from typing import Dict, Any, List
from urllib.parse import urlparse

# Assicura che la root del progetto sia nel path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from collectors.gsc_collector import GSCCollector


def load_config(path: str = "config.yaml") -> Dict[str, Any]:
    if os.path.exists(path):
        with open(path) as f:
            return yaml.safe_load(f) or {}
    return {}


def load_existing(path: str) -> Dict[str, Any]:
    """Carica il file esistente o ritorna struttura vuota multi-dominio."""
    if not os.path.exists(path):
        return {'domains': {}, 'options': {}}

    with open(path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f) or {}

    # Se è in formato vecchio flat, convertilo
    if 'domains' not in data:
        return {
            'domains': {},
            'options': data.get('options', {}) or {},
        }

    return data


def normalize_domain(domain: str) -> str:
    d = domain.replace('https://', '').replace('http://', '').replace('www.', '')
    return d.split('/')[0].lower().rstrip('/')


def normalize_url(url: str) -> str:
    if not url:
        return '/'
    if '://' in url:
        url = urlparse(url).path
    url = url.split('?')[0].split('#')[0]
    return url.rstrip('/') or '/'


def derive_keyword_from_title(title: str, h1: str = '') -> str:
    """Fallback: se non ci sono query GSC, usa il title pulito."""
    text = (title or h1 or '').lower()
    for sep in [' | ', ' - ', ' – ', ' — ']:
        if sep in text:
            text = text.split(sep)[0]

    stop = {
        'il', 'lo', 'la', 'i', 'gli', 'le', 'un', 'uno', 'una', 'di', 'a', 'da',
        'in', 'con', 'su', 'per', 'tra', 'fra', 'e', 'o', 'ma', 'che', 'non',
        'è', 'sono', 'del', 'della', 'dei', 'delle', 'come', 'più', 'anche',
        'the', 'and', 'of', 'to', 'in', 'is', 'it',
    }
    words = [w.strip('.,!?:;') for w in text.split()]
    meaningful = [w for w in words if w and w not in stop and len(w) > 3]
    return ' '.join(meaningful[:4])


def fetch_gsc_data(domain: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Esegue il GSC collector per ottenere i dati necessari al generatore."""
    collector = GSCCollector(config)
    if not collector.is_available():
        print("⚠️  GSC non disponibile: verifica le credenziali.")
        return {}
    return collector.collect(domain)


def build_url_to_queries(gsc_data: Dict[str, Any]) -> Dict[str, List[Dict]]:
    """Associa a ogni URL le query che portano impression.

    Priorità:
      1. Usa `page_query_pairs` (nuovo campo dal collector, dimensioni multiple)
      2. Fallback: se manca, prova a ricostruire da altri campi
    """
    url_to_queries: Dict[str, List[Dict]] = {}

    # --- Fonte principale: page_query_pairs (v2.4.0+) ---
    for row in gsc_data.get('page_query_pairs', []) or []:
        page = row.get('page', '')
        query = row.get('query', '')
        if not page or not query:
            continue
        url = normalize_url(page)
        url_to_queries.setdefault(url, []).append({
            'query': query,
            'clicks': row.get('clicks', 0),
            'impressions': row.get('impressions', 0),
            'position': row.get('position', 0),
        })

    # Ordina per impression decrescenti per ogni URL
    for url in url_to_queries:
        url_to_queries[url].sort(
            key=lambda x: (x['impressions'], x['clicks']),
            reverse=True,
        )

    return url_to_queries


def generate_keywords_for_domain(
    domain: str,
    gsc_data: Dict[str, Any],
    existing_domain_section: Dict[str, Any],
) -> Dict[str, Any]:
    """Costruisce la sezione keywords per un dominio.

    Preserva le entry esistenti. Aggiunge nuove entry derivate da GSC.
    """
    url_to_queries = build_url_to_queries(gsc_data)
    existing_keywords = existing_domain_section.get('keywords', {}) or {}

    # Parti dalle keyword già esistenti (mantienile intatte)
    new_keywords: Dict[str, Any] = {}
    for url, entry in existing_keywords.items():
        normalized = normalize_url(url)
        new_keywords[normalized] = entry

    # Aggiungi/arricchisci con quelle derivate da GSC
    for url, queries in url_to_queries.items():
        if not queries:
            continue

        if url in new_keywords:
            # Entry esistente: preservala, arricchisci solo se secondary è vuoto
            entry = new_keywords[url]
            if isinstance(entry, dict):
                if not entry.get('secondary'):
                    entry['secondary'] = [
                        q['query'] for q in queries[1:5]
                    ]
            continue

        # Nuova entry: primary = top query per impression
        primary = queries[0]['query']
        secondary = [q['query'] for q in queries[1:5]]

        new_keywords[url] = {
            'primary': primary,
            'secondary': secondary,
        }

    # Ordina per URL
    new_keywords = dict(sorted(new_keywords.items()))

    return {'keywords': new_keywords}


def main():
    parser = argparse.ArgumentParser(
        description="Genera bozza di focus_keywords.yaml dai dati GSC."
    )
    parser.add_argument('domain', help="Dominio (es. passionevo.com)")
    parser.add_argument(
        '--output', default='focus_keywords.yaml',
        help="File di output (default: focus_keywords.yaml)"
    )
    parser.add_argument(
        '--overwrite', action='store_true',
        help="Sovrascrive anche le entry esistenti (default: preserva)"
    )
    args = parser.parse_args()

    domain_key = normalize_domain(args.domain)
    config = load_config()
    existing = load_existing(args.output)

    print(f"🔍 Raccolta dati GSC per {domain_key}...")
    gsc_data = fetch_gsc_data(domain_key, config)
    if not gsc_data:
        print("✗ Nessun dato GSC raccolto.")
        sys.exit(1)

    n_pairs = len(gsc_data.get('page_query_pairs', []) or [])
    print(f"  ✓ Recuperate {n_pairs} coppie page+query")
    print(f"  ✓ {len(gsc_data.get('performance', []) or [])} pagine con performance")

    existing_section = existing.get('domains', {}).get(domain_key, {})

    if args.overwrite:
        print(f"  ⚠️  Modalità --overwrite: la sezione esistente verrà rigenerata")
        existing_section = {}

    new_section = generate_keywords_for_domain(
        domain_key, gsc_data, existing_section
    )

    if 'domains' not in existing:
        existing['domains'] = {}
    existing['domains'][domain_key] = new_section

    if 'options' not in existing:
        existing['options'] = {
            'missing_keyword_behavior': 'warn',
            'min_density': 0.8,
            'ideal_density': 1.5,
            'max_density': 3.5,
            'check_title': True,
            'check_h1': True,
        }

    # Salva
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(f"# focus_keywords.yaml — generato {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"# Ultimo dominio: {domain_key}\n")
        yaml.dump(existing, f, allow_unicode=True, sort_keys=False, indent=2)

    n_keywords = len(new_section.get('keywords', {}))
    print(f"✓ Salvate {n_keywords} keyword in {args.output}")
    print(f"  Dominio: {domain_key}")
    print()
    print("Prossimi passi:")
    print("  1. Apri il file e verifica le keyword suggerite")
    print("  2. Correggi manualmente quelle non ottimali")
    print("  3. Riesegui l'audit: le keyword saranno usate automaticamente")


if __name__ == '__main__':
    main()