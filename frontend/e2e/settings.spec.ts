import { expect, test } from '@playwright/test';
import {
  E2E_NEW_PASSWORD,
  login,
  openSettings,
  setTarget,
  startRun,
} from './helpers';

test.describe('Segurança (Configurações)', () => {
  test('kill-switch ativado em runtime bloqueia novos runs', async ({ page }) => {
    await login(page);
    await openSettings(page);

    const security = page.locator('.settings-section', { hasText: 'Segurança' });
    await expect(security).toBeVisible();
    await expect(security.locator('.settings-model-model')).toContainText('Inativo');

    await page.locator('#kill-switch-reason').fill('incidente no alvo exemplo.com');
    await page.locator('.settings-key-toggle', { hasText: 'Ativar kill-switch' }).click();
    await page.locator('.settings-key-toggle', { hasText: 'Confirmar ativação' }).click();

    await expect(security.locator('.settings-model-model')).toContainText('ATIVO (runtime)');
    await expect(page.locator('.settings-toast')).toContainText('Kill-switch ativado');

    // Fecha as configurações e tenta rodar: o backend responde 423.
    await page.locator('.modal-submit', { hasText: 'Fechar' }).click();
    await setTarget(page, 'example.com');
    await startRun(page);
    await expect(page.locator('.run-result')).toContainText('Kill switch', { timeout: 30_000 });
  });

  test('rotação de senha invalida a sessão atual e exige re-login com a nova senha', async ({
    page,
  }) => {
    await login(page);
    await openSettings(page);

    await page.locator('#pwd-current').fill('e2e-super-secret-pass');
    await page.locator('#pwd-new').fill(E2E_NEW_PASSWORD);
    await page.locator('#pwd-confirm').fill(E2E_NEW_PASSWORD);
    await page.locator('.modal-submit', { hasText: 'Trocar senha' }).click();

    // Sessão invalidada → volta para a tela de login.
    await expect(page.locator('.login-card')).toBeVisible();

    // A senha antiga não entra mais.
    await page.locator('#password').fill('e2e-super-secret-pass');
    await page.locator('button.login-submit').click();
    await expect(page.locator('.login-error')).toContainText('Senha inválida');

    // A nova senha entra.
    await login(page, E2E_NEW_PASSWORD);
  });
});