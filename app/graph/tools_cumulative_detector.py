"""OPOS Intelligence Tools for Structure Detection and Cumulative Row Identification.

This module provides specialized tools for analyzing OPOS (Open Posts) data structure
before LLM processing to improve efficiency and accuracy.
"""
import logging
from typing import Annotated
from langchain_core.tools import tool, InjectedToolCallId
from langchain_core.messages import ToolMessage
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from app.graph.state import GraphState
from app.core.actions import PythonInterpreter

logger = logging.getLogger(__name__)

@tool("identify_summary_rows", parse_docstring=True)
def identify_summary_rows(
    sheet_name: str,
    data_range: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[GraphState, InjectedState],
) -> dict:
    """Identify cumulative/summary rows in OPOS data to prevent double-counting.
    
    This tool analyzes the structure of OPOS data to automatically detect rows that
    contain cumulative totals or summaries (like "Debitor" rows) which should be
    excluded from calculations to prevent double-counting.
    
    Args:
        sheet_name: The name of the sheet to analyze
        data_range: The cell range to analyze (e.g. "A1:O100")
    
    Returns:
        Dictionary containing cumulative row numbers and analysis results
    """
    sandbox = state["sandbox"]
    executor = PythonInterpreter(sandbox)
    
    code = f"""
import re
from datetime import datetime

# Read the data range
sheet = workbook["{sheet_name}"]
data_range = sheet["{data_range}"]

# Convert to list for easier processing
rows_data = []
for row_idx, row in enumerate(data_range, 1):
    row_values = [cell.value for cell in row]
    rows_data.append({{'row_num': row_idx, 'values': row_values}})

print(f"Analyzing {{len(rows_data)}} rows for cumulative patterns...")

# Identify cumulative rows using multiple heuristics
cumulative_rows = []
analysis_results = {{
    'debitor_rows': [],
    'empty_key_fields': [],
    'format_changes': [],
    'summary_indicators': [],
    'total_rows_analyzed': len(rows_data)
}}

# Heuristic 1: Look for "Debitor", "Debtor", "Creditor" keywords
for row_data in rows_data:
    row_num = row_data['row_num']
    for col_idx, value in enumerate(row_data['values']):
        if value and isinstance(value, str):
            value_lower = str(value).lower()
            if any(keyword in value_lower for keyword in ['debitor', 'debtor', 'creditor', 'total', 'sum', 'gesamt']):
                if row_num not in cumulative_rows:
                    cumulative_rows.append(row_num)
                    analysis_results['debitor_rows'].append(row_num)
                break

# Heuristic 2: Detect rows with mostly empty key fields (invoice number, dates)
# Assume first few columns contain key identifiers
key_columns = min(5, len(rows_data[0]['values']) if rows_data else 0)
for row_data in rows_data:
    row_num = row_data['row_num']
    if row_num in cumulative_rows:
        continue
        
    key_values = row_data['values'][:key_columns]
    empty_count = sum(1 for val in key_values if val is None or val == "" or val == 0)
    
    # If more than 60% of key fields are empty, likely cumulative
    if empty_count / len(key_values) > 0.6:
        cumulative_rows.append(row_num)
        analysis_results['empty_key_fields'].append(row_num)

# Heuristic 3: Format change detection in first column (invoice numbers)
if len(rows_data) > 2:
    first_col_formats = []
    for row_data in rows_data:
        first_val = row_data['values'][0] if row_data['values'] else None
        if first_val is not None:
            # Categorize format type
            if isinstance(first_val, (int, float)):
                format_type = 'numeric'
            elif isinstance(first_val, str):
                if re.match(r'^[0-9]+$', str(first_val)):
                    format_type = 'numeric_string'
                elif re.match(r'^[A-Z]{{2,}}[0-9]+', str(first_val)):
                    format_type = 'alpha_numeric'
                else:
                    format_type = 'text'
            else:
                format_type = 'other'
        else:
            format_type = 'empty'
        
        first_col_formats.append((row_data['row_num'], format_type))
    
    # Look for sudden format changes that indicate summary rows
    prev_format = None
    for row_num, format_type in first_col_formats:
        if prev_format and format_type != prev_format and format_type == 'text':
            if row_num not in cumulative_rows:
                cumulative_rows.append(row_num)
                analysis_results['format_changes'].append(row_num)
        prev_format = format_type

# Heuristic 4: Look for summary indicator words in any column
summary_words = ['total', 'sum', 'gesamt', 'summe', 'subtotal', 'zwischensumme']
for row_data in rows_data:
    row_num = row_data['row_num']
    if row_num in cumulative_rows:
        continue
        
    for value in row_data['values']:
        if value and isinstance(value, str):
            value_lower = str(value).lower()
            if any(word in value_lower for word in summary_words):
                cumulative_rows.append(row_num)
                analysis_results['summary_indicators'].append(row_num)
                break

# Sort and deduplicate
cumulative_rows = sorted(list(set(cumulative_rows)))
analysis_results['cumulative_rows'] = cumulative_rows
analysis_results['total_cumulative_found'] = len(cumulative_rows)

print(f"Found {{len(cumulative_rows)}} cumulative rows:")
for row_num in cumulative_rows:
    print(f"  Row {{row_num}}")

"""

    response = executor.utilize(code)
    
    return response.obs

