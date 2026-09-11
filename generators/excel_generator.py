import pandas as pd
from typing import Dict, List, Any, Optional
from openpyxl import load_workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from datetime import datetime


# ---------------------------------------------------------------------------
# COSTANTI — Colori per stati e priorità (elimina duplicazioni)
# ---------------------------------------------------------------------------
STATE_COLORS = {
    "OK": PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid"),
    "WARN": PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid"),
    "FAIL": PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid"),
    "INFO": PatternFill(start_color="BDD7EE", end_color="BDD7EE", fill_type="solid"),
    "N/A": PatternFill(start_color="D9D9D9", end_color="D9D9D9", fill_type="solid"),
}

PRIORITY_COLORS = {
    1: PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid"),
    2: PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid"),
    3: PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid"),
}

HEADER_FILL = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
HEADER_ALIGNMENT = Alignment(horizontal="center", vertical="center", wrap_text=True)

SECTION_FILL = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
SECTION_FONT = Font(bold=True, size=12)

# Larghezze colonne predefinite per tipo di foglio
COLUMN_WIDTHS = {
    "AUDIT": [10, 12, 30, 8, 10, 50, 40, 40],
    "Checklist": [5, 15, 30, 12, 50, 50, 15, 8, 40, 30],
    "drilldown": [60, 60, 60, 60],  # URL, content, problem, extra
}


# ---------------------------------------------------------------------------
# HELPER 1 — Creazione DataFrame drill-down (elimina duplicazioni)
# ---------------------------------------------------------------------------
def create_drilldown_dataframe(
    data: List[Dict],
    columns: List[str],
    empty_message: str = "Nessun problema rilevato"
) -> pd.DataFrame:
    """Crea un DataFrame per fogli drill-down, gestendo il caso vuoto."""
    if not data:
        # Crea riga "N/A" con tutte le colonne
        na_row = {col: "N/A" for col in columns}
        na_row[columns[-1]] = empty_message  # Ultima colonna = messaggio
        return pd.DataFrame([na_row], columns=columns)
    
    return pd.DataFrame(data, columns=columns)


# ---------------------------------------------------------------------------
# HELPER 2 — Formattazione header (centralizza logica)
# ---------------------------------------------------------------------------
def apply_header_format(worksheet):
    """Applica formattazione standard all'header del foglio."""
    for cell in worksheet[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = HEADER_ALIGNMENT


# ---------------------------------------------------------------------------
# HELPER 3 — Larghezza colonne automatica
# ---------------------------------------------------------------------------
def auto_adjust_columns(worksheet, max_width: int = 80):
    """Regola automaticamente la larghezza delle colonne in base al contenuto."""
    for col in worksheet.columns:
        max_length = 0
        column_letter = col[0].column_letter
        
        for cell in col:
            try:
                cell_len = len(str(cell.value)) if cell.value else 0
                if cell_len > max_length:
                    max_length = cell_len
            except:
                pass
        
        adjusted_width = min(max_length + 2, max_width)
        worksheet.column_dimensions[column_letter].width = adjusted_width


# ---------------------------------------------------------------------------
# HELPER 4 — Imposta larghezze colonne da lista
# ---------------------------------------------------------------------------
def set_column_widths(worksheet, widths: List[int]):
    """Imposta larghezze colonne da una lista di valori."""
    for i, width in enumerate(widths, 1):
        worksheet.column_dimensions[get_column_letter(i)].width = width


# ---------------------------------------------------------------------------
# HELPER 5 — Applica colori stato a colonna specifica
# ---------------------------------------------------------------------------
def apply_state_colors(worksheet, column_index: int, color_map: Dict = None):
    """Applica colori di stato a una colonna specifica."""
    if color_map is None:
        color_map = STATE_COLORS
    
    for row in worksheet.iter_rows(min_row=2, max_row=worksheet.max_row):
        cell = row[column_index - 1]
        if cell.value in color_map:
            cell.fill = color_map[cell.value]
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.font = Font(bold=True)


# ---------------------------------------------------------------------------
# HELPER 6 — Applica colori priorità a colonna specifica
# ---------------------------------------------------------------------------
def apply_priority_colors(worksheet, column_index: int, color_map: Dict = None):
    """Applica colori di priorità a una colonna specifica."""
    if color_map is None:
        color_map = PRIORITY_COLORS
    
    for row in worksheet.iter_rows(min_row=2, max_row=worksheet.max_row):
        cell = row[column_index - 1]
        if cell.value in color_map:
            cell.fill = color_map[cell.value]
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.font = Font(bold=True)


# ---------------------------------------------------------------------------
# HELPER 7 — Applica wrap text a tutte le celle dati
# ---------------------------------------------------------------------------
def apply_wrap_text(worksheet, start_row: int = 2):
    """Applica wrap text e allineamento verticale a tutte le celle dati."""
    for row in worksheet.iter_rows(min_row=start_row, max_row=worksheet.max_row):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)


