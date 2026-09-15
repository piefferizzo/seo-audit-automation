# SEO Audit Automation

> Motore Python per l'automazione di audit SEO tecnici, on-page, di performance, analytics e visibilità organica.

[![Version](https://img.shields.io/badge/version-2.4.0-blue.svg)](#)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](#)
[![Status](https://img.shields.io/badge/status-MVP%20internal%20tool-yellow.svg)](#)

SEO Audit Automation raccoglie dati SEO da fonti multiple, li elabora con regole deterministiche e produce un report Excel multi-foglio pensato per il lavoro di consulenza.

**Obiettivo**: ridurre il lavoro manuale ripetitivo dell'analista, standardizzare i controlli e trasformare dati eterogenei in evidenze operative.

---

## Indice

- [Quick Start](#quick-start)
- [Cosa produce](#cosa-produce)
- [Installazione](#installazione)
- [Configurazione](#configurazione)
- [Credenziali](#credenziali)
- [Utilizzo](#utilizzo)
- [Focus Keywords](#focus-keywords)
- [Struttura del progetto](#struttura-del-progetto)
- [Fonti dati](#fonti-dati)
- [Troubleshooting](#troubleshooting)
- [Roadmap](#roadmap)
- [License](#license)

---

## Quick Start

```bash
# 1. Clona e installa
git clone https://github.com/piefferizzo/seo-audit-automation.git
cd seo-audit-automation
pip install -r requirements.txt
playwright install

# 2. Copia i file di esempio e compila
cp .env.example .env
cp config.yaml.example config.yaml
# → modifica .env e config.yaml con le tue credenziali

# 3. Metti il Service Account GCP in credentials/
#    (vedi sezione Credenziali)

# 4. Esegui l'audit
python3 main.py esempio.com

# 5. Apri il report
open reports/AuditSEO_esempio.com_*.xlsx