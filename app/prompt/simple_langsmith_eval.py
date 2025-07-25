import os
import nest_asyncio
from dotenv import load_dotenv
from langsmith import Client
from langchain_openai import ChatOpenAI
from langchain.smith import RunEvalConfig, run_on_dataset

nest_asyncio.apply()

load_dotenv()
os.environ["LANGCHAIN_API_KEY"] = str(os.getenv("LANGCHAIN_API_KEY") or os.getenv("LANGSMITH_API_KEY", ""))
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGCHAIN_PROJECT", "sheet-agent-prompt-optimization")
os.environ["OPENAI_API_KEY"] = str(os.getenv("OPENAI_API_KEY"))

client = Client()

# Use GPT-3.5-turbo for minimal token consumption
llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0)

dataset_name = "OPOS Cumulated Row Detection"

# Better examples with clear context about OPOS analysis
opos_examples = [
    {
        "input": {
            "text": "In an OPOS spreadsheet, a row contains 'TOTAL' and sums invoice amounts. Is this a cumulative row that should be excluded from invoice calculations?"
        },
        "output": {
            "label": "Yes, cumulative row"
        }
    },
    {
        "input": {
            "text": "In an OPOS spreadsheet, a row contains individual invoice data with invoice number INV001, amount €1500, due date. Is this a cumulative row?"
        },
        "output": {
            "label": "No, individual invoice row"
        }
    },
    {
        "input": {
            "text": "In an OPOS spreadsheet, a row shows 'Debitor XYZ' with a SUM formula aggregating multiple invoices. Is this a cumulative row?"
        },
        "output": {
            "label": "Yes, cumulative row"
        }
    }
]

# Create or get dataset
try:
    dataset = client.create_dataset(
        dataset_name=dataset_name,
        description="OPOS analysis: detecting cumulative rows vs individual invoice rows"
    )
    print(f"Created dataset: {dataset_name}")
except Exception as e:
    # Dataset might already exist
    datasets = list(client.list_datasets(dataset_name=dataset_name))
    if datasets:
        dataset = datasets[0]
        print(f"Using existing dataset: {dataset_name}")
    else:
        print(f"Error creating dataset: {e}")
        exit(1)

# Add examples to dataset
for i, example in enumerate(opos_examples):
    try:
        client.create_example(
            inputs=example["input"],
            outputs=example["output"],
            dataset_id=dataset.id,
        )
        print(f"Added example {i+1}")
    except Exception as e:
        print(f"Example {i+1} might already exist: {e}")


def detect_opos_cumulated(inputs):
    """Enhanced function with clear OPOS context"""
    text = inputs["text"]
    
    # Provide clear context about OPOS analysis
    context_prompt = f"""
You are analyzing an OPOS (Open Posts) spreadsheet containing unpaid invoices and credits.

Context: In OPOS analysis, there are two types of rows:
1. Individual invoice/credit rows: contain specific invoice numbers, amounts, due dates
2. Cumulative rows: contain totals, sums, or aggregated data (like "Debitor Total", "SUM formulas")

Task: {text}

Answer with exactly one of these options:
- "Yes, cumulative row" (if it's a total/sum/aggregate row)
- "No, individual invoice row" (if it's a specific invoice/credit)
"""
    
    try:
        response = llm.predict(context_prompt)
        # Clean up response to match expected format
        if "yes" in response.lower() and "cumulative" in response.lower():
            return {"label": "Yes, cumulative row"}
        elif "no" in response.lower():
            return {"label": "No, individual invoice row"}
        else:
            # Fallback based on keywords
            if any(word in text.lower() for word in ["total", "sum", "debitor", "aggregate"]):
                return {"label": "Yes, cumulative row"}
            else:
                return {"label": "No, individual invoice row"}
    except Exception as e:
        print(f"Error in prediction: {e}")
        return {"label": "No, individual invoice row"}


eval_config = RunEvalConfig(
    evaluators=[
        # Simple string matching evaluator
        "exact_match"
    ]
)

try:
    print("Starting evaluation...")
    results = run_on_dataset(
        client=client,
        dataset_name=dataset_name,
        llm_or_chain_factory=detect_opos_cumulated,
        evaluation=eval_config,
        verbose=True,
    )
    
    print("✅ OPOS Cumulated Row Detection evaluation completed!")
    print(f"Results: {results}")
    
except Exception as e:
    print(f"❌ Error during evaluation: {e}")

