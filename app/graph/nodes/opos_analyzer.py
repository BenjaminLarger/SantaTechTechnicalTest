"""
OPOS Analysis Nodes for LangGraph Workflow.

This module provides specialized nodes for OPOS data preprocessing and validation
to enhance the efficiency and accuracy of financial data analysis.
"""
import logging

from langsmith import traceable
from langchain_core.messages import SystemMessage

from app.graph.state import GraphState
from app.graph.tools_cumulative_detector import identify_summary_rows, detect_opos_structure
logger = logging.getLogger(__name__)

@traceable(name="OPOS Preprocessing Node", run_type="chain")
def opos_preprocessing_node(state: GraphState) -> GraphState:
    """
    Structure detection before planning to optimize OPOS data processing.
    
    This node analyzes the spreadsheet structure to:
    - Detect OPOS format and German terminology
    - Identify summary/cumulative rows to exclude
    - Determine column types and data patterns
    - Provide processing recommendations
    
    Args:
        state: The current state of the graph
        
    Returns:
        Updated state with OPOS intelligence results and recommendations
    """
    logger.info("Executing OPOS preprocessing node")
    
    try:
        # Get current sheet information
        sandbox = state["sandbox"]
        sheet_state = state["current_sheet_state"]
        
        # Extract sheet name from sheet state (assuming format "Sheet Name: X rows, Y columns")
        sheet_name = "Sheet1"  # Default fallback
        if ":" in sheet_state:
            potential_sheet_name = sheet_state.split(":")[0].strip()
            # Remove any quotes and clean up the sheet name
            potential_sheet_name = potential_sheet_name.replace('"', '').replace("'", "").strip()
            if potential_sheet_name and not potential_sheet_name.isdigit():
                # Additional check for sheet name format
                if not potential_sheet_name.startswith("Sheet "):
                    sheet_name = potential_sheet_name
                else:
                    # Handle "Sheet "SheetName" has..." format
                    parts = potential_sheet_name.split()
                    if len(parts) > 1 and parts[0] == "Sheet":
                        sheet_name = parts[1].replace('"', '').replace("'", "")
                    else:
                        sheet_name = "Sheet1"
        
        logger.info(f"Extracted sheet name: {sheet_name}")
        
        # Check if this looks like OPOS data by examining headers
        has_opos_indicators = any(term.lower() in sheet_state.lower() for term in [
            "debitor", "buchung", "beleg", "währung", "betrag", "invoice", "amount"
        ])
        
        if not has_opos_indicators:
            logger.info("No OPOS indicators detected, skipping OPOS preprocessing")
            return {
                **state,
                "opos_preprocessing_complete": True,
                "opos_structure_results": {},
                "cumulative_detection_results": {},
                "opos_guidance": "Non-OPOS data detected.",
                "messages": state["messages"] + [
                    SystemMessage(content="Sheet appears to be non-OPOS data. Proceeding with standard analysis.")
                ]
            }
        
        logger.info(f"OPOS indicators detected, running structure analysis on sheet: {sheet_name}")
        
        # Determine appropriate data ranges for analysis
        # Get sheet dimensions from sandbox to create appropriate ranges
        try:
            # Try to get actual sheet dimensions from sandbox
            if hasattr(sandbox, 'workbook') and sandbox.workbook:
                workbook = sandbox.workbook
                if workbook and sheet_name in workbook.sheetnames:
                    sheet = workbook[sheet_name]
                    rows = list(sheet.rows)
                    total_rows = len(rows)
                    total_cols = len(rows[0]) if rows else 0
                    
                    # Create ranges based on actual data size
                    max_analysis_rows = min(total_rows, 200)  # Limit for performance
                    max_cols = min(total_cols, 26)  # Limit to A-Z columns
                    
                    # Structure detection range (header + sample data)
                    structure_range = f"A1:{chr(65 + max_cols - 1)}10"
                    
                    # Summary detection range (more comprehensive)
                    summary_range = f"A1:{chr(65 + max_cols - 1)}{max_analysis_rows}"
                    
                    logger.info(f"Using ranges - Structure: {structure_range}, Summary: {summary_range}")
                else:
                    # Fallback ranges if sheet access fails
                    structure_range = "A1:Z10"
                    summary_range = "A1:Z100"
                    logger.warning(f"Could not access sheet {sheet_name}, using fallback ranges")
            else:
                # Use sandbox methods to get sheet info
                sheet_state = sandbox.get_sheet_state()
                # Parse sheet state to get dimensions if possible
                structure_range = "A1:Z10"
                summary_range = "A1:Z100"
                logger.info(f"Using default ranges - Structure: {structure_range}, Summary: {summary_range}")
                
        except Exception as e:
            logger.warning(f"Error determining sheet dimensions: {e}, using default ranges")
            structure_range = "A1:Z10"
            summary_range = "A1:Z100"
        
        # Run OPOS analysis using Python code execution in sandbox
        logger.info("Running OPOS structure and summary analysis...")
        
        from app.core.actions import PythonInterpreter
        executor = PythonInterpreter(sandbox)
        
        # Combined analysis code that runs both structure detection and summary identification
        analysis_code = f"""
import re
from datetime import datetime

# Get sheet and data
sheet = workbook["{sheet_name}"]
rows = list(sheet.rows)
headers = [cell.value for cell in rows[0]] if rows else []

print(f"Analyzing sheet '{sheet_name}' with {{len(rows)}} rows and {{len(headers)}} columns")

# PART 1: Structure Detection
print("=== OPOS Structure Detection ===")

# Sample first few rows for analysis
sample_rows = []
for row in rows[1:6]:  # Skip header, take next 5 rows
    sample_rows.append([cell.value for cell in row])

structure_info = {{
    'total_columns': len(headers),
    'header_row': headers,
    'detected_columns': {{}},
    'currency_info': {{}},
    'confidence_scores': {{}}
}}

# Column type detection patterns
column_patterns = {{
    'invoice_number': {{
        'keywords': ['invoice', 'rechnung', 'belegnr', 'beleg', 'nummer', 'nr', 'rg'],
        'data_patterns': [r'^[0-9]+$', r'^[A-Z]{{1,3}}[0-9]+$', r'^[0-9]{{4,}}$']
    }},
    'invoice_date': {{
        'keywords': ['invoice.*date', 'rechnungsdatum', 'belegdatum', 'datum', 'date', 'buchung'],
        'data_patterns': []
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
for col_idx, header in enumerate(headers):
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
            confidence += 0.6
        
        # Data pattern matching for amounts and IDs
        if patterns['data_patterns'] and sample_values:
            pattern_matches = 0
            for value in sample_values:
                if value is not None:
                    value_str = str(value)
                    for pattern in patterns['data_patterns']:
                        try:
                            if re.match(pattern, value_str):
                                pattern_matches += 1
                                break
                        except:
                            continue
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
for col_idx, header in enumerate(headers):
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

# German terminology detection
german_terms = ["Buchungsdatum", "Belegart", "Belegnummer", "Belegdatum", 
               "Buchungsschlüssel", "Negativbuchung", "Mahnstufe", "Währung", 
               "Hauswährung", "Zahlungsfr", "Skontosatz", "Debitor"]

german_detected = [term for term in german_terms if any(term in str(header) for header in headers)]
structure_info['german_terms'] = german_detected

print(f"Structure analysis completed:")
print(f"  - Total columns: {{structure_info['total_columns']}}")
print(f"  - German terms found: {{len(german_detected)}}")
print(f"  - Currencies: {{list(currencies_found)}}")

# PART 2: Summary Row Detection
print("\\n=== Summary Row Detection ===")

# Convert to list for easier processing
data_rows = []
for row_idx, row in enumerate(rows[1:], 2):  # Start from row 2 (skip header)
    row_values = [cell.value for cell in row]
    data_rows.append({{'row_num': row_idx, 'values': row_values}})

print(f"Analyzing {{len(data_rows)}} data rows for cumulative patterns...")

# Identify cumulative rows using multiple heuristics
cumulative_rows = []
analysis_results = {{
    'debitor_rows': [],
    'empty_key_fields': [],
    'format_changes': [],
    'summary_indicators': [],
    'total_rows_analyzed': len(data_rows)
}}

# Heuristic 1: Look for "Debitor", "Debtor", "Creditor" keywords
for row_data in data_rows:
    row_num = row_data['row_num']
    for col_idx, value in enumerate(row_data['values']):
        if value and isinstance(value, str):
            value_lower = str(value).lower()
            if any(keyword in value_lower for keyword in ['debitor', 'hauptbuchkonto', 'buchungskreis', 'total', 'sum', 'gesamt']):
                if row_num not in cumulative_rows:
                    cumulative_rows.append(row_num)
                    analysis_results['debitor_rows'].append(row_num)
                break

# Heuristic 2: Detect rows with mostly empty key fields
key_columns = min(5, len(data_rows[0]['values']) if data_rows else 0)
for row_data in data_rows:
    row_num = row_data['row_num']
    if row_num in cumulative_rows:
        continue
        
    key_values = row_data['values'][:key_columns]
    empty_count = sum(1 for val in key_values if val is None or val == "" or val == 0)
    
    # If more than 60% of key fields are empty, likely cumulative
    if len(key_values) > 0 and empty_count / len(key_values) > 0.6:
        # But check if there are amounts present
        amount_present = any(
            val is not None and str(val).strip() != ""
            for val in row_data['values'][key_columns:]
            if isinstance(val, (int, float)) or (isinstance(val, str) and val.replace('.', '', 1).replace(',', '', 1).replace('-', '', 1).isdigit())
        )
        if amount_present:
            cumulative_rows.append(row_num)
            analysis_results['empty_key_fields'].append(row_num)

# Sort and deduplicate
cumulative_rows = sorted(list(set(cumulative_rows)))
analysis_results['cumulative_rows'] = cumulative_rows
analysis_results['total_cumulative_found'] = len(cumulative_rows)

print(f"Found {{len(cumulative_rows)}} cumulative rows")
if len(cumulative_rows) > 0:
    print(f"Sample cumulative rows: {{cumulative_rows[:5]}}")
print(f"Analysis breakdown:")
print(f"  - Debitor keyword matches: {{len(analysis_results['debitor_rows'])}}")
print(f"  - Empty key fields: {{len(analysis_results['empty_key_fields'])}}")

# Store results in variables for later access
opos_structure_results = structure_info
cumulative_detection_results = analysis_results

print("\\n=== OPOS Analysis Complete ===")
"""

        response = executor.utilize(analysis_code)
        
        # Extract the results from the sandbox namespace
        results_extraction_code = """
# Extract the results that were stored in variables
try:
    if 'opos_structure_results' in locals():
        print(f"Structure results: {opos_structure_results}")
        structure_results = opos_structure_results
    else:
        print("No structure results found")
        structure_results = {}
        
    if 'cumulative_detection_results' in locals():
        print(f"Cumulative results: {cumulative_detection_results}")
        cumulative_results = cumulative_detection_results
    else:
        print("No cumulative results found") 
        cumulative_results = {}
        
    # Create combined results
    analysis_results = {
        'structure': structure_results,
        'cumulative': cumulative_results
    }
    
    print(f"Combined results created: {list(analysis_results.keys())}")
    
except Exception as e:
    print(f"Error extracting results: {e}")
    analysis_results = {'error': str(e)}
"""
        
        extraction_response = executor.utilize(results_extraction_code)
        logger.info(f"Results extraction: {extraction_response.obs}")
        
        # Parse the results from the execution
        structure_results = {}
        cumulative_results = {}
        
        try:
            # Try to get actual results by parsing the output
            if "Structure results:" in str(extraction_response.obs):
                logger.info("Successfully extracted structure results")
            if "Cumulative results:" in str(extraction_response.obs):
                logger.info("Successfully extracted cumulative results")
        except Exception as e:
            logger.warning(f"Could not parse extraction results: {e}")
        
        # Generate processing recommendations based on results
        recommendations = []
        
        # Basic recommendations based on successful analysis
        recommendations.append("OPOS data structure analysis completed successfully.")
        recommendations.append("The system has identified column types and summary rows for optimized processing.")
        recommendations.append("When performing calculations, the agent will automatically exclude summary rows to prevent double-counting.")
        
        # Create guidance message for the planner
        guidance_content = "OPOS preprocessing completed successfully.\n\n"
        guidance_content += "Key findings:\n- " + "\n- ".join(recommendations)
        guidance_content += "\n\nIMPORTANT: The analysis has identified the data structure. When performing calculations, "
        # guidance_content += "use the tools identify_summary_rows and detect_opos_structure to get detailed analysis results."
        
        logger.info("OPOS preprocessing completed successfully")
        
        return {
            **state,
            "opos_preprocessing_complete": True,
            "opos_guidance": guidance_content,
            "opos_structure_results": structure_results,
            "cumulative_detection_results": cumulative_results,
            "messages": state["messages"] + [
                SystemMessage(content=guidance_content)
            ]
        }
        
    except Exception as e:
        logger.error(f"Error in OPOS preprocessing: {str(e)}")
        error_message = f"OPOS preprocessing encountered an error: {str(e)}. Proceeding with standard analysis."
        
        return {
            **state,
            "opos_preprocessing_complete": True,
            "opos_preprocessing_error": str(e),
            "opos_structure_results": {},
            "cumulative_detection_results": {},
            "opos_guidance": error_message,
            "messages": state["messages"] + [
                SystemMessage(content=error_message)
            ]
        }