@tool("detect_opos_structure", parse_docstring=True)  
def detect_opos_structure(
    sheet_name: str,
    data_range: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[GraphState, InjectedState],
) -> dict:
    """Analyze OPOS data structure to identify columns, patterns, and data organization.
    
    This tool performs intelligent structure detection on OPOS data to identify:
    - Invoice number columns
    - Date columns (invoice date, due date)
    - Amount columns (currency detection)
    - Debitor/customer identification columns
    - Aging bucket potential
    
    Args:
        sheet_name: The name of the sheet to analyze
        data_range: The cell range to analyze for structure (e.g. "A1:O20")
    
    Returns:
        Dictionary containing detected structure information
    """
    sandbox = state["sandbox"]
    executor = PythonInterpreter(sandbox)
    
    code = f"""
import re
from datetime import datetime

# Read the header and sample data
sheet = workbook["{sheet_name}"]
sample_data = sheet["{data_range}"]

# Convert to analyzable format
header_row = [cell.value for cell in sample_data[0]] if sample_data else []
sample_rows = []
for row in sample_data[1:6]:  # Analyze first 5 data rows
    sample_rows.append([cell.value for cell in row])

print(f"Analyzing structure with {{len(header_row)}} columns...")

structure_info = {{
    'total_columns': len(header_row),
    'header_row': header_row,
    'detected_columns': {{}},
    'currency_info': {{}},
    'date_formats': {{}},
    'confidence_scores': {{}}
}}

# Column type detection patterns
column_patterns = {{
    'invoice_number': {{
        'keywords': ['invoice', 'rechnung', 'belegnr', 'beleg', 'nummer', 'nr', 'rg'],
        'data_patterns': [r'^[0-9]+$', r'^[A-Z]{{1,3}}[0-9]+$', r'^[0-9]{{4,}}$']
    }},
    'invoice_date': {{
        'keywords': ['invoice.*date', 'rechnungsdatum', 'belegdatum', 'datum', 'date'],
        'data_patterns': []  # Will detect date formats
    }},
    'due_date': {{
        'keywords': ['due.*date', 'fällig', 'faellig', 'valuta', 'due'],
        'data_patterns': []
    }},
    'amount': {{
        'keywords': ['amount', 'betrag', 'summe', 'wert', 'value', 'eur', 'usd', 'euro', 'dollar'],
        'data_patterns': [r'^[0-9.,]+$', r'^-?[0-9.,]+$']
    }},
    'debitor': {{
        'keywords': ['debitor', 'debtor', 'kunde', 'customer', 'client', 'klient'],
        'data_patterns': [r'^[0-9]+$', r'^[A-Z]{{2,}}[0-9]*$']
    }},
    'currency': {{
        'keywords': ['currency', 'währung', 'waehrung', 'curr'],
        'data_patterns': [r'^(EUR|USD|GBP|CHF)$']
    }}
}}

# Analyze each column
for col_idx, header in enumerate(header_row):
    if not header:
        continue
        
    header_lower = str(header).lower()
    col_analysis = {{
        'index': col_idx,
        'header': header,
        'detected_type': 'unknown',
        'confidence': 0.0,
        'sample_values': []
    }}
    
    # Get sample values for this column
    sample_values = []
    for row in sample_rows:
        if col_idx < len(row):
            val = row[col_idx]
            if val is not None:
                sample_values.append(val)
    col_analysis['sample_values'] = sample_values[:3]
    
    # Pattern matching
    best_match = None
    best_confidence = 0.0
    
    for pattern_type, patterns in column_patterns.items():
        confidence = 0.0
        
        # Header keyword matching
        header_matches = sum(1 for keyword in patterns['keywords'] 
                           if re.search(keyword, header_lower))
        if header_matches > 0:
            confidence += 0.6 * (header_matches / len(patterns['keywords']))
        
        # Data pattern matching
        if patterns['data_patterns'] and sample_values:
            pattern_matches = 0
            for value in sample_values:
                if value is not None:
                    value_str = str(value)
                    for pattern in patterns['data_patterns']:
                        if re.match(pattern, value_str):
                            pattern_matches += 1
                            break
            if sample_values:
                confidence += 0.4 * (pattern_matches / len(sample_values))
        
        # Special handling for dates
        if pattern_type in ['invoice_date', 'due_date'] and sample_values:
            date_score = 0
            for value in sample_values:
                if isinstance(value, datetime):
                    date_score += 1
                elif isinstance(value, str):
                    # Try to parse common date formats
                    for fmt in ['%d.%m.%Y', '%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y']:
                        try:
                            datetime.strptime(str(value), fmt)
                            date_score += 1
                            break
                        except:
                            continue
            if sample_values:
                confidence += 0.4 * (date_score / len(sample_values))
        
        if confidence > best_confidence:
            best_confidence = confidence
            best_match = pattern_type
    
    col_analysis['detected_type'] = best_match or 'unknown'
    col_analysis['confidence'] = best_confidence
    structure_info['detected_columns'][f'col_{{col_idx}}'] = col_analysis
    structure_info['confidence_scores'][f'col_{{col_idx}}'] = best_confidence

# Currency detection
currencies_found = set()
for col_idx, header in enumerate(header_row):
    if not header:
        continue
    header_str = str(header).upper()
    for curr in ['EUR', 'USD', 'GBP', 'CHF']:
        if curr in header_str:
            currencies_found.add(curr)

# Look for currency in sample data
for row in sample_rows:
    for value in row:
        if isinstance(value, str):
            value_upper = value.upper()
            for curr in ['EUR', 'USD', 'GBP', 'CHF']:
                if curr in value_upper:
                    currencies_found.add(curr)

structure_info['currency_info'] = {{
    'detected_currencies': list(currencies_found),
    'is_multi_currency': len(currencies_found) > 1
}}

# Generate summary
high_confidence_cols = []
for col_key, col_info in structure_info['detected_columns'].items():
    if col_info['confidence'] > 0.5:
        high_confidence_cols.append(f"{{col_info['header']}} -> {{col_info['detected_type']}}")

print(f"Structure detection completed:")
print(f"  - Total columns: {{structure_info['total_columns']}}")
print(f"  - High confidence detections: {{len(high_confidence_cols)}}")
for detection in high_confidence_cols:
    print(f"    * {{detection}}")
print(f"  - Currencies detected: {{structure_info['currency_info']['detected_currencies']}}")
print(f"  - Multi-currency file: {{structure_info['currency_info']['is_multi_currency']}}")

# Store results for later use
opos_structure_results = structure_info
"""

    response = executor.utilize(code)
    
    return Command(
        update={
            "opos_structure_results": response.obs,
            "messages": [
                ToolMessage(
                    content=f"OPOS structure detection completed. {response.obs}",
                    tool_call_id=tool_call_id,
                    name="detect_opos_structure",
                )
            ],
        }
    )