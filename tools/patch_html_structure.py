"""
Sostituisce il blocco H-05..H-08 in _process_html con la chiamata
a HTMLStructureRules. Mantiene inline U-03, H-09, H-10, T-04, C-01.

Ridefinisce `lang` inline per H-10 (che altrimenti non avrebbe la variabile).
Backup automatico in processors/audit_processor.py.bak
"""
import os
import shutil
import sys

TARGET = "processors/audit_processor.py"
BACKUP = TARGET + ".bak"

START_MARKER = (
    "        images = homepage.get('images', [])\n"
    "        total_images = len(images)\n"
)
END_MARKER = "        viewport = homepage.get('viewport', '')\n"

REPLACEMENT = (
    "        # H-05..H-08 → HTMLStructureRules (v2.4.0)\n"
    "        from processors.rules.html_structure_rules import HTMLStructureRules\n"
    "        structure_rule = HTMLStructureRules(self.config)\n"
    "        rows.extend(structure_rule.evaluate({\"html\": data}, domain))\n"
    "\n"
    "        # `lang` serve a H-10 (inline), quindi lo ridefiniamo qui\n"
    "        lang = homepage.get('lang', '')\n"
    "\n"
)

def main():
    if not os.path.exists(TARGET):
        print(f"✗ File non trovato: {TARGET}")
        sys.exit(1)

    with open(TARGET, "r", encoding="utf-8") as f:
        content = f.read()

    start_idx = content.find(START_MARKER)
    if start_idx == -1:
        print("✗ Marker di inizio non trovato")
        sys.exit(1)

    if content.find(START_MARKER, start_idx + 1) != -1:
        print("✗ Marker di inizio ambiguo (appare 2+ volte)")
        sys.exit(1)

    end_idx = content.find(END_MARKER, start_idx)
    if end_idx == -1:
        print("✗ Marker di fine non trovato dopo l'inizio")
        sys.exit(1)

    block = content[start_idx:end_idx]
    print(f"Blocco trovato: {len(block)} caratteri, {block.count(chr(10))} righe")
    print("--- prime 200 caratteri ---")
    print(block[:200])
    print("--- ultimi 200 caratteri ---")
    print(block[-200:])

    required = ['"H-05"', '"H-06"', '"H-07"', '"H-08"']
    forbidden = ['"U-03"', '"H-09"', '"H-10"', '"T-04"', '"C-01"', 'viewport =']

    for must in required:
        if must not in block:
            print(f"✗ Sanity: manca {must}")
            sys.exit(1)

    for bad in forbidden:
        if bad in block:
            print(f"✗ Sanity: {bad} presente nel blocco")
            sys.exit(1)

    if block.count("\n") > 100:
        print(f"✗ Sanity: blocco troppo grande ({block.count(chr(10))} righe)")
        sys.exit(1)

    print("✓ Sanity check passato")

    confirm = input("Procedere con la sostituzione? [y/N] ").strip().lower()
    if confirm != "y":
        print("Annullato.")
        sys.exit(0)

    shutil.copy2(TARGET, BACKUP)
    print(f"✓ Backup creato: {BACKUP}")

    new_content = content[:start_idx] + REPLACEMENT + content[end_idx:]

    with open(TARGET, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"✓ File aggiornato")
    print(f"  Righe prima: {content.count(chr(10)) + 1}")
    print(f"  Righe dopo:  {new_content.count(chr(10)) + 1}")


if __name__ == "__main__":
    main()