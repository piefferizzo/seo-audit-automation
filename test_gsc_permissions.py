#!/usr/bin/env python3
"""
Script di test per verificare i permessi del Service Account con Google Search Console API.
Uso: python test_gsc_permissions.py [dominio]
Esempio: python test_gsc_permissions.py https://arkys.agency
"""

import sys
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Configurazione
SERVICE_ACCOUNT_FILE = 'credentials/service-account.json'
SCOPES = [
    'https://www.googleapis.com/auth/webmasters.readonly',
    'https://www.googleapis.com/auth/webmasters'  # Aggiunto per URL Inspection API
]

def print_header(text):
    """Stampa un header formattato."""
    print(f"\n{'='*70}")
    print(f"  {text}")
    print(f"{'='*70}\n")

def print_success(text):
    """Stampa un messaggio di successo."""
    print(f"✅ {text}")

def print_error(text):
    """Stampa un messaggio di errore."""
    print(f"❌ {text}")

def print_warning(text):
    """Stampa un messaggio di warning."""
    print(f"⚠️  {text}")

def print_info(text):
    """Stampa un messaggio informativo."""
    print(f"ℹ️  {text}")

def test_credentials():
    """Test 1: Verifica che le credenziali siano valide."""
    print_header("TEST 1: Verifica Credenziali")
    
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        print_error(f"File credenziali non trovato: {SERVICE_ACCOUNT_FILE}")
        print_info("Assicurati che il file esista nel percorso specificato")
        return None
    
    try:
        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
        print_success("Credenziali caricate correttamente")
        print_info(f"Service Account Email: {credentials.service_account_email}")
        return credentials
    except Exception as e:
        print_error(f"Errore nel caricamento delle credenziali: {e}")
        return None

def test_list_sites(service):
    """Test 2: Lista tutti i siti verificati."""
    print_header("TEST 2: Lista Siti Verificati")
    
    try:
        response = service.sites().list().execute()
        
        if 'siteEntry' in response:
            print_success(f"Trovati {len(response['siteEntry'])} siti verificati:\n")
            for site in response['siteEntry']:
                url = site['siteUrl']
                permission = site['permissionLevel']
                print(f"  • {url}")
                print(f"    Permesso: {permission}")
            return True
        else:
            print_warning("Nessun sito trovato")
            print_info("Assicurati che l'email del Service Account sia stata aggiunta come utente in GSC")
            return False
            
    except HttpError as e:
        print_error(f"Errore HTTP: {e}")
        return False
    except Exception as e:
        print_error(f"Errore: {e}")
        return False

def test_site_access(service, site_url):
    """Test 3: Verifica accesso a un sito specifico."""
    print_header(f"TEST 3: Accesso a {site_url}")
    
    try:
        response = service.sites().get(siteUrl=site_url).execute()
        permission = response.get('permissionLevel', 'unknown')
        
        print_success(f"Accesso confermato a {site_url}")
        print_info(f"Livello di permesso: {permission}")
        
        if permission in ['siteOwner', 'siteFullUser']:
            print_success("Hai permessi completi (Owner/Full User)")
        elif permission == 'siteRestrictedUser':
            print_warning("Hai permessi limitati (Restricted User)")
        else:
            print_warning(f"Permesso non standard: {permission}")
        
        return True
        
    except HttpError as e:
        if e.resp.status == 403:
            print_error(f"Accesso negato (403 Forbidden)")
            print_info("Il Service Account non ha accesso a questo sito")
            print_info("Verifica che l'email del Service Account sia stata aggiunta in GSC")
        else:
            print_error(f"Errore HTTP {e.resp.status}: {e}")
        return False
    except Exception as e:
        print_error(f"Errore: {e}")
        return False

def test_sitemaps(service, site_url):
    """Test 4: Testa l'accesso alle sitemap."""
    print_header(f"TEST 4: Accesso Sitemap per {site_url}")
    
    try:
        response = service.sitemaps().list(siteUrl=site_url).execute()
        sitemaps = response.get('sitemap', [])
        
        if sitemaps:
            print_success(f"Trovate {len(sitemaps)} sitemap:\n")
            for sitemap in sitemaps:
                path = sitemap.get('path', 'N/A')
                contents = sitemap.get('contents', [])
                print(f"  • {path}")
                for content in contents:
                    submitted = content.get('submitted', 0)
                    indexed = content.get('indexed', 0)
                    print(f"    URL inviate: {submitted} | Indicizzate: {indexed}")
            return True
        else:
            print_warning("Nessuna sitemap trovata")
            return False
            
    except HttpError as e:
        print_error(f"Errore HTTP {e.resp.status}: {e}")
        return False
    except Exception as e:
        print_error(f"Errore: {e}")
        return False

