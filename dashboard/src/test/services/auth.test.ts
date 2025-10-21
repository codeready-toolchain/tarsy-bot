/**
 * Tests for auth service
 * Testing authentication logic with OAuth2 proxy
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { authService } from '../../services/auth';

// Mock config
vi.mock('../../config/env', () => ({
  config: {
    isDevelopment: true,
  },
}));

describe('authService', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    // Reset fetch mock
    fetchMock = vi.fn();
    global.fetch = fetchMock;

    // Mock console methods
    vi.spyOn(console, 'log').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});

    // Mock window.location
    delete (window as any).location;
    window.location = {
      href: '',
      pathname: '/dashboard',
      search: '?filter=test',
      origin: 'http://localhost:3000',
    } as any;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('checkAuthStatus', () => {
    it('should return true for successful authenticated response', async () => {
      fetchMock.mockResolvedValue({
        status: 200,
        redirected: false,
        headers: new Headers({ 'content-type': 'application/json' }),
      });

      const isAuthenticated = await authService.checkAuthStatus();
      expect(isAuthenticated).toBe(true);
    });

    it('should return false for redirected response', async () => {
      fetchMock.mockResolvedValue({
        status: 200,
        redirected: true,
        headers: new Headers({ 'content-type': 'application/json' }),
      });

      const isAuthenticated = await authService.checkAuthStatus();
      expect(isAuthenticated).toBe(false);
    });

    it('should return false for 302 redirect status', async () => {
      fetchMock.mockResolvedValue({
        status: 302,
        redirected: false,
        headers: new Headers({ 'content-type': 'application/json' }),
      });

      const isAuthenticated = await authService.checkAuthStatus();
      expect(isAuthenticated).toBe(false);
    });

    it('should return false for non-JSON content type', async () => {
      fetchMock.mockResolvedValue({
        status: 200,
        redirected: false,
        headers: new Headers({ 'content-type': 'text/html' }),
      });

      const isAuthenticated = await authService.checkAuthStatus();
      expect(isAuthenticated).toBe(false);
    });

    it('should return false for 401 unauthorized', async () => {
      fetchMock.mockResolvedValue({
        status: 401,
        redirected: false,
        headers: new Headers({ 'content-type': 'application/json' }),
      });

      const isAuthenticated = await authService.checkAuthStatus();
      expect(isAuthenticated).toBe(false);
    });

    it('should return false on fetch error', async () => {
      fetchMock.mockRejectedValue(new Error('Network error'));

      const isAuthenticated = await authService.checkAuthStatus();
      expect(isAuthenticated).toBe(false);
      expect(console.warn).toHaveBeenCalledWith(
        'Auth status check failed:',
        expect.any(Error)
      );
    });

    it('should make request to correct endpoint', async () => {
      fetchMock.mockResolvedValue({
        status: 200,
        redirected: false,
        headers: new Headers({ 'content-type': 'application/json' }),
      });

      await authService.checkAuthStatus();

      expect(fetchMock).toHaveBeenCalledWith('/api/v1/history/active-sessions', {
        method: 'GET',
        credentials: 'include',
        headers: { Accept: 'application/json' },
      });
    });
  });

  describe('getCurrentUser', () => {
    it('should get user from OAuth2 userinfo endpoint', async () => {
      fetchMock.mockResolvedValue({
        ok: true,
        json: async () => ({
          email: 'user@example.com',
          user: 'testuser',
          groups: ['admin', 'developer'],
        }),
      });

      const user = await authService.getCurrentUser();

      expect(user).toEqual({
        email: 'user@example.com',
        name: 'testuser',
        groups: [],
      });

      expect(fetchMock).toHaveBeenCalledWith('/oauth2/userinfo', {
        method: 'GET',
        credentials: 'include',
        headers: { Accept: 'application/json' },
      });
    });

    it('should fallback to headers when userinfo fails', async () => {
      fetchMock
        .mockResolvedValueOnce({
          ok: false,
        })
        .mockResolvedValueOnce({
          ok: true,
          headers: new Headers({
            'X-Forwarded-Email': 'user@example.com',
            'X-Forwarded-User': 'testuser',
            'X-Forwarded-Groups': 'group1,group2',
          }),
        });

      const user = await authService.getCurrentUser();

      expect(user).toEqual({
        email: 'user@example.com',
        name: 'testuser',
        groups: ['group1', 'group2'],
      });
    });

    it('should handle various email header names', async () => {
      fetchMock
        .mockResolvedValueOnce({ ok: false })
        .mockResolvedValueOnce({
          ok: true,
          headers: new Headers({
            'X-User-Email': 'user@example.com',
          }),
        });

      const user = await authService.getCurrentUser();

      expect(user?.email).toBe('user@example.com');
    });

    it('should handle username without email', async () => {
      fetchMock
        .mockResolvedValueOnce({ ok: false })
        .mockResolvedValueOnce({
          ok: true,
          headers: new Headers({
            'X-Forwarded-User': 'testuser',
          }),
        });

      const user = await authService.getCurrentUser();

      expect(user).toEqual({
        email: 'unknown@user.com',
        name: 'testuser',
        groups: [],
      });
    });

    it('should return default user when no info available', async () => {
      fetchMock
        .mockResolvedValueOnce({ ok: false })
        .mockResolvedValueOnce({
          ok: true,
          headers: new Headers({}),
        });

      const user = await authService.getCurrentUser();

      expect(user).toEqual({
        email: 'unknown@user.com',
        name: 'Authenticated User',
        groups: [],
      });
    });

    it('should return null on error', async () => {
      fetchMock.mockRejectedValue(new Error('Network error'));

      const user = await authService.getCurrentUser();

      expect(user).toBeNull();
      expect(console.warn).toHaveBeenCalledWith(
        'Failed to get current user:',
        expect.any(Error)
      );
    });

    it('should handle invalid email format', async () => {
      fetchMock
        .mockResolvedValueOnce({ ok: false })
        .mockResolvedValueOnce({
          ok: true,
          headers: new Headers({
            'X-Forwarded-Email': 'not-an-email',
            'X-Forwarded-User': 'testuser',
          }),
        });

      const user = await authService.getCurrentUser();

      // Should use username when email is invalid
      expect(user).toEqual({
        email: 'unknown@user.com',
        name: 'testuser',
        groups: [],
      });
    });

    it('should parse groups correctly', async () => {
      fetchMock
        .mockResolvedValueOnce({ ok: false })
        .mockResolvedValueOnce({
          ok: true,
          headers: new Headers({
            'X-Forwarded-Email': 'user@example.com',
            'X-Forwarded-Groups': 'group1, group2 , group3',
          }),
        });

      const user = await authService.getCurrentUser();

      expect(user?.groups).toEqual(['group1', 'group2', 'group3']);
    });

    it('should handle empty groups header', async () => {
      fetchMock
        .mockResolvedValueOnce({ ok: false })
        .mockResolvedValueOnce({
          ok: true,
          headers: new Headers({
            'X-Forwarded-Email': 'user@example.com',
            'X-Forwarded-Groups': '',
          }),
        });

      const user = await authService.getCurrentUser();

      expect(user?.groups).toEqual([]);
    });

    it('should use preferred_username from userinfo', async () => {
      fetchMock.mockResolvedValue({
        ok: true,
        json: async () => ({
          email: 'user@example.com',
          preferred_username: 'preferred_user',
        }),
      });

      const user = await authService.getCurrentUser();

      expect(user?.name).toBe('preferred_user');
    });

    it('should fallback to email prefix for name', async () => {
      fetchMock.mockResolvedValue({
        ok: true,
        json: async () => ({
          email: 'testuser@example.com',
        }),
      });

      const user = await authService.getCurrentUser();

      expect(user?.name).toBe('testuser');
    });
  });

  describe('redirectToLogin', () => {
    it('should redirect to OAuth2 sign in with return URL', () => {
      window.location.pathname = '/session/123';
      window.location.search = '?filter=test';

      authService.redirectToLogin();

      expect(window.location.href).toContain('/oauth2/sign_in?rd=');
      expect(window.location.href).toContain(encodeURIComponent('/session/123?filter=test'));
    });

    it('should handle root path', () => {
      window.location.pathname = '/';
      window.location.search = '';

      authService.redirectToLogin();

      expect(window.location.href).toContain('/oauth2/sign_in?rd=');
      expect(window.location.href).toContain(encodeURIComponent('/'));
    });

    it('should preserve query parameters', () => {
      window.location.pathname = '/dashboard';
      window.location.search = '?tab=alerts&status=active';

      authService.redirectToLogin();

      expect(window.location.href).toContain(
        encodeURIComponent('?tab=alerts&status=active')
      );
    });
  });

  describe('logout', () => {
    it('should redirect to OAuth2 sign out', () => {
      authService.logout();

      expect(window.location.href).toContain('/oauth2/sign_out?rd=');
    });

    it('should encode redirect URL', () => {
      // Mock window.location with a different origin
      delete (window as any).location;
      window.location = {
        href: '',
        pathname: '/dashboard',
        search: '',
        origin: 'http://example.com:3000',
      } as any;

      authService.logout();

      expect(window.location.href).toContain(
        encodeURIComponent('http://example.com:3000/')
      );
    });
  });

  describe('handleAuthError', () => {
    it('should redirect to login for auth errors', () => {
      window.location.pathname = '/dashboard';

      authService.handleAuthError();

      expect(window.location.href).toContain('/oauth2/sign_in');
    });

    it('should not redirect if already on OAuth2 sign in page', () => {
      window.location.pathname = '/oauth2/sign_in';
      const originalHref = window.location.href;

      authService.handleAuthError();

      expect(window.location.href).toBe(originalHref);
      expect(console.warn).toHaveBeenCalledWith(
        'Already on OAuth login/callback page, avoiding redirect loop'
      );
    });

    it('should not redirect if on OAuth2 callback page', () => {
      window.location.pathname = '/oauth2/callback';
      const originalHref = window.location.href;

      authService.handleAuthError();

      expect(window.location.href).toBe(originalHref);
      expect(console.warn).toHaveBeenCalledWith(
        'Already on OAuth login/callback page, avoiding redirect loop'
      );
    });

    it('should handle nested OAuth2 paths', () => {
      window.location.pathname = '/oauth2/sign_in/redirect';

      authService.handleAuthError();

      // Should not redirect (already on OAuth path)
      expect(console.warn).toHaveBeenCalled();
    });
  });

  describe('singleton pattern', () => {
    it('should return same instance', () => {
      const instance1 = authService;
      const instance2 = authService;

      expect(instance1).toBe(instance2);
    });
  });
});

