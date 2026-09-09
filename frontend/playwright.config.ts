import { defineConfig } from '@playwright/test';

const E2E_DIR = '/tmp/argus-e2e';

// Backend real rodando fora do sandbox do pytest, em modo determinístico:
// sem chaves de LLM (agentes degradam para simulate), fontes apontando para um
// manifest inexistente (nenhuma chamada de rede), scan limitado a 1 página e
// verificação do Carro desligada. Assim o happy path completa offline com
// resultado estável, sem dependência de provedores externos.
const backendEnv: Record<string, string> = {
  DATABASE_URL: `sqlite+aiosqlite:////${E2E_DIR}/argus.db`,
  EVIDENCE_DIR: `${E2E_DIR}/evidence`,
  ALLOWED_SCOPES: '["example.com"]',
  // Fernet key válida fixa (32 bytes) para exercitar a rotação de senha (Etapa 10).
  ARGUS_ENCRYPTION_KEY: 'MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=',
  UI_PASSWORD: 'e2e-super-secret-pass',
  CAVEMAN_PROMPTS: 'false',
  HISTORY_COMPRESSION: 'false',
  HISTORY_LLM_SUMMARY: 'false',
  TOOL_OUTPUT_COMPRESSION: 'false',
  BUDGET_TOKENS_PER_AGENT: '0',
  BUDGET_COST_PER_AGENT: '0.0',
  SOURCES_MANIFEST: 'missing.e2e-sources.json',
  CHARIOT_VERIFY_ENABLED: 'false',
  SCAN_MAX_PAGES: '1',
};

export default defineConfig({
  testDir: './e2e',
  globalSetup: './global-setup.ts',
  // Um único worker: os specs compartilham o mesmo backend (run único, e o
  // kill-switch ativado no último spec é one-way e não pode vazar para outro).
  fullyParallel: false,
  workers: 1,
  timeout: 120_000,
  expect: { timeout: 15_000 },
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: 'http://127.0.0.1:5173',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  webServer: [
    {
      cwd: '../backend',
      command: './e2e-backend.sh',
      url: 'http://127.0.0.1:8000/health',
      timeout: 60_000,
      env: backendEnv,
      reuseExistingServer: false,
    },
    {
      command: 'npx vite --host 127.0.0.1 --port 5173',
      url: 'http://127.0.0.1:5173',
      timeout: 60_000,
      reuseExistingServer: false,
    },
  ],
});