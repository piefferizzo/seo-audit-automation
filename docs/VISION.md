# Vision — SEO Audit Automation

Documento di visione architetturale. Definisce dove il progetto vuole arrivare, cosa è in scope e cosa **non** lo è.

Il codice attuale è descritto nel [README](../README.md). Questo documento descrive il **target**, non lo stato presente.

---

## Indice

- [Obiettivi](#obiettivi)
- [Architettura attuale](#architettura-attuale)
- [Architettura target](#architettura-target)
- [SEO Data Model](#seo-data-model)
- [Prioritizzazione](#prioritizzazione)
- [Action Plan](#action-plan)
- [AI Layer](#ai-layer)
- [Output futuri](#output-futuri)
- [Roadmap](#roadmap)
- [Cosa NON è previsto](#cosa-non-è-previsto)
- [Principi architetturali](#principi-architetturali)
- [Visione](#visione)

---

## Obiettivi

Il progetto ha quattro obiettivi principali.

### 1. Automatizzare la raccolta dati

Raccogliere automaticamente dati SEO da:

- sito web
- crawler
- Google Search Console
- Google Analytics 4
- PageSpeed Insights
- WHOIS / RDAP
- SEMrush
- analisi GEO
- input manuali

### 2. Ridurre il lavoro manuale

Evitare che l'analista debba:

- raccogliere dati manualmente da piattaforme diverse
- copiare metriche in fogli Excel
- controllare manualmente ogni URL
- ripetere gli stessi controlli tecnici
- costruire ogni volta la stessa struttura di audit

### 3. Standardizzare l'audit

Applicare regole coerenti e ripetibili per identificare:

- problemi tecnici
- problemi on-page
- problemi di performance
- problemi di indicizzazione
- problemi di contenuto
- problemi di immagini
- problemi di visibilità organica
- problemi relativi a GA4
- problemi relativi a GEO / AI visibility
- opportunità SEO

### 4. Trasformare i dati in azioni

L'obiettivo finale non è produrre un elenco di errori.

Il sistema deve arrivare a rispondere a una domanda più utile:

> **Quali sono le cose più importanti da correggere e perché?**

---

## Architettura attuale

L'architettura attuale segue questo modello:

```text
WEBSITE
   │
   ├── HTML / Crawler
   ├── PageSpeed
   ├── Google Search Console
   ├── Google Analytics 4
   ├── WHOIS / RDAP
   ├── GEO
   └── Manual
          │
          ▼
     COLLECTORS
          │
          ▼
       RAW DATA
          │
          ▼
   AUDIT PROCESSOR
          │
          ├── Audit
          ├── Checklist
          ├── Drilldown
          └── Summary
          │
          ▼
   EXCEL GENERATOR
          │
          ▼
       XLSX