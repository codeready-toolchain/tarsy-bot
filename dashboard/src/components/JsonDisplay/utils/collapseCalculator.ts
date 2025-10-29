/**
 * Calculate smart collapse level based on JSON content size
 * Returns more conservative expansion for better readability
 * 
 * @param content - Content to analyze
 * @param collapsedProp - User's collapse preference
 * @returns Collapse level (false = fully expand, number = depth to expand)
 */
export const calculateSmartCollapseLevel = (
  content: any,
  collapsedProp?: boolean | number
): boolean | number => {
  // Only respect explicit false or numeric values
  // Let true fall through to smart sizing
  if (collapsedProp === false) return false;
  if (typeof collapsedProp === 'number') return collapsedProp;
  
  try {
    const jsonString = JSON.stringify(content);
    const size = jsonString.length;
    
    // More conservative thresholds for better readability
    if (size < 300) return false;      // Fully expand tiny JSON (<300 chars)
    if (size < 1000) return 2;         // Show 2 levels for small JSON
    if (size < 3000) return 1;         // Show 1 level for medium JSON
    return 1; // Collapse to 1 level for large JSON
  } catch {
    return 1; // Default to collapsed
  }
};

/**
 * Calculate smart string truncation based on JSON content size
 * Returns number of chars before truncating strings
 * 
 * @param content - Content to analyze
 * @returns Number of characters before truncation (0 = no truncation)
 */
export const calculateShortenTextAfterLength = (content: any): number => {
  try {
    const jsonString = JSON.stringify(content);
    const size = jsonString.length;
    
    // More aggressive truncation for larger content
    if (size < 500) return 0;          // No truncation for tiny JSON
    if (size < 2000) return 200;       // Truncate at 200 chars for small JSON
    if (size < 5000) return 100;       // Truncate at 100 chars for medium JSON
    return 80;                         // Truncate at 80 chars for large JSON
  } catch {
    return 100; // Default truncation
  }
};

/**
 * Check if JSON content is already fully expanded (nothing to collapse/expand)
 * 
 * @param content - Content to check
 * @returns True if content is tiny and already fully visible
 */
export const isAlreadyFullyExpanded = (content: any): boolean => {
  try {
    const jsonString = JSON.stringify(content);
    const size = jsonString.length;
    // If content is tiny (<300 chars), it's already fully shown
    // This matches the threshold in calculateSmartCollapseLevel
    return size < 300;
  } catch {
    return false;
  }
};
