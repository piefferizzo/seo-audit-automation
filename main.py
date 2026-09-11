#!/usr/bin/env python3
"""
SEO Audit Automation Tool
Main script per eseguire audit SEO completi con multipli collector.
"""

import sys
import os
import argparse
import yaml
import traceback
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

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


def load_config(config_path: str = "config.yaml") -> dict:
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


def show_cache_stats(domain: str = None):
    """Mostra le statistiche della cache."""
    console = Console()
    cache = CacheManager(cache_dir="cache")
    stats = cache.get_stats()
    
    table = Table(title="📊 Statistiche Cache PageSpeed")
    table.add_column("Metrica", style="cyan")
    table.add_column("Valore", style="green")
    
    table.add_row("Cache Hits", str(stats.get('hits', 0)))
    table.add_row("Cache Misses", str(stats.get('misses', 0)))
    table.add_row("API Calls Risparmiate", str(stats.get('hits', 0)))
    
    console.print(table)


def clear_cache(domain: str = None):
    """Pulisce la cache."""
    console = Console()
    cache = CacheManager(cache_dir="cache")
    
    if domain:
        cache.clear(domain)
        console.print(f"[green]✅ Cache PageSpeed cancellata per {domain}[/green]")
    else:
        cache.clear()
        console.print("[green]✅ Tutta la cache è stata cancellata[/green]")


def main(domain: str = None, clear_cache_flag: bool = False, cache_stats_flag: bool = False):
    """Funzione principale per l'audit SEO."""
    
    # Gestione comandi cache
    if cache_stats_flag:
        show_cache_stats(domain)
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
    if not domain.startswith('http'):
        domain = f"https://{domain}"
    
    # Setup
    console = Console()
    logger = setup_logger("Main")
    config = load_config()
    
    console.print(Panel(
        f"[bold cyan]🚀 SEO Audit Automation Tool[/bold cyan]\n\n"
        f"  Dominio: [green]{domain}[/green]\n"
        f"  Data: [yellow]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/yellow]",
        title="Audit SEO",
        border_style="blue"
    ))
    
    # Inizializza collector
    console.print("\n[bold]📦 Fase 1: Raccolta dati[/bold]")
    
    collectors = {
        "pagespeed": PageSpeedCollector(config),
        "gsc": GSCCollector(config),
        "ga4": GA4Collector(config),
        "html": HTMLCollector(config),
        "whois": WhoisCollector(config),
        #"semrush": SemrushCollector(config),
        "manual": ManualCollector(config),
    }
    
    # Raccolta dati
    raw_data = {}
    
    for name, collector in collectors.items():
        try:
            if collector.is_available():
                console.print(f"  [cyan]⠋[/cyan] Raccolta dati {name}...")
                raw_data[name] = collector.collect(domain)
                console.print(f"  [green]✓[/green] {name} completato")
            else:
                console.print(f"  [yellow]⚠[/yellow] {name} non disponibile")
        except Exception as e:
            logger.error(f"Errore nel collector {name}: {e}")
            logger.error(traceback.format_exc())
            console.print(f"  [red]✗[/red] {name} fallito: {e}")
    
    # Verifica dati raccolti
    console.print("\n[bold]🔍 Verifica dati raccolti[/bold]")
    for name in collectors.keys():
        status = "✓" if raw_data.get(name) else "✗"
        color = "green" if raw_data.get(name) else "red"
        console.print(f"  [{color}]{status}[/{color}] {name}: {bool(raw_data.get(name))}")
    
    # Elaborazione dati
    console.print("\n[bold]🔄 Fase 2: Elaborazione dati[/bold]")
    
    try:
        processor = AuditProcessor(config_path="config.yaml")
        processed = processor.process(domain, raw_data)
        
        console.print(f"  [green]✓[/green] Righe Audit generate: {len(processed['audit'])}")
        console.print(f"  [green]✓[/green] Righe Checklist generate: {len(processed['checklist'])}")
        console.print(f"  [green]✓[/green] Health Score: {processed['summary']['health_score']}/100")
        
        # Verifica check PageSpeed
        ps_checks = [r for r in processed['audit'] if r.get('ID Audit', '').startswith('U-')]
        console.print(f"  [green]✓[/green] Check PageSpeed trovati: {len(ps_checks)}")
        for check in ps_checks:
            console.print(f"    - {check.get('ID Audit')}: {check.get('Elemento Analizzato')} - {check.get('Stato')}")
        
    except Exception as e:
        logger.error(f"Errore nell'elaborazione: {e}")
        logger.error(traceback.format_exc())
        console.print(f"  [red]✗ Errore nell'elaborazione: {e}[/red]")
        sys.exit(1)
    
    # Generazione report
    console.print("\n[bold]📊 Fase 3: Generazione report[/bold]")
    
    # Crea directory reports se non esiste
    os.makedirs("reports", exist_ok=True)
    
    # Genera nome file con timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    domain_clean = domain.replace('https://', '').replace('http://', '').replace('/', '_')
    output_file = f"reports/AuditSEO_{domain_clean}_{timestamp}.xlsx"
    
    try:
        generator = ExcelGenerator()
        generator.generate(processed, output_file)
        console.print(f"\n[green]✅ Completato![/green]")
        console.print(f"📁 Report salvato in: [bold cyan]{output_file}[/bold cyan]")
    except Exception as e:
        logger.error(f"Errore nella generazione del report: {e}")
        logger.error(traceback.format_exc())
        console.print(f"  [red]✗ Errore nella generazione del report: {e}[/red]")
        sys.exit(1)
    
    # Mostra statistiche cache
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