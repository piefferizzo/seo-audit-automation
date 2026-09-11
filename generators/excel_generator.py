import pandas as pd
from typing import Dict, List
from openpyxl import load_workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from datetime import datetime

class ExcelGenerator:
    """Genera il report Excel dell'audit SEO nel formato target."""
    
    def __init__(self):
        self.state_colors = {
            "OK": PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid"),
            "WARN": PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid"),
            "FAIL": PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid"),
            "INFO": PatternFill(start_color="BDD7EE", end_color="BDD7EE", fill_type="solid"),
            "N/A": PatternFill(start_color="D9D9D9", end_color="D9D9D9", fill_type="solid"),
        }
        
        self.priority_colors = {
            1: PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid"),
            2: PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid"),
            3: PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid"),
        }
    
    def generate(self, processed_data: Dict, output_path: str):
        """Genera il file Excel completo."""
        
        summary = processed_data['summary']
        audit_rows = processed_data['audit']
        checklist_rows = processed_data['checklist']
        drilldown = processed_data.get('drilldown', {})
        
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            # 1. Executive Summary (RIPRISTINATO)
            self._write_summary(writer, summary, audit_rows)
            
            # 2. AUDIT (RIPRISTINATO)
            self._write_audit(writer, audit_rows)
            
            # 3. Checklist principale
            self._write_checklist(writer, checklist_rows, audit_rows)
            
            # 4. HTML - IMG
            self._write_html_img(writer, drilldown)
            
            # 5. Title
            self._write_title(writer, drilldown)
            
            # 6. Description
            self._write_description(writer, drilldown)
            
            # 7. HTML - HEADINGS
            self._write_headings(writer, drilldown)
            
            # 8. Consigli generali
            self._write_consigli(writer)
        
        # Formatta il file
        self._format_excel(output_path)
    
    def _write_summary(self, writer, summary: Dict, audit_rows: List[Dict]):
        """Scrive il foglio Executive Summary."""
        by_category = {}
        for row in audit_rows:
            cat = row['Categoria']
            if cat not in by_category:
                by_category[cat] = {'OK': 0, 'WARN': 0, 'FAIL': 0, 'INFO': 0, 'N/A': 0}
            by_category[cat][row['Stato']] += 1
        
        rows = [
            ["DATI CLIENTE", ""],
            ["Dominio", summary['domain']],
            ["Data Audit", summary['date']],
            ["Versione Report", summary['version']],
            ["", ""],
            ["HEALTH SCORE", ""],
            ["Punteggio Tecnico", f"{summary['health_score']}/100"],
            ["", ""],
            ["STATISTICHE", ""],
            ["Totale check eseguiti", summary['total_checks']],
            ["Errori critici (FAIL)", summary['fails']],
            ["Warning (WARN)", summary['warnings']],
            ["OK", summary['oks']],
            ["Info (INFO)", summary.get('infos', 0)],
            ["Non applicabili (N/A)", summary.get('na', 0)],
            ["", ""],
            ["TOP 3 CRITICITÀ", ""],
        ]
        
        for i, crit in enumerate(summary.get('top_criticità', [])[:3], 1):
            rows.append([f"{i}.", f"{crit['Elemento Analizzato']}: {crit['Risultato / Evidenza']}"])
        
        if not summary.get('top_criticità'):
            rows.append(["", "Nessuna criticità rilevata!"])
        
        rows.extend([
            ["", ""],
            ["TOP PUNTI DI FORZA", ""],
        ])
        
        for i, pf in enumerate(summary.get('top_punti_forza', [])[:3], 1):
            rows.append([f"{i}.", pf['Elemento Analizzato']])
        
        rows.extend([
            ["", ""],
            ["RIPARTIZIONE PER CATEGORIA", ""],
            ["Categoria", "OK / WARN / FAIL / INFO / N/A"],
        ])
        
        for cat, counts in sorted(by_category.items()):
            stats = f"{counts['OK']} / {counts['WARN']} / {counts['FAIL']} / {counts['INFO']} / {counts['N/A']}"
            rows.append([cat, stats])
        
        df = pd.DataFrame(rows, columns=["Metrica", "Dettaglio"])
        df.to_excel(writer, sheet_name="Executive Summary", index=False)
    
    def _write_audit(self, writer, audit_rows: List[Dict]):
        """Scrive il foglio AUDIT."""
        df = pd.DataFrame(audit_rows)
        
        columns = [
            "ID Audit", "Categoria", "Elemento Analizzato", "Stato", "Severità",
            "Risultato / Evidenza", "URL / Link Evidenza", "Note Tecniche"
        ]
        
        # Filtra solo le colonne esistenti
        columns = [c for c in columns if c in df.columns]
        df = df[columns]
        
        df.to_excel(writer, sheet_name="AUDIT", index=False)
    
    def _write_checklist(self, writer, checklist_rows: List[Dict], audit_rows: List[Dict]):
        """Scrive il foglio Checklist."""
        audit_map = {row['ID Audit']: row for row in audit_rows}
        
        rows = []
        check_num = 1
        
        for chk in checklist_rows:
            audit_id = chk['Rif. Audit']
            audit_row = audit_map.get(audit_id, {})
            
            priority = chk.get('Priorità', 2)
            results = audit_row.get('Risultato / Evidenza', '')
            to_do = chk.get('Azione Richiesta', '')
            owner = chk.get('Owner', '')
            note = audit_row.get('Note Tecniche', '')
            
            rows.append({
                '#': check_num,
                'Category': audit_row.get('Categoria', ''),
                'Activities': audit_row.get('Elemento Analizzato', ''),
                'Priority (1 alta, 3 bassa)': priority,
                'Results': results,
                'to do': to_do,
                'Owner': owner,
                'Check': 'FALSE',
                'Note': note,
                'NOTE PF': ''
            })
            
            check_num += 1
        
        df = pd.DataFrame(rows)
        df.to_excel(writer, sheet_name='Checklist', index=False)
    
    def _write_html_img(self, writer, drilldown: Dict):
        """Scrive il foglio HTML - IMG."""
        images = drilldown.get('images', [])
        
        if not images:
            rows = [{'URl': 'N/A', 'problem': 'Nessun problema rilevato'}]
        else:
            rows = [{'URl': img['url'], 'problem': img['problem']} for img in images]
        
        df = pd.DataFrame(rows)
        df.to_excel(writer, sheet_name='HTML - IMG', index=False)
    
    def _write_title(self, writer, drilldown: Dict):
        """Scrive il foglio Title."""
        titles = drilldown.get('titles', [])
        
        if not titles:
            rows = [{'URl': 'N/A', 'meta title': 'N/A', 'problem': 'Nessun problema rilevato'}]
        else:
            rows = [{'URl': t['url'], 'meta title': t['meta_title'], 'problem': t['problem']} for t in titles]
        
        df = pd.DataFrame(rows)
        df.to_excel(writer, sheet_name='Title', index=False)
    
    def _write_description(self, writer, drilldown: Dict):
        """Scrive il foglio Description."""
        descriptions = drilldown.get('descriptions', [])
        
        if not descriptions:
            rows = [{'URl': 'N/A', 'meta description': 'N/A', 'problem': 'Nessun problema rilevato'}]
        else:
            rows = [{'URl': d['url'], 'meta description': d['meta_description'], 'problem': d['problem']} for d in descriptions]
        
        df = pd.DataFrame(rows)
        df.to_excel(writer, sheet_name='Description', index=False)
    
    def _write_headings(self, writer, drilldown: Dict):
        """Scrive il foglio HTML - HEADINGS."""
        headings = drilldown.get('headings', [])
        
        if not headings:
            rows = [{'URl': 'N/A', 'h1-1': 'N/A', 'h1-2': 'N/A', 'problem': 'Nessun problema rilevato'}]
        else:
            rows = [{
                'URl': h['url'],
                'h1-1': h.get('h1-1', ''),
                'h1-2': h.get('h1-2', ''),
                'problem': h['problem']
            } for h in headings]
        
        df = pd.DataFrame(rows)
        df.to_excel(writer, sheet_name='HTML - HEADINGS', index=False)
    
    def _write_consigli(self, writer):
        """Scrive il foglio Consigli generali."""
        rows = [{
            'Consigli generali da applicare': 'I consigli strategici verranno generati automaticamente in base ai problemi rilevati dall\'audit.'
        }]
        
        df = pd.DataFrame(rows)
        df.to_excel(writer, sheet_name='Consigli generali', index=False)
    
    def _format_excel(self, file_path: str):
        """Applica la formattazione al file Excel."""
        wb = load_workbook(file_path)
        
        # Formatta Executive Summary
        if "Executive Summary" in wb.sheetnames:
            ws = wb["Executive Summary"]
            ws.column_dimensions['A'].width = 30
            ws.column_dimensions['B'].width = 60
            
            ws['B7'].font = Font(bold=True, size=16, color="0000FF")
            
            for row in ws.iter_rows(min_row=1, max_row=ws.max_row):
                cell_a = row[0]
                if cell_a.value and isinstance(cell_a.value, str):
                    if cell_a.value in ["DATI CLIENTE", "HEALTH SCORE", "STATISTICHE", 
                                       "TOP 3 CRITICITÀ", "TOP PUNTI DI FORZA", 
                                       "RIPARTIZIONE PER CATEGORIA"]:
                        cell_a.font = Font(bold=True, size=12)
                        cell_a.fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
        
        # Formatta AUDIT
        if "AUDIT" in wb.sheetnames:
            ws = wb["AUDIT"]
            
            widths = [10, 12, 30, 8, 10, 50, 40, 40]
            for i, width in enumerate(widths, 1):
                ws.column_dimensions[get_column_letter(i)].width = width
            
            for cell in ws[1]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
                cell.alignment = Alignment(horizontal="center", vertical="center")
            
            stato_col = 4
            for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
                cell = row[stato_col - 1]
                if cell.value in self.state_colors:
                    cell.fill = self.state_colors[cell.value]
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                    cell.font = Font(bold=True)
        
        # Formatta Checklist
        if 'Checklist' in wb.sheetnames:
            ws = wb['Checklist']
            
            widths = [5, 15, 30, 12, 50, 50, 15, 8, 40, 30]
            for i, width in enumerate(widths, 1):
                ws.column_dimensions[get_column_letter(i)].width = width
            
            for cell in ws[1]:
                cell.font = Font(bold=True, color="FFFFFF", size=11)
                cell.fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            
            priority_col = 4
            for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
                cell = row[priority_col - 1]
                if cell.value in self.priority_colors:
                    cell.fill = self.priority_colors[cell.value]
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                    cell.font = Font(bold=True)
            
            for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
                for cell in row:
                    cell.alignment = Alignment(vertical="top", wrap_text=True)
        
        # Formatta fogli drill-down
        for sheet_name in ['HTML - IMG', 'Title', 'Description', 'HTML - HEADINGS']:
            if sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                
                for cell in ws[1]:
                    cell.font = Font(bold=True, color="FFFFFF", size=11)
                    cell.fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                
                for col in ws.columns:
                    max_length = 0
                    column = col[0].column_letter
                    for cell in col:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
                            pass
                    adjusted_width = min(max_length + 2, 80)
                    ws.column_dimensions[column].width = adjusted_width
                
                for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
                    for cell in row:
                        cell.alignment = Alignment(vertical="top", wrap_text=True)
        
        # Formatta Consigli generali
        if 'Consigli generali' in wb.sheetnames:
            ws = wb['Consigli generali']
            ws.column_dimensions['A'].width = 100
            
            for cell in ws[1]:
                cell.font = Font(bold=True, color="FFFFFF", size=11)
                cell.fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        
        wb.save(file_path)