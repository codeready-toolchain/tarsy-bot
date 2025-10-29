/**
 * Escape HTML to prevent XSS attacks
 */
const escapeHtml = (text: string): string => {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
};

/**
 * Apply syntax highlighting to YAML content
 * 
 * Colors used (GitHub-inspired palette):
 * - Keys: #22863a (green, bold)
 * - String values: #032f62 (dark blue)
 * - Numbers/booleans: #005cc5 (blue)
 * - Null values: #d73a49 (red)
 * - List markers: #6f42c1 (purple)
 * - Comments: #6a737d (gray, italic)
 * 
 * @param yaml - YAML content as string
 * @returns HTML string with syntax highlighting
 */
export const highlightYaml = (yaml: string): string => {
  const lines = yaml.split('\n');
  const highlightedLines = lines.map(line => {
    // Preserve leading whitespace
    const leadingSpaces = line.match(/^(\s*)/)?.[1] || '';
    const trimmedLine = line.trimStart();
    
    // Comment lines
    if (trimmedLine.startsWith('#')) {
      return `${leadingSpaces}<span style="color: #6a737d; font-style: italic;">${escapeHtml(trimmedLine)}</span>`;
    }
    
    // Key-value pairs
    const keyValueMatch = trimmedLine.match(/^([^:]+):\s*(.*)$/);
    if (keyValueMatch) {
      const key = keyValueMatch[1];
      const value = keyValueMatch[2];
      
      let highlightedValue = escapeHtml(value);
      
      // Highlight different value types
      if (value === 'null' || value === '~') {
        highlightedValue = `<span style="color: #d73a49;">${escapeHtml(value)}</span>`;
      } else if (value === 'true' || value === 'false') {
        highlightedValue = `<span style="color: #005cc5;">${escapeHtml(value)}</span>`;
      } else if (/^-?\d+(\.\d+)?$/.test(value.trim())) {
        highlightedValue = `<span style="color: #005cc5;">${escapeHtml(value)}</span>`;
      } else if (value.startsWith('"') && value.endsWith('"')) {
        highlightedValue = `<span style="color: #032f62;">${escapeHtml(value)}</span>`;
      } else if (value.startsWith("'") && value.endsWith("'")) {
        highlightedValue = `<span style="color: #032f62;">${escapeHtml(value)}</span>`;
      } else if (value.trim() && !value.startsWith('-') && !value.startsWith('[') && !value.startsWith('{')) {
        // Unquoted string value
        highlightedValue = `<span style="color: #032f62;">${escapeHtml(value)}</span>`;
      }
      
      return `${leadingSpaces}<span style="color: #22863a; font-weight: 600;">${escapeHtml(key)}</span>: ${highlightedValue}`;
    }
    
    // List items
    if (trimmedLine.startsWith('- ')) {
      const content = trimmedLine.substring(2);
      return `${leadingSpaces}<span style="color: #6f42c1;">-</span> ${escapeHtml(content)}`;
    }
    
    // Default: return escaped line
    return `${leadingSpaces}${escapeHtml(trimmedLine)}`;
  });
  
  return highlightedLines.join('\n');
};
