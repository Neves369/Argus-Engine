import react from '@vitejs/plugin-react'
import type { IncomingMessage, ServerResponse } from 'node:http'
import type { Socket } from 'node:net'
import { defineConfig } from 'vite'

// https://vite.dev/config/
const config = defineConfig({
  plugins: [react()],
  esbuild: {
    jsx: 'automatic',
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        configure: (proxy) => {
          // O Vite registra seu listener de erro do proxy só depois do
          // `configure`, então o removemos no próximo macrotask e instalamos
          // um handle próprio: ECONNREFUSED é transitório (backend ainda
          // subindo ou em reload com --reload) e o polling do front se
          // recupera sozinho — não merece erro no console do Vite.
          setTimeout(() => {
            proxy.removeAllListeners('error')
            proxy.on('error', (err: Error, _req: IncomingMessage, res: ServerResponse | Socket) => {
              const code = (err as Error & { code?: string }).code
              const silent = code === 'ECONNREFUSED'
              if ('req' in res) {
                ;(res as ServerResponse).writeHead(502, { 'Content-Type': 'text/plain' }).end()
                if (!silent) console.error('[vite proxy]', err.message)
              } else {
                ;(res as Socket).destroy()
              }
            })
          }, 0)
        },
      },
    },
  },
})

export default {
  ...config,
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
  },
}
