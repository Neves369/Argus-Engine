import { expect, test } from '@playwright/test';
import { login } from './helpers';

test.describe('Autenticação', () => {
  test('senha errada mostra erro e não entra', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('#password')).toBeVisible();
    await page.locator('#password').fill('senha-errada');
    await page.locator('button.login-submit').click();
    await expect(page.locator('.login-error')).toContainText('Senha inválida');
    await expect(page.locator('.end-turn-button')).toHaveCount(0);
  });

  test('login com senha correta entra e logout volta para a tela de login', async ({ page }) => {
    await login(page);
    await expect(page.locator('.end-turn-button')).toBeVisible();

    await page.locator('.character-panel--ally .character-photo').click();
    await expect(page.locator('.modal-menu')).toBeVisible();
    await page.locator('.modal-menu-item', { hasText: 'Sair' }).click();
    await expect(page.locator('.login-card')).toBeVisible();
  });
});