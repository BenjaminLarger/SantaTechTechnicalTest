import logging
from datetime import datetime
from pathlib import Path
from typing import Union
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, HttpUrl, Field, field_validator

from app.services.analysis_service import run_analysis

router = APIRouter()
PROMPT = f"""
You have to analyze an open posts list from a company. It holds all unpaid invoices and credits for the company.
            
            # Rules
            - Check the format of the due date in the excel file. Chances are high that the format used is german. You need to cater for this.
            - Identify the format of "non-cumulative" rows. These are typically rows that contain an invoice number, a due date, an invoice date and an invoice amount.
            - Identify "invoice" rows. These are rows that are "non-cumulative" AND have a positive invoice amount.
            - Identify "credit" rows. These are rows that are "non-cumulative" AND have a negative invoice amount.
            - All rows that are not "non-cumulative" are "cumulative" rows. 
            - You get the maturity of an invoice by calculating the difference between today's date and the due date. 
            - You store all your output in a new sheet named "Analysis".
            
            # Your Tasks
            You provide a multi-step analysis of the entire open posts list.
            Here is each step outlined with additional instructions:
            1. Create a list of "cumulative" row numbers
               - You can tell that a row is cumulative if the key identifier (mostly the invoice number) all of a sudden changes format compared to the previous rows.
               - Sometimes, the key identifier contains the word "debitor", "debtor", "creditor". You then know that the file holds cumulative rows.
               - Sometimes, the values such as invoice date, due date, etc are empty
               - Other forms of cumulative rows are rows that accumulate the entire file under a given filter.
               - Programmatically create a list of "cumulative" row numbers.
               - Make sure to reuse the list accordingly in later steps.
            2. Create a list of "invoice" row numbers
               - You can tell that a row is an invoice row if it is not a "cumulative" row and has a POSITIVE invoice amount.
               - Programmatically create a list of "cumulative" row numbers.
               - Make sure to reuse the list accordingly in later steps.
            3. Create a list of "credit" row numbers
               - You can tell that a row is a credit row if it is not a "cumulative" row and has a NEGATIVE invoice amount.
               - Programmatically create a list of "credit" row numbers.
               - Make sure to reuse the list accordingly in later steps.
            4. Check each "invoice" and each "credit" row for completeness. "Is all required information present?"
               - Are invoice numbers, amounts, addresses, debtor names, creditor names, debtor numbers, etc present?
               - Use only "invoice" rows and "credit" rows.
            5. Calculate the sum over the invoice amounts of all "invoice" rows
            6. Calculate the sum over the credit amounts of all "credit" rows
            7. Create an ageing report on the "invoice" rows.
               - Cluster "invoice" rows by maturity into clusters: 1. Not mature 2. 1-30 days maturity 3. 31-60 days maturity 4. >60 days maturity. 
               - Calculate the maturity of a credit row by: (today's date - due date).days
               - For each maturity cluster, accumulate the invoice amount (sum of all invoice amounts in the cluster). 
               - For each maturity cluster, give the percentage of the total accumulated invoice amount, calculated in step 3.
            8. Create an ageing report on the "credit" rows.
               - Cluster "credit" rows by maturity into clusters: 1. Not mature 2. 1-30 days maturity 3. 31-60 days maturity 4. >60 days maturity. 
               - Calculate the maturity of a credit row by: (today's date - due date).days
               - For each maturity cluster, accumulate the credit amount (sum of all credit amounts in the cluster). 
               - For each maturity cluster, give the percentage of the total accumulated credit amount, calculated in step 4.
            9. Calculate the top 10 credit positions by amount (lowest to highest).
            10. Calculate the top 10 debtor positions by amount (highest to lowest).
            11. Duplicate analysis
               - Check whether the "invoice" rows hold duplicate invoice numbers.
               - If there are duplicates, provide a list of the duplicate invoice numbers.
               - Check the "cumulative" rows for duplicate debtor numbers or names.
               - If there are duplicates, provide a list of the duplicate debtor numbers or names.
            
            # Output
            Create a new sheet named "Analysis".
            Write the output in the "Analysis" sheet.
            Paste the output of each step so that it is clearly visible and easy to understand.     
            Use columns to separate the output of each step
            
            Today's date is the {datetime.now().strftime("%dth of %B %Y")}
            
            Take a deep breath and think step by step.
"""
OPTIMIZED_PROMPT = f"""
You are an expert Excel analyst specializing in OPOS (Open Posts) analysis. Your goal is to complete the analysis efficiently with MINIMAL tool calls.

# EFFICIENCY RULES (CRITICAL)
- READ DATA IN BULK: Always read entire ranges at once (e.g., A1:Z1000) instead of cell-by-cell
- BATCH OPERATIONS: Combine multiple analyses in single code executions
- REUSE DATA: Store data in variables to avoid re-reading
- STRUCTURE-FIRST: Read headers and sample rows to understand format before full analysis

# ANALYSIS WORKFLOW - OPTIMIZED APPROACH

## STEP 1: EFFICIENT DATA LOADING
- Read ALL data in one operation (suggested range: A1:Z1000 or identify actual range first)
- Identify column structure and German date formats in the same analysis
- Store data in pandas DataFrame for efficient processing

## STEP 2: BATCH ROW CLASSIFICATION 
- In ONE code execution, create ALL three lists simultaneously:
  * cumulative_rows = [] (contains "debitor", "total", empty key fields, format changes)
  * invoice_rows = [] (non-cumulative + positive amounts)  
  * credit_rows = [] (non-cumulative + negative amounts)
- Use vectorized pandas operations for classification

## STEP 3: COMPREHENSIVE CALCULATIONS (Single Execution)
- Calculate ALL required metrics in one code block:
  * Sum of invoice amounts
  * Sum of credit amounts  
  * Completeness check for both invoice and credit rows
  * Maturity calculations for aging reports
  * Top 10 debtors and credits
  * Duplicate detection

## STEP 4: BATCH REPORT GENERATION
- Create "Analysis" sheet and populate ALL results in one operation
- Use efficient pandas to_excel() methods for bulk writing

# SPECIFIC ANALYSIS TASKS

1. **Row Classification Indicators:**
   - Cumulative: "debitor", "debtor", "total", "sum", empty invoice numbers, format breaks
   - Invoice: Non-cumulative + amount > 0
   - Credit: Non-cumulative + amount < 0

2. **German Date Handling:**
   - Detect DD.MM.YYYY format automatically
   - Convert using pd.to_datetime with dayfirst=True

3. **Aging Clusters:**
   - Not mature: due_date > today
   - 1-30 days: 1 <= (today - due_date).days <= 30  
   - 31-60 days: 31 <= (today - due_date).days <= 60
   - >60 days: (today - due_date).days > 60

4. **Output Structure in "Analysis" Sheet:**
   - Column A: Step descriptions
   - Column B: Results/Lists  
   - Column C: Calculations
   - Column D: Percentages
   - Column E: Additional metrics

# OPTIMIZATION REMINDERS
- Minimize cell_range_reader calls by reading large ranges
- Use pandas for all data manipulation (faster than openpyxl loops)
- Combine related operations in single code blocks
- Cache intermediate results in variables

Today's date is the {datetime.now().strftime("%dth of %B %Y")}

EXECUTE WITH MAXIMUM EFFICIENCY - TARGET: ≤5 TOOL CALLS TOTAL
"""

