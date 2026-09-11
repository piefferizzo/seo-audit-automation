#!/usr/bin/env python3
"""Test completo del flusso di esecuzione con TUTTI i collector."""

import sys
import traceback
import yaml
from datetime import datetime

print("=" * 70)
print("🔍 TEST FLUSSO COMPLETO - ESECUZIONE TUTTI I COLLECTOR")
print("=" * 70)

# Step 1: Carica configurazione
print("\n[1/7] Caricamento configurazione...")
try:
    with open('config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    print("  ✓ Configurazione caricata")
    print(f"  - API key PageSpeed presente: {bool(config.get('PAGE_SPEED_API_KEY'))}")
    print(f"  - File GSC: {config.get('GSC_SERVICE_ACCOUNT_FILE')}")
except Exception as e:
    print(f"  ✗ ERRORE: {e}")
    traceback.print_exc()
    sys.exit(1)

# Step 2: Inizializza collector
print("\n[2/7] Inizializzazione collector...")
try:
    from collectors.pagespeed_collector import PageSpeedCollector
    from collectors.gsc_collector import GSCCollector
    from collectors.ga4_collector import GA4Collector
    from collectors.html_collector import HTMLCollector
    from collectors.whois_collector import WhoisCollector
    #from collectors.semrush_collector import SemrushCollector
    from collectors.manual_collector import ManualCollector
    
    collectors = {
        "pagespeed": PageSpeedCollector(config),
        "gsc": GSCCollector(config),
        "ga4": GA4Collector(config),
        "html": HTMLCollector(config),
        "whois": WhoisCollector(config),
        #"semrush": SemrushCollector(config),
        "manual": ManualCollector(config),
    }
    print("  ✓ Tutti i collector inizializzati")
    for name, collector in collectors.items():
        print(f"    - {name}: disponibile={collector.is_available()}")
except Exception as e:
    print(f"  ✗ ERRORE: {e}")
    traceback.print_exc()
    sys.exit(1)

# Step 3: Esegui TUTTI i collector
print("\n[3/7] Esecuzione TUTTI i collector...")
domain = "https://arkys.agency"
raw_data = {}

for name, collector in collectors.items():
    try:
        print(f"\n  🔍 Esecuzione {name}...")
        if collector.is_available():
            raw_data[name] = collector.collect(domain)
            print(f"  ✓ {name} completato")
            
            # Verifica dati raccolti
            if name == 'pagespeed':
                print(f"    - mobile presente: {'mobile' in raw_data[name]}")
                print(f"    - desktop presente: {'desktop' in raw_data[name]}")
                if 'mobile' in raw_data[name]:
                    print(f"    - performance score: {raw_data[name]['mobile'].get('performance_score', 'N/A')}")
            elif name == 'gsc':
                print(f"    - verification: {raw_data[name].get('verification', 'N/A')}")
                print(f"    - performance rows: {len(raw_data[name].get('performance', []))}")
            elif name == 'html':
                print(f"    - homepage presente: {'homepage' in raw_data[name]}")
                print(f"    - drilldown presente: {'drilldown' in raw_data[name]}")
        else:
            print(f"  ⚠ {name} non disponibile")
    except Exception as e:
        print(f"  ✗ ERRORE in {name}: {e}")
        traceback.print_exc()

# Step 4: Verifica dati raccolti
print("\n[4/7] Verifica dati raccolti...")
print(f"  - pagespeed: {bool(raw_data.get('pagespeed'))}")
print(f"  - gsc: {bool(raw_data.get('gsc'))}")
print(f"  - ga4: {bool(raw_data.get('ga4'))}")
print(f"  - html: {bool(raw_data.get('html'))}")
print(f"  - whois: {bool(raw_data.get('whois'))}")
print(f"  - semrush: {bool(raw_data.get('semrush'))}")
print(f"  - manual: {bool(raw_data.get('manual'))}")

# Step 5: Test processor
print("\n[5/7] Test processor...")
try:
    from processors.audit_processor import AuditProcessor
    processor = AuditProcessor(config_path="config.yaml")
    print("  ✓ AuditProcessor creato")
except Exception as e:
    print(f"  ✗ ERRORE: {e}")
    traceback.print_exc()
    sys.exit(1)

# Step 6: Esegui processing
print("\n[6/7] Esecuzione processing...")
try:
    processed = processor.process(domain, raw_data)
    print("  ✓ Processing completato")
    print(f"  - Righe audit: {len(processed.get('audit', []))}")
    print(f"  - Righe checklist: {len(processed.get('checklist', []))}")
    print(f"  - Health score: {processed.get('summary', {}).get('health_score', 'N/A')}")
    print(f"  - Drilldown presente: {'drilldown' in processed}")
    
    # Verifica check PageSpeed
    audit_rows = processed.get('audit', [])
    ps_checks = [r for r in audit_rows if r.get('ID Audit', '').startswith('U-')]
    print(f"  - Check PageSpeed trovati: {len(ps_checks)}")
    for check in ps_checks:
        print(f"    - {check.get('ID Audit')}: {check.get('Elemento Analizzato')} - {check.get('Stato')}")
    
except Exception as e:
    print(f"  ✗ ERRORE: {e}")
    traceback.print_exc()
    sys.exit(1)

# Step 7: Test generator
print("\n[7/7] Test generator...")
try:
    from generators.excel_generator import ExcelGenerator
    generator = ExcelGenerator()
    print("  ✓ ExcelGenerator creato")
    
    # Genera report
    output_file = f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    generator.generate(processed, output_file)
    print(f"  ✓ Report generato: {output_file}")
except Exception as e:
    print(f"  ✗ ERRORE: {e}")
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 70)
print("✅ TEST COMPLETATO CON SUCCESSO!")
print("=" * 70)
print(f"\n📁 Report di test salvato in: {output_file}")