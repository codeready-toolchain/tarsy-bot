/**
 * Search and highlighting utilities for Phase 4
 */

/**
 * Highlights search terms in text with HTML markup
 * @param text - The text to highlight search terms in
 * @param searchTerm - The search term to highlight
 * @returns HTML string with highlighted search terms
 */
export const highlightSearchTerm = (text: string, searchTerm: string): string => {
  if (!searchTerm || !searchTerm.trim()) {
    return text;
  }

  // Escape special regex characters in search term
  const escapedSearchTerm = searchTerm.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  
  // Create regex for case-insensitive search
  const regex = new RegExp(`(${escapedSearchTerm})`, 'gi');
  
  // Replace matches with highlighted version
  return text.replace(regex, '<mark style="background-color: #ffeb3b; padding: 1px 2px; border-radius: 2px;">$1</mark>');
};

/**
 * Checks if any filters are active
 * @param filters - The session filters object
 * @returns true if any filters are active
 */
export const hasActiveFilters = (filters: {
  search?: string;
  status?: string[];
  agent_type?: string[];
  alert_type?: string[];
}): boolean => {
  return Boolean(
    (filters.search && filters.search.trim()) ||
    (filters.status && filters.status.length > 0) ||
    (filters.agent_type && filters.agent_type.length > 0) ||
    (filters.alert_type && filters.alert_type.length > 0)
  );
};

 