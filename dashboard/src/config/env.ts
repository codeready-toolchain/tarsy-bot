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
  const devServerPort = parseInt(import.meta.env.VITE_DEV_SERVER_PORT || '3000', 10);
  const devServerUrl = `http://${devServerHost}:${devServerPort}`;
  
  // Production URLs (only used when building for production)
  // In development, these are ignored in favor of Vite proxy
  const prodApiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:4180';
  const prodWsBaseUrl = import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:4180';
  
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
    submitAlert: '/alerts',
  },
  
  // WebSocket endpoints
  websocket: {
    // Simple rule: use dev server WebSocket in dev, production URL in prod
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
      wsBase: urls.websocket.base,
    }),
    
    // Production settings
    ...(!config.isDevelopment && {
      apiBase: urls.api.base,
      wsBase: urls.websocket.base,
    }),
  });
};

// Always validate configuration on module load
validateConfig();
