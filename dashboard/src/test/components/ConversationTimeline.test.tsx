/**
 * Tests for ConversationTimeline localStorage cleanup functionality
 * 
 * The cleanup function should:
 * 1. Remove entries older than 7 days
 * 2. Keep only the 50 most recent sessions
 * 3. Handle corrupted entries gracefully
 * 4. Support both old (array) and new (object with timestamp) formats
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { cleanupOldSessionEntries } from '../../components/ConversationTimeline';

describe('cleanupOldSessionEntries', () => {
  // Save original localStorage
  const originalLocalStorage = global.localStorage;

  beforeEach(() => {
    // Mock localStorage
    const localStorageMock = (() => {
      let store: Record<string, string> = {};

      return {
        getItem: (key: string) => store[key] || null,
        setItem: (key: string, value: string) => {
          store[key] = value;
        },
        removeItem: (key: string) => {
          delete store[key];
        },
        clear: () => {
          store = {};
        },
        key: (index: number) => {
          const keys = Object.keys(store);
          return keys[index] || null;
        },
        get length() {
          return Object.keys(store).length;
        }
      };
    })();

    Object.defineProperty(global, 'localStorage', {
      value: localStorageMock,
      writable: true
    });

    // Mock console methods to suppress expected warnings
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.spyOn(console, 'log').mockImplementation(() => {});
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    global.localStorage.clear();
    vi.restoreAllMocks();
    
    // Restore original localStorage
    Object.defineProperty(global, 'localStorage', {
      value: originalLocalStorage,
      writable: true
    });
  });

  it('should remove entries older than 7 days', () => {
    const now = Date.now();
    const eightDaysAgo = now - (8 * 24 * 60 * 60 * 1000);
    const fiveDaysAgo = now - (5 * 24 * 60 * 60 * 1000);

    // Add old entry (8 days ago)
    localStorage.setItem('session-old-123-expanded-items', JSON.stringify({
      items: ['item1', 'item2'],
      timestamp: eightDaysAgo
    }));

    // Add recent entry (5 days ago)
    localStorage.setItem('session-recent-456-expanded-items', JSON.stringify({
      items: ['item3', 'item4'],
      timestamp: fiveDaysAgo
    }));

    // Add current entry (now)
    localStorage.setItem('session-current-789-expanded-items', JSON.stringify({
      items: ['item5', 'item6'],
      timestamp: now
    }));

    cleanupOldSessionEntries();

    // Old entry should be removed
    expect(localStorage.getItem('session-old-123-expanded-items')).toBeNull();
    
    // Recent entries should remain
    expect(localStorage.getItem('session-recent-456-expanded-items')).not.toBeNull();
    expect(localStorage.getItem('session-current-789-expanded-items')).not.toBeNull();
  });

  it('should keep only the 50 most recent sessions', () => {
    const now = Date.now();

    // Add 60 sessions (all recent, within 7 days)
    for (let i = 0; i < 60; i++) {
      const timestamp = now - (i * 60 * 1000); // 1 minute apart
      localStorage.setItem(`session-test-${i}-expanded-items`, JSON.stringify({
        items: [`item-${i}`],
        timestamp
      }));
    }

    expect(localStorage.length).toBe(60);

    cleanupOldSessionEntries();

    // Should keep only 50
    expect(localStorage.length).toBe(50);

    // Verify the most recent 50 are kept (0-49)
    for (let i = 0; i < 50; i++) {
      expect(localStorage.getItem(`session-test-${i}-expanded-items`)).not.toBeNull();
    }

    // Verify the oldest 10 are removed (50-59)
    for (let i = 50; i < 60; i++) {
      expect(localStorage.getItem(`session-test-${i}-expanded-items`)).toBeNull();
    }
  });

  it('should handle old format entries (array without timestamp)', () => {
    const now = Date.now();

    // Add old format entry (array)
    localStorage.setItem('session-old-format-123-expanded-items', JSON.stringify(['item1', 'item2']));

    // Add new format entry
    localStorage.setItem('session-new-format-456-expanded-items', JSON.stringify({
      items: ['item3', 'item4'],
      timestamp: now
    }));

    cleanupOldSessionEntries();

    // Both should remain (old format entries get timestamp 0, so they're kept)
    expect(localStorage.getItem('session-old-format-123-expanded-items')).not.toBeNull();
    expect(localStorage.getItem('session-new-format-456-expanded-items')).not.toBeNull();
  });

  it('should remove corrupted entries', () => {
    // Add corrupted entry (invalid JSON)
    localStorage.setItem('session-corrupted-123-expanded-items', 'invalid-json{]');

    // Add valid entry
    localStorage.setItem('session-valid-456-expanded-items', JSON.stringify({
      items: ['item1'],
      timestamp: Date.now()
    }));

    cleanupOldSessionEntries();

    // Corrupted entry should be removed
    expect(localStorage.getItem('session-corrupted-123-expanded-items')).toBeNull();
    
    // Valid entry should remain
    expect(localStorage.getItem('session-valid-456-expanded-items')).not.toBeNull();
    
    // Should have logged a warning
    expect(console.warn).toHaveBeenCalledWith(
      expect.stringContaining('Removing corrupted localStorage entry'),
      expect.any(Error)
    );
  });

  it('should only remove session entries with correct prefix and suffix', () => {
    const now = Date.now();

    // Add session entries
    localStorage.setItem('session-test-123-expanded-items', JSON.stringify({
      items: ['item1'],
      timestamp: now
    }));

    // Add non-session entries
    localStorage.setItem('other-key-123', 'other-value');
    localStorage.setItem('session-incomplete', 'incomplete-key');
    localStorage.setItem('not-a-session-key', 'not-a-session');

    cleanupOldSessionEntries();

    // Only session entries should be processed; non-session entries should remain
    expect(localStorage.getItem('session-test-123-expanded-items')).not.toBeNull();
    expect(localStorage.getItem('other-key-123')).not.toBeNull();
    expect(localStorage.getItem('session-incomplete')).not.toBeNull();
    expect(localStorage.getItem('not-a-session-key')).not.toBeNull();
  });

  it('should handle empty localStorage', () => {
    expect(localStorage.length).toBe(0);
    
    // Should not throw
    expect(() => cleanupOldSessionEntries()).not.toThrow();
    
    expect(localStorage.length).toBe(0);
  });

  it('should combine age and count limits correctly', () => {
    const now = Date.now();
    const eightDaysAgo = now - (8 * 24 * 60 * 60 * 1000);

    // Add 55 sessions: 5 old (>7 days) + 50 recent
    for (let i = 0; i < 5; i++) {
      localStorage.setItem(`session-old-${i}-expanded-items`, JSON.stringify({
        items: [`old-item-${i}`],
        timestamp: eightDaysAgo - (i * 60 * 1000)
      }));
    }

    for (let i = 0; i < 50; i++) {
      localStorage.setItem(`session-recent-${i}-expanded-items`, JSON.stringify({
        items: [`recent-item-${i}`],
        timestamp: now - (i * 60 * 1000)
      }));
    }

    expect(localStorage.length).toBe(55);

    cleanupOldSessionEntries();

    // All old entries should be removed (age limit)
    for (let i = 0; i < 5; i++) {
      expect(localStorage.getItem(`session-old-${i}-expanded-items`)).toBeNull();
    }

    // All recent entries should remain (within age limit and count limit)
    for (let i = 0; i < 50; i++) {
      expect(localStorage.getItem(`session-recent-${i}-expanded-items`)).not.toBeNull();
    }

    expect(localStorage.length).toBe(50);
  });

  it('should log cleanup activity', () => {
    const now = Date.now();
    const eightDaysAgo = now - (8 * 24 * 60 * 60 * 1000);

    // Add some old entries to trigger cleanup
    localStorage.setItem('session-old-1-expanded-items', JSON.stringify({
      items: ['item1'],
      timestamp: eightDaysAgo
    }));
    localStorage.setItem('session-old-2-expanded-items', JSON.stringify({
      items: ['item2'],
      timestamp: eightDaysAgo
    }));

    cleanupOldSessionEntries();

    // Should have logged cleanup activity
    expect(console.log).toHaveBeenCalledWith(
      expect.stringContaining('Cleaned up')
    );
  });

  it('should not log when nothing is cleaned up', () => {
    const now = Date.now();

    // Add a recent entry
    localStorage.setItem('session-recent-123-expanded-items', JSON.stringify({
      items: ['item1'],
      timestamp: now
    }));

    cleanupOldSessionEntries();

    // Should not have logged cleanup (nothing was removed)
    expect(console.log).not.toHaveBeenCalled();
  });
});
