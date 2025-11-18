import React, { useState } from 'react';
import {
  Box,
  Typography,
  Pagination,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  TextField
} from '@mui/material';

import type { PaginationControlsProps } from '../types';

/**
 * PaginationControls component for Phase 6 - Advanced Filtering & Pagination
 * Enhanced pagination with page size controls, jump-to-page, and comprehensive navigation
 */
const PaginationControls: React.FC<PaginationControlsProps> = ({
  pagination,
  onPageChange,
  onPageSizeChange,
  disabled = false
}) => {
  const [jumpToPage, setJumpToPage] = useState<string>('');

  // Calculate display range
  const startItem = (pagination.page - 1) * pagination.pageSize + 1;
  const endItem = Math.min(pagination.page * pagination.pageSize, pagination.totalItems);

  // Handle jump to page
  const handleJumpToPageChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const value = event.target.value;
    // Only allow digits
    if (value === '' || /^\d+$/.test(value)) {
      setJumpToPage(value);
    }
  };

  const handleJumpToPageKeyPress = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter') {
      const pageNumber = parseInt(jumpToPage);
      if (pageNumber >= 1 && pageNumber <= pagination.totalPages) {
        onPageChange(pageNumber);
        setJumpToPage('');
      }
    }
  };

  const handleJumpToPageBlur = () => {
    const pageNumber = parseInt(jumpToPage);
    if (pageNumber >= 1 && pageNumber <= pagination.totalPages) {
      onPageChange(pageNumber);
    }
    setJumpToPage('');
  };

  // Page size options
  const pageSizeOptions = [10, 25, 50, 100];

  // Handle page size change
  const handlePageSizeChange = (newPageSize: number) => {
    // When changing page size, calculate what the new page should be to maintain position
    const currentFirstItem = (pagination.page - 1) * pagination.pageSize + 1;
    const newPage = Math.max(1, Math.ceil(currentFirstItem / newPageSize));
    
    onPageSizeChange(newPageSize);
    if (newPage !== pagination.page) {
      onPageChange(newPage);
    }
  };

  // Early return if no pagination needed
  if (pagination.totalItems <= Math.min(...pageSizeOptions)) {
    return null;
  }

  return (
    <Box sx={{ 
      display: 'flex', 
      justifyContent: 'space-between', 
      alignItems: 'center', 
      mt: 2,
      flexWrap: 'wrap',
      gap: 2
    }}>
      {/* Results Info */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, minWidth: 200 }}>
        <Typography variant="body2" color="text.secondary">
          Showing {startItem.toLocaleString()}-{endItem.toLocaleString()} of {pagination.totalItems.toLocaleString()} results
        </Typography>
        
        {/* Page Size Selector */}
        <FormControl size="small" sx={{ minWidth: 80 }}>
          <InputLabel>Per Page</InputLabel>
          <Select
            value={pagination.pageSize}
            label="Per Page"
            onChange={(e) => handlePageSizeChange(e.target.value as number)}
            disabled={disabled}
          >
            {pageSizeOptions.map((size) => (
              <MenuItem key={size} value={size}>
                {size}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </Box>

      {/* Pagination Controls */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
        {/* Jump to Page */}
        {pagination.totalPages > 10 && (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Typography variant="body2" color="text.secondary">
              Go to page:
            </Typography>
            <TextField
              size="small"
              type="text"
              value={jumpToPage}
              onChange={handleJumpToPageChange}
              onKeyPress={handleJumpToPageKeyPress}
              onBlur={handleJumpToPageBlur}
              placeholder={pagination.page.toString()}
              disabled={disabled}
              inputProps={{ 
                min: 1, 
                max: pagination.totalPages,
                style: { width: 60, textAlign: 'center' }
              }}
              sx={{ 
                '& .MuiOutlinedInput-input': {
                  textAlign: 'center'
                }
              }}
            />
            <Typography variant="body2" color="text.secondary">
              of {pagination.totalPages}
            </Typography>
          </Box>
        )}

        {/* Pagination Navigation */}
        <Pagination
          count={pagination.totalPages}
          page={pagination.page}
          onChange={(_, page) => onPageChange(page)}
          color="primary"
          size="small"
          showFirstButton={true}
          showLastButton={true}
          siblingCount={1}
          boundaryCount={1}
          disabled={disabled}
          sx={{
            '& .MuiPaginationItem-root': {
              fontSize: '0.875rem'
            }
          }}
        />
      </Box>
    </Box>
  );
};

export default PaginationControls; 
