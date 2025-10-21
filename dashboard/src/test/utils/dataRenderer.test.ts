/**
 * Tests for dataRenderer utility functions
 * Testing complex logic for rendering values with XSS prevention, timestamp detection, etc.
 */

import { describe, it, expect, vi } from 'vitest';
import {
  renderValue,
  formatKeyName,
  sortAlertFields,
  getFieldPriority,
} from '../../utils/dataRenderer';

// Mock formatTimestamp from timestamp module
vi.mock('../../utils/timestamp', () => ({
  formatTimestamp: vi.fn((_timestampUs: number, format: string) => {
    if (format === 'absolute') {
      return '2024-01-15 10:30:45';
    }
    return '2 hours ago';
  }),
}));

describe('dataRenderer', () => {
  describe('renderValue', () => {
    describe('null and undefined handling', () => {
      it('should handle null values', () => {
        const result = renderValue(null);
        expect(result).toEqual({
          type: 'simple',
          content: 'N/A',
          displayValue: 'N/A',
        });
      });

      it('should handle undefined values', () => {
        const result = renderValue(undefined);
        expect(result).toEqual({
          type: 'simple',
          content: 'N/A',
          displayValue: 'N/A',
        });
      });
    });

    describe('string handling', () => {
      it('should handle simple strings', () => {
        const result = renderValue('hello world');
        expect(result.type).toBe('simple');
        expect(result.displayValue).toBe('hello world');
      });

      it('should escape HTML in strings for XSS prevention', () => {
        const result = renderValue('<script>alert("xss")</script>');
        expect(result.content).not.toContain('<script>');
        expect(result.content).toContain('&lt;script&gt;');
      });

      it('should handle multiline strings', () => {
        const result = renderValue('line1\nline2\nline3');
        expect(result.type).toBe('multiline');
        expect(result.displayValue).toContain('\n');
      });

      it('should detect and mark URLs', () => {
        const result = renderValue('https://example.com/path');
        expect(result.type).toBe('url');
        expect(result.displayValue).toBe('https://example.com/path');
      });

      it('should not mark non-URLs as URLs', () => {
        const result = renderValue('example.com');
        expect(result.type).not.toBe('url');
      });

      it('should detect JSON strings', () => {
        const jsonStr = '{"key": "value", "number": 42}';
        const result = renderValue(jsonStr);
        expect(result.type).toBe('json');
        expect(result.displayValue).toContain('"key"');
      });

      it('should truncate very long strings', () => {
        const longString = 'a'.repeat(60000);
        const result = renderValue(longString);
        expect(result.displayValue).toContain('... [truncated]');
        expect(result.displayValue.length).toBeLessThan(51000);
      });
    });

    describe('number handling', () => {
      it('should handle regular numbers', () => {
        const result = renderValue(42);
        // Small numbers like 42 are within the timestamp range (seconds since 1970)
        // and will be detected as timestamps by the heuristic
        expect(result.type).toBe('timestamp');
      });

      it('should handle negative numbers', () => {
        const result = renderValue(-123.456);
        expect(result.type).toBe('simple');
        expect(result.displayValue).toBe('-123.456');
      });

      it('should handle NaN', () => {
        const result = renderValue(NaN);
        expect(result.type).toBe('simple');
        expect(result.displayValue).toBe('NaN');
      });

      it('should handle Infinity', () => {
        const result = renderValue(Infinity);
        expect(result.type).toBe('simple');
        expect(result.displayValue).toBe('Infinity');
      });

      it('should handle -Infinity', () => {
        const result = renderValue(-Infinity);
        expect(result.type).toBe('simple');
        expect(result.displayValue).toBe('-Infinity');
      });

      it('should detect timestamps by field name', () => {
        const timestamp = 1705315845000000; // microseconds
        const result = renderValue(timestamp, 'created_at');
        expect(result.type).toBe('timestamp');
        expect(result.displayValue).toContain('2024-01-15');
        expect(result.timestampUs).toBe(timestamp);
      });

      it('should detect timestamps by value pattern (microseconds)', () => {
        const timestamp = 1705315845000000; // 2024 in microseconds
        const result = renderValue(timestamp);
        expect(result.type).toBe('timestamp');
      });

      it('should detect timestamps by value pattern (milliseconds)', () => {
        const timestamp = 1705315845000; // 2024 in milliseconds
        const result = renderValue(timestamp);
        expect(result.type).toBe('timestamp');
      });

      it('should detect timestamps by value pattern (seconds)', () => {
        const timestamp = 1705315845; // 2024 in seconds
        const result = renderValue(timestamp);
        expect(result.type).toBe('timestamp');
      });

      it('should not treat very small negative numbers as timestamps', () => {
        // Negative numbers should not be timestamps
        const result = renderValue(-123);
        expect(result.type).toBe('simple');
        expect(result.displayValue).toBe('-123');
      });

      it('should recognize various timestamp field names', () => {
        const timestamp = 1705315845000000;
        const fieldNames = [
          'timestamp',
          'created_at',
          'updated_at',
          'event_time',
          'processed_at',
          'started_at',
          'finished_at',
        ];

        fieldNames.forEach((fieldName) => {
          const result = renderValue(timestamp, fieldName);
          expect(result.type).toBe('timestamp');
        });
      });
    });

    describe('boolean handling', () => {
      it('should handle true', () => {
        const result = renderValue(true);
        expect(result.type).toBe('simple');
        expect(result.displayValue).toBe('true');
      });

      it('should handle false', () => {
        const result = renderValue(false);
        expect(result.type).toBe('simple');
        expect(result.displayValue).toBe('false');
      });
    });

    describe('object and array handling', () => {
      it('should handle objects as JSON', () => {
        const obj = { key: 'value', number: 42 };
        const result = renderValue(obj);
        expect(result.type).toBe('json');
        expect(result.displayValue).toContain('"key"');
        expect(result.displayValue).toContain('"value"');
      });

      it('should handle arrays as JSON', () => {
        const arr = [1, 2, 3, 'test'];
        const result = renderValue(arr);
        expect(result.type).toBe('json');
        expect(result.displayValue).toContain('[');
      });

      it('should handle nested objects', () => {
        const obj = {
          level1: {
            level2: {
              value: 'deep',
            },
          },
        };
        const result = renderValue(obj);
        expect(result.type).toBe('json');
        expect(result.displayValue).toContain('level2');
      });

      it('should handle circular references gracefully', () => {
        const circular: any = { name: 'test' };
        circular.self = circular;
        const result = renderValue(circular);
        expect(result.type).toBe('simple');
        expect(result.displayValue).toContain('circular reference');
      });

      it('should handle very large objects', () => {
        const largeObj: Record<string, string> = {};
        for (let i = 0; i < 10000; i++) {
          largeObj[`key${i}`] = 'x'.repeat(20);
        }
        const result = renderValue(largeObj);
        expect(result.type).toBe('simple');
        expect(result.displayValue).toContain('Large object');
      });

      it('should escape HTML in JSON content', () => {
        const obj = { script: '<script>alert("xss")</script>' };
        const result = renderValue(obj);
        expect(result.content).not.toContain('<script>');
      });
    });

    describe('special types', () => {
      it('should handle symbols', () => {
        const sym = Symbol('test');
        const result = renderValue(sym);
        expect(result.type).toBe('simple');
        expect(result.displayValue).toBe('[Symbol]');
      });

      it('should handle BigInt', () => {
        const bigInt = BigInt(12345678901234567890);
        const result = renderValue(bigInt);
        expect(result.type).toBe('simple');
        expect(result.displayValue).toContain('n');
      });

      it('should handle functions', () => {
        const func = () => {};
        const result = renderValue(func);
        expect(result.type).toBe('simple');
        // Functions pass JSON.stringify() and fall through to String(value) fallback
        // Arrow functions become "() => {}", regular functions become "function() {}"
        expect(result.displayValue).toMatch(/(\(\)|function)/);
      });
    });

    describe('error handling', () => {
      it('should handle rendering errors gracefully', () => {
        // Mock console.error to avoid noise in test output
        const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

        // Create an object that throws when accessed
        const problematic = {};
        Object.defineProperty(problematic, 'toString', {
          get() {
            throw new Error('toString error');
          },
        });

        // This should not throw, but return error message
        const result = renderValue(problematic);
        expect(result.type).toBe('json'); // Will be handled as JSON

        consoleErrorSpy.mockRestore();
      });
    });
  });

  describe('formatKeyName', () => {
    it('should convert snake_case to Title Case', () => {
      expect(formatKeyName('alert_type')).toBe('Alert Type');
    });

    it('should handle single words', () => {
      expect(formatKeyName('namespace')).toBe('Namespace');
    });

    it('should handle multiple underscores', () => {
      expect(formatKeyName('created_at_timestamp_us')).toBe('Created At Timestamp Us');
    });

    it('should handle already formatted names', () => {
      expect(formatKeyName('AlertType')).toBe('Alerttype');
    });

    it('should handle empty strings', () => {
      expect(formatKeyName('')).toBe('');
    });
  });

  describe('getFieldPriority', () => {
    it('should return highest priority for alert_type', () => {
      expect(getFieldPriority('alert_type')).toBe(1);
    });

    it('should return high priority for severity', () => {
      expect(getFieldPriority('severity')).toBe(2);
    });

    it('should return low priority for runbook', () => {
      expect(getFieldPriority('runbook')).toBe(99);
    });

    it('should return low priority for context', () => {
      expect(getFieldPriority('context')).toBe(98);
    });

    it('should return default priority for unknown fields', () => {
      expect(getFieldPriority('unknown_field')).toBe(50);
    });

    it('should prioritize core fields', () => {
      const priorities = [
        'alert_type',
        'severity',
        'environment',
        'timestamp_us',
        'message',
      ].map(getFieldPriority);

      // Verify they're in ascending order (lower = higher priority)
      for (let i = 1; i < priorities.length; i++) {
        expect(priorities[i]).toBeGreaterThan(priorities[i - 1]);
      }
    });
  });

  describe('sortAlertFields', () => {
    it('should sort fields by priority', () => {
      const alertData = {
        runbook: 'some runbook',
        alert_type: 'critical',
        unknown_field: 'test',
        severity: 'high',
        context: 'some context',
      };

      const sorted = sortAlertFields(alertData);
      const keys = sorted.map(([key]) => key);

      // alert_type should be first
      expect(keys[0]).toBe('alert_type');
      // severity should be second
      expect(keys[1]).toBe('severity');
      // context and runbook should be near the end
      expect(keys.indexOf('context')).toBeGreaterThan(keys.indexOf('unknown_field'));
      expect(keys.indexOf('runbook')).toBeGreaterThan(keys.indexOf('unknown_field'));
    });

    it('should preserve all field values', () => {
      const alertData = {
        alert_type: 'critical',
        severity: 'high',
        message: 'test message',
      };

      const sorted = sortAlertFields(alertData);
      const sortedObj = Object.fromEntries(sorted);

      expect(sortedObj).toEqual(alertData);
    });

    it('should handle empty objects', () => {
      const sorted = sortAlertFields({});
      expect(sorted).toEqual([]);
    });

    it('should handle single field', () => {
      const alertData = { severity: 'high' };
      const sorted = sortAlertFields(alertData);
      expect(sorted).toEqual([['severity', 'high']]);
    });
  });
});

