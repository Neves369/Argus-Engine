"use client";

import { useState, useEffect } from 'react';
import './Settings.css';
import { listProviders, setProviderApiKey, setProviderEnabled } from '../api/client';
import type { ProviderConfig } from '../api/client';

interface SettingsProps {
  onClose: () => void;
}

function formatTokens(value: number) {
  return value.toLocaleString('pt-BR');
}

function Settings({ onClose }: SettingsProps) {
  const [providers, setProviders] = useState<ProviderConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [visibleKeys, setVisibleKeys] = useState<Set<string>>(new Set());
  const [cleared, setCleared] = useState(false);
  const [keyInputs, setKeyInputs] = useState<Record<string, string>>({});
  const [flash, setFlash] = useState<{type: 'success' | 'error', msg: string} | null>(null);
  const [hasEncryption, setHasEncryption] = useState(true);

  useEffect(() => {
    async function loadProviders() {
      try {
        const data = await listProviders();
        setProviders(data.providers || []);
        setHasEncryption(data.has_encryption_configured);
        setLoading(false);
      } catch (err) {
        setFlash({ type: 'error', msg: `Falha ao carregar provedores: ${err instanceof Error ? err.message : String(err)}` });
        setLoading(false);
      }
    }
    loadProviders();
  }, []);

  if (loading) {
    return (
      <div className="settings">
        <span>Carregando configurações...</span>
      </div>
    );
  }

  const totalTokens = providers.reduce((sum, p) => sum + p.usage_tokens, 0);
  const totalCost = providers.reduce((sum, p) => sum + p.usage_cost, 0);

  function toggleKeyVisibility(provider: string) {
    setVisibleKeys((prev) => {
      const next = new Set(prev);
      if (next.has(provider)) {
        next.delete(provider);
      } else {
        next.add(provider);
      }
      return next;
    });
  }

  function clearAllCache() {
    setProviders((prev) =>
      prev.map((p) => ({ ...p, usage_tokens: 0, usage_cost: 0 }))
    );
    setCleared(true);
    window.setTimeout(() => setCleared(false), 2000);
  }

  function restoreDefaults() {
    setProviders([]);
  }

  async function handleSetProviderApiKey(provider: string) {
    const key = keyInputs[provider];
    if (!key) {
      setFlash({ type: 'error', msg: 'Por favor, digite uma chave de API.' });
      return;
    }
    try {
      const result = await setProviderApiKey(provider, key);
      setFlash({ type: 'success', msg: result.status || 'Chave salva com sucesso!' });
      setKeyInputs({});
      setProviders((prev) =>
        prev.map((p) =>
          p.provider === provider
            ? { ...p, has_api_key: true, key_source: 'db' }
            : p
        )
      );
    } catch (err) {
      setFlash({ type: 'error', msg: `Falha ao salvar chave: ${err instanceof Error ? err.message : String(err)}` });
    }
  }

  async function handleSetProviderEnabled(provider: string, enabled: boolean) {
    try {
      const result = await setProviderEnabled(provider, enabled);
      setFlash({ type: result.status === 'ok' ? 'success' : 'error', msg: result.status || 'Atualizado' });
      setProviders((prev) =>
        prev.map((p) => (p.provider === provider ? { ...p, enabled } : p))
      );
    } catch (err) {
      setFlash({ type: 'error', msg: `Falha ao atualizar provedor: ${err instanceof Error ? err.message : String(err)}` });
    }
  }

  return (
    <div className="settings">
      <div className="settings-summary">
        <div className="settings-summary-item">
          <span className="settings-summary-label">Total de tokens</span>
          <span className="settings-summary-value">{formatTokens(totalTokens)}</span>
        </div>
        <div className="settings-summary-item">
          <span className="settings-summary-label">Custo total</span>
          <span className="settings-summary-value">${totalCost.toFixed(2)}</span>
        </div>
      </div>

      {!hasEncryption && (
        <div className="settings-warning">
          As chaves de API serão mantidas apenas em memória e perdidas ao reiniciar o
          servidor. Configure <code>ARGUS_ENCRYPTION_KEY</code> no <code>.env</code> para
          persistir com segurança.
        </div>
      )}

      {flash && (
        <div className={`settings-toast ${flash.type}`}>
          {flash.msg}
        </div>
      )}

      {providers.length === 0 ? (
        <div className="settings-section">
          <span className="settings-section-title">Não há provedores configurados</span>
          <span className="settings-section-description">
            Adicione chaves de API para cada provedor (groq, openrouter, openai).
          </span>
        </div>
      ) : (
        providers.map((provider) => {
          const usagePercent = provider.usage_tokens
            ? Math.min((provider.usage_tokens / (provider.usage_tokens + 1)) * 100, 100)
            : 0;

          return (
            <div key={provider.provider} className="settings-section">
              <div className="settings-section-header">
                <span className="settings-section-title">
                  {provider.provider.toUpperCase()} {provider.enabled ? '' : '(desativado)'}
                </span>
                <span className="settings-section-meta">
                  {formatTokens(provider.usage_tokens)} tokens ·
                  ${provider.usage_cost.toFixed(2)}
                </span>
              </div>

              <div className="settings-section-body">
                <div className="settings-model-row">
                  <span className="settings-model-name">Modelos compatíveis:</span>
                  <span className="settings-model-model">
                    {provider.models.map((m) => `#${m}`).join(' ')}
                  </span>
                </div>

                <div className="settings-price-row">
                  <span className="settings-price-label">Preço</span>
                  <span className="settings-price-value">
                    ${provider.price_in.toFixed(2)} in · ${provider.price_out.toFixed(2)} out / 1K tokens
                  </span>
                </div>

                <label className="settings-toggle">
                  <input
                    type="checkbox"
                    checked={provider.enabled}
                    onChange={(e) => handleSetProviderEnabled(provider.provider, e.target.checked)}
                  />
                  <span className="settings-toggle-slider" />
                </label>

                <div className="modal-field">
                  <label className="modal-label" htmlFor={`api-key-${provider.provider}`}>
                    Chave de API
                  </label>
                  <div className="settings-key-row">
                    <input
                      id={`api-key-${provider.provider}`}
                      className="modal-input"
                      type={visibleKeys.has(provider.provider) ? 'text' : 'password'}
                      placeholder={provider.key_source ? 'Nova chave (para substituir)' : 'Cole sua chave de API aqui'}
                      value={keyInputs[provider.provider] || ''}
                      onChange={(e) => setKeyInputs({ ...keyInputs, [provider.provider]: e.target.value })}
                      autoComplete="off"
                      spellCheck={false}
                    />
                    <button
                      type="button"
                      className="settings-key-toggle"
                      onClick={() => handleSetProviderApiKey(provider.provider)}
                      disabled={!keyInputs[provider.provider]}
                      aria-label="Salvar chave"
                    >
                      Salvar chave
                    </button>
                    <button
                      type="button"
                      className="settings-key-toggle"
                      onClick={() => toggleKeyVisibility(provider.provider)}
                      aria-label="Mostrar/ocultar chave"
                    >
                      {visibleKeys.has(provider.provider) ? 'Ocultar' : 'Mostrar'}
                    </button>
                  </div>
                  {provider.key_source === 'db' && (
                    <span className="settings-key-status">Chave salva no banco (cifrada)</span>
                  )}
                  {provider.key_source === 'env' && (
                    <span className="settings-key-status">Chave configurada no ambiente (não exibida)</span>
                  )}
                  {!provider.key_source && (
                    <span className="settings-key-status">
                      Nenhuma chave configurada — digite acima e clique em &quot;Salvar chave&quot;
                    </span>
                  )}
                </div>

                <div className="settings-usage">
                  <div className="settings-usage-line">
                    <span className="settings-usage-text">
                      {formatTokens(provider.usage_tokens)} tokens
                    </span>
                    <span className="settings-usage-cost">
                      ${provider.usage_cost.toFixed(2)}
                    </span>
                  </div>
                  <div className="settings-usage-bar">
                    <div className="settings-usage-fill" style={{ width: `${usagePercent}%` }} />
                  </div>
                </div>
              </div>
            </div>
          );
        })
      )}

      <div className="settings-actions">
        <button type="button" className="modal-submit" onClick={clearAllCache}>
          Limpar cache de todos
        </button>
        <button type="button" className="modal-submit" onClick={restoreDefaults}>
          Restaurar padrões
        </button>
        <button type="button" className="modal-submit" onClick={onClose}>
          Fechar
        </button>
      </div>

      {cleared && <div className="settings-toast">Cache limpo</div>}
    </div>
  );
}

export default Settings;