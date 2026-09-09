import { expect, test } from '@playwright/test';
import { login, metricValue, openMenu, readMetrics, setTarget, startRun } from './helpers';

test.describe('Run ponta a ponta', () => {
  test('alvo → run ao vivo (SSE) → relatório → dashboard', async ({ page, request }) => {
    await login(page);
    await setTarget(page);

    await startRun(page);

    // SSE ao vivo: o painel abre em "Em execução" e o log/chat vão populando.
    await expect(page.locator('.run-panel-status')).toContainText('Em execução');

    // Run conclui offline de forma determinística.
    await expect(page.locator('.run-panel-status')).toContainText('Concluído', {
      timeout: 90_000,
    });
    await expect(page.locator('.run-panel-title')).toContainText('Run #');

    // Métricas de negócio: o run concluído (compartilhamos o mesmo backend
    // determinístico entre os specs, então é exatamente 1 run completed) é
    // refletido no /metrics — contador, gauge de ativo e timestamp resetado.
    const metrics = await readMetrics(request);
    expect(metricValue(metrics, 'argus_runs_total', { status: 'completed' })).toBe(1);
    expect(metricValue(metrics, 'argus_runs_active')).toBe(0);
    expect(metricValue(metrics, 'argus_run_started_at_seconds')).toBe(0);

    // Relatório: alvo + seções de resultado renderizadas.
    await expect(
      page.locator('.run-panel-meta-item', { hasText: 'Alvo: example.com' }),
    ).toBeVisible();
    await expect(page.locator('.run-panel-section-title', { hasText: 'Trace' })).toBeVisible();
    await expect(page.locator('.run-panel-section-title', { hasText: 'Achados' })).toBeVisible();
    await expect(page.locator('summary', { hasText: 'Observabilidade' })).toBeVisible();

    // Painel de observabilidade: tokens consumidos no run.
    await page.locator('.run-panel-observability summary').click();
    await expect(
      page.locator('.run-panel-meta-item', { hasText: 'Tokens:' }),
    ).toBeVisible();

    // A aba de log mostrou os passos transmitidos via SSE.
    await page.locator('.run-panel-tab', { hasText: 'Log' }).click();
    await expect(page.locator('.run-panel-log-line').first()).toBeVisible();

    // Dashboard: o run aparece com status concluído.
    await openMenu(page);
    await page.locator('.modal-menu-item', { hasText: 'Dashboard' }).click();
    await expect(page.locator('.dashboard-card-label', { hasText: 'Runs totais' })).toBeVisible();
    const row = page
      .locator('.dashboard-tr:not(.dashboard-tr--head)')
      .filter({ hasText: 'Concluído' });
    await expect(row.first()).toBeVisible();
  });
});