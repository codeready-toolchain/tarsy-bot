/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Backend server configuration
// const BACKEND_URL = 'localhost:8000'
const BACKEND_URL = '127.0.0.1:4180'
const BACKEND_HTTP_TARGET = 'http://' + BACKEND_URL
const BACKEND_WS_TARGET = 'ws://' + BACKEND_URL

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Proxy to OAuth2 proxy with CORS headers
    proxy: {
      // Proxy API requests to the backend server
      '/api': {
        target: BACKEND_HTTP_TARGET,
        changeOrigin: true,
        secure: false,
        configure: (proxy, _options) => {
          proxy.on('proxyRes', (_proxyRes, _req, res) => {
            // Add CORS headers to allow credentials
            res.setHeader('Access-Control-Allow-Origin', 'http://localhost:5173');
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
        target: BACKEND_HTTP_TARGET,
        changeOrigin: true,
        secure: false,
      },
      // Proxy alert-types endpoint to the backend server
      '/alert-types': {
        target: BACKEND_HTTP_TARGET,
        changeOrigin: true,
        secure: false,
      },
      // Proxy session-id endpoint to the backend server (for WebSocket subscription setup)
      '/session-id': {
        target: BACKEND_HTTP_TARGET,
        changeOrigin: true,
        secure: false,
        ws: true, // Enable WebSocket proxying for session-based subscriptions
      },
      // Proxy OAuth2 requests to the backend server
      '/oauth2': {
        target: BACKEND_HTTP_TARGET,
        changeOrigin: true,
        secure: false,
      },
      // Proxy WebSocket requests to the backend server
      '/ws': {
        target: BACKEND_WS_TARGET,
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
})
