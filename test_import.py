#!/usr/bin/env python3
"""Test minimale per identificare errori di importazione."""

import sys
import traceback

print("🔍 Inizio test importazioni...")

try:
    print("1. Import yaml...")
    import yaml
    print("   ✓ yaml OK")
except Exception as e:
    print(f"   ✗ yaml FALLITO: {e}")
    traceback.print_exc()

try:
    print("2. Import collectors...")
    from collectors.pagespeed_collector import PageSpeedCollector
    print("   ✓ PageSpeedCollector OK")
except Exception as e:
    print(f"   ✗ PageSpeedCollector FALLITO: {e}")
    traceback.print_exc()

try:
    print("3. Import GSCCollector...")
    from collectors.gsc_collector import GSCCollector
    print("   ✓ GSCCollector OK")
except Exception as e:
    print(f"   ✗ GSCCollector FALLITO: {e}")
    traceback.print_exc()

try:
    print("4. Import GA4Collector...")
    from collectors.ga4_collector import GA4Collector
    print("   ✓ GA4Collector OK")
except Exception as e:
    print(f"   ✗ GA4Collector FALLITO: {e}")
    traceback.print_exc()

try:
    print("5. Import HTMLCollector...")
    from collectors.html_collector import HTMLCollector
    print("   ✓ HTMLCollector OK")
except Exception as e:
    print(f"   ✗ HTMLCollector FALLITO: {e}")
    traceback.print_exc()

try:
    print("6. Import WhoisCollector...")
    from collectors.whois_collector import WhoisCollector
    print("   ✓ WhoisCollector OK")
except Exception as e:
    print(f"   ✗ WhoisCollector FALLITO: {e}")
    traceback.print_exc()

try:
    print("7. Import SemrushCollector...")
    from collectors.semrush_collector import SemrushCollector
    print("   ✓ SemrushCollector OK")
except Exception as e:
    print(f"   ✗ SemrushCollector FALLITO: {e}")
    traceback.print_exc()

try:
    print("8. Import ManualCollector...")
    from collectors.manual_collector import ManualCollector
    print("   ✓ ManualCollector OK")
except Exception as e:
    print(f"   ✗ ManualCollector FALLITO: {e}")
    traceback.print_exc()

try:
    print("9. Import AuditProcessor...")
    from processors.audit_processor import AuditProcessor
    print("   ✓ AuditProcessor OK")
except Exception as e:
    print(f"   ✗ AuditProcessor FALLITO: {e}")
    traceback.print_exc()

try:
    print("10. Import ExcelGenerator...")
    from generators.excel_generator import ExcelGenerator
    print("   ✓ ExcelGenerator OK")
except Exception as e:
    print(f"   ✗ ExcelGenerator FALLITO: {e}")
    traceback.print_exc()

try:
    print("11. Import CacheManager...")
    from utils.cache import CacheManager
    print("   ✓ CacheManager OK")
except Exception as e:
    print(f"   ✗ CacheManager FALLITO: {e}")
    traceback.print_exc()

print("\n✅ Test completato!")