#!/usr/bin/env python3
"""
SEO Audit Automation Tool
Main script per eseguire audit SEO completi con multipli collector.
"""

# Carica variabili d'ambiente PRIMA di tutto
from dotenv import load_dotenv
load_dotenv()

import sys
import os
import argparse
import yaml
import traceback
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

# Import collector
from collectors.pagespeed_collector import PageSpeedCollector
from collectors.gsc_collector import GSCCollector
from collectors.ga4_collector import GA4Collector
from collectors.html_collector import HTMLCollector
from collectors.whois_collector import WhoisCollector
#from collectors.semrush_collector import SemrushCollector
from collectors.manual_collector import ManualCollector

# Import processor e generator
from processors.audit_processor import AuditProcessor
from generators.excel_generator import ExcelGenerator

# Import utilities
from utils.logger import setup_logger
from utils.cache import CacheManager


# ---------------------------------------------------------------------------
# COSTANTI — Configurazione e stili
# ---------------------------------------------------------------------------
DEFAULT_CONFIG_PATH = "config.yaml"
REPORTS_DIR = "reports"
CACHE_DIR = "cache"

# Stili Rich
STYLES = {
    'title': 'bold cyan',
    'success': 'green',
    'warning': 'yellow',
    'error': 'red',
    'info': 'blue',
    'domain': 'green',
    'date': 'yellow',
    'phase': 'bold',
    'file_path': 'bold cyan',
}

# Icone per output
ICONS = {
    'success': '✓',
    'warning': '⚠',
    'error': '✗',
    'info': 'ℹ',
    'start': '⠋',
    'rocket': '🚀',
    'package': '📦',
    'refresh': '🔄',
    'chart': '📊',
    'folder': '📁',
    'search': '🔍',
}

# Mapping collector
COLLECTOR_CLASSES = {
    "pagespeed": PageSpeedCollector,
    "gsc": GSCCollector,
    "ga4": GA4Collector,
    "html": HTMLCollector,
    "whois": WhoisCollector,
    #"semrush": SemrushCollector,
    "manual": ManualCollector,
}


# ---------------------------------------------------------------------------
# HELPER 1 — Normalizzazione dominio
# ---------------------------------------------------------------------------
def normalize_domain(domain: str) -> str:
    """Normalizza il dominio aggiungendo https:// se necessario."""
    if not domain.startswith('http'):
        return f"https://{domain}"
    return domain


