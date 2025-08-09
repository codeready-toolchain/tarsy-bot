/**
 * Timestamp utility functions for handling Unix timestamps in the frontend.
 * 
 * All functions work with Unix timestamps in microseconds (as received from the backend)
 * and provide various formatting options for display to users in their local timezone.
 */

import { formatDistanceToNow, format, isValid } from 'date-fns';

/**
 * Convert Unix timestamp (microseconds) to JavaScript Date object
 */
export const timestampUsToDate = (timestampUs: number): Date => {
  // Convert microseconds to milliseconds for JavaScript Date
  return new Date(timestampUs / 1000);
};

/**
 * Get current timestamp in microseconds (matching backend format)
 */
export const getCurrentTimestampUs = (): number => {
  return Date.now() * 1000;
};

/**
 * Format timestamp for display with various options
 */
export const formatTimestamp = (
  timestampUs: number, 
  formatType: 'relative' | 'absolute' | 'short' | 'time-only' | 'date-only' = 'relative'
): string => {
  const date = timestampUsToDate(timestampUs);
  
  if (!isValid(date)) {
    return 'Invalid date';
  }
  
  switch (formatType) {
    case 'relative':
      return formatDistanceToNow(date, { addSuffix: true });
    case 'absolute':
      return format(date, 'PPpp'); // e.g., "Dec 19, 2024 at 2:30:45 PM"
    case 'short':
      return format(date, 'MMM dd, HH:mm:ss'); // e.g., "Dec 19, 14:30:45"
    case 'time-only':
      return format(date, 'HH:mm:ss.SSS'); // e.g., "14:30:45.123"
    case 'date-only':
      return format(date, 'PPP'); // e.g., "December 19th, 2024"
    default:
      return date.toLocaleString();
  }
};

/**
 * Format duration between two timestamps
 */
export const formatDuration = (startUs: number, endUs?: number): string => {
  const endTime = endUs || getCurrentTimestampUs();
  const durationUs = endTime - startUs;
  const durationMs = durationUs / 1000; // Convert to milliseconds
  
  if (durationMs < 0) return '0ms';
  
  // Less than 1 second - show milliseconds
  if (durationMs < 1000) {
    return `${Math.round(durationMs)}ms`;
  }
  
  // Less than 1 minute - show seconds with decimal
  if (durationMs < 60000) {
    return `${(durationMs / 1000).toFixed(1)}s`;
  }
  
  // Less than 1 hour - show minutes and seconds
  if (durationMs < 3600000) {
    const minutes = Math.floor(durationMs / 60000);
    const seconds = Math.round((durationMs % 60000) / 1000);
    return `${minutes}m ${seconds}s`;
  }
  
  // 1 hour or more - show hours, minutes, and seconds
  const hours = Math.floor(durationMs / 3600000);
  const minutes = Math.floor((durationMs % 3600000) / 60000);
  const seconds = Math.round((durationMs % 60000) / 1000);
  return `${hours}h ${minutes}m ${seconds}s`;
};

/**
 * Format duration in milliseconds to human readable format
 */
export const formatDurationMs = (durationMs: number): string => {
  if (durationMs < 0) return '0ms';
  
  if (durationMs < 1000) {
    return `${Math.round(durationMs)}ms`;
  }
  
  if (durationMs < 60000) {
    return `${Math.round(durationMs / 1000)}s`;
  }
  
  const minutes = Math.floor(durationMs / 60000);
  const seconds = Math.round((durationMs % 60000) / 1000);
  return `${minutes}m ${seconds}s`;
};

/**
 * Check if a timestamp is within the last N minutes
 */
export const isWithinLastMinutes = (timestampUs: number, minutes: number): boolean => {
  const now = getCurrentTimestampUs();
  const minutesInUs = minutes * 60 * 1000 * 1000; // Convert to microseconds
  return (now - timestampUs) <= minutesInUs;
};

/**
 * Sort timestamps in reverse chronological order (newest first)
 */
export const sortTimestampsDesc = <T extends { timestamp_us: number }>(items: T[]): T[] => {
  return [...items].sort((a, b) => b.timestamp_us - a.timestamp_us);
};