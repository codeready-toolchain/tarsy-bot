"""
Utility functions for extracting comprehensive error details from exceptions.
"""

from tarsy.utils.logger import get_module_logger

logger = get_module_logger(__name__)


def extract_error_details(exception: Exception) -> str:
    """
    Extract comprehensive error details from an exception.
    
    This function provides detailed information about an exception including:
    - Exception type and message
    - Root cause analysis (walks exception chain)
    - All exception instance variables
    
    Args:
        exception: The exception to analyze
        
    Returns:
        A formatted string containing all available error details
    """
    details = []
    details.append(f"Type={type(exception).__name__}")
    details.append(f"Message={str(exception)}")
    
    # Get the root cause (walk to the bottom of the exception chain)
    root_cause = exception
    while root_cause.__cause__ is not None:
        root_cause = root_cause.__cause__
    
    # If we found a different root cause, include it
    if root_cause != exception:
        details.append(f"RootCause={type(root_cause).__name__}: {str(root_cause)}")
    
    # Use vars() to dump all instance variables
    try:
        exception_vars = vars(exception)
        if exception_vars:
            for key, value in exception_vars.items():
                str_value = repr(value)
                # No truncation - preserve full error details for debugging
                details.append(f"{key}={str_value}")
    except Exception as e:
        # Log the failure to extract exception variables, but continue with available details
        logger.warning(
            f"Failed to extract variables from exception {type(exception).__name__}: {e}"
        )
    
    return " | ".join(details)
