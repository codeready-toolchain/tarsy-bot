/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string
  readonly VITE_WS_BASE_URL?: string
  readonly VITE_DEV_SERVER_HOST?: string
  readonly VITE_DEV_SERVER_PORT?: string
  readonly VITE_OAUTH_PROXY_URL?: string
  readonly VITE_NODE_ENV?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
