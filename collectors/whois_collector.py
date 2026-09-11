import socket
import subprocess
import re
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from collectors.base_collector import BaseCollector


# ---------------------------------------------------------------------------
# HELPER 1 — Parsing date Whois (elimina duplicazioni di formato)
# ---------------------------------------------------------------------------
WHOIS_DATE_FORMATS = [
    '%Y-%m-%d',
    '%d-%m-%Y',
    '%d/%m/%Y',
    '%Y/%m/%d',
    '%d-%b-%Y',
    '%Y-%m-%dT%H:%M:%S',
    '%Y-%m-%d %H:%M:%S',
]


def parse_whois_date(date_str: str) -> Optional[datetime]:
    """Parsa una data whois in vari formati, restituendo datetime o None."""
    if not date_str:
        return None
    
    # Pulisci la stringa
    date_str = date_str.split('T')[0].strip()
    
    # Prova formati standard
    for fmt in WHOIS_DATE_FORMATS:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    # Fallback: dateutil parser
    try:
        from dateutil import parser
        return parser.parse(date_str).replace(tzinfo=None)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# HELPER 2 — Gestione timezone (evita errori di calcolo)
# ---------------------------------------------------------------------------
def safe_datetime(value: Any) -> Optional[datetime]:
    """Converte valore in datetime rimuovendo timezone per evitare errori."""
    if value is None:
        return None
    
    if isinstance(value, list) and value:
        for d in value:
            if isinstance(d, datetime):
                return d.replace(tzinfo=None)
        return None
    
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    
    return None


# ---------------------------------------------------------------------------
# HELPER 3 — Pattern regex per parsing whois (tabella dichiarativa)
# ---------------------------------------------------------------------------
WHOIS_FIELD_PATTERNS = {
    'creation_date': [
        r'(?:Creation Date|Created(?: On)?|Registered on|Registration Date)[:\s]+([^\n]+)',
    ],
    'expiration_date': [
        r'(?:Registry Expiry Date|Expir(?:y|es|ation) Date|Expires on|Renewal Date)[:\s]+([^\n]+)',
    ],
    'updated_date': [
        r'(?:Updated Date|Last Updated|Modified)[:\s]+([^\n]+)',
    ],
    'registrar': [
        r'Registrar[:\s]+([^\n]+)',
    ],
    'name_servers': [
        r'Name Server[:\s]+([^\n]+)',
        r'Nameserver[:\s]+([^\n]+)',
    ],
    'status': [
        r'Domain Status[:\s]+([^\n]+)',
        r'Status[:\s]+([^\n]+)',
    ],
    'dnssec': [
        r'DNSSEC[:\s]+([^\n]+)',
    ],
}


def extract_whois_fields(whois_text: str) -> Dict[str, Any]:
    """Estrae campi whois da testo usando pattern regex dichiarativi."""
    data = {}
    
    for field_name, patterns in WHOIS_FIELD_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, whois_text, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                
                # Gestione speciale per campi multipli
                if field_name in ['name_servers', 'status']:
                    all_matches = re.findall(pattern, whois_text, re.IGNORECASE)
                    data[field_name] = [m.strip().lower() for m in all_matches if m.strip()]
                elif field_name in ['creation_date', 'expiration_date', 'updated_date']:
                    data[field_name] = parse_whois_date(value)
                else:
                    data[field_name] = value
                
                break  # Usa primo pattern che matcha
    
    return data


# ---------------------------------------------------------------------------
# HELPER 4 — Normalizzazione valori (elimina duplicazioni)
# ---------------------------------------------------------------------------
def normalize_value(value: Any) -> Any:
    """Normalizza valore: se è lista, prende primo elemento."""
    if isinstance(value, list) and value:
        return value[0]
    return value


