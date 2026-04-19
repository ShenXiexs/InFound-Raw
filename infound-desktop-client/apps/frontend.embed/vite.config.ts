import { fileURLToPath, URL } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const useDevProxy = env.VITE_USE_DEV_PROXY === 'true'
  const openapiTarget = env.VITE_OPENAPI_BASE_URL

  return {
    plugins: [vue()],
    resolve: {
      alias: {
        '@infound/desktop-base': fileURLToPath(new URL('../../packages/frontend.desktop.base/src/index.ts', import.meta.url))
      }
    },
    server: {
      proxy:
        useDevProxy && openapiTarget
          ? {
              '/outreach': {
                target: openapiTarget,
                changeOrigin: true,
                secure: false
              },
              '/contract': {
                target: openapiTarget,
                changeOrigin: true,
                secure: false
              },
              '/api': {
                target: openapiTarget,
                changeOrigin: true,
                secure: false
              },
              '/user': {
                target: openapiTarget,
                changeOrigin: true,
                secure: false
              },
              '/account': {
                target: openapiTarget,
                changeOrigin: true,
                secure: false
              }
            }
          : undefined
    }
  }
})
