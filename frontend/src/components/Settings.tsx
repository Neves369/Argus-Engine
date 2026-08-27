import { useState } from 'react';
import { DEFAULT_SECTIONS, type ModelConfig, type SettingsSection } from '../data/agents';
import './Settings.css';

interface SettingsProps {
  onClose: () => void;
}

function formatTokens(value: number) {
  return value.toLocaleString('pt-BR');
}

function sectionTotals(models: ModelConfig[]) {
  return models.reduce(
    (acc, model) => ({
      tokens: acc.tokens + model.tokensUsed,
      cost: acc.cost + model.cost,
    }),
    { tokens: 0, cost: 0 },
  );
}

function Settings({ onClose }: SettingsProps) {
  const [sections, setSections] = useState<SettingsSection[]>(DEFAULT_SECTIONS);
  const [openSections, setOpenSections] = useState<Set<string>>(
    () => new Set(DEFAULT_SECTIONS.map((section) => section.id)),
  );
  const [visibleKeys, setVisibleKeys] = useState<Set<string>>(new Set());
  const [cleared, setCleared] = useState(false);

  const allModels = sections.flatMap((section) => section.models);
  const totalTokens = allModels.reduce((sum, model) => sum + model.tokensUsed, 0);
  const totalCost = allModels.reduce((sum, model) => sum + model.cost, 0);

  function updateModel(sectionId: string, modelId: string, patch: Partial<ModelConfig>) {
    setSections((prev) =>
      prev.map((section) =>
        section.id !== sectionId
          ? section
          : {
              ...section,
              models: section.models.map((model) =>
                model.id === modelId ? { ...model, ...patch } : model,
              ),
            },
      ),
    );
  }

  function toggleSection(sectionId: string) {
    setOpenSections((prev) => {
      const next = new Set(prev);
      if (next.has(sectionId)) {
        next.delete(sectionId);
      } else {
        next.add(sectionId);
      }
      return next;
    });
  }

  function toggleKeyVisibility(modelId: string) {
    setVisibleKeys((prev) => {
      const next = new Set(prev);
      if (next.has(modelId)) {
        next.delete(modelId);
      } else {
        next.add(modelId);
      }
      return next;
    });
  }

  function clearModelCache(sectionId: string, modelId: string) {
    updateModel(sectionId, modelId, { tokensUsed: 0, cost: 0 });
  }

  function clearAllCache() {
    setSections((prev) =>
      prev.map((section) => ({
        ...section,
        models: section.models.map((model) => ({ ...model, tokensUsed: 0, cost: 0 })),
      })),
    );
    setCleared(true);
    window.setTimeout(() => setCleared(false), 2000);
  }

  function restoreDefaults() {
    setSections(DEFAULT_SECTIONS);
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

      {sections.map((section) => {
        const isOpen = openSections.has(section.id);
        const totals = sectionTotals(section.models);

        return (
          <div key={section.id} className="settings-section">
            <button
              type="button"
              className="settings-section-header"
              onClick={() => toggleSection(section.id)}
              aria-expanded={isOpen}
            >
              <div className="settings-section-heading">
                <span className="settings-section-title">{section.title}</span>
                {section.description && (
                  <span className="settings-section-description">{section.description}</span>
                )}
              </div>
              <div className="settings-section-meta">
                <span className="settings-section-totals">
                  {formatTokens(totals.tokens)} tokens · ${totals.cost.toFixed(2)}
                </span>
                <span className={`settings-section-chevron${isOpen ? ' is-open' : ''}`}>▾</span>
              </div>
            </button>

            {isOpen && (
              <div className="settings-section-body">
                {section.models.map((model) => {
                  const usage = Math.min((model.tokensUsed / model.tokensLimit) * 100, 100);

                  return (
                    <div
                      key={model.id}
                      className={`settings-model${model.enabled ? '' : ' is-disabled'}`}
                    >
                      <div className="settings-model-header">
                        <div className="settings-model-title">
                          <span className="settings-model-name">{model.name}</span>
                          <span className="settings-model-model">{model.model}</span>
                        </div>
                        <label className="settings-toggle">
                          <input
                            type="checkbox"
                            checked={model.enabled}
                            onChange={(e) =>
                              updateModel(section.id, model.id, { enabled: e.target.checked })
                            }
                          />
                          <span className="settings-toggle-slider" />
                        </label>
                      </div>

                      <div className="modal-field">
                        <label className="modal-label" htmlFor={`api-key-${model.id}`}>
                          Chave de API
                        </label>
                        <div className="settings-key-row">
                          <input
                            id={`api-key-${model.id}`}
                            className="modal-input"
                            type={visibleKeys.has(model.id) ? 'text' : 'password'}
                            value={model.apiKey}
                            onChange={(e) =>
                              updateModel(section.id, model.id, { apiKey: e.target.value })
                            }
                            autoComplete="off"
                            spellCheck={false}
                          />
                          <button
                            type="button"
                            className="settings-key-toggle"
                            onClick={() => toggleKeyVisibility(model.id)}
                            aria-label="Mostrar/ocultar chave"
                          >
                            {visibleKeys.has(model.id) ? 'Ocultar' : 'Mostrar'}
                          </button>
                        </div>
                      </div>

                      <div className="settings-usage">
                        <div className="settings-usage-line">
                          <span className="settings-usage-text">
                            {formatTokens(model.tokensUsed)} / {formatTokens(model.tokensLimit)} tokens
                          </span>
                          <span className="settings-usage-cost">${model.cost.toFixed(2)}</span>
                        </div>
                        <div className="settings-usage-bar">
                          <div className="settings-usage-fill" style={{ width: `${usage}%` }} />
                        </div>
                      </div>

                      <button
                        type="button"
                        className="settings-model-clear"
                        onClick={() => clearModelCache(section.id, model.id)}
                      >
                        Limpar cache
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}

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
