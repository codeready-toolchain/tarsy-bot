/// <reference types="vitest" />
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Load environment variables based on mode
  const env = loadEnv(mode, process.cwd(), '');
  
  // Development server configuration
  const devServerHost = env.VITE_DEV_SERVER_HOST || 'localhost';
  const devServerPort = parseInt(env.VITE_DEV_SERVER_PORT || '3000', 10);
  const devServerOrigin = `http://${devServerHost}:${devServerPort}`;
  
  // Proxy target configuration - fully configurable
  // These are the INTERNAL targets that Vite proxy forwards TO
  // For containers: use service names (oauth2-proxy:4180)  
  // For local dev: use localhost (localhost:4180)
  const backendHttpTarget = env.VITE_PROXY_TARGET_HTTP || 'http://localhost:4180';
  const backendWsTarget = env.VITE_PROXY_TARGET_WS || 'ws://localhost:4180';
  const proxyHostHeader = env.VITE_PROXY_HOST_HEADER || 'localhost:4180';
  
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
              // Override host header to match OAuth2-proxy cookie domain
              proxyReq.setHeader('Host', proxyHostHeader);
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
              // Override host header to match OAuth2-proxy cookie domain
              proxyReq.setHeader('Host', proxyHostHeader);
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
