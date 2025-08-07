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
    - CLASSIC_REACT: Standard ReAct pattern with Think→Action→Observation cycles
    """
    REGULAR = "regular"
    CLASSIC_REACT = "classic_react"