# ---------------------------------------------------------------------------
# HELPER 2 — Caricamento configurazione
# ---------------------------------------------------------------------------
def load_config(config_path: str = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    """Carica la configurazione dal file YAML."""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print(f"❌ File di configurazione non trovato: {config_path}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Errore nel caricamento della configurazione: {e}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# HELPER 3 — Visualizzazione statistiche cache
# ---------------------------------------------------------------------------
def display_cache_stats(domain: Optional[str] = None):
    """Mostra le statistiche della cache."""
    console = Console()
    cache = CacheManager(cache_dir=CACHE_DIR)
    stats = cache.get_stats()
    
    table = Table(title="📊 Statistiche Cache PageSpeed")
    table.add_column("Metrica", style="cyan")
    table.add_column("Valore", style="green")
    
    table.add_row("Cache Hits", str(stats.get('hits', 0)))
    table.add_row("Cache Misses", str(stats.get('misses', 0)))
    table.add_row("API Calls Risparmiate", str(stats.get('hits', 0)))
    
    console.print(table)


# ---------------------------------------------------------------------------
# HELPER 4 — Pulizia cache
# ---------------------------------------------------------------------------
def clear_cache(domain: Optional[str] = None):
    """Pulisce la cache."""
    console = Console()
    cache = CacheManager(cache_dir=CACHE_DIR)
    
    if domain:
        cache.clear(domain)
        console.print(f"[{STYLES['success']}]✅ Cache PageSpeed cancellata per {domain}[/{STYLES['success']}]")
    else:
        cache.clear()
        console.print(f"[{STYLES['success']}]✅ Tutta la cache è stata cancellata[/{STYLES['success']}]")


# ---------------------------------------------------------------------------
# HELPER 5 — Inizializzazione collector
# ---------------------------------------------------------------------------
def initialize_collectors(config: Dict[str, Any]) -> Dict[str, Any]:
    """Inizializza tutti i collector."""
    return {
        name: collector_class(config)
        for name, collector_class in COLLECTOR_CLASSES.items()
    }


# ---------------------------------------------------------------------------
# HELPER 6 — Esecuzione collector con gestione errori
# ---------------------------------------------------------------------------
def run_collector(collector, domain: str, console: Console, logger) -> Optional[Dict[str, Any]]:
    """Esegue un collector con gestione errori."""
    collector_name = collector.__class__.__name__
    
    try:
        if collector.is_available():
            console.print(f"  [{STYLES['info']}]{ICONS['start']} Raccolta dati {collector_name}...[/{STYLES['info']}]")
            data = collector.collect(domain)
            console.print(f"  [{STYLES['success']}]{ICONS['success']} {collector_name} completato[/{STYLES['success']}]")
            return data
        else:
            console.print(f"  [{STYLES['warning']}]{ICONS['warning']} {collector_name} non disponibile[/{STYLES['warning']}]")
            return None
    except Exception as e:
        logger.error(f"Errore nel collector {collector_name}: {e}")
        logger.error(traceback.format_exc())
        console.print(f"  [{STYLES['error']}]{ICONS['error']} {collector_name} fallito: {e}[/{STYLES['error']}]")
        return None


# ---------------------------------------------------------------------------
# HELPER 7 — Raccolta dati da tutti i collector
# ---------------------------------------------------------------------------
def collect_all_data(collectors: Dict[str, Any], domain: str, console: Console, logger) -> Dict[str, Any]:
    """Raccoglie dati da tutti i collector."""
    raw_data = {}
    
    for name, collector in collectors.items():
        data = run_collector(collector, domain, console, logger)
        if data:
            raw_data[name] = data
    
    return raw_data


# ---------------------------------------------------------------------------
# HELPER 8 — Visualizzazione verifica dati
# ---------------------------------------------------------------------------
def display_data_verification(collectors: Dict[str, Any], raw_data: Dict[str, Any], console: Console):
    """Mostra la verifica dei dati raccolti."""
    console.print(f"\n[{STYLES['phase']}]{ICONS['search']} Verifica dati raccolti[/{STYLES['phase']}]")
    
    for name in collectors.keys():
        has_data = bool(raw_data.get(name))
        icon = ICONS['success'] if has_data else ICONS['error']
        color = STYLES['success'] if has_data else STYLES['error']
        console.print(f"  [{color}]{icon} {name}: {has_data}[/{color}]")


# ---------------------------------------------------------------------------
# HELPER 9 — Elaborazione dati
# ---------------------------------------------------------------------------
def process_data(domain: str, raw_data: Dict[str, Any], console: Console, logger) -> Dict[str, Any]:
    """Elabora i dati grezzi."""
    try:
        processor = AuditProcessor(config_path=DEFAULT_CONFIG_PATH)
        processed = processor.process(domain, raw_data)
        
        console.print(f"  [{STYLES['success']}]{ICONS['success']} Righe Audit generate: {len(processed['audit'])}[/{STYLES['success']}]")
        console.print(f"  [{STYLES['success']}]{ICONS['success']} Righe Checklist generate: {len(processed['checklist'])}[/{STYLES['success']}]")
        console.print(f"  [{STYLES['success']}]{ICONS['success']} Health Score: {processed['summary']['health_score']}/100[/{STYLES['success']}]")
        
        # Verifica check PageSpeed
        ps_checks = [r for r in processed['audit'] if r.get('ID Audit', '').startswith('U-')]
        console.print(f"  [{STYLES['success']}]{ICONS['success']} Check PageSpeed trovati: {len(ps_checks)}[/{STYLES['success']}]")
        for check in ps_checks:
            console.print(f"    - {check.get('ID Audit')}: {check.get('Elemento Analizzato')} - {check.get('Stato')}")
        
        return processed
        
    except Exception as e:
        logger.error(f"Errore nell'elaborazione: {e}")
        logger.error(traceback.format_exc())
        console.print(f"  [{STYLES['error']}]{ICONS['error']} Errore nell'elaborazione: {e}[/{STYLES['error']}]")
        sys.exit(1)


# ---------------------------------------------------------------------------
# HELPER 10 — Generazione report
# ---------------------------------------------------------------------------
def generate_report(processed: Dict[str, Any], domain: str, raw_data: Dict[str, Any], console: Console, logger) -> str:
    """Genera il report Excel."""
    # Crea directory reports se non esiste
    os.makedirs(REPORTS_DIR, exist_ok=True)
    
    # Genera nome file con timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    domain_clean = domain.replace('https://', '').replace('http://', '').replace('/', '_')
    output_file = f"{REPORTS_DIR}/AuditSEO_{domain_clean}_{timestamp}.xlsx"
    
    try:
        generator = ExcelGenerator()
        generator.generate(processed, output_file, raw_data)  # ← raw_data passato al generator
        console.print(f"\n[{STYLES['success']}]✅ Completato![/{STYLES['success']}]")
        console.print(f"{ICONS['folder']} Report salvato in: [{STYLES['file_path']}]{output_file}[/{STYLES['file_path']}]")
        return output_file
        
    except Exception as e:
        logger.error(f"Errore nella generazione del report: {e}")
        logger.error(traceback.format_exc())
        console.print(f"  [{STYLES['error']}]{ICONS['error']} Errore nella generazione del report: {e}[/{STYLES['error']}]")
        sys.exit(1)


# ---------------------------------------------------------------------------
# HELPER 11 — Visualizzazione statistiche cache finali
# ---------------------------------------------------------------------------
def display_final_cache_stats(collectors: Dict[str, Any], console: Console):
    """Mostra le statistiche finali della cache."""
    console.print()
    pagespeed_collector = collectors.get("pagespeed")
    
    if pagespeed_collector and hasattr(pagespeed_collector, 'get_cache_stats'):
        cache_stats = pagespeed_collector.get_cache_stats()
        
        table = Table(title="📊 Statistiche Cache PageSpeed")
        table.add_column("Metrica", style="cyan")
        table.add_column("Valore", style="green")
        
        table.add_row("Cache Hits", str(cache_stats.get('hits', 0)))
        table.add_row("Cache Misses", str(cache_stats.get('misses', 0)))
        table.add_row("API Calls Risparmiate", str(cache_stats.get('hits', 0)))
        
        console.print(table)


# ---------------------------------------------------------------------------
# HELPER 12 — Visualizzazione header audit
# ---------------------------------------------------------------------------
def display_audit_header(domain: str, console: Console):
    """Mostra l'header dell'audit."""
    console.print(Panel(
        f"[{STYLES['title']}]{ICONS['rocket']} SEO Audit Automation Tool[/{STYLES['title']}]\n\n"
        f"  Dominio: [{STYLES['domain']}]{domain}[/{STYLES['domain']}]\n"
        f"  Data: [{STYLES['date']}]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/{STYLES['date']}]",
        title="Audit SEO",
        border_style="blue"
    ))


# ---------------------------------------------------------------------------
# FUNZIONE PRINCIPALE
# ---------------------------------------------------------------------------
def main(domain: Optional[str] = None, clear_cache_flag: bool = False, cache_stats_flag: bool = False):
    """Funzione principale per l'audit SEO."""
    
    # Gestione comandi cache
    if cache_stats_flag:
        display_cache_stats(domain)
        return
    
    if clear_cache_flag:
        clear_cache(domain)
        return
    
    # Verifica dominio
    if not domain:
        print("❌ Errore: Dominio non specificato")
        print("Uso: python main.py <dominio>")
        print("Esempio: python main.py https://example.com")
        sys.exit(1)
    
    # Normalizza dominio
    domain = normalize_domain(domain)
    
    # Setup
    console = Console()
    logger = setup_logger("Main")
    config = load_config()
    
    # Header
    display_audit_header(domain, console)
    
    # ============================================
    # FASE 1: RACCOLTA DATI
    # ============================================
    console.print(f"\n[{STYLES['phase']}]{ICONS['package']} Fase 1: Raccolta dati[/{STYLES['phase']}]")
    
    collectors = initialize_collectors(config)
    raw_data = collect_all_data(collectors, domain, console, logger)  # ← raw_data definito qui
    
    # Verifica dati raccolti
    display_data_verification(collectors, raw_data, console)
    
    # ============================================
    # FASE 2: ELABORAZIONE DATI
    # ============================================
    console.print(f"\n[{STYLES['phase']}]{ICONS['refresh']} Fase 2: Elaborazione dati[/{STYLES['phase']}]")
    
    processed = process_data(domain, raw_data, console, logger)
    
    # ============================================
    # FASE 3: GENERAZIONE REPORT
    # ============================================
    console.print(f"\n[{STYLES['phase']}]{ICONS['chart']} Fase 3: Generazione report[/{STYLES['phase']}]")
    
    # ← raw_data passato a generate_report
    generate_report(processed, domain, raw_data, console, logger)
    
    # Statistiche cache finali
    display_final_cache_stats(collectors, console)


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser(
            description="SEO Audit Automation Tool - Genera report SEO completi",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Esempi:
  python main.py https://example.com              # Esegui audit completo
  python main.py --cache-stats                    # Mostra statistiche cache
  python main.py --clear-cache                    # Cancella tutta la cache
  python main.py --clear-cache https://example.com # Cancella cache per dominio
            """
        )
        
        parser.add_argument(
            "domain",
            nargs="?",
            help="Dominio da analizzare (es. https://example.com)"
        )
        
        parser.add_argument(
            "--clear-cache",
            action="store_true",
            help="Cancella la cache"
        )
        
        parser.add_argument(
            "--cache-stats",
            action="store_true",
            help="Mostra statistiche della cache"
        )
        
        args = parser.parse_args()
        
        if not args.domain and not args.clear_cache and not args.cache_stats:
            parser.print_help()
            sys.exit(1)
        
        main(
            domain=args.domain,
            clear_cache_flag=args.clear_cache,
            cache_stats_flag=args.cache_stats
        )
        
    except Exception as e:
        print(f"\n❌ Errore fatale: {e}")
        print(traceback.format_exc())
        sys.exit(1)