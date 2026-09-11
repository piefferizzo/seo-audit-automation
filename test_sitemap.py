#!/usr/bin/env python3
"""Script di test per verificare il rilevamento sitemap."""

import requests
import re
from bs4 import BeautifulSoup

def test_sitemap(domain):
    """Testa il rilevamento sitemap con metodi multipli."""
    print(f"\n{'='*70}")
    print(f"  TEST SITEMAP: {domain}")
    print(f"{'='*70}\n")
    
    # Test 1: robots.txt
    print("1. Test robots.txt...")
    try:
        response = requests.get(f"{domain}/robots.txt", timeout=10)
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            content = response.text
            print(f"   Contenuto:\n{content[:500]}")
            
            # Cerca sitemap
            sitemap_url = ''
            for line in content.split('\n'):
                if line.strip().lower().startswith('sitemap:'):
                    sitemap_url = line.split(':', 1)[1].strip()
                    break
            
            if sitemap_url:
                print(f"   ✓ Sitemap trovata: {sitemap_url}")
            else:
                print(f"   ✗ Nessuna sitemap dichiarata")
        else:
            print(f"   ✗ robots.txt non accessibile")
    except Exception as e:
        print(f"   ✗ Errore: {e}")
    
    # Test 2: URL sitemap comuni
    print("\n2. Test URL sitemap comuni...")
    sitemap_candidates = [
        f"{domain}/sitemap.xml",
        f"{domain}/sitemap_index.xml",
        f"{domain}/wp-sitemap.xml",
        f"{domain}/sitemap/sitemap.xml",
        f"{domain}/sitemap-index.xml"
    ]
    
    for candidate in sitemap_candidates:
        print(f"\n   → Testing: {candidate}")
        try:
            response = requests.get(candidate, timeout=10)
            print(f"     Status: {response.status_code}")
            
            if response.status_code == 200:
                content = response.text
                print(f"     Dimensione: {len(content)} bytes")
                print(f"     Prime 200 caratteri:\n     {content[:200]}")
                
                # Conta URL
                urls = re.findall(r'<loc>(.*?)</loc>', content)
                print(f"     ✓ Trovate {len(urls)} URL")
                
                # Controlla se è sitemap index
                if '<sitemapindex' in content:
                    print(f"     🗂️  È un sitemap index")
                    sub_sitemaps = re.findall(r'<loc>(.*?)</loc>', content)
                    print(f"     📋 {len(sub_sitemaps)} sotto-sitemap")
                elif '<urlset' in content:
                    print(f"     📄 È una sitemap normale")
                else:
                    print(f"     ⚠️  Formato non standard")
            else:
                print(f"     ✗ Non accessibile")
        except Exception as e:
            print(f"     ✗ Errore: {e}")
    
    # Test 3: Con user-agent Googlebot
    print("\n3. Test con User-Agent Googlebot...")
    headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'
    }
    
    for candidate in sitemap_candidates[:2]:  # Testa solo i primi 2
        print(f"\n   → Testing: {candidate}")
        try:
            response = requests.get(candidate, headers=headers, timeout=10)
            print(f"     Status: {response.status_code}")
            
            if response.status_code == 200:
                content = response.text
                urls = re.findall(r'<loc>(.*?)</loc>', content)
                print(f"     ✓ Trovate {len(urls)} URL")
            else:
                print(f"     ✗ Non accessibile")
        except Exception as e:
            print(f"     ✗ Errore: {e}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Uso: python test_sitemap.py <dominio>")
        print("Esempio: python test_sitemap.py https://passionevo.com")
        sys.exit(1)
    
    domain = sys.argv[1]
    if not domain.startswith('http'):
        domain = f"https://{domain}"
    
    test_sitemap(domain)