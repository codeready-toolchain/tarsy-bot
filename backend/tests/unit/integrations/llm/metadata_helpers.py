"""
Helper functions for testing LLM metadata extraction.

These utilities help parse and validate response metadata from LLM providers,
particularly for Google/Gemini native tools (Google Search, URL Context).
"""

from typing import Any, Dict, List, Optional


def aggregate_chunks(chunks: List[Any]) -> Optional[Any]:
    """
    Aggregate streaming chunks to reconstruct final message with metadata.
    
    LangChain's AIMessageChunk supports the + operator which:
    - Concatenates content
    - Merges metadata from all chunks
    - Returns complete message with full response_metadata
    
    Args:
        chunks: List of AIMessageChunk objects from streaming
        
    Returns:
        Final aggregated message with complete metadata, or None if no chunks
        
    Example:
        >>> chunks = [chunk1, chunk2, chunk3]
        >>> final = aggregate_chunks(chunks)
        >>> print(final.response_metadata)
    """
    if not chunks:
        return None
    
    try:
        # Start with first chunk
        final_message = chunks[0]
        
        # Aggregate remaining chunks using LangChain's + operator
        for chunk in chunks[1:]:
            final_message = final_message + chunk
        
        return final_message
    except Exception as e:
        print(f"Failed to aggregate chunks for metadata: {e}")
        return None


def extract_tool_usage_summary(metadata: dict, content: str = "") -> Optional[Dict[str, Any]]:
    """
    Extract structured tool usage information from response metadata and content.
    
    Extracts:
    - Google Search: web_search_queries, search_entry_point (from metadata)
    - URL Context: grounding_chunks with web URIs (from metadata)
    - Code Execution: Python code blocks and output blocks (from content)
    
    Args:
        metadata: Response metadata from aggregated message
        content: Response content for code execution detection
        
    Returns:
        Structured tool usage summary, or None if no tools used
        
    Example:
        >>> metadata = {
        ...     'grounding_metadata': {
        ...         'web_search_queries': ['test query']
        ...     }
        ... }
        >>> summary = extract_tool_usage_summary(metadata)
        >>> print(summary['google_search']['query_count'])
        1
    """
    if not metadata and not content:
        return None
    
    tool_usage = {}
    
    # Check for grounding metadata (Google Search or URL Context)
    if metadata:
        grounding = metadata.get('grounding_metadata', {})
        
        if grounding:
            # Google Search detection
            search_queries = grounding.get('web_search_queries', [])
            if search_queries:
                tool_usage['google_search'] = {
                    'queries': search_queries,
                    'query_count': len(search_queries)
                }
            
            # URL Context detection (grounding chunks without search queries)
            chunks = grounding.get('grounding_chunks', [])
            if chunks and not search_queries:
                urls = []
                for chunk in chunks:
                    if 'web' in chunk and 'uri' in chunk['web']:
                        urls.append({
                            'uri': chunk['web']['uri'],
                            'title': chunk['web'].get('title', '')
                        })
                if urls:
                    tool_usage['url_context'] = {
                        'urls': urls,
                        'url_count': len(urls)
                    }
    
    # Code Execution detection (appears in content, not metadata)
    if content:
        code_blocks = content.count("```python")
        output_blocks = content.count("```output")
        
        if code_blocks > 0 or output_blocks > 0:
            tool_usage['code_execution'] = {
                'code_blocks': code_blocks,
                'output_blocks': output_blocks,
                'detected': True
            }
    
    return tool_usage if tool_usage else None

