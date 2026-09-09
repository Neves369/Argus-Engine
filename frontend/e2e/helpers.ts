import { expect, type APIRequestContext, type Page } from '@playwright/test';

export const E2E_PASSWORD = 'e2e-super-secret-pass';
export const E2E_NEW_PASSWORD = 'e2e-new-secret-pass-123';
export const METRICS_URL = 'http://127.0.0.1:8000/metrics';

// O backend do E2E expõe /metrics na porta real (:8000, fora do proxy do
// frontend) — as métricas de negócio são públicas para o próprio Prometheus.
export async function readMetrics(request: APIRequestContext): Promise<string> {
  const res = await request.get(METRICS_URL);
  expect(res.ok()).toBeTruthy();
  return await res.text();
}

// Extrai o valor de uma sample Prometheus em texto plano, ex.:
// argus_runs_total{status="completed"} 1.0
export function metricValue(
  body: string,
  name: string,
  labels?: Record<string, string>,
): number | null {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const suffix = labels
    ? '{' + Object.entries(labels).map(([k, v]) => `${k}="${v}"`).join(',') + '}'
    : '';
  const match = body.match(new RegExp(`^${escaped}${suffix}\\s+([0-9.]+)`, 'm'));
  return match ? Number(match[1]) : null;
}

export async function login(page: Page, password: string = E2E_PASSWORD) {
  await page.goto('/');
  await expect(page.locator('#password')).toBeVisible();
  await page.locator('#password').fill(password);
  await page.locator('button.login-submit').click();
  await expect(page.locator('.end-turn-button')).toBeVisible();
}

export async function openMenu(page: Page) {
  await page.locator('.character-panel--ally .character-photo').click();
  await expect(page.locator('.modal-menu')).toBeVisible();
}

export async function openSettings(page: Page) {
  await openMenu(page);
  await page.locator('.modal-menu-item', { hasText: 'Configurações' }).click();
  await expect(page.locator('.settings')).toBeVisible();
}

export async function setTarget(page: Page, name = 'example.com') {
  await page.locator('.character-panel--enemy .character-photo').click();
  await expect(page.locator('#enemy-name')).toBeVisible();
  await page.locator('#enemy-name').fill(name);
  await page.locator('.modal-submit', { hasText: 'Salvar' }).click();
}

export async function startRun(page: Page) {
  await page.locator('.end-turn-button').click();
  await expect(page.locator('.run-panel')).toBeVisible();
}