## 🧠 Take-Home Assignment: Improving the SheetAgent AI Workflow

Welcome to the technical take-home challenge for the AI Engineer position at Santa Technologies\!

### 🗂️ Context

We’ve built a repo called **SheetAgent**, an AI-powered system designed to analyze Excel files containing open invoice data. These files often vary significantly in format:

\- Column names and structures are inconsistent (e.g., invoice amount might be in column \`D\` or \`E\`)  
\- Some contain **cumulated rows** that total the rows above them  
\- The agent must intelligently read the structure and perform computations

SheetAgent is powered by **LangGraph** and uses a planner/tool loop to:  
1\. Read cell ranges  
2\. Execute Python code (via \`openpyxl\`) in a sandboxed environment

It is already functional and used in production.

### 🧪 Your Task

Your assignment is to **improve the performance and reliability of the SheetAgent**, with a focus on enhancing the LLM workflow.

You are free to choose **how** you approach this. Some directions you might explore:  
\- Refine or restructure the LangGraph logic for better decision-making  
\- Improve the **prompts** used in the planner node to reduce redundant tool invocations  
\- Introduce **additional graph nodes** or **tool extensions** that make analysis more robust  
\- Add **heuristics or pre-processing logic** to help the LLM understand cumulated rows more efficiently

### 🎯 Evaluation Criteria

We’re particularly interested in how you:

1\. Understand and navigate an existing LangGraph-based architecture  
2\. Decide **which optimization levers** (prompt, graph structure, toolset) make the most impact  
3\. Communicate your thought process clearly and concisely (via code comments or a short write-up)

There are **no hard requirements** – creativity and clarity are more important than quantity.

### 🧰 Tools at Your Disposal

\- The existing codebase as outline in the README  
\- Example Excel workbooks for local testing [here](https://storage.googleapis.com/kritis-documents/Opos-test.xlsx)  
\- The existing prompt, which also explains more about the calculations and filtering criteria. You can find this PROMPT in \`app/api/endpoints/opos.py\` starting at line 12\.   
\- The correct analysis of a previous Sheet Agent run [here in the sheet "Analysis](https://docs.google.com/spreadsheets/d/1yw9TqUW2Necl0myW8mX_rqP9RjDu4Yb1LVvrUNxVJi8/edit?usp=sharing)

###  📦 Deliverables

1\. A pull request with your code improvements   
2\. A short README or comment in the PR summarizing:  
   \- What you changed  
   \- Why you chose this approach  
   \- Any limitations or further ideas

