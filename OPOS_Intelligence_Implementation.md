# OPOS Intelligence Implementation

## Overview

This document describes the implementation of the OPOS (Open Posts) intelligence system within the SheetAgent project. The system provides automated detection and analysis of German financial data structures to improve processing efficiency and accuracy.

## What is OPOS?

OPOS (Open Posts) refers to unpaid invoices or outstanding accounts receivable in German accounting systems. These files typically contain:

- **Invoice data**: Belegnummer (document numbers), Rechnungsdatum (invoice dates)
- **Customer information**: Debitor numbers and names
- **Financial details**: Amounts, currencies, due dates
- **German terminology**: Buchungsdatum, Belegart, Währung, etc.
- **Summary rows**: Cumulative totals that can cause double-counting if not excluded

## Architecture

The OPOS intelligence system consists of three main components:

### 1. Standalone Analysis Tool (`excel_structure_analyzer.py`)

A command-line tool for direct Excel file analysis:

```bash
python excel_structure_analyzer.py path/to/file.xlsx [--sheet SheetName]
```

**Features:**
- Independent Excel structure analysis
- OPOS pattern detection
- Cumulative row identification
- JSON and human-readable output
- No dependencies on the main SheetAgent workflow

### 2. LangGraph Integration (`app/graph/nodes/opos_analyzer.py`)

Specialized nodes integrated into the LangGraph workflow:

#### OPOS Preprocessing Node
- **Trigger**: Automatically detects OPOS indicators in sheet data
- **Function**: Analyzes structure before LLM planning
- **Output**: Processing recommendations and structural insights

#### OPOS Validation Node
- **Trigger**: Runs after analysis completion
- **Function**: Validates results against OPOS best practices
- **Output**: Quality checks and corrective recommendations

### 3. Tool Suite (`app/graph/tools_cumulative_detector.py`)

LangChain tools for runtime analysis:

- `identify_summary_rows`: Detects cumulative rows to exclude
- `detect_opos_structure`: Analyzes column types and German terminology

## Detection Algorithms

### Summary Row Detection

The system uses multiple heuristics to identify cumulative/summary rows:

#### Heuristic 1: Keyword Detection
Searches for German financial keywords in row data:
```python
keywords = ['debitor', 'hauptbuchkonto', 'buchungskreis', 'total', 'sum', 'gesamt']
```

#### Heuristic 2: Empty Key Fields
Identifies rows with >60% empty key fields but containing amounts:
- Indicates summary rows that aggregate data from detail rows
- Prevents double-counting in financial calculations

#### Heuristic 3: Format Changes
Detects formatting anomalies that indicate structural boundaries:
- Font changes, bold text, spacing patterns
- Different data types in typically uniform columns

### Structure Detection

#### Column Type Recognition
Uses pattern matching to identify:

- **Invoice Numbers**: Patterns like `^[A-Z]{1,3}[0-9]+$`
- **Dates**: Multiple German date formats
- **Amounts**: Numeric patterns with currency indicators
- **Debitor IDs**: Customer identification patterns
- **Currency**: EUR, USD, GBP, CHF detection

#### German Terminology Detection
Recognizes German accounting terms:
```python
german_terms = [
    "Buchungsdatum", "Belegart", "Belegnummer", "Belegdatum",
    "Buchungsschlüssel", "Negativbuchung", "Mahnstufe", 
    "Währung", "Hauswährung", "Zahlungsfr", "Skontosatz", "Debitor"
]
```

## Integration with LangGraph Workflow

### Workflow Enhancement

The OPOS system enhances the standard SheetAgent workflow:

```
1. File Upload → Sheet Selection
2. **OPOS Preprocessing** ← NEW
3. Planning & Analysis
4. Tool Execution
5. **OPOS Validation** ← NEW
6. Results & Output
```

### State Management

Extended `GraphState` includes OPOS-specific fields:

```python
class GraphState(TypedDict):
    # ... existing fields ...
    opos_preprocessing_complete: bool
    opos_guidance: str
    cumulative_detection_results: Dict[str, Any]
    opos_structure_results: Dict[str, Any]
    validation_issues: List[str]
    validation_warnings: List[str]
```

### Routing Logic

Smart routing based on content detection:

```python
def should_run_opos_preprocessing(state: GraphState) -> bool:
    """Detect OPOS indicators to trigger preprocessing"""
    opos_indicators = [
        "debitor", "buchung", "beleg", "währung", "betrag",
        "invoice", "amount", "due", "fällig", "rechnungsdatum"
    ]
    return any(indicator in sheet_state.lower() for indicator in opos_indicators)
```

## Enhanced Prompt Management

### OPOS-Aware Instructions

The system provides specialized guidance to the LLM:

```
When analyzing OPOS data:
1. Use identify_summary_rows to detect cumulative rows
2. Exclude detected summary rows from calculations
3. Focus on transaction-level data for accurate totals
4. Handle German terminology appropriately
5. Consider currency conversions in multi-currency data
```

