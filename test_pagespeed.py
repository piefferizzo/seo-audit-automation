#!/usr/bin/env python3
"""Test diagnostico per PageSpeed Collector."""

import yaml
from collectors.pagespeed_collector import PageSpeedCollector

# Carica configurazione
with open('config.yaml', 'r') as f:
    config = yaml.safe_load(f)

# Inizializza collector
collector = PageSpeedCollector(config)

# Verifica disponibilità
print(f"API Key configurata: {bool(collector.api_key)}")
print(f"API Key (primi 10 char): {collector.api_key[:10] if collector.api_key else 'N/A'}...")
print(f"Collector disponibile: {collector.is_available()}")

# Esegui test
print("\n🔍 Esecuzione test PageSpeed...")
result = collector.collect("https://arkys.agency")

print(f"\n📊 Risultato raccolto:")
print(f"  - Chiavi presenti: {list(result.keys())}")
print(f"  - Mobile presente: {'mobile' in result}")
print(f"  - Desktop presente: {'desktop' in result}")

if 'mobile' in result:
    mobile = result['mobile']
    print(f"\n📱 Dati Mobile:")
    print(f"  - Performance Score: {mobile.get('performance_score', 'N/A')}")
    print(f"  - LCP: {mobile.get('lcp', 'N/A')}s")
    print(f"  - FCP: {mobile.get('fcp', 'N/A')}s")
    print(f"  - CLS: {mobile.get('cls', 'N/A')}")
else:
    print("\n❌ Nessun dato mobile raccolto!")

if 'desktop' in result:
    desktop = result['desktop']
    print(f"\n💻 Dati Desktop:")
    print(f"  - Performance Score: {desktop.get('performance_score', 'N/A')}")
    print(f"  - LCP: {desktop.get('lcp', 'N/A')}s")
    print(f"  - FCP: {desktop.get('fcp', 'N/A')}s")
    print(f"  - CLS: {desktop.get('cls', 'N/A')}")
else:
    print("\n❌ Nessun dato desktop raccolto!")

# Verifica cache
print(f"\n📦 Statistiche Cache:")
stats = collector.get_cache_stats()
print(f"  - Cache Hits: {stats.get('hits', 0)}")
print(f"  - Cache Misses: {stats.get('misses', 0)}")