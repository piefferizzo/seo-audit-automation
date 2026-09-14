"""
FocusKeywordsManager — gestione keyword target per URL (multi-dominio).

Supporta due formati nel file focus_keywords.yaml:

FORMATO NUOVO (multi-dominio, consigliato):
    domains:
      passionevo.com:
        keywords:
          "/":
            primary: "oleoturismo liguria"
            secondary: ["degustazione olio"]
      arkys.agency:
        keywords:
          "/":
            primary: "agenzia seo milano"

    options:
      min_density: 0.8

FORMATO VECCHIO (flat, retrocompatibile):
    keywords:
      "/":
        primary: "..."
    options:
      min_density: 0.8
"""

import os
import yaml
from typing import Dict, Optional, Any, List
from urllib.parse import urlparse


DEFAULT_OPTIONS = {
    'missing_keyword_behavior': 'skip',
    'min_density': 0.8,
    'ideal_density': 1.5,
    'max_density': 3.5,
    'check_title': True,
    'check_h1': True,
    'check_url': False,
    'check_meta_description': False,
}


class FocusKeywordsManager:
    """Gestisce la mappa URL → keyword target per un dominio specifico."""

    def __init__(self, file_path: str = "focus_keywords.yaml", domain: str = ""):
        self.file_path = file_path
        self.domain = self._normalize_domain(domain)
        self.keywords: Dict[str, Dict[str, Any]] = {}
        self.options: Dict[str, Any] = dict(DEFAULT_OPTIONS)
        self._loaded = False

    @staticmethod
    def _normalize_domain(domain: str) -> str:
        """Normalizza il dominio per il matching nella sezione 'domains'."""
        if not domain:
            return ""
        d = domain.replace('https://', '').replace('http://', '').replace('www.', '')
        return d.split('/')[0].lower().rstrip('/')

    def load(self):
        """Carica il file YAML e la sezione del dominio corrente. Idempotente."""
        if self._loaded:
            return
        self._loaded = True

        if not os.path.exists(self.file_path):
            return

        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}

            raw_keywords: Dict[str, Any] = {}

            # --- Formato multi-dominio ---
            if 'domains' in data and isinstance(data['domains'], dict):
                domains_section = data['domains']
                matched_domain = None
                for d in domains_section.keys():
                    if self._normalize_domain(d) == self.domain:
                        matched_domain = d
                        break
                if matched_domain:
                    section = domains_section[matched_domain] or {}
                    if isinstance(section, dict):
                        raw_keywords = section.get('keywords', {}) or {}
            # --- Formato vecchio flat (retrocompatibile) ---
            else:
                raw_keywords = data.get('keywords', {}) or {}

            # Normalizza le chiavi URL
            for url, value in raw_keywords.items():
                normalized = self._normalize_url(url)
                if isinstance(value, str):
                    self.keywords[normalized] = {
                        'primary': value,
                        'secondary': [],
                    }
                elif isinstance(value, dict):
                    self.keywords[normalized] = {
                        'primary': value.get('primary', '') or '',
                        'secondary': value.get('secondary', []) or [],
                    }

            # Opzioni globali
            opts = data.get('options', {}) or {}
            self.options.update(opts)

        except Exception as e:
            print(f"⚠️  focus_keywords.yaml malformato: {e}")

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Normalizza un URL in path canonico per il matching."""
        if not url:
            return '/'

        if '://' in url:
            url = urlparse(url).path
        elif url.startswith('/'):
            pass
        else:
            parsed = urlparse('https://' + url)
            url = parsed.path or '/'

        url = url.split('?')[0].split('#')[0]
        url = url.rstrip('/') or '/'
        return url

    def get_for_url(self, url: str) -> Optional[Dict[str, Any]]:
        """Ritorna {'primary': str, 'secondary': [...]} o None."""
        self.load()
        normalized = self._normalize_url(url)
        return self.keywords.get(normalized)

    def get_primary(self, url: str) -> Optional[str]:
        """Ritorna la keyword primaria o None."""
        data = self.get_for_url(url)
        if not data:
            return None
        return data.get('primary') or None

    def get_secondary(self, url: str) -> List[str]:
        """Ritorna la lista keyword secondarie (eventualmente vuota)."""
        data = self.get_for_url(url)
        if not data:
            return []
        return data.get('secondary') or []

    @property
    def is_empty(self) -> bool:
        self.load()
        return not self.keywords

    @property
    def count(self) -> int:
        self.load()
        return len(self.keywords)

    @property
    def is_multi_domain(self) -> bool:
        """True se il file ha struttura 'domains'."""
        if not os.path.exists(self.file_path):
            return False
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
            return 'domains' in data
        except Exception:
            return False