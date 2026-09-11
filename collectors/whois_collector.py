import socket
import subprocess
import re
from typing import Dict, Any
from datetime import datetime
from collectors.base_collector import BaseCollector

class WhoisCollector(BaseCollector):
    """Raccoglie dati Whois del dominio con multiple strategie di fallback."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
    
    def is_available(self) -> bool:
        """Sempre disponibile (ha fallback multipli)."""
        return True
    
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
        try:
            import whois
            w = whois.whois(clean_domain)
            
            if w.domain_name:
                result['registrar'] = self._normalize_value(w.registrar) or ''
                result['creation_date'] = self._normalize_date(w.creation_date)
                result['expiration_date'] = self._normalize_date(w.expiration_date)
                result['updated_date'] = self._normalize_date(w.updated_date)
                result['name_servers'] = self._normalize_list(w.name_servers)
                result['status'] = self._normalize_list(w.status)
                result['dnssec'] = self._normalize_value(w.dnssec) or ''
                result['source'] = 'python-whois'
                self.logger.info(f"  ✓ Whois ottenuto con python-whois")
        except Exception as e:
            self.logger.warning(f"  ⚠️  python-whois fallito: {e}")
        
        # STRATEGIA 2: Comando whois di sistema
        if not result['creation_date']:
            system_result = self._whois_from_system(clean_domain)
            if system_result:
                for key, value in system_result.items():
                    if value:
                        result[key] = value
                result['source'] = 'system-command'
                self.logger.info(f"  ✓ Whois ottenuto con comando di sistema")
        
        # STRATEGIA 3: Web scraping da whois.com
        if not result['creation_date']:
            web_result = self._whois_from_web(clean_domain)
            if web_result:
                for key, value in web_result.items():
                    if value:
                        result[key] = value
                result['source'] = 'web-scraping'
                self.logger.info(f"  ✓ Whois ottenuto con web scraping")
        
        # Calcola età del dominio (FIX: gestione timezone)
        if result['creation_date']:
            creation_dt = result['creation_date']
            if creation_dt.tzinfo is not None:
                creation_dt = creation_dt.replace(tzinfo=None)
            
            age_days = (datetime.now() - creation_dt).days
            result['age_days'] = age_days
            result['age_years'] = round(age_days / 365.25, 1)
        
        # Calcola giorni alla scadenza (FIX: gestione timezone)
        if result['expiration_date']:
            expiry_dt = result['expiration_date']
            if expiry_dt.tzinfo is not None:
                expiry_dt = expiry_dt.replace(tzinfo=None)
            
            days_to_expiry = (expiry_dt - datetime.now()).days
            result['days_to_expiry'] = days_to_expiry
        
        # Risolvi IP
        result['ip_address'] = self._resolve_ip(clean_domain)
        
        if not result['creation_date']:
            self.logger.warning(f"  ⚠️  Nessun dato Whois trovato per {clean_domain}")
            result['source'] = 'none'
        else:
            self.logger.info(f"  ✓ Whois completo: dominio {result.get('age_years', 0)} anni, registrar: {result.get('registrar', 'N/A')}")
        
        return result
    
    def _whois_from_system(self, domain: str) -> Dict[str, Any]:
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
            
            whois_text = result.stdout
            data = {}
            
            creation_match = re.search(r'(?:Creation Date|Created(?: On)?|Registered on)[:\s]+([^\n]+)', whois_text, re.IGNORECASE)
            if creation_match:
                data['creation_date'] = self._parse_whois_date(creation_match.group(1).strip())
            
            expiry_match = re.search(r'(?:Registry Expiry Date|Expir(?:y|es|ation) Date|Expires on)[:\s]+([^\n]+)', whois_text, re.IGNORECASE)
            if expiry_match:
                data['expiration_date'] = self._parse_whois_date(expiry_match.group(1).strip())
            
            registrar_match = re.search(r'Registrar[:\s]+([^\n]+)', whois_text, re.IGNORECASE)
            if registrar_match:
                data['registrar'] = registrar_match.group(1).strip()
            
            ns_matches = re.findall(r'Name Server[:\s]+([^\n]+)', whois_text, re.IGNORECASE)
            if ns_matches:
                data['name_servers'] = [ns.strip().lower() for ns in ns_matches]
            
            return data if data else None
            
        except FileNotFoundError:
            self.logger.warning(f"  ⚠️  Comando 'whois' non trovato nel sistema")
            return None
        except Exception as e:
            self.logger.warning(f"  ⚠️  Comando whois di sistema fallito: {e}")
            return None
    
    def _whois_from_web(self, domain: str) -> Dict[str, Any]:
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
                        data['creation_date'] = self._parse_whois_date(value_text)
                    elif 'expir' in label_text:
                        data['expiration_date'] = self._parse_whois_date(value_text)
                    elif 'registrar' in label_text:
                        data['registrar'] = value_text
            
            return data if data else None
            
        except Exception as e:
            self.logger.warning(f"  ⚠️  Web scraping whois fallito: {e}")
            return None
    
    def _parse_whois_date(self, date_str: str):
        """Parsa una data whois in vari formati."""
        if not date_str:
            return None
        
        date_str = date_str.split('T')[0]
        date_str = date_str.strip()
        
        formats = [
            '%Y-%m-%d',
            '%d-%m-%Y',
            '%d/%m/%Y',
            '%Y/%m/%d',
            '%d-%b-%Y',
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        
        try:
            from dateutil import parser
            return parser.parse(date_str).replace(tzinfo=None)
        except:
            return None
    
    def _normalize_value(self, value):
        if isinstance(value, list) and value:
            return value[0]
        return value
    
    def _normalize_list(self, value):
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return list(set([v for v in value if v]))
        return []
    
    def _normalize_date(self, value):
        """Normalizza una data e rimuove il fuso orario (tzinfo) per evitare errori di calcolo."""
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
    
    def _resolve_ip(self, domain: str) -> str:
        try:
            return socket.gethostbyname(domain)
        except:
            return ""