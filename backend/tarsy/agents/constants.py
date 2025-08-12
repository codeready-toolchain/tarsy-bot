"""
Shared constants for agent processing.

"""


# ====================================================================
# Iteration Strategy Configuration
# ====================================================================

from enum import Enum

class IterationStrategy(str, Enum):
    """
    Available iteration strategies for agent processing.
    
    Each strategy implements a different approach to alert analysis:
    - REGULAR: Simple tool iteration without reasoning overhead
    - REACT: Standard ReAct pattern with Think→Action→Observation cycles
    - REACT_TOOLS: ReAct pattern focused on data collection only, no analysis
    - REACT_TOOLS_PARTIAL: ReAct + tools + partial analysis for incremental insights
    - REACT_FINAL_ANALYSIS: ReAct final analysis only, no tools, uses all accumulated data
    """
    REGULAR = "regular"
    REACT = "react"
    
    # NEW: Tool-focused strategies (data collection only)
    REACT_TOOLS = "react-tools"           # ReAct pattern, tools only, no analysis
    
    # NEW: Analysis-focused strategies  
    REACT_TOOLS_PARTIAL = "react-tools-partial"     # ReAct + tools + partial analysis
    REACT_FINAL_ANALYSIS = "react-final-analysis"   # ReAct final analysis only, no tools