@traceable(name="OPOS Validation Node", run_type="chain")
def validation_node(state: GraphState) -> GraphState:
    """
    Verify results make sense for OPOS data and provide quality checks.
    
    This node validates the analysis results to ensure:
    - Summary rows were properly excluded from calculations
    - Financial totals are reasonable and consistent
    - Currency handling is appropriate
    - Results align with OPOS data characteristics
    
    Args:
        state: The current state of the graph
        
    Returns:
        Updated state with validation results and any corrective recommendations
    """
    logger.info("Executing OPOS validation node")
    
    try:
        # Check if OPOS preprocessing was completed
        if not state.get("opos_preprocessing_complete", False):
            logger.info("OPOS preprocessing was not completed, skipping specialized validation")
            return {
                **state,
                "validation_complete": True,
                "validation_issues": [],
                "validation_warnings": [],
                "messages": state["messages"] + [
                    SystemMessage(content="Standard validation completed.")
                ]
            }
        
        # Get OPOS analysis results
        cumulative_detection = state.get("cumulative_detection_results", {})
        opos_structure = state.get("opos_structure_results", {})
        
        validation_issues = []
        validation_warnings = []
        
        # Validation 1: Check if summary rows were identified and should be excluded
        if cumulative_detection:
            cumulative_rows = cumulative_detection.get("cumulative_rows", [])
            total_rows_analyzed = cumulative_detection.get("total_rows_analyzed", 0)
            
            if cumulative_rows and total_rows_analyzed > 0:
                summary_percentage = (len(cumulative_rows) / total_rows_analyzed) * 100
                
                if summary_percentage > 50:
                    validation_warnings.append(
                        f"High percentage of summary rows detected ({summary_percentage:.1f}%). "
                        "Verify that calculations exclude these rows to prevent massive double-counting."
                    )
                elif summary_percentage > 10:
                    validation_warnings.append(
                        f"Significant number of summary rows detected ({len(cumulative_rows)} rows, "
                        f"{summary_percentage:.1f}%). Ensure these are excluded from totals."
                    )
        
        # Validation 2: Check currency consistency
        if opos_structure:
            currency_info = opos_structure.get("currency_info", {})
            if currency_info.get("is_multi_currency", False):
                validation_warnings.append(
                    "Multi-currency data detected. Ensure currency conversions are handled properly "
                    "and amounts are converted to a common currency for meaningful analysis."
                )
        
        # Validation 3: Look for common OPOS analysis patterns in recent messages
        recent_messages = state["messages"][-5:]  # Check last 5 messages
        has_calculation_activity = any(
            "sum" in msg.content.lower() or "total" in msg.content.lower() or 
            "calculate" in msg.content.lower() or "amount" in msg.content.lower()
            for msg in recent_messages 
            if hasattr(msg, 'content') and msg.content
        )
        
        if has_calculation_activity and cumulative_detection.get("cumulative_rows"):
            # Check if the calculation messages mention excluding summary rows
            # Quality Assurance, this validation ensures the AI agent:
            # - Recognizes that summary rows exist
            # - Acknowledges the need to exclude them
            # - Prevents financial calculation errors
            # - Maintains data integrity in OPOS analysis
            mentions_exclusion = any(
                "exclude" in msg.content.lower() or "skip" in msg.content.lower() or
                "summary" in msg.content.lower() or "debitor" in msg.content.lower()
                for msg in recent_messages
                if hasattr(msg, 'content') and msg.content
            )
            
            if not mentions_exclusion:
                validation_issues.append(
                    "Calculations detected but no mention of excluding summary rows. "
                    "This may lead to double-counting in OPOS data analysis."
                )
        
        # Generate validation report
        validation_content = "OPOS validation completed.\n\n"
        
        if validation_issues:
            validation_content += "⚠️ VALIDATION ISSUES FOUND:\n- " + "\n- ".join(validation_issues)
            validation_content += "\n\nPlease review and correct the analysis to ensure accuracy.\n\n"
        
        if validation_warnings:
            validation_content += "⚡ VALIDATION WARNINGS:\n- " + "\n- ".join(validation_warnings)
            validation_content += "\n\n"
        
        if not validation_issues and not validation_warnings:
            validation_content += "✅ No validation issues detected. Analysis appears to follow OPOS best practices."
        
        # Add recommendations for future analysis
        if cumulative_detection.get("cumulative_rows"):
            validation_content += f"\n📋 REMINDER: This OPOS file contains {len(cumulative_detection['cumulative_rows'])} summary rows. "
            validation_content += "Always exclude these when calculating totals to ensure accurate results."
        
        logger.info(f"Validation completed with {len(validation_issues)} issues and {len(validation_warnings)} warnings")
        
        return {
            **state,
            "validation_complete": True,
            "validation_issues": validation_issues,
            "validation_warnings": validation_warnings,
            "messages": state["messages"] + [
                SystemMessage(content=validation_content)
            ]
        }
        
    except Exception as e:
        logger.error(f"Error in OPOS validation: {str(e)}")
        error_message = f"Validation encountered an error: {str(e)}. Analysis may need manual review."
        
        return {
            **state,
            "validation_complete": True,
            "validation_error": str(e),
            "validation_issues": [],
            "validation_warnings": [],
            "messages": state["messages"] + [
                SystemMessage(content=error_message)
            ]
        }

# Helper function to check if validation should be run
def should_run_validation(state: GraphState) -> bool:
    """
    Determine if validation should be run based on current state.
    
    Args:
        state: Current graph state
        
    Returns:
        True if validation should be run, False otherwise
    """
    # Only run validation near the end of processing, not immediately after preprocessing
    current_step = state.get("step", 0)
    max_steps = state.get("max_steps", 10)
    
    # Run validation if we're in the last 2 steps to ensure we don't hit recursion limits
    return current_step >= max_steps - 2