def test_performance(service, site_url):
    """Test 5: Testa l'accesso ai dati performance."""
    print_header(f"TEST 5: Accesso Performance per {site_url}")
    
    try:
        from datetime import datetime, timedelta
        
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        
        request = {
            'startDate': start_date,
            'endDate': end_date,
            'dimensions': ['page'],
            'rowLimit': 5
        }
        
        response = service.searchanalytics().query(siteUrl=site_url, body=request).execute()
        rows = response.get('rows', [])
        
        if rows:
            print_success(f"Dati performance disponibili (ultimi 7 giorni):\n")
            for row in rows[:5]:
                page = row.get('keys', ['N/A'])[0]
                clicks = row.get('clicks', 0)
                impressions = row.get('impressions', 0)
                print(f"  • {page}")
                print(f"    Click: {clicks} | Impression: {impressions}")
            return True
        else:
            print_warning("Nessun dato performance disponibile")
            return False
            
    except HttpError as e:
        print_error(f"Errore HTTP {e.resp.status}: {e}")
        return False
    except Exception as e:
        print_error(f"Errore: {e}")
        return False

def test_url_inspection(service, site_url, test_url):
    """Test 6: Testa l'URL Inspection API (quella che sta dando problemi)."""
    print_header(f"TEST 6: URL Inspection API")
    print_info(f"Sito: {site_url}")
    print_info(f"URL da ispezionare: {test_url}\n")
    
    try:
        request = {
            'inspectionUrl': test_url,
            'siteUrl': site_url
        }
        
        response = service.urlInspection().index().inspect(body=request).execute()
        
        print_success("URL Inspection API funzionante!\n")
        
        # Estrai informazioni utili
        index_status = response.get('indexStatusResult', {})
        verdict = index_status.get('verdict', 'N/A')
        last_crawl_time = index_status.get('lastCrawlTime', 'N/A')
        indexing_state = index_status.get('indexingState', 'N/A')
        
        print_info(f"Stato indicizzazione: {verdict}")
        print_info(f"Ultimo crawl: {last_crawl_time}")
        print_info(f"Stato indexing: {indexing_state}")
        
        # Verifica copertura
        coverage = index_status.get('coverage', {})
        if coverage:
            print_info(f"Copertura: {coverage}")
        
        return True
        
    except HttpError as e:
        if e.resp.status == 403:
            print_error("URL Inspection API: Accesso negato (403 Forbidden)")
            print_info("\nPossibili cause:")
            print_info("  1. L'URL non appartiene a questa property GSC")
            print_info("  2. Il Service Account non ha permessi sufficienti")
            print_info("  3. L'API non è abilitata nel progetto Google Cloud")
            print_info("\nSoluzioni:")
            print_info("  • Verifica che l'URL corrisponda esattamente alla property GSC")
            print_info("  • Controlla che il Service Account abbia ruolo 'Owner' o 'Full User'")
            print_info("  • Abilita 'Search Console API' nel progetto Google Cloud")
        else:
            print_error(f"Errore HTTP {e.resp.status}: {e}")
        return False
    except Exception as e:
        print_error(f"Errore: {e}")
        return False

def main():
    """Funzione principale."""
    print_header("GOOGLE SEARCH CONSOLE - TEST PERMESSI")
    
    # Verifica argomenti
    if len(sys.argv) < 2:
        print_info("Uso: python test_gsc_permissions.py [dominio]")
        print_info("Esempio: python test_gsc_permissions.py https://arkys.agency")
        print_info("\nSe non specifichi un dominio, testerò solo la connessione base\n")
        domain = None
    else:
        domain = sys.argv[1]
        if not domain.startswith('http'):
            domain = f"https://{domain}"
        print_info(f"Dominio da testare: {domain}\n")
    
    # Test 1: Credenziali
    credentials = test_credentials()
    if not credentials:
        print_error("Impossibile procedere senza credenziali valide")
        return
    
    # Inizializza servizio
    try:
        service = build('searchconsole', 'v1', credentials=credentials)
        print_success("Servizio Search Console inizializzato")
    except Exception as e:
        print_error(f"Errore nell'inizializzazione del servizio: {e}")
        return
    
    # Test 2: Lista siti
    if not test_list_sites(service):
        print_warning("Impossibile listare i siti, ma continuo con i test...\n")
    
    # Se è stato specificato un dominio, esegui test specifici
    if domain:
        # Test 3: Accesso sito
        if not test_site_access(service, domain):
            print_error("Impossibile accedere al sito, test terminati")
            return
        
        # Test 4: Sitemap
        test_sitemaps(service, domain)
        
        # Test 5: Performance
        test_performance(service, domain)
        
        # Test 6: URL Inspection API (quella problematica)
        test_url_inspection(service, domain, domain)
    
    # Riepilogo finale
    print_header("RIEPILOGO")
    print_success("Test completati!")
    print_info("\nSe tutti i test sono passati, il Service Account è configurato correttamente.")
    print_info("Se qualche test è fallito, controlla i messaggi di errore per le soluzioni.")
    print_info("\nPer problemi con l'URL Inspection API:")
    print_info("  • Verifica che l'URL corrisponda ESATTAMENTE alla property GSC")
    print_info("  • Controlla i permessi del Service Account in GSC")
    print_info("  • Verifica che l'API sia abilitata in Google Cloud Console")

if __name__ == "__main__":
    main()