"""
Base iteration controller interface and shared types.

This module provides the minimal interface and types needed by 
all iteration controller implementations.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Callable, Optional, List

if TYPE_CHECKING:
    from ...models.processing_context import StageContext

class IterationController(ABC):
    """
    Abstract controller for different iteration processing strategies.
    
    This allows clean separation between ReAct and regular processing flows
    without conditional logic scattered throughout the BaseAgent.
    """
    
    @abstractmethod
    def needs_mcp_tools(self) -> bool:
        """
        Determine if this iteration strategy requires MCP tool discovery.
        
        Returns:
            True if MCP tools should be discovered, False otherwise
        """
        pass
    
    @abstractmethod
    async def execute_analysis_loop(self, context: 'StageContext') -> str:
        """
        Execute analysis loop with clean StageContext.
        
        Args:
            context: StageContext containing all stage processing data
            
        Returns:
            Final analysis result string
        """
        pass

    def create_result_summary(
        self, 
        analysis_result: str, 
        context: 'StageContext'
    ) -> str:
        """
        Create result summary with clean StageContext.
        
        Default implementation provides simple formatting. Individual strategies
        can override this method to provide specialized formatting.
        
        Args:
            analysis_result: Raw analysis text from execute_analysis_loop
            context: StageContext containing all stage processing data
            
        Returns:
            Formatted summary string for this iteration strategy
        """
        if not analysis_result:
            return "No analysis result generated"
        
        return f"## Analysis Result\n\n{analysis_result}"

    def extract_final_analysis(
        self, 
        analysis_result: str, 
        context: 'StageContext'
    ) -> str:
        """
        Extract final analysis with clean StageContext.
        
        This method should extract a concise, user-friendly final analysis
        from the full analysis result for API consumption.
        
        Default implementation returns the analysis result as-is. Individual strategies
        should override this method to extract relevant final analysis.
        
        Args:
            analysis_result: Raw analysis text from execute_analysis_loop
            context: StageContext containing all stage processing data
            
        Returns:
            Clean final analysis string for API/dashboard consumption
        """
        if not analysis_result:
            return "No analysis result generated"
        
        return analysis_result

    def _extract_react_final_analysis(
        self, 
        analysis_result: str, 
        completion_patterns: list[str], 
        incomplete_patterns: list[str],
        fallback_extractor: Optional[Callable[[List[str]], str]],
        fallback_message: str,
        context: 'StageContext'
    ) -> str:
        """
        Shared utility for extracting final analysis from ReAct conversations.
        
        Args:
            analysis_result: Full ReAct conversation history
            completion_patterns: List of patterns to look for completion messages
            incomplete_patterns: List of patterns for incomplete messages
            fallback_extractor: Function to extract fallback data from list of strings
            fallback_message: Default message if no analysis found
            context: StageContext containing all stage processing data
            
        Returns:
            Extracted final analysis
        """
        if not analysis_result:
            return fallback_message
        
        lines = analysis_result.split('\n')
        
        # Look for final answer first (universal across all ReAct controllers)
        final_answer_content = []
        collecting_final_answer = False
        
        for i, line in enumerate(lines):
            if line.startswith("Final Answer:"):
                collecting_final_answer = True
                # Add content from the same line if any
                content = line.replace("Final Answer:", "").strip()
                if content:
                    final_answer_content.append(content)
                continue
            
            if collecting_final_answer:
                # Stop collecting if we hit another ReAct section
                if (line.startswith("Thought:") or 
                    line.startswith("Action:") or 
                    line.startswith("Observation:")):
                    break
                
                # Add all content lines (including empty ones within the final answer)
                final_answer_content.append(line)
        
        if final_answer_content:
            # Clean up trailing empty lines but preserve internal structure
            while final_answer_content and final_answer_content[-1].strip() == "":
                final_answer_content.pop()
            return '\n'.join(final_answer_content)
        
        # Look for stage-specific completion patterns
        for line in lines:
            for pattern in completion_patterns:
                if pattern in line and ":" in line:
                    summary_start = line.find(':') + 1
                    return line[summary_start:].strip()
        
        # Look for incomplete patterns
        for line in lines:
            for pattern in incomplete_patterns:
                if line.startswith(pattern):
                    return f"{pattern.rstrip(':')} due to iteration limits"
        
        # Use fallback extractor if provided
        if fallback_extractor:
            fallback_result = fallback_extractor(lines)
            if fallback_result:
                return fallback_result
        
        return fallback_message