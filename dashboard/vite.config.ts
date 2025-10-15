/// <reference types="vitest" />
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Load environment variables based on mode
  const env = loadEnv(mode, process.cwd(), '');
  
  // Development server configuration
  const devServerHost = env.VITE_DEV_SERVER_HOST || 'localhost';
  const devServerPort = parseInt(env.VITE_DEV_SERVER_PORT || '5173', 10);
  
  // Determine if running in container mode (when environment variables are set)
  const isContainerMode = env.VITE_PROXY_TARGET_HTTP || env.NODE_ENV === 'container';
  
  // Proxy targets:
  // - Container mode: proxy to oauth2-proxy service  
  // - Dev mode: proxy to direct backend
  const backendHttpTarget = isContainerMode 
    ? (env.VITE_PROXY_TARGET_HTTP || 'http://oauth2-proxy:4180')
    : 'http://localhost:8000';
  const backendWsTarget = isContainerMode
    ? (env.VITE_PROXY_TARGET_WS || 'ws://oauth2-proxy:4180') 
    : 'ws://localhost:8000';
  const proxyHostHeader = isContainerMode 
    ? (env.VITE_PROXY_HOST_HEADER || 'localhost:4180')
    : 'localhost:8000';
  
  console.log('🔧 Vite Configuration:', {
    mode,
    isContainerMode,
    backendHttpTarget,
    backendWsTarget,
    devServerHost,
    devServerPort,
  });

  return {
    plugins: [react()],
    server: {
      host: devServerHost,
      port: devServerPort,
      // Proxy configuration: build dynamically to avoid TypeScript issues
      proxy: (() => {
        const baseProxy = {
          '/api': {
            target: backendHttpTarget,
            changeOrigin: true,
            secure: false,
            ...(isContainerMode && {
              configure: (proxy: any, _options: any) => {
                proxy.on('proxyReq', (proxyReq: any, req: any, _res: any) => {
                  if (req.headers.cookie) {
                    proxyReq.setHeader('Cookie', req.headers.cookie);
                  }
                  proxyReq.setHeader('Host', proxyHostHeader);
                });
              }
            })
          },
          '/health': {
            target: backendHttpTarget,
            changeOrigin: true,
            secure: false,
            ...(isContainerMode && {
              configure: (proxy: any, _options: any) => {
                proxy.on('proxyReq', (proxyReq: any, req: any, _res: any) => {
                  if (req.headers.cookie) {
                    proxyReq.setHeader('Cookie', req.headers.cookie);
                  }
                  proxyReq.setHeader('Host', proxyHostHeader);
                });
              }
            })
          },
          '/ws': {
            target: backendWsTarget,
            changeOrigin: true,
            secure: false,
            ws: true,
            ...(isContainerMode && {
              configure: (proxy: any, _options: any) => {
                proxy.on('proxyReqWs', (proxyReq: any, req: any, _socket: any, _options: any, _head: any) => {
                  if (req.headers.cookie) {
                    proxyReq.setHeader('cookie', req.headers.cookie);
                  }
                  if (req.headers.host) {
                    proxyReq.setHeader('host', req.headers.host);
                  }
                });
              }
            })
          },
        };

        if (isContainerMode) {
          return {
            ...baseProxy,
            '/oauth2': {
              target: backendHttpTarget,
              changeOrigin: true,
              secure: false,
              configure: (proxy: any, _options: any) => {
                proxy.on('proxyReq', (proxyReq: any, req: any, _res: any) => {
                  if (req.headers.cookie) {
                    proxyReq.setHeader('Cookie', req.headers.cookie);
                  }
                  proxyReq.setHeader('Host', proxyHostHeader);
                });
              },
            },
          };
        }

        return baseProxy;
      })(),
    },
    test: {
      globals: true,
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
    },
  };
});
