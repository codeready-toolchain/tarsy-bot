"""Data masking service for sensitive MCP server data.

This module provides the core data masking functionality to prevent
sensitive data from reaching the LLM, logging, and storage systems.
"""

import re
from typing import Any, Dict, List, Optional, Pattern
import json

from tarsy.models.agent_config import MaskingConfig, MaskingPattern
from tarsy.config.builtin_config import BUILTIN_MASKING_PATTERNS, BUILTIN_PATTERN_GROUPS
from tarsy.utils.logger import get_logger

# Import will be available when MCPServerRegistry is implemented
# For now, we'll use TYPE_CHECKING to avoid runtime import issues
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from tarsy.services.mcp_server_registry import MCPServerRegistry

logger = get_logger(__name__)


class DataMaskingService:
    """Service for masking sensitive data in MCP server responses.
    
    This service applies configurable regex patterns to mask sensitive
    information before it reaches the LLM, logging, or storage systems.
    """
    
    def __init__(self, mcp_registry: Optional["MCPServerRegistry"] = None):
        """Initialize the data masking service.
        
        Args:
            mcp_registry: Registry for looking up MCP server configurations.
                         If None, masking will be disabled for all servers.
        """
        self.mcp_registry = mcp_registry
        self.compiled_patterns: Dict[str, Pattern[str]] = {}
        self.custom_pattern_metadata: Dict[str, Dict[str, str]] = {}
        self._load_builtin_patterns()
        
        logger.info("DataMaskingService initialized")
    
    def _load_builtin_patterns(self) -> None:
        """Load and compile built-in regex patterns.
        
        This method compiles all built-in patterns for performance.
        Patterns that fail to compile will be logged and skipped.
        """
        logger.debug("Loading built-in masking patterns")
        
        for pattern_name, pattern_config in BUILTIN_MASKING_PATTERNS.items():
            try:
                compiled_pattern = re.compile(
                    pattern_config["pattern"], 
                    re.DOTALL | re.MULTILINE
                )
                self.compiled_patterns[pattern_name] = compiled_pattern
                logger.debug(f"Compiled pattern: {pattern_name}")
            except re.error as e:
                logger.error(f"Failed to compile built-in pattern '{pattern_name}': {e}")
        
        logger.info(f"Loaded {len(self.compiled_patterns)} built-in patterns")
    
    def _compile_and_add_custom_patterns(self, custom_patterns: List[MaskingPattern]) -> List[str]:
        """Compile custom patterns and add them to the compiled patterns dictionary.
        
        Args:
            custom_patterns: List of MaskingPattern objects to compile and add
            
        Returns:
            List of pattern names that were successfully compiled and added
        """
        compiled_pattern_names = []
        
        for custom_pattern in custom_patterns:
            if not custom_pattern.enabled:
                logger.debug(f"Skipping disabled custom pattern: {custom_pattern.name}")
                continue
                
            try:
                compiled_pattern = re.compile(
                    custom_pattern.pattern,
                    re.DOTALL | re.MULTILINE
                )
                
                # Store both compiled pattern and replacement text
                # Use a unique key to avoid conflicts with built-in patterns
                pattern_key = f"custom_{custom_pattern.name}"
                self.compiled_patterns[pattern_key] = compiled_pattern
                
                # Store custom pattern metadata for replacement lookup
                self.custom_pattern_metadata[pattern_key] = {
                    'replacement': custom_pattern.replacement,
                    'description': custom_pattern.description
                }
                
                compiled_pattern_names.append(pattern_key)
                logger.debug(f"Compiled custom pattern: {custom_pattern.name} -> {pattern_key}")
                
            except re.error as e:
                logger.error(f"Failed to compile custom pattern '{custom_pattern.name}': {e}")
                continue
        
        logger.debug(f"Successfully compiled {len(compiled_pattern_names)} custom patterns")
        return compiled_pattern_names
    
    def mask_response(self, response: Dict[str, Any], server_name: str) -> Dict[str, Any]:
        """Apply server-specific masking patterns to response data.
        
        This method looks up the masking configuration for the specified server
        and applies all configured patterns to the response data.
        
        Args:
            response: The response data from the MCP server
            server_name: Name of the MCP server that generated the response
            
        Returns:
            The response data with sensitive information masked
        """
        logger.debug(f"mask_response called for server: {server_name}")
        
        try:
            # Step 1: Get masking configuration for the server
            masking_config = self._get_server_masking_config(server_name)
            if not masking_config or not masking_config.enabled:
                logger.debug(f"Masking disabled for server: {server_name}")
                return response
            
            # Step 2: Expand pattern groups to individual patterns
            all_patterns = []
            if masking_config.pattern_groups:
                expanded_patterns = self._expand_pattern_groups(masking_config.pattern_groups)
                all_patterns.extend(expanded_patterns)
            
            # Step 3: Add individual patterns
            if masking_config.patterns:
                all_patterns.extend(masking_config.patterns)
            
            # Step 4: Add custom patterns
            custom_pattern_names = []
            if masking_config.custom_patterns:
                custom_pattern_names = self._compile_and_add_custom_patterns(masking_config.custom_patterns)
                logger.debug(f"Compiled and added {len(custom_pattern_names)} custom patterns: {custom_pattern_names}")
            
            # Combine all patterns (built-in + custom)
            all_patterns.extend(custom_pattern_names)
            
            if not all_patterns:
                logger.debug(f"No patterns configured for server: {server_name}")
                return response
            
            # Remove duplicates while preserving order
            unique_patterns = []
            seen = set()
            for pattern in all_patterns:
                if pattern not in seen:
                    unique_patterns.append(pattern)
                    seen.add(pattern)
            
            logger.debug(f"Applying {len(unique_patterns)} patterns to response for server: {server_name}")
            
            # Step 5: Apply masking to the response data
            masked_response = self._mask_data_structure(response, unique_patterns)
            
            logger.debug(f"Masking completed for server: {server_name}")
            return masked_response
            
        except Exception as e:
            logger.error(f"Error during masking for server '{server_name}': {e}")
            # Fail-safe behavior: mask the entire response content
            logger.warning(f"Applying fail-safe masking for server: {server_name}")
            return self._apply_failsafe_masking(response)
    
    def _mask_data_structure(self, data: Any, patterns: List[str]) -> Any:
        """Recursively traverse and mask data structures.
        
        Args:
            data: The data structure to mask (can be dict, list, str, or other types)
            patterns: List of pattern names to apply
            
        Returns:
            The data structure with sensitive information masked
        """
        if isinstance(data, dict):
            # Recursively mask dictionary values
            masked_dict = {}
            for key, value in data.items():
                masked_dict[key] = self._mask_data_structure(value, patterns)
            return masked_dict
            
        elif isinstance(data, list):
            # Recursively mask list elements
            return [self._mask_data_structure(item, patterns) for item in data]
            
        elif isinstance(data, str):
            # Apply patterns to string content
            return self._apply_patterns(data, patterns)
            
        else:
            # For other types (int, float, bool, None), return unchanged
            return data
    
    def _apply_failsafe_masking(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Apply fail-safe masking when normal masking fails.
        
        Args:
            response: The original response data
            
        Returns:
            A response with all string content masked
        """
        logger.debug("Applying fail-safe masking")
        
        try:
            # Convert response to string and mask it entirely
            response_str = json.dumps(response, default=str)
            masked_content = "***MASKED_ERROR***"
            
            # Try to preserve the basic response structure
            if "result" in response:
                return {"result": masked_content}
            else:
                return {"masked_response": masked_content}
                
        except Exception as e:
            logger.error(f"Error in fail-safe masking: {e}")
            # Ultimate fail-safe
            return {"result": "***MASKED_ERROR***"}
    
    def _apply_patterns(self, text: str, patterns: List[str]) -> str:
        """Apply a list of compiled regex patterns to mask text content.
        
        This method applies patterns sequentially and handles errors gracefully
        with fail-safe behavior.
        
        Args:
            text: The text content to mask
            patterns: List of pattern names to apply
            
        Returns:
            The text with sensitive information masked
        """
        logger.debug(f"_apply_patterns called with {len(patterns)} patterns on text length {len(text)}")
        
        if not text or not patterns:
            return text
        
        masked_text = text
        patterns_applied = 0
        
        for pattern_name in patterns:
            if pattern_name not in self.compiled_patterns:
                logger.warning(f"Pattern '{pattern_name}' not found in compiled patterns - skipping")
                continue
            
            # Get replacement text (built-in vs custom patterns)
            if pattern_name.startswith("custom_"):
                # Custom pattern - get replacement from metadata
                if pattern_name not in self.custom_pattern_metadata:
                    logger.warning(f"Custom pattern '{pattern_name}' metadata not found - skipping")
                    continue
                replacement = self.custom_pattern_metadata[pattern_name]["replacement"]
            else:
                # Built-in pattern - get replacement from builtin patterns
                if pattern_name not in BUILTIN_MASKING_PATTERNS:
                    logger.warning(f"Built-in pattern '{pattern_name}' not found in builtin patterns - skipping")
                    continue
                replacement = BUILTIN_MASKING_PATTERNS[pattern_name]["replacement"]
            
            try:
                compiled_pattern = self.compiled_patterns[pattern_name]
                
                # Apply the pattern with error handling
                original_length = len(masked_text)
                masked_text = compiled_pattern.sub(replacement, masked_text)
                new_length = len(masked_text)
                
                if new_length != original_length:
                    patterns_applied += 1
                    logger.debug(f"Pattern '{pattern_name}' applied - text length changed from {original_length} to {new_length}")
                else:
                    logger.debug(f"Pattern '{pattern_name}' applied - no matches found")
                    
            except Exception as e:
                logger.error(f"Error applying pattern '{pattern_name}': {e}")
                # Continue with other patterns rather than failing completely
                continue
        
        logger.debug(f"Pattern application complete - {patterns_applied}/{len(patterns)} patterns had matches")
        return masked_text
    
    def _expand_pattern_groups(self, pattern_groups: List[str]) -> List[str]:
        """Expand pattern group names to individual pattern names.
        
        Args:
            pattern_groups: List of pattern group names to expand
            
        Returns:
            List of individual pattern names from all specified groups
        """
        logger.debug(f"_expand_pattern_groups called with groups: {pattern_groups}")
        
        expanded_patterns = []
        for group_name in pattern_groups:
            if group_name in BUILTIN_PATTERN_GROUPS:
                group_patterns = BUILTIN_PATTERN_GROUPS[group_name]
                expanded_patterns.extend(group_patterns)
                logger.debug(f"Expanded group '{group_name}' to patterns: {group_patterns}")
            else:
                logger.warning(f"Unknown pattern group '{group_name}' - skipping")
        
        # Remove duplicates while preserving order
        unique_patterns = []
        seen = set()
        for pattern in expanded_patterns:
            if pattern not in seen:
                unique_patterns.append(pattern)
                seen.add(pattern)
        
        logger.debug(f"Final expanded patterns: {unique_patterns}")
        return unique_patterns
    
    def _get_server_masking_config(self, server_name: str) -> Optional[MaskingConfig]:
        """Get masking configuration for a specific server.
        
        Args:
            server_name: Name of the MCP server
            
        Returns:
            The masking configuration for the server, or None if not configured
        """
        logger.debug(f"_get_server_masking_config called for server: {server_name}")
        
        if not self.mcp_registry:
            logger.debug("No MCP registry available - masking disabled")
            return None
        
        try:
            # Query the MCP registry for server configuration
            server_config = self.mcp_registry.get_server_config_safe(server_name)
            if not server_config:
                logger.debug(f"Server configuration not found for: {server_name}")
                return None
            
            # Check if the server has masking configuration
            if not hasattr(server_config, 'data_masking') or not server_config.data_masking:
                logger.debug(f"No masking configuration found for server: {server_name}")
                return None
            
            masking_config = server_config.data_masking
            logger.debug(f"Found masking configuration for server '{server_name}': enabled={masking_config.enabled}")
            return masking_config
            
        except Exception as e:
            logger.error(f"Error retrieving masking config for server '{server_name}': {e}")
            return None