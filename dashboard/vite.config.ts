/// <reference types="vitest" />
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Load environment variables based on mode
  const env = loadEnv(mode, process.cwd(), '');
  
  // Backend server configuration from environment
  const backendApiUrl = env.VITE_API_BASE_URL || 'http://localhost:4180';
  const backendWsUrl = env.VITE_WS_BASE_URL || 'ws://localhost:4180';
  const devServerHost = env.VITE_DEV_SERVER_HOST || 'localhost';
  const devServerPort = parseInt(env.VITE_DEV_SERVER_PORT || '5173', 10);
  const devServerOrigin = `http://${devServerHost}:${devServerPort}`;
  
  // Remove protocol for targets
  const backendHttpTarget = backendApiUrl;
  const backendWsTarget = backendWsUrl;
  
  console.log('🔧 Vite Configuration:', {
    mode,
    backendHttpTarget,
    backendWsTarget,
    devServerOrigin,
  });

  return {
    plugins: [react()],
    server: {
      host: devServerHost,
      port: devServerPort,
      // Proxy to OAuth2 proxy with CORS headers
      proxy: {
        // Proxy API requests to the backend server
        '/api': {
          target: backendHttpTarget,
          changeOrigin: true,
          secure: false,
          configure: (proxy, _options) => {
            proxy.on('proxyRes', (_proxyRes, _req, res) => {
              // Add CORS headers to allow credentials
              res.setHeader('Access-Control-Allow-Origin', devServerOrigin);
              res.setHeader('Access-Control-Allow-Credentials', 'true');
              res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
              res.setHeader('Access-Control-Allow-Headers', 'Origin, X-Requested-With, Content-Type, Accept, Authorization');
            });
            proxy.on('proxyReq', (proxyReq, req, _res) => {
              // Ensure credentials are forwarded
              if (req.headers.cookie) {
                proxyReq.setHeader('Cookie', req.headers.cookie);
              }
            });
          }
        },
        // Proxy alerts endpoint to the backend server
        '/alerts': {
          target: backendHttpTarget,
          changeOrigin: true,
          secure: false,
        },
        // Proxy alert-types endpoint to the backend server
        '/alert-types': {
          target: backendHttpTarget,
          changeOrigin: true,
          secure: false,
        },
        // Proxy session-id endpoint to the backend server (for WebSocket subscription setup)
        '/session-id': {
          target: backendHttpTarget,
          changeOrigin: true,
          secure: false,
          ws: true, // Enable WebSocket proxying for session-based subscriptions
        },
        // Proxy OAuth2 requests to the backend server
        '/oauth2': {
          target: backendHttpTarget,
          changeOrigin: true,
          secure: false,
          configure: (proxy, _options) => {
            proxy.on('proxyRes', (_proxyRes, _req, res) => {
              // Add CORS headers for OAuth2 endpoints
              res.setHeader('Access-Control-Allow-Origin', devServerOrigin);
              res.setHeader('Access-Control-Allow-Credentials', 'true');
            });
            proxy.on('proxyReq', (proxyReq, req, _res) => {
              // Ensure OAuth cookies are forwarded
              if (req.headers.cookie) {
                proxyReq.setHeader('Cookie', req.headers.cookie);
              }
            });
          },
        },
        // Proxy WebSocket requests to the backend server
        '/ws': {
          target: backendWsTarget,
          changeOrigin: true,
          secure: false,
          ws: true, // Enable WebSocket proxying
        },
      },
    },
    test: {
      globals: true,
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
    },
  };
});