# ---------------------------------------------------------------------------
# HELPER 8 — Estrazione dati drill-down con fallback
# ---------------------------------------------------------------------------
def extract_drilldown_data(
    drilldown: Dict,
    key: str,
    columns: List[str],
    field_mapping: Dict[str, str]
) -> List[Dict]:
    """Estrae dati drill-down con mapping campi, gestendo fallback."""
    data = drilldown.get(key, [])
    if not data:
        return []
    
    result = []
    for item in data:
        row = {}
        for col in columns:
            field = field_mapping.get(col, col)
            row[col] = item.get(field, "N/A")
        result.append(row)
    
    return result


class ExcelGenerator:
    """Genera il report Excel dell'audit SEO nel formato target."""
    
    def __init__(self):
        # Usa le costanti di modulo
        self.state_colors = STATE_COLORS
        self.priority_colors = PRIORITY_COLORS
    
    def generate(self, processed_data: Dict, output_path: str, raw_data: Dict = None):
        """Genera il file Excel completo."""
        
        summary = processed_data['summary']
        audit_rows = processed_data['audit']
        checklist_rows = processed_data['checklist']
        drilldown = processed_data.get('drilldown', {})
        
        # Se raw_data non è passato, usa dict vuoto
        if raw_data is None:
            raw_data = {}
        
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            # 1. Executive Summary
            self._write_summary(writer, summary, audit_rows)
            
            # 2. AUDIT
            self._write_audit(writer, audit_rows)
            
            # 3. Checklist principale
            self._write_checklist(writer, checklist_rows, audit_rows)
            
            # 4. Fogli drill-down (usano helper generico)
            self._write_drilldown_sheet(
                writer, 'HTML - IMG', drilldown, 'images',
                columns=['URl', 'problem'],
                field_mapping={'URl': 'url', 'problem': 'problem'}
            )
            
            self._write_drilldown_sheet(
                writer, 'Title', drilldown, 'titles',
                columns=['URl', 'meta_title', 'problem'],
                field_mapping={'URl': 'url', 'meta_title': 'meta_title', 'problem': 'problem'}
            )
            
            self._write_drilldown_sheet(
                writer, 'Description', drilldown, 'descriptions',
                columns=['URl', 'meta_description', 'problem'],
                field_mapping={'URl': 'url', 'meta_description': 'meta_description', 'problem': 'problem'}
            )
            
            self._write_drilldown_sheet(
                writer, 'HTML - HEADINGS', drilldown, 'headings',
                columns=['URl', 'h1-1', 'h1-2', 'problem'],
                field_mapping={'URl': 'url', 'h1-1': 'h1-1', 'h1-2': 'h1-2', 'problem': 'problem'}
            )
            
            # 5. Fogli GA4 avanzati (se raw_data è disponibile)
            ga4_data = raw_data.get('ga4', {})
            if ga4_data:
                self._write_ga4_landing_pages(writer, ga4_data)
                self._write_ga4_exit_pages(writer, ga4_data)
                self._write_ga4_geo(writer, ga4_data)
            
            # 6. Consigli generali
            self._write_consigli(writer)
        
        # Formatta il file
        self._format_excel(output_path)
        
    def _write_drilldown_sheet(
        self,
        writer,
        sheet_name: str,
        drilldown: Dict,
        data_key: str,
        columns: List[str],
        field_mapping: Dict[str, str]
    ):
        """Scrive un foglio drill-down generico usando helper."""
        data = extract_drilldown_data(drilldown, data_key, columns, field_mapping)
        df = create_drilldown_dataframe(data, columns)
        df.to_excel(writer, sheet_name=sheet_name, index=False)
    
    def _write_summary(self, writer, summary: Dict, audit_rows: List[Dict]):
        """Scrive il foglio Executive Summary."""
        # Raggruppa per categoria
        by_category = self._group_by_category(audit_rows)
        
        # Costruisci righe
        rows = self._build_summary_rows(summary, by_category)
        
        df = pd.DataFrame(rows, columns=["Metrica", "Dettaglio"])
        df.to_excel(writer, sheet_name="Executive Summary", index=False)
    
    def _group_by_category(self, audit_rows: List[Dict]) -> Dict[str, Dict[str, int]]:
        """Raggruppa i check per categoria e stato."""
        by_category = {}
        for row in audit_rows:
            cat = row['Categoria']
            if cat not in by_category:
                by_category[cat] = {'OK': 0, 'WARN': 0, 'FAIL': 0, 'INFO': 0, 'N/A': 0}
            by_category[cat][row['Stato']] += 1
        return by_category
    
    def _build_summary_rows(self, summary: Dict, by_category: Dict) -> List[List]:
        """Costruisce le righe del summary."""
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
        
        # Top criticità
        top_criticità = summary.get('top_criticità', [])[:3]
        if top_criticità:
            for i, crit in enumerate(top_criticità, 1):
                rows.append([f"{i}.", f"{crit['Elemento Analizzato']}: {crit['Risultato / Evidenza']}"])
        else:
            rows.append(["", "Nessuna criticità rilevata!"])
        
        rows.extend([
            ["", ""],
            ["TOP PUNTI DI FORZA", ""],
        ])
        
        # Top punti di forza
        for i, pf in enumerate(summary.get('top_punti_forza', [])[:3], 1):
            rows.append([f"{i}.", pf['Elemento Analizzato']])
        
        rows.extend([
            ["", ""],
            ["RIPARTIZIONE PER CATEGORIA", ""],
            ["Categoria", "OK / WARN / FAIL / INFO / N/A"],
        ])
        
        # Ripartizione per categoria
        for cat, counts in sorted(by_category.items()):
            stats = f"{counts['OK']} / {counts['WARN']} / {counts['FAIL']} / {counts['INFO']} / {counts['N/A']}"
            rows.append([cat, stats])
        
        return rows
    
    def _write_audit(self, writer, audit_rows: List[Dict]):
        """Scrive il foglio AUDIT."""
        columns = [
            "ID Audit", "Categoria", "Elemento Analizzato", "Stato", "Severità",
            "Risultato / Evidenza", "URL / Link Evidenza", "Note Tecniche"
        ]
        
        # Filtra solo le colonne esistenti
        available_columns = [c for c in columns if c in audit_rows[0]] if audit_rows else columns
        df = pd.DataFrame(audit_rows, columns=available_columns)
        df.to_excel(writer, sheet_name="AUDIT", index=False)
    
    def _write_checklist(self, writer, checklist_rows: List[Dict], audit_rows: List[Dict]):
        """Scrive il foglio Checklist."""
        audit_map = {row['ID Audit']: row for row in audit_rows}
        
        rows = []
        for check_num, chk in enumerate(checklist_rows, 1):
            audit_id = chk['Rif. Audit']
            audit_row = audit_map.get(audit_id, {})
            
            rows.append({
                '#': check_num,
                'Category': audit_row.get('Categoria', ''),
                'Activities': audit_row.get('Elemento Analizzato', ''),
                'Priority (1 alta, 3 bassa)': chk.get('Priorità', 2),
                'Results': audit_row.get('Risultato / Evidenza', ''),
                'to do': chk.get('Azione Richiesta', ''),
                'Owner': chk.get('Owner', ''),
                'Check': 'FALSE',
                'Note': audit_row.get('Note Tecniche', ''),
                'NOTE PF': ''
            })
        
        df = pd.DataFrame(rows)
        df.to_excel(writer, sheet_name='Checklist', index=False)
    
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
        
        # Formattazione specifica per ogni tipo di foglio
        formatters = {
            "Executive Summary": self._format_summary_sheet,
            "AUDIT": self._format_audit_sheet,
            "Checklist": self._format_checklist_sheet,
            "HTML - IMG": self._format_drilldown_sheet,
            "Title": self._format_drilldown_sheet,
            "Description": self._format_drilldown_sheet,
            "HTML - HEADINGS": self._format_drilldown_sheet,
            "GA4 Landing Pages": self._format_drilldown_sheet,
            "GA4 Exit Pages": self._format_drilldown_sheet,
            "GA4 Geo": self._format_drilldown_sheet,
            "Consigli generali": self._format_consigli_sheet,
        }
        
        for sheet_name, formatter in formatters.items():
            if sheet_name in wb.sheetnames:
                formatter(wb[sheet_name])
        
        wb.save(file_path)
    
    def _format_summary_sheet(self, worksheet):
        """Formatta il foglio Executive Summary."""
        worksheet.column_dimensions['A'].width = 30
        worksheet.column_dimensions['B'].width = 60
        
        # Health Score evidenziato
        worksheet['B7'].font = Font(bold=True, size=16, color="0000FF")
        
        # Sezioni evidenziate
        section_titles = [
            "DATI CLIENTE", "HEALTH SCORE", "STATISTICHE",
            "TOP 3 CRITICITÀ", "TOP PUNTI DI FORZA",
            "RIPARTIZIONE PER CATEGORIA"
        ]
        
        for row in worksheet.iter_rows(min_row=1, max_row=worksheet.max_row):
            cell_a = row[0]
            if cell_a.value in section_titles:
                cell_a.font = SECTION_FONT
                cell_a.fill = SECTION_FILL
    
    def _format_audit_sheet(self, worksheet):
        """Formatta il foglio AUDIT."""
        set_column_widths(worksheet, COLUMN_WIDTHS["AUDIT"])
        apply_header_format(worksheet)
        apply_state_colors(worksheet, column_index=4)  # Colonna "Stato"
    
    def _format_checklist_sheet(self, worksheet):
        """Formatta il foglio Checklist."""
        set_column_widths(worksheet, COLUMN_WIDTHS["Checklist"])
        apply_header_format(worksheet)
        apply_priority_colors(worksheet, column_index=4)  # Colonna "Priority"
        apply_wrap_text(worksheet)
    
    def _format_drilldown_sheet(self, worksheet):
        """Formatta un foglio drill-down generico."""
        apply_header_format(worksheet)
        auto_adjust_columns(worksheet)
        apply_wrap_text(worksheet)
    
    def _format_consigli_sheet(self, worksheet):
    
        """Formatta il foglio Consigli generali."""
        worksheet.column_dimensions['A'].width = 100
        apply_header_format(worksheet)

    def _write_ga4_landing_pages(self, writer, ga4_data: Dict):
        """Scrive il foglio GA4 Landing Pages."""
        landing_pages = ga4_data.get('landing_pages', {}).get('landing_pages', [])
        
        if not landing_pages:
            rows = [{'Pagina': 'N/A', 'Sessioni': 'N/A', 'Utenti': 'N/A', 'Engaged': 'N/A', 'Bounce': 'N/A', 'Durata': 'N/A'}]
        else:
            rows = []
            for lp in landing_pages[:15]:
                rows.append({
                    'Pagina': lp.get('page', ''),
                    'Sessioni': lp.get('sessions', 0),
                    'Utenti': lp.get('users', 0),
                    'Engaged': lp.get('engaged_sessions', 0),
                    'Bounce': f"{lp.get('bounce_rate', 0)*100:.1f}%",
                    'Durata': f"{lp.get('avg_duration', 0)/60:.1f}m"
                })
        
        df = pd.DataFrame(rows)
        df.to_excel(writer, sheet_name='GA4 Landing Pages', index=False)
    
    def _write_ga4_exit_pages(self, writer, ga4_data: Dict):
        """Scrive il foglio GA4 Exit Pages."""
        exit_pages = ga4_data.get('exit_pages', {}).get('exit_pages', [])
        
        if not exit_pages:
            rows = [{'Pagina': 'N/A', 'Exits (stima)': 'N/A', 'Views': 'N/A', 'Sessioni': 'N/A', 'Bounce': 'N/A'}]
        else:
            rows = []
            for ep in exit_pages[:15]:
                rows.append({
                    'Pagina': ep.get('page', ''),
                    'Exits (stima)': ep.get('estimated_exits', 0),
                    'Views': ep.get('views', 0),
                    'Sessioni': ep.get('sessions', 0),
                    'Bounce': f"{ep.get('bounce_rate', 0)*100:.1f}%"
                })
        
        df = pd.DataFrame(rows)
        df.to_excel(writer, sheet_name='GA4 Exit Pages', index=False)
    
    def _write_ga4_geo(self, writer, ga4_data: Dict):
        """Scrive il foglio GA4 Geo Distribution."""
        geo_data = ga4_data.get('geo_distribution', {}).get('geo_distribution', [])
        
        if not geo_data:
            rows = [{'Paese': 'N/A', 'Sessioni': 'N/A'}]
        else:
            rows = []
            for geo in geo_data[:10]:
                rows.append({
                    'Paese': geo.get('country', ''),
                    'Sessioni': geo.get('sessions', 0)
                })
        
        df = pd.DataFrame(rows)
        df.to_excel(writer, sheet_name='GA4 Geo', index=False)