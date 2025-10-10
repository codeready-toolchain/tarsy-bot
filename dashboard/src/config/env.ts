/**
 * Clean Environment Configuration
 * Simple, predictable URL handling for development vs production
 */

interface AppConfig {
  // Environment Info
  isDevelopment: boolean;
  isProduction: boolean;
  nodeEnv: string;
  
  // Development Server Configuration (for dev mode only)
  devServerHost: string;
  devServerPort: number;
  devServerUrl: string;
  
  // Production URLs (only used in production)
  prodApiBaseUrl: string;
  prodWsBaseUrl: string;
}

/**
 * Parse environment variables with simple, clear logic
 */
const parseEnvConfig = (): AppConfig => {
  const isDevelopment = import.meta.env.DEV;
  const isProduction = import.meta.env.PROD;
  const nodeEnv = import.meta.env.MODE || 'development';
  
  // Development server settings (used in development only)
  const devServerHost = import.meta.env.VITE_DEV_SERVER_HOST || 'localhost';
  const devServerPort = parseInt(import.meta.env.VITE_DEV_SERVER_PORT || '5173', 10);
  const devServerUrl = `http://${devServerHost}:${devServerPort}`;
  
  // Production URLs (only used when building for production)
  // In development, these are ignored in favor of Vite proxy
  // Use ?? instead of || to allow empty string (for relative URLs)
  const prodApiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:4180';
  
  // Derive WebSocket URL from API URL if not explicitly set
  let prodWsBaseUrl = import.meta.env.VITE_WS_BASE_URL;
  if (!prodWsBaseUrl) {
    try {
      const apiUrl = new URL(prodApiBaseUrl);
      // Don't derive from localhost fallback - use hardcoded default instead
      if (apiUrl.hostname === 'localhost') {
        prodWsBaseUrl = 'ws://localhost:4180';
      } else {
        const wsScheme = apiUrl.protocol === 'https:' ? 'wss:' : 'ws:';
        prodWsBaseUrl = `${wsScheme}//${apiUrl.host}${apiUrl.pathname}`;
      }
    } catch {
      // If URL parsing fails, fall back to localhost default
      prodWsBaseUrl = 'ws://localhost:4180';
    }
  }
  
  return {
    isDevelopment,
    isProduction,
    nodeEnv,
    devServerHost,
    devServerPort, 
    devServerUrl,
    prodApiBaseUrl,
    prodWsBaseUrl,
  };
};

/**
 * Application configuration instance
 */
export const config = parseEnvConfig();

/**
 * Clean URL configuration - ONE source of truth
 * Development: Use relative URLs + Vite proxy
 * Production: Use absolute URLs from environment
 */
export const urls = {
  // API endpoints
  api: {
    // Simple rule: relative URLs in dev (proxy handles it), absolute in prod
    base: config.isDevelopment ? '' : config.prodApiBaseUrl,
    health: '/api/v1/history/health',
    activeAlerts: '/api/v1/history/active-alerts', 
    historicalAlerts: '/api/v1/history/historical-alerts',
    activeSessions: '/api/v1/history/active-sessions',
    sessionDetail: (sessionId: string) => `/api/v1/history/sessions/${sessionId}`,
    sessionSummary: (sessionId: string) => `/api/v1/history/sessions/${sessionId}/summary`,
    submitAlert: '/api/v1/alerts',
  },
  
  // SSE (Server-Sent Events) endpoints
  // IMPORTANT: SSE connections bypass Vite proxy in development to avoid connection pool exhaustion
  // Vite's proxy has limited connections and long-lived SSE streams exhaust it
  sse: {
    // In development: connect directly to backend (localhost:8000)
    // In production: use same base as API
    base: config.isDevelopment ? 'http://localhost:8000' : config.prodApiBaseUrl,
    stream: '/api/v1/events/stream',
  },
  
  // WebSocket endpoints
  websocket: {
    // Simple rule: use Vite proxy in dev (same port as frontend), production URL in prod
    base: config.isDevelopment ? `ws://${config.devServerHost}:${config.devServerPort}` : config.prodWsBaseUrl,
    connect: '/ws',
  },
  
  // OAuth2 endpoints
  oauth: {
    // Simple rule: relative URLs in dev (proxy handles it), absolute in prod
    base: config.isDevelopment ? '' : config.prodApiBaseUrl,
    signIn: '/oauth2/sign_in',
    signOut: '/oauth2/sign_out', 
    userInfo: '/oauth2/userinfo',
  },
  
  // Development server
  devServer: {
    origin: config.devServerUrl,
  },
} as const;

/**
 * Simple validation and logging
 */
export const validateConfig = (): void => {
  console.log('✅ Clean configuration loaded:', {
    environment: config.nodeEnv,
    isDevelopment: config.isDevelopment,
    
    // Development settings
    ...(config.isDevelopment && {
      devServerHost: config.devServerHost,
      devServerPort: config.devServerPort,
      apiBase: urls.api.base || '(relative - using Vite proxy)',
      sseBase: urls.sse.base + ' (direct to backend, bypasses Vite proxy)',
      wsBase: urls.websocket.base,
    }),
    
    // Production settings
    ...(!config.isDevelopment && {
      apiBase: urls.api.base,
      sseBase: urls.sse.base,
      wsBase: urls.websocket.base,
    }),
  });
};

// Always validate configuration on module load
validateConfig();
