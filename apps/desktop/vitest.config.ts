import { resolve } from 'node:path'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  resolve: {
    alias: { '@contracts': resolve(__dirname, '../../packages/contracts/ts/index.ts') }
  },
  test: { include: ['src/**/*.test.ts'] }
})
