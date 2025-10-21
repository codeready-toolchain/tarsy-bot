/**
 * Tests for filterPersistence utility functions
 * Testing localStorage operations for filter state management
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import type { SessionFilter } from '../../types';
import {
  saveFiltersToStorage,
  loadFiltersFromStorage,
  clearFiltersFromStorage,
  savePaginationToStorage,
  loadPaginationFromStorage,
  clearPaginationFromStorage,
  saveSortToStorage,
  loadSortFromStorage,
  clearSortFromStorage,
  saveAdvancedFiltersVisibility,
  loadAdvancedFiltersVisibility,
  clearAllDashboardState,
  getDefaultFilters,
  getDefaultPagination,
  getDefaultSort,
  mergeWithDefaults,
} from '../../utils/filterPersistence';

describe('filterPersistence', () => {
  // Mock localStorage
  const localStorageMock = (() => {
    let store: Record<string, string> = {};

    return {
      getItem: (key: string) => store[key] || null,
      setItem: (key: string, value: string) => {
        store[key] = value.toString();
      },
      removeItem: (key: string) => {
        delete store[key];
      },
      clear: () => {
        store = {};
      },
    };
  })();

  beforeEach(() => {
    // Replace global localStorage with mock
    Object.defineProperty(window, 'localStorage', {
      value: localStorageMock,
      writable: true,
    });
    localStorageMock.clear();

    // Reset console.warn spy
    vi.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('filter persistence', () => {
    it('should save filters to localStorage', () => {
      const filters: SessionFilter = {
        search: 'test query',
        status: ['completed', 'failed'],
        agent_type: ['kubernetes'],
        alert_type: ['critical'],
        start_date: '2024-01-01',
        end_date: '2024-01-31',
        time_range_preset: '7d',
      };

      saveFiltersToStorage(filters);
      const stored = localStorage.getItem('tarsy-dashboard-filters');
      expect(stored).toBeTruthy();
      expect(JSON.parse(stored!)).toEqual(filters);
    });

    it('should load filters from localStorage', () => {
      const filters: SessionFilter = {
        search: 'test',
        status: ['completed'],
        agent_type: [],
        alert_type: [],
        start_date: null,
        end_date: null,
        time_range_preset: null,
      };

      localStorage.setItem('tarsy-dashboard-filters', JSON.stringify(filters));
      const loaded = loadFiltersFromStorage();
      expect(loaded).toEqual(filters);
    });

    it('should return null when no filters stored', () => {
      const loaded = loadFiltersFromStorage();
      expect(loaded).toBeNull();
    });

    it('should clear filters from localStorage', () => {
      const filters = getDefaultFilters();
      saveFiltersToStorage(filters);
      expect(localStorage.getItem('tarsy-dashboard-filters')).toBeTruthy();

      clearFiltersFromStorage();
      expect(localStorage.getItem('tarsy-dashboard-filters')).toBeNull();
    });

    it('should handle corrupted filter data gracefully', () => {
      localStorage.setItem('tarsy-dashboard-filters', 'invalid json{');
      const loaded = loadFiltersFromStorage();
      expect(loaded).toBeNull();
      expect(console.warn).toHaveBeenCalled();
    });

    it('should handle localStorage errors gracefully when saving', () => {
      // Mock setItem to throw error
      vi.spyOn(localStorage, 'setItem').mockImplementation(() => {
        throw new Error('Storage full');
      });

      const filters = getDefaultFilters();
      // Should not throw
      expect(() => saveFiltersToStorage(filters)).not.toThrow();
      expect(console.warn).toHaveBeenCalled();
    });
  });

  describe('pagination persistence', () => {
    it('should save pagination to localStorage', () => {
      const pagination = {
        page: 2,
        pageSize: 25,
        totalPages: 10,
        totalItems: 250,
      };

      savePaginationToStorage(pagination);
      const stored = localStorage.getItem('tarsy-dashboard-pagination');
      expect(stored).toBeTruthy();
      expect(JSON.parse(stored!)).toEqual(pagination);
    });

    it('should merge partial pagination updates', () => {
      const initial = {
        page: 1,
        pageSize: 10,
      };

      savePaginationToStorage(initial);

      const update = {
        page: 3,
      };

      savePaginationToStorage(update);

      const stored = localStorage.getItem('tarsy-dashboard-pagination');
      const parsed = JSON.parse(stored!);
      expect(parsed.page).toBe(3);
      expect(parsed.pageSize).toBe(10);
    });

    it('should load pagination from localStorage', () => {
      const pagination = {
        page: 5,
        pageSize: 50,
      };

      localStorage.setItem('tarsy-dashboard-pagination', JSON.stringify(pagination));
      const loaded = loadPaginationFromStorage();
      expect(loaded).toEqual(pagination);
    });

    it('should return null when no pagination stored', () => {
      const loaded = loadPaginationFromStorage();
      expect(loaded).toBeNull();
    });

    it('should clear pagination from localStorage', () => {
      savePaginationToStorage({ page: 1, pageSize: 10 });
      expect(localStorage.getItem('tarsy-dashboard-pagination')).toBeTruthy();

      clearPaginationFromStorage();
      expect(localStorage.getItem('tarsy-dashboard-pagination')).toBeNull();
    });

    it('should handle corrupted pagination data', () => {
      localStorage.setItem('tarsy-dashboard-pagination', 'not valid json');
      const loaded = loadPaginationFromStorage();
      expect(loaded).toBeNull();
      expect(console.warn).toHaveBeenCalled();
    });
  });

  describe('sort persistence', () => {
    it('should save sort state to localStorage', () => {
      const sort = {
        field: 'created_at',
        direction: 'asc' as const,
      };

      saveSortToStorage(sort);
      const stored = localStorage.getItem('tarsy-dashboard-sort');
      expect(stored).toBeTruthy();
      expect(JSON.parse(stored!)).toEqual(sort);
    });

    it('should load sort state from localStorage', () => {
      const sort = {
        field: 'severity',
        direction: 'desc' as const,
      };

      localStorage.setItem('tarsy-dashboard-sort', JSON.stringify(sort));
      const loaded = loadSortFromStorage();
      expect(loaded).toEqual(sort);
    });

    it('should return null when no sort state stored', () => {
      const loaded = loadSortFromStorage();
      expect(loaded).toBeNull();
    });

    it('should clear sort state from localStorage', () => {
      const sort = { field: 'created_at', direction: 'desc' as const };
      saveSortToStorage(sort);
      expect(localStorage.getItem('tarsy-dashboard-sort')).toBeTruthy();

      clearSortFromStorage();
      expect(localStorage.getItem('tarsy-dashboard-sort')).toBeNull();
    });

    it('should handle corrupted sort data', () => {
      localStorage.setItem('tarsy-dashboard-sort', '{invalid}');
      const loaded = loadSortFromStorage();
      expect(loaded).toBeNull();
      expect(console.warn).toHaveBeenCalled();
    });
  });

  describe('advanced filters visibility', () => {
    it('should save visibility state', () => {
      saveAdvancedFiltersVisibility(true);
      const stored = localStorage.getItem('tarsy-dashboard-advanced-filters-shown');
      expect(stored).toBeTruthy();
      expect(JSON.parse(stored!)).toBe(true);
    });

    it('should load visibility state', () => {
      localStorage.setItem('tarsy-dashboard-advanced-filters-shown', 'true');
      const visible = loadAdvancedFiltersVisibility();
      expect(visible).toBe(true);
    });

    it('should default to false when not stored', () => {
      const visible = loadAdvancedFiltersVisibility();
      expect(visible).toBe(false);
    });

    it('should handle boolean false correctly', () => {
      saveAdvancedFiltersVisibility(false);
      const visible = loadAdvancedFiltersVisibility();
      expect(visible).toBe(false);
    });

    it('should handle corrupted visibility data', () => {
      localStorage.setItem('tarsy-dashboard-advanced-filters-shown', 'invalid');
      const visible = loadAdvancedFiltersVisibility();
      expect(visible).toBe(false);
      expect(console.warn).toHaveBeenCalled();
    });
  });

  describe('clearAllDashboardState', () => {
    it('should clear all stored state', () => {
      // Set all types of data
      saveFiltersToStorage(getDefaultFilters());
      savePaginationToStorage({ page: 2, pageSize: 20 });
      saveSortToStorage({ field: 'test', direction: 'asc' });
      saveAdvancedFiltersVisibility(true);

      // Verify they're stored
      expect(localStorage.getItem('tarsy-dashboard-filters')).toBeTruthy();
      expect(localStorage.getItem('tarsy-dashboard-pagination')).toBeTruthy();
      expect(localStorage.getItem('tarsy-dashboard-sort')).toBeTruthy();
      expect(localStorage.getItem('tarsy-dashboard-advanced-filters-shown')).toBeTruthy();

      // Clear all
      clearAllDashboardState();

      // Verify all are cleared
      expect(localStorage.getItem('tarsy-dashboard-filters')).toBeNull();
      expect(localStorage.getItem('tarsy-dashboard-pagination')).toBeNull();
      expect(localStorage.getItem('tarsy-dashboard-sort')).toBeNull();
      expect(localStorage.getItem('tarsy-dashboard-advanced-filters-shown')).toBeNull();
    });

    it('should handle errors gracefully', () => {
      vi.spyOn(localStorage, 'removeItem').mockImplementation(() => {
        throw new Error('Cannot remove');
      });

      // Should not throw
      expect(() => clearAllDashboardState()).not.toThrow();
      expect(console.warn).toHaveBeenCalled();
    });
  });

  describe('default value getters', () => {
    it('should return default filters', () => {
      const defaults = getDefaultFilters();
      expect(defaults).toEqual({
        search: '',
        status: [],
        agent_type: [],
        alert_type: [],
        start_date: null,
        end_date: null,
        time_range_preset: null,
      });
    });

    it('should return default pagination', () => {
      const defaults = getDefaultPagination();
      expect(defaults).toEqual({
        page: 1,
        pageSize: 10,
        totalPages: 1,
        totalItems: 0,
      });
    });

    it('should return default sort', () => {
      const defaults = getDefaultSort();
      expect(defaults).toEqual({
        field: 'started_at_us',
        direction: 'desc',
      });
    });
  });

  describe('mergeWithDefaults', () => {
    it('should use defaults when saved is null', () => {
      const defaults = { a: 1, b: 2, c: 3 };
      const result = mergeWithDefaults(null, defaults);
      expect(result).toEqual(defaults);
    });

    it('should merge saved values with defaults', () => {
      const defaults = { a: 1, b: 2, c: 3 };
      const saved = { a: 10, c: 30 };
      const result = mergeWithDefaults(saved, defaults);
      expect(result).toEqual({ a: 10, b: 2, c: 30 });
    });

    it('should override all default values if saved has them', () => {
      const defaults = { a: 1, b: 2 };
      const saved = { a: 10, b: 20 };
      const result = mergeWithDefaults(saved, defaults);
      expect(result).toEqual(saved);
    });

    it('should ignore extra keys in saved', () => {
      const defaults = { a: 1, b: 2 };
      const saved = { a: 10, c: 30 };
      const result = mergeWithDefaults(saved, defaults);
      // c should be included as spread includes it
      expect(result.a).toBe(10);
      expect(result.b).toBe(2);
    });

    it('should handle empty saved object', () => {
      const defaults = { a: 1, b: 2 };
      const saved = {};
      const result = mergeWithDefaults(saved, defaults);
      expect(result).toEqual(defaults);
    });

    it('should handle partial updates correctly', () => {
      const defaults = {
        page: 1,
        pageSize: 10,
        totalPages: 1,
        totalItems: 0,
      };
      const saved = { page: 5 };
      const result = mergeWithDefaults(saved, defaults);
      expect(result.page).toBe(5);
      expect(result.pageSize).toBe(10);
      expect(result.totalPages).toBe(1);
      expect(result.totalItems).toBe(0);
    });
  });
});

