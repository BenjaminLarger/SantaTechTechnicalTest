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

The OPOS intelligence system consists of two main components:

### 1. LangGraph Integration (`app/graph/nodes/opos_analyzer.py`)

Specialized nodes integrated into the LangGraph workflow:

#### OPOS Preprocessing Node
- **Trigger**: Automatically detects OPOS indicators in sheet data
- **Function**: Performs comprehensive structure and summary row analysis before LLM planning
- **Output**: Complete processing recommendations, column classifications, and summary row identification

#### OPOS Validation Node
- **Trigger**: Runs after analysis completion
- **Function**: Validates results against OPOS best practices
- **Output**: Quality checks and corrective recommendations

### 2. Centralized Analysis Approach

**Note**: Previous tool-based approach (`identify_summary_rows`, `detect_opos_structure`) has been **deprecated** to eliminate redundancy. All OPOS analysis now occurs during preprocessing for optimal efficiency.

## Detection Algorithms

All detection algorithms are now implemented within the **OPOS Preprocessing Node** to eliminate redundancy and improve performance. The preprocessing node performs comprehensive analysis in a single pass.

### Summary Row Detection

The preprocessing node uses multiple heuristics to identify cumulative/summary rows:

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

The preprocessing node performs column type recognition and German terminology detection:

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

The OPOS system enhances the standard SheetAgent workflow with intelligent routing and safety mechanisms:

```
1. File Upload → Sheet Selection
2. **OPOS Preprocessing** ← Comprehensive structure and summary analysis
3. Planning & Analysis (Enhanced with complete structural context)
4. Tool Execution (Limited to 15 executions for safety)
5. **OPOS Validation** ← Quality checks and recommendations
6. Results & Output
```

**Key Improvement**: All OPOS analysis now occurs during preprocessing, eliminating the need for redundant tool calls during planning.

### Safety Mechanisms

The enhanced workflow includes multiple safety mechanisms to prevent infinite loops:

- **Max Steps Limit**: Default reduced to 10 steps (from 15) for faster termination
- **Tool Execution Limit**: Maximum 15 tool executions per workflow
- **Recursion Limit**: Set to 25 to prevent stack overflow
- **Hard Termination**: Multiple exit conditions to ensure graceful shutdown

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
    step: int                    # Current workflow step
    tool_executions: int         # Count of tool executions
    max_steps: int              # Maximum allowed steps (default: 10)
```

### Routing Logic

Smart routing with enhanced safety mechanisms:

```python
def should_run_opos_preprocessing(state: GraphState) -> bool:
    """Detect OPOS indicators to trigger preprocessing"""
    opos_indicators = [
        "debitor", "buchung", "beleg", "währung", "betrag",
        "invoice", "amount", "due", "fällig", "rechnungsdatum"
    ]
    return any(indicator in sheet_state.lower() for indicator in opos_indicators)

def planner_routing(state: GraphState):
    """Enhanced routing with safety limits"""
    current_step = state.get("step", 0)
    max_steps = state.get("max_steps", 10)  # Reduced from 15
    tool_executions = state.get("tool_executions", 0)
    
    # Hard limits to prevent infinite loops
    if current_step >= max_steps:
        return END
        
    if tool_executions >= 15:  # Tool execution limit
        return "validation"
        
    # Intelligent routing based on workflow state
    if should_validate(state):
        return "validation"
    else:
        return "tools"
```

## Enhanced Prompt Management

### OPOS-Aware Instructions

The system provides specialized guidance to the LLM based on preprocessing results:

```
When analyzing OPOS data:
1. Structure analysis is ALREADY COMPLETE from preprocessing
2. Summary/cumulative rows have been identified and should be excluded
3. Column types and German terminology have been classified
4. Focus on transaction-level data using the provided structural context
5. Handle multi-currency data appropriately based on preprocessing findings

IMPORTANT: Do not re-analyze structure or search for summary rows - 
this information is available from the preprocessing results.
```

## Performance Optimizations & Configuration

### Execution Limits

The enhanced system includes several performance optimizations:

```python
# Default configuration values
max_steps: int = 10              # Reduced from 15 for faster execution
tool_execution_limit: int = 15   # Prevents infinite tool loops
recursion_limit: int = 25        # Stack overflow prevention
planner_timeout: int = 60        # LLM call timeout in seconds
```

### Node Execution Flow

Enhanced workflow with centralized preprocessing:

1. **Entry Point**: Always starts with OPOS preprocessing
2. **Preprocessing**: Comprehensive analysis if OPOS indicators detected
   - Column type classification
   - Summary row identification
   - German terminology detection
   - Currency analysis
3. **Planning Loop**: Intelligent routing with complete structural context
4. **Tool Execution**: Focused on calculations using preprocessing results
5. **Validation**: Quality checks against OPOS best practices
6. **Termination**: Multiple exit conditions ensure graceful shutdown

**Performance Benefit**: Single comprehensive analysis eliminates redundant tool calls and reduces LLM workload.

## Benefits of Centralized Preprocessing

### Eliminated Redundancy
- **Before**: Structure analysis could occur multiple times through tool calls
- **After**: Single comprehensive analysis during preprocessing
- **Result**: Faster execution and reduced computational overhead

### Improved Accuracy
- **Consistent Results**: Same analysis logic applied once, eliminating potential discrepancies
- **Complete Context**: LLM receives full structural information upfront
- **Reduced Errors**: Less opportunity for inconsistent or incomplete analysis

### Enhanced Performance
- **Fewer Tool Calls**: LLM can proceed directly to calculations
- **Faster Execution**: No need to discover structure through trial-and-error
- **Better Resource Usage**: Single analysis pass vs. multiple tool invocations

### Simplified Workflow
- **Clear Separation**: Structure analysis separated from business logic
- **Maintainable Code**: Single source of truth for OPOS analysis
- **Easier Debugging**: Centralized analysis results for troubleshooting

### Error Handling

Robust error handling mechanisms:

- **Graceful Degradation**: Continues execution on non-critical errors
- **Step Increment**: Always increments step counter to prevent infinite loops
- **Resource Cleanup**: Automatic workbook saving and state preservation
- **Logging Integration**: Comprehensive logging for debugging and monitoring

