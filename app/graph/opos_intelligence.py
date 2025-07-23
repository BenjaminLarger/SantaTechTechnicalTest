"""OPOS Intelligence Tool Registry.

This module provides a centralized registry for all OPOS intelligence tools
to be easily imported and used by the LangGraph system.
"""

# Import all OPOS intelligence tools
from app.graph.tools_cumulative_detector import identify_summary_rows, detect_opos_structure

# Export all tools for easy access
__all__ = [
    'identify_summary_rows',
    'detect_opos_structure', 
]

# Tool registry for programmatic access
OPOS_INTELLIGENCE_TOOLS = {
    'identify_summary_rows': identify_summary_rows,
    'detect_opos_structure': detect_opos_structure,
}

def get_all_intelligence_tools():
    """Get all OPOS intelligence tools as a list."""
    return list(OPOS_INTELLIGENCE_TOOLS.values())

def get_intelligence_tool(tool_name: str):
    """Get a specific intelligence tool by name."""
    return OPOS_INTELLIGENCE_TOOLS.get(tool_name)
