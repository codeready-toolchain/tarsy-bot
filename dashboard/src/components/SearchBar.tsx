import { useState, useEffect, useRef } from 'react';
import { TextField, InputAdornment } from '@mui/material';
import { Search } from '@mui/icons-material';
import type { SearchBarProps } from '../types';

/**
 * SearchBar component for Phase 4 - Search & Basic Filtering
 * Provides debounced search input with Material-UI styling
 */
const SearchBar: React.FC<SearchBarProps> = ({
  value,
  onChange,
  onSearch,
  placeholder = "Search alerts by type, error message...",
  debounceMs = 500
}) => {
  const [localValue, setLocalValue] = useState(value);
  const debounceTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Update local value when external value changes
  useEffect(() => {
    setLocalValue(value);
  }, [value]);

  // Clean up timeout on unmount
  useEffect(() => {
    return () => {
      if (debounceTimeoutRef.current) {
        clearTimeout(debounceTimeoutRef.current);
      }
    };
  }, []);

  const handleInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = event.target.value;
    setLocalValue(newValue);
    onChange(newValue);

    // Clear existing timeout
    if (debounceTimeoutRef.current) {
      clearTimeout(debounceTimeoutRef.current);
    }

    // Set new timeout for debounced search
    debounceTimeoutRef.current = setTimeout(() => {
      console.log('🔍 Debounced search triggered for:', newValue);
      onSearch(newValue);
      debounceTimeoutRef.current = null;
    }, debounceMs);
  };

  const handleKeyPress = (event: React.KeyboardEvent) => {
    // Trigger immediate search on Enter key
    if (event.key === 'Enter') {
      event.preventDefault();
      if (debounceTimeoutRef.current) {
        clearTimeout(debounceTimeoutRef.current);
        debounceTimeoutRef.current = null;
      }
      console.log('⚡ Immediate search triggered for:', localValue);
      onSearch(localValue);
    }
  };

  return (
    <TextField
      fullWidth
      placeholder={placeholder}
      variant="outlined"
      size="small"
      value={localValue}
      onChange={handleInputChange}
      onKeyPress={handleKeyPress}
      InputProps={{
        startAdornment: (
          <InputAdornment position="start">
            <Search />
          </InputAdornment>
        ),
      }}
      sx={{
        '& .MuiOutlinedInput-root': {
          backgroundColor: 'background.paper',
          '&:hover': {
            backgroundColor: 'background.paper',
          },
          '&.Mui-focused': {
            backgroundColor: 'background.paper',
          },
        },
      }}
    />
  );
};

export default SearchBar; 