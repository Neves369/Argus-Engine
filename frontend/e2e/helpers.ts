import { expect, type Page } from '@playwright/test';

export const E2E_PASSWORD = 'e2e-super-secret-pass';
export const E2E_NEW_PASSWORD = 'e2e-new-secret-pass-123';

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