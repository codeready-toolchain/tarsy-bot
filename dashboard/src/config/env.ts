/**
 * Environment Configuration
 * Centralized configuration for all environment variables and URLs
 */

interface AppConfig {
  // API Configuration
  apiBaseUrl: string;
  wsBaseUrl: string;
  oauthProxyUrl: string;
  
  // Development Server Configuration
  devServerHost: string;
  devServerPort: number;
  devServerUrl: string;
  
  // Environment Info
  isDevelopment: boolean;
  isProduction: boolean;
  nodeEnv: string;
}

/**
 * Parse environment variables with fallbacks
 */
const parseEnvConfig = (): AppConfig => {
  // Get environment variables with fallbacks
  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:4180';
  const wsBaseUrl = import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:4180';
  const oauthProxyUrl = import.meta.env.VITE_OAUTH_PROXY_URL || apiBaseUrl;
  const devServerHost = import.meta.env.VITE_DEV_SERVER_HOST || 'localhost';
  const devServerPort = parseInt(import.meta.env.VITE_DEV_SERVER_PORT || '5173', 10);
  const nodeEnv = import.meta.env.VITE_NODE_ENV || import.meta.env.MODE || 'development';
  
  // Computed values
  const devServerUrl = `http://${devServerHost}:${devServerPort}`;
  const isDevelopment = import.meta.env.DEV;
  const isProduction = import.meta.env.PROD;
  
  return {
    apiBaseUrl,
    wsBaseUrl,
    oauthProxyUrl,
    devServerHost,
    devServerPort,
    devServerUrl,
    isDevelopment,
    isProduction,
    nodeEnv,
  };
};

/**
 * Application configuration instance
 * Use this throughout the app instead of directly accessing import.meta.env
 */
export const config = parseEnvConfig();

/**
 * URL builders for common endpoints
 */
export const urls = {
  // API endpoints
  api: {
    base: config.isDevelopment ? '' : config.apiBaseUrl,
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
    base: config.isDevelopment ? `ws://${config.devServerHost}:${config.devServerPort}` : config.wsBaseUrl,
    connect: '/ws',
  },
  
  // OAuth2 endpoints
  oauth: {
    base: config.isDevelopment ? '' : config.oauthProxyUrl,
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
 * Validation function to ensure all required config is present
 */
export const validateConfig = (): void => {
  const requiredEnvVars = [
    { name: 'VITE_API_BASE_URL', configKey: 'apiBaseUrl' },
    { name: 'VITE_WS_BASE_URL', configKey: 'wsBaseUrl' }
  ] as const;
  
  const missing = requiredEnvVars.filter(({ name }) => !import.meta.env[name]);
  
  if (missing.length > 0 && !config.isDevelopment) {
    throw new Error(`Missing required environment variables: ${missing.map(({ name }) => name).join(', ')}`);
  }
  
  console.log('✅ Configuration validated successfully', {
    environment: config.nodeEnv,
    apiBaseUrl: config.apiBaseUrl,
    wsBaseUrl: config.wsBaseUrl,
    isDevelopment: config.isDevelopment,
  });
};

// Validate configuration on module load in development
if (config.isDevelopment) {
  validateConfig();
}