TEST_PROMPT = """
You have to analyze an open posts list from a company. It holds all unpaid invoices and credits for the company.
            
            # Rules
            - Check the format of the due date in the excel file. Chances are high that the format used is german. You need to cater for this.
            - Identify the format of "non-cumulative" rows. These are typically rows that contain an invoice number, a due date, an invoice date and an invoice amount.
            - Identify "invoice" rows. These are rows that are "non-cumulative" AND have a positive invoice amount.
            - Identify "credit" rows. These are rows that are "non-cumulative" AND have a negative invoice amount.
            - All rows that are not "non-cumulative" are "cumulative" rows. 
            - You get the maturity of an invoice by calculating the difference between today's date and the due date. 
            - You store all your output in a new sheet named "Analysis".
            
            # Your Tasks
            You provide a multi-step analysis of the entire open posts list.
            Here is each step outlined with additional instructions:
            1. Create a list of "cumulative" row numbers
               - You can tell that a row is cumulative if the key identifier (mostly the invoice number) all of a sudden changes format compared to the previous rows.
               - Sometimes, the key identifier contains the word "debitor", "debtor", "creditor". You then know that the file holds cumulative rows.
               - Sometimes, the values such as invoice date, due date, etc are empty
               - Other forms of cumulative rows are rows that accumulate the entire file under a given filter.
               - Programmatically create a list of "cumulative" row numbers.
               - Make sure to reuse the list accordingly in later steps.
            
            
            # Output
            Write the output in the "Analysis" sheet.
            Paste the output of each step so that it is clearly visible and easy to understand.     
            Use columns to separate the output of each step
            
            Today's date is the 10th of June 2025
            
            Take a deep breath and think step by step.
"""

# Alternative: Even more aggressive optimization prompt
ULTRA_EFFICIENT_PROMPT = f"""
OPOS ANALYSIS - ULTRA-EFFICIENT MODE

OBJECTIVE: Complete full OPOS analysis in ≤3 tool calls

TOOL CALL 1: BULK DATA READING + STRUCTURE DETECTION
- Read entire sheet range (A1:Z1000)  
- Identify columns, detect German dates, sample data patterns
- Return: DataFrame with all data + column mapping

TOOL CALL 2: COMPLETE ANALYSIS ENGINE
Execute ALL calculations in one comprehensive script:
```python
# Row classification (vectorized)
cumulative_mask = df['invoice_col'].str.contains('debitor|total', na=True) | df['invoice_col'].isna()
invoice_mask = (~cumulative_mask) & (df['amount_col'] > 0)
credit_mask = (~cumulative_mask) & (df['amount_col'] < 0)

# All calculations at once
invoice_sum = df[invoice_mask]['amount_col'].sum()
credit_sum = df[credit_mask]['amount_col'].sum()

# Aging analysis (vectorized)
df['maturity'] = (pd.Timestamp.now() - pd.to_datetime(df['due_date'], dayfirst=True)).dt.days
aging_invoice = df[invoice_mask].groupby(pd.cut(df[invoice_mask]['maturity'], 
    bins=[-float('inf'), 0, 30, 60, float('inf')], 
    labels=['Not mature', '1-30 days', '31-60 days', '>60 days']))['amount_col'].agg(['sum', 'count'])

# Top 10 + duplicates
top_debtors = df[invoice_mask].nlargest(10, 'amount_col')
duplicate_invoices = df[df['invoice_col'].duplicated()]['invoice_col'].tolist()
```

TOOL CALL 3: BATCH REPORT OUTPUT
- Create "Analysis" sheet
- Write all results using efficient bulk operations
- Format for readability

German dates: Use dayfirst=True in pandas.to_datetime()
Today: {datetime.now().strftime("%dth of %B %Y")}

EFFICIENCY TARGET: 3 tool calls maximum
"""

TEST = "Create a new sheet named 'Analysis'. Then write 'Hello World' in the sheet."


class AnalysisRequest(BaseModel):
    """Request model for the analysis endpoint."""

    instruction: str = Field(PROMPT, description="The instruction for the analysis")
    workbook_source: str = Field(
        "https://storage.googleapis.com/kritis-documents/Opos-test.xlsx",
        description="The URL or local file path of the workbook to analyze",
    )

    @field_validator("workbook_source")
    @classmethod
    def validate_workbook_source(cls, v: str) -> str:
        """Validate that the workbook source is either a valid URL or an existing local file path."""
        if not v:
            raise ValueError("Workbook source cannot be empty")

        # Check if it's a URL
        parsed = urlparse(v)
        if parsed.scheme in ("http", "https"):
            return v

        # Check if it's a local file path
        file_path = Path(v)
        if file_path.exists() and file_path.is_file():
            # Check if it's an Excel file
            if file_path.suffix.lower() not in [".xlsx", ".xls"]:
                raise ValueError("Local file must be an Excel file (.xlsx or .xls)")
            return str(file_path.resolve())

        raise ValueError(
            "Workbook source must be either a valid URL (http/https) or an existing local Excel file path"
        )

    @property
    def is_url(self) -> bool:
        """Check if the workbook source is a URL."""
        parsed = urlparse(self.workbook_source)
        return parsed.scheme in ("http", "https")

    @property
    def is_local_file(self) -> bool:
        """Check if the workbook source is a local file."""
        return not self.is_url


class AnalysisResponse(BaseModel):
    """Response model for the analysis endpoint."""

    analysis_file_url: str


@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_workbook(request: AnalysisRequest):
    """
    Triggers the analysis of a workbook from a given URL or local file path.

    This endpoint initiates the analysis process, which includes:
    1. Loading the workbook from the provided URL or local file path
    2. Processing the data in a secure sandbox environment
    3. Generating an analysis report in a new Excel file
    4. In non-local environments, uploading the result to Google Cloud Storage

    All file operations are performed in a secure temporary directory to prevent
    unauthorized file system access.

    Args:
        request: The analysis request containing the workbook source (URL or local file path).

    Returns:
        A response containing the URL to the analysis file. In local environments,
        this will be a success message with the local file path. In non-local
        environments, this will be a public URL to the file in Google Cloud Storage.

    Raises:
        HTTPException: If an error occurs during the analysis process.
    """
    try:
        result_url = run_analysis(
            instruction=request.instruction,
            workbook_source=request.workbook_source,
            is_local_file=request.is_local_file,
        )
        return {"analysis_file_url": result_url}
    except Exception as e:
        logging.exception("Error during analysis")
        raise HTTPException(
            status_code=500, detail=f"An unexpected error occurred: {e}"
        )
