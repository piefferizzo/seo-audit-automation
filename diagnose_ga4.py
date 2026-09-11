#!/usr/bin/env python3
"""Diagnosi problema GA4 collector."""

import os
import yaml

print("=" * 70)
print("🔍 DIAGNOSI GA4 COLLECTOR")
print("=" * 70)

# 1. Verifica config.yaml
print("\n[1/5] Verifica config.yaml...")
try:
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    ga4_file = config.get('GA4_CREDENTIALS_FILE', 'credentials/ga4-credentials.json')
    print(f"  ✓ GA4_CREDENTIALS_FILE: {ga4_file}")
except Exception as e:
    print(f"  ✗ Errore config.yaml: {e}")
    exit(1)

# 2. Verifica esistenza file credenziali
print("\n[2/5] Verifica file credenziali...")
if os.path.exists(ga4_file):
    print(f"  ✓ File esiste: {ga4_file}")
else:
    print(f"  ✗ File NON esiste: {ga4_file}")
    print(f"  💡 Soluzione: Crea il file o correggi il path in config.yaml")
    exit(1)

# 3. Verifica contenuto credenziali
print("\n[3/5] Verifica contenuto credenziali...")
try:
    import json
    with open(ga4_file, 'r') as f:
        creds = json.load(f)
    
    required_fields = ['type', 'project_id', 'private_key_id', 'private_key', 'client_email']
    missing = [f for f in required_fields if f not in creds]
    
    if missing:
        print(f"  ✗ Campi mancanti: {missing}")
    else:
        print(f"  ✓ Credenziali complete")
        print(f"    - type: {creds.get('type')}")
        print(f"    - project_id: {creds.get('project_id')}")
        print(f"    - client_email: {creds.get('client_email')}")
except Exception as e:
    print(f"  ✗ Errore lettura credenziali: {e}")
    exit(1)

# 4. Verifica ga4_properties.yaml
print("\n[4/5] Verifica ga4_properties.yaml...")
try:
    with open('ga4_properties.yaml', 'r') as f:
        properties = yaml.safe_load(f)
    
    print(f"  ✓ File esiste con {len(properties)} domini")
    
    # Cerca arkys.agency
    domain = 'arkys.agency'
    if domain in properties:
        prop_id = properties[domain].get('property_id')
        print(f"  ✓ {domain} trovato: property_id={prop_id}")
    else:
        print(f"  ✗ {domain} NON trovato in ga4_properties.yaml")
        print(f"  💡 Soluzione: Aggiungi {domain} a ga4_properties.yaml")
except Exception as e:
    print(f"  ✗ Errore ga4_properties.yaml: {e}")
    exit(1)

# 5. Test collector
print("\n[5/5] Test collector GA4...")
try:
    from collectors.ga4_collector import GA4Collector
    
    collector = GA4Collector(config)
    print(f"  ✓ Collector inizializzato")
    print(f"    - is_available(): {collector.is_available()}")
    print(f"    - credentials_file: {collector.credentials_file}")
    
    # Test raccolta dati
    result = collector.collect(f"https://{domain}")
    if result:
        print(f"  ✓ Dati raccolti: {list(result.keys())}")
    else:
        print(f"  ✗ Nessun dato raccolto")
except Exception as e:
    print(f"  ✗ Errore collector: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
print("✅ DIAGNOSI COMPLETATA")
print("=" * 70)