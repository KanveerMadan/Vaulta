import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist', 'dist-e2e', 'dev-dist', 'test-results', 'playwright-report', 'public/ocr']),
  {
    files: ['**/*.{js,jsx}'],
    extends: [
      js.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
  },
  {
    // Node-side code: build scripts, configs, Playwright tests, Vitest suites
    files: ['scripts/**', 'e2e/**', '*.config.js', '**/*.test.js', 'src/import/testUtils.js'],
    languageOptions: { globals: { ...globals.node, ...globals.browser } },
  },
])