def normalize_list(value: Any) -> List[str]:
    """Normalizza valore in lista di stringhe."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return list(set([str(v) for v in value if v]))
    return []


class WhoisCollector(BaseCollector):
    """Raccoglie dati Whois del dominio con multiple strategie di fallback."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self._whois_lib_available = self._check_whois_library()
    
    def is_available(self) -> bool:
        """Whois collector è sempre disponibile (ha fallback multipli)."""
        return True
    
    def _check_whois_library(self) -> bool:
        """Verifica se python-whois è installato."""
        try:
            import whois
            return True
        except ImportError:
            self.logger.debug("python-whois non installato, userò fallback")
            return False
    
    def collect(self, domain: str) -> Dict[str, Any]:
        """Raccoglie dati Whois completi per il dominio."""
        clean_domain = domain.replace('https://', '').replace('http://', '').replace('www.', '').split('/')[0]
        
        self.logger.info(f"🔍 Raccolta dati Whois per {clean_domain}...")
        
        result = {
            'domain_name': clean_domain,
            'registrar': '',
            'creation_date': None,
            'expiration_date': None,
            'updated_date': None,
            'name_servers': [],
            'status': [],
            'dnssec': '',
            'age_days': 0,
            'age_years': 0,
            'days_to_expiry': 0,
            'ip_address': '',
            'source': ''
        }
        
        # STRATEGIA 1: python-whois library
        if self._whois_lib_available:
            lib_result = self._whois_from_library(clean_domain)
            if lib_result:
                result.update(lib_result)
                result['source'] = 'python-whois'
                self.logger.info(f"  ✓ Whois ottenuto con python-whois")
        
        # STRATEGIA 2: Comando whois di sistema
        if not result['creation_date']:
            system_result = self._whois_from_system(clean_domain)
            if system_result:
                result.update(system_result)
                result['source'] = 'system-command'
                self.logger.info(f"  ✓ Whois ottenuto con comando di sistema")
        
        # STRATEGIA 3: Web scraping da whois.com
        if not result['creation_date']:
            web_result = self._whois_from_web(clean_domain)
            if web_result:
                result.update(web_result)
                result['source'] = 'web-scraping'
                self.logger.info(f"  ✓ Whois ottenuto con web scraping")
        
        # Calcola età del dominio
        self._calculate_domain_age(result)
        
        # Calcola giorni alla scadenza
        self._calculate_days_to_expiry(result)
        
        # Risolvi IP
        result['ip_address'] = self._resolve_ip(clean_domain)
        
        if not result['creation_date']:
            self.logger.warning(f"  ⚠️  Nessun dato Whois trovato per {clean_domain}")
            result['source'] = 'none'
        else:
            self.logger.info(f"  ✓ Whois completo: dominio {result.get('age_years', 0)} anni, registrar: {result.get('registrar', 'N/A')}")
        
        return result
    
    def _whois_from_library(self, domain: str) -> Optional[Dict[str, Any]]:
        """Raccoglie whois usando python-whois library."""
        try:
            import whois
            w = whois.whois(domain)
            
            if not w.domain_name:
                return None
            
            return {
                'registrar': normalize_value(w.registrar) or '',
                'creation_date': safe_datetime(w.creation_date),
                'expiration_date': safe_datetime(w.expiration_date),
                'updated_date': safe_datetime(w.updated_date),
                'name_servers': normalize_list(w.name_servers),
                'status': normalize_list(w.status),
                'dnssec': normalize_value(w.dnssec) or '',
            }
        except Exception as e:
            self.logger.warning(f"  ⚠️  python-whois fallito: {e}")
            return None
    
    def _whois_from_system(self, domain: str) -> Optional[Dict[str, Any]]:
        """Usa il comando whois di sistema come fallback."""
        try:
            result = subprocess.run(
                ['whois', domain],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0 or not result.stdout:
                return None
            
            return extract_whois_fields(result.stdout)
            
        except FileNotFoundError:
            self.logger.debug(f"  ⚠️  Comando 'whois' non trovato nel sistema")
            return None
        except Exception as e:
            self.logger.warning(f"  ⚠️  Comando whois di sistema fallito: {e}")
            return None
    
    def _whois_from_web(self, domain: str) -> Optional[Dict[str, Any]]:
        """Usa web scraping da whois.com come fallback finale."""
        try:
            import requests
            from bs4 import BeautifulSoup
            
            url = f"https://www.whois.com/whois/{domain}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.text, 'html.parser')
            data = {}
            
            # Cerca dati nella struttura della pagina
            for row in soup.find_all('div', class_=re.compile('df-raw', re.I)):
                label = row.find('div', class_=re.compile('label', re.I))
                value = row.find('div', class_=re.compile('value', re.I))
                
                if label and value:
                    label_text = label.get_text().strip().lower()
                    value_text = value.get_text().strip()
                    
                    if 'creation date' in label_text or 'registered on' in label_text:
                        data['creation_date'] = parse_whois_date(value_text)
                    elif 'expir' in label_text:
                        data['expiration_date'] = parse_whois_date(value_text)
                    elif 'registrar' in label_text:
                        data['registrar'] = value_text
            
            return data if data else None
            
        except Exception as e:
            self.logger.warning(f"  ⚠️  Web scraping whois fallito: {e}")
            return None
    
    def _calculate_domain_age(self, result: Dict[str, Any]):
        """Calcola età del dominio in giorni e anni."""
        if result.get('creation_date'):
            creation_dt = result['creation_date']
            age_days = (datetime.now() - creation_dt).days
            result['age_days'] = age_days
            result['age_years'] = round(age_days / 365.25, 1)
    
    def _calculate_days_to_expiry(self, result: Dict[str, Any]):
        """Calcola giorni alla scadenza del dominio."""
        if result.get('expiration_date'):
            expiry_dt = result['expiration_date']
            days_to_expiry = (expiry_dt - datetime.now()).days
            result['days_to_expiry'] = days_to_expiry
    
    def _resolve_ip(self, domain: str) -> str:
        """Risolvi dominio in indirizzo IP."""
        try:
            return socket.gethostbyname(domain)
        except Exception:
            return ""