/**
 * Tests for timestamp utility functions
 * Testing timestamp conversion and formatting logic
 */

import { describe, it, expect, vi } from 'vitest';
import {
  timestampUsToDate,
  getCurrentTimestampUs,
  formatTimestamp,
  formatDuration,
  formatDurationMs,
  isWithinLastMinutes,
  sortTimestampsDesc,
} from '../../utils/timestamp';

// Mock date-fns to have predictable results
vi.mock('date-fns', () => ({
  formatDistanceToNow: vi.fn((_date: Date) => '2 hours ago'),
  format: vi.fn((_date: Date, formatStr: string) => {
    if (formatStr === 'PPpp') return 'Jan 15, 2024, 10:30:45 AM';
    if (formatStr === 'MMM dd, HH:mm:ss') return 'Jan 15, 10:30:45';
    if (formatStr === 'HH:mm:ss.SSS') return '10:30:45.123';
    if (formatStr === 'PPP') return 'January 15th, 2024';
    return _date.toLocaleString();
  }),
  isValid: vi.fn((date: Date) => !isNaN(date.getTime())),
}));

describe('timestamp utilities', () => {
  describe('timestampUsToDate', () => {
    it('should convert microseconds to Date', () => {
      const microseconds = 1705315845000000; // Jan 15, 2024
      const date = timestampUsToDate(microseconds);
      expect(date).toBeInstanceOf(Date);
      expect(date.getTime()).toBe(microseconds / 1000);
    });

    it('should handle zero timestamp', () => {
      const date = timestampUsToDate(0);
      expect(date).toBeInstanceOf(Date);
      expect(date.getTime()).toBe(0);
    });

    it('should handle recent timestamps', () => {
      const now = Date.now();
      const microseconds = now * 1000;
      const date = timestampUsToDate(microseconds);
      expect(Math.abs(date.getTime() - now)).toBeLessThan(1);
    });
  });

  describe('getCurrentTimestampUs', () => {
    it('should return current timestamp in microseconds', () => {
      const before = Date.now() * 1000;
      const current = getCurrentTimestampUs();
      const after = Date.now() * 1000;

      expect(current).toBeGreaterThanOrEqual(before);
      expect(current).toBeLessThanOrEqual(after);
    });

    it('should return timestamp as number', () => {
      const timestamp = getCurrentTimestampUs();
      expect(typeof timestamp).toBe('number');
      expect(Number.isInteger(timestamp)).toBe(true);
    });

    it('should return value in microseconds range', () => {
      const timestamp = getCurrentTimestampUs();
      // Should be > 1 trillion (microseconds since 1970)
      expect(timestamp).toBeGreaterThan(1000000000000);
    });
  });

  describe('formatTimestamp', () => {
    const testTimestamp = 1705315845000000; // Jan 15, 2024

    it('should format as relative by default', () => {
      const formatted = formatTimestamp(testTimestamp);
      expect(formatted).toBe('2 hours ago');
    });

    it('should format as relative when specified', () => {
      const formatted = formatTimestamp(testTimestamp, 'relative');
      expect(formatted).toBe('2 hours ago');
    });

    it('should format as absolute when specified', () => {
      const formatted = formatTimestamp(testTimestamp, 'absolute');
      expect(formatted).toBe('Jan 15, 2024, 10:30:45 AM');
    });

    it('should format as short when specified', () => {
      const formatted = formatTimestamp(testTimestamp, 'short');
      expect(formatted).toBe('Jan 15, 10:30:45');
    });

    it('should format as time-only when specified', () => {
      const formatted = formatTimestamp(testTimestamp, 'time-only');
      expect(formatted).toBe('10:30:45.123');
    });

    it('should format as date-only when specified', () => {
      const formatted = formatTimestamp(testTimestamp, 'date-only');
      expect(formatted).toBe('January 15th, 2024');
    });

    it('should handle invalid timestamps', () => {
      const formatted = formatTimestamp(NaN);
      expect(formatted).toBe('Invalid date');
    });

    it('should handle negative timestamps', () => {
      const formatted = formatTimestamp(-1000000);
      expect(typeof formatted).toBe('string');
    });
  });

  describe('formatDuration', () => {
    it('should format sub-second durations as "0s"', () => {
      const start = 1000000000000; // microseconds
      const end = start + 500000; // +500ms
      const formatted = formatDuration(start, end);
      expect(formatted).toBe('0s');
    });

    it('should format second durations', () => {
      const start = 1000000000000;
      const end = start + 2500000; // +2.5s
      const formatted = formatDuration(start, end);
      expect(formatted).toBe('2.5s');
    });

    it('should format minute durations', () => {
      const start = 1000000000000;
      const end = start + 125000000; // +2m 5s
      const formatted = formatDuration(start, end);
      expect(formatted).toMatch(/2m 5s/);
    });

    it('should format hour durations', () => {
      const start = 1000000000000;
      const end = start + 7325000000; // +2h 2m 5s
      const formatted = formatDuration(start, end);
      expect(formatted).toMatch(/2h 2m 5s/);
    });

    it('should use current time when end is not provided', () => {
      const start = getCurrentTimestampUs() - 1000000; // 1 second ago
      const formatted = formatDuration(start);
      expect(formatted).toMatch(/0s|s/);
    });

    it('should handle zero duration', () => {
      const time = 1000000000000;
      const formatted = formatDuration(time, time);
      expect(formatted).toBe('0s');
    });

    it('should handle negative duration (return "0s")', () => {
      const start = 1000000000000;
      const end = start - 1000000;
      const formatted = formatDuration(start, end);
      expect(formatted).toBe('0s');
    });

    it('should not show milliseconds for sub-second durations', () => {
      const start = 1000000000000;
      const end = start + 123456; // 123.456ms
      const formatted = formatDuration(start, end);
      expect(formatted).toBe('0s');
    });
  });

  describe('formatDurationMs', () => {
    it('should format sub-second durations as "0s"', () => {
      expect(formatDurationMs(500)).toBe('0s');
    });

    it('should format second durations', () => {
      expect(formatDurationMs(2500)).toBe('3s');
    });

    it('should format minute durations', () => {
      expect(formatDurationMs(125000)).toBe('2m 5s');
    });

    it('should handle zero', () => {
      expect(formatDurationMs(0)).toBe('0s');
    });

    it('should handle negative values', () => {
      expect(formatDurationMs(-100)).toBe('0s');
    });

    it('should round values appropriately', () => {
      expect(formatDurationMs(1234)).toBe('1s');
      expect(formatDurationMs(999)).toBe('0s');
    });

    it('should format large minute durations', () => {
      expect(formatDurationMs(305000)).toBe('5m 5s');
    });
  });

  describe('isWithinLastMinutes', () => {
    it('should return true for recent timestamps', () => {
      const now = getCurrentTimestampUs();
      const recentTime = now - 30000000; // 30 seconds ago
      expect(isWithinLastMinutes(recentTime, 1)).toBe(true);
    });

    it('should return false for old timestamps', () => {
      const now = getCurrentTimestampUs();
      const oldTime = now - 120000000; // 2 minutes ago
      expect(isWithinLastMinutes(oldTime, 1)).toBe(false);
    });

    it('should handle exact boundary', () => {
      // Use fake timers to avoid race condition between capturing time and checking
      vi.useFakeTimers();
      const fixedTime = new Date('2024-01-15T10:30:45.000Z');
      vi.setSystemTime(fixedTime);
      
      const now = getCurrentTimestampUs();
      const exactMinuteAgo = now - 60000000; // exactly 60 seconds
      expect(isWithinLastMinutes(exactMinuteAgo, 1)).toBe(true);
      
      vi.useRealTimers();
    });

    it('should handle multiple minutes', () => {
      const now = getCurrentTimestampUs();
      const fiveMinutesAgo = now - 300000000; // 5 minutes ago
      expect(isWithinLastMinutes(fiveMinutesAgo, 10)).toBe(true);
      expect(isWithinLastMinutes(fiveMinutesAgo, 4)).toBe(false);
    });

    it('should handle zero minutes', () => {
      const now = getCurrentTimestampUs();
      expect(isWithinLastMinutes(now, 0)).toBe(true);
      expect(isWithinLastMinutes(now - 1000, 0)).toBe(false);
    });

    it('should return false for future timestamps', () => {
      const now = getCurrentTimestampUs();
      const future = now + 60000000; // 1 minute in future
      expect(isWithinLastMinutes(future, 5)).toBe(false);
    });
  });

  describe('sortTimestampsDesc', () => {
    it('should sort items by timestamp descending', () => {
      const items = [
        { timestamp_us: 1000000000000, id: '1' },
        { timestamp_us: 3000000000000, id: '3' },
        { timestamp_us: 2000000000000, id: '2' },
      ];

      const sorted = sortTimestampsDesc(items);
      expect(sorted[0].id).toBe('3');
      expect(sorted[1].id).toBe('2');
      expect(sorted[2].id).toBe('1');
    });

    it('should handle empty array', () => {
      const sorted = sortTimestampsDesc([]);
      expect(sorted).toEqual([]);
    });

    it('should handle single item', () => {
      const items = [{ timestamp_us: 1000000000000, id: '1' }];
      const sorted = sortTimestampsDesc(items);
      expect(sorted).toEqual(items);
    });

    it('should handle duplicate timestamps', () => {
      const items = [
        { timestamp_us: 1000000000000, id: '1' },
        { timestamp_us: 1000000000000, id: '2' },
        { timestamp_us: 2000000000000, id: '3' },
      ];

      const sorted = sortTimestampsDesc(items);
      expect(sorted[0].id).toBe('3');
      // Order of items with same timestamp is preserved
      expect([sorted[1].id, sorted[2].id]).toContain('1');
      expect([sorted[1].id, sorted[2].id]).toContain('2');
    });

    it('should not mutate original array', () => {
      const items = [
        { timestamp_us: 1000000000000, id: '1' },
        { timestamp_us: 2000000000000, id: '2' },
      ];

      const original = [...items];
      sortTimestampsDesc(items);

      expect(items).toEqual(original);
    });

    it('should work with objects containing extra properties', () => {
      const items = [
        { timestamp_us: 1000000000000, id: '1', extra: 'data1' },
        { timestamp_us: 2000000000000, id: '2', extra: 'data2' },
      ];

      const sorted = sortTimestampsDesc(items);
      expect(sorted[0].extra).toBe('data2');
      expect(sorted[1].extra).toBe('data1');
    });
  });
});

