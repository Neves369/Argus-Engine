import { useEffect, useMemo, useState } from 'react';
import {
  listPolicyPackages,
  listProbes,
  type PolicyPackage,
  type ProbeClass,
  type RunDepth,
  type TarotPreset,
} from '../api/client';
import './RunConfig.css';

export interface RunPolicyState {
  depth: RunDepth;
  probeClasses: string[];
  policyPackage: string | null;
  preset: string | null;
}

interface RunConfigProps {
  value: RunPolicyState;
  presets: TarotPreset[];
  onChange: (next: RunPolicyState) => void;
  onApplyPreset: (preset: TarotPreset) => void;
  disabled?: boolean;
}

interface SelectProps {
  label: string;
  hint: string;
  id: string;
  value: string;
  options: { id: string; name: string; description: string }[];
  placeholder: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

function RunConfigSelect({
  label,
  hint,
  id,
  value,
  options,
  placeholder,
  onChange,
  disabled = false,
}: SelectProps) {
  return (
    <div className="modal-field">
      <label className="modal-label" htmlFor={id}>
        {label}
      </label>
      <select
        className="modal-input run-config-select"
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
      >
        <option value="">{placeholder}</option>
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {option.name}
          </option>
        ))}
      </select>
      <p className="modal-hint">{hint}</p>
    </div>
  );
}

function RunConfig({ value, presets, onChange, onApplyPreset, disabled = false }: RunConfigProps) {
  const [packages, setPackages] = useState<PolicyPackage[]>([]);
  const [probes, setProbes] = useState<ProbeClass[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listPolicyPackages()
      .then(setPackages)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
    listProbes()
      .then(setProbes)
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : String(err)),
      );
  }, []);

  const selectedPackage = useMemo(
    () => packages.find((p) => p.id === value.policyPackage) ?? null,
    [packages, value.policyPackage],
  );
  const selectedPreset = useMemo(
    () => presets.find((p) => p.id === value.preset) ?? null,
    [presets, value.preset],
  );

  const managed = value.policyPackage != null;
  const probesByPriority = useMemo(() => {
    const order = ['P0', 'P1', 'P2', 'P3'];
    return [...probes].sort(
      (a, b) => order.indexOf(a.priority) - order.indexOf(b.priority),
    );
  }, [probes]);

  function toggleProbe(id: string) {
    const next = value.probeClasses.includes(id)
      ? value.probeClasses.filter((x) => x !== id)
      : [...value.probeClasses, id];
    onChange({ ...value, probeClasses: next });
  }

  function handlePresetChange(presetId: string) {
    const preset = presets.find((p) => p.id === presetId);
    const base: RunPolicyState = preset
      ? { ...value, preset: preset.id, policyPackage: preset.policy_package }
      : { ...value, preset: null };
    onChange(base);
    if (preset) {
      onApplyPreset(preset);
    }
  }

  function handlePackageChange(packageId: string) {
    onChange({ ...value, policyPackage: packageId || null });
  }

  if (error) {
    return <div className="run-config">Erro ao carregar políticas: {error}</div>;
  }

  const presetActive = value.preset != null;

  return (
    <section className="run-config" aria-label="Política do run">
      <div className="run-config-title">Política do run</div>
      <p className="modal-hint">
        Escolha profundidade, classes de comportamento e política sem editar YAML.
        Um pacote de política governa depth/classes/jornadas do run.
      </p>

      <RunConfigSelect
        label="Preset Tarot"
        id="run-preset"
        value={value.preset ?? ''}
        options={presets.map((p) => ({
          id: p.id,
          name: p.name,
          description: p.description,
        }))}
        placeholder="Nenhum — escolho as cartas na mão"
        onChange={handlePresetChange}
        disabled={disabled}
        hint={
          selectedPreset
            ? `Cartas: ${selectedPreset.archetypes.join(' → ')}. Pareado com o pacote ${selectedPreset.policy_package ?? '—'}.`
            : 'Composição pronta de cartas pareada a um pacote de política.'
        }
      />

      <RunConfigSelect
        label="Pacote de política"
        id="run-package"
        value={value.policyPackage ?? ''}
        options={packages.map((p) => ({
          id: p.id,
          name: p.name,
          description: p.description,
        }))}
        placeholder="Nenhum — controlo depth e classes na mão"
        onChange={handlePackageChange}
        disabled={presetActive || disabled}
        hint={
          presetActive
            ? `Com o preset ativo, o pacote "${selectedPackage?.name ?? value.policyPackage}" governa o run. Limpe o preset na mão para escolher outro pacote ou controlar manualmente.`
            : selectedPackage
              ? `${selectedPackage.description} Governa depth=${selectedPackage.depth}, ${selectedPackage.probe_classes.length} classes de probe e ${selectedPackage.journey_classes.length} jornada(s).`
              : 'Pacote versionado (lab, bugbounty-web, api-only, surface-only). Quando definido, depth/classes explícitas são ignoradas.'
        }
      />

      <div className={`run-config-block${managed ? ' is-governed' : ''}`}>
        <div className="modal-field">
          <span className="modal-label">Profundidade</span>
          <div className="run-config-radios">
            {(['quick', 'deep'] as RunDepth[]).map((option) => (
              <label key={option} className="run-config-radio">
                <input
                  type="radio"
                  name="run-depth"
                  value={option}
                  checked={value.depth === option}
                  onChange={() => onChange({ ...value, depth: option })}
                  disabled={managed || disabled}
                />
                {option === 'quick' ? 'Quick (seguro)' : 'Deep (amplo + probes)'}
              </label>
            ))}
          </div>
          {managed && (
            <p className="modal-hint">
              Governado pelo pacote: depth={selectedPackage?.depth}.
            </p>
          )}
          {!managed && (
            <p className="modal-hint">
              Default seguro é quick. Deep adiciona o Carro (probes ao vivo) e amplia o crawl.
            </p>
          )}
        </div>
      </div>

      <div className={`run-config-block${managed ? ' is-governed' : ''}`}>
        <div className="modal-field">
          <span className="modal-label">Classes de comportamento (M6)</span>
          {managed ? (
            <p className="modal-hint">
              Liberadas pelo pacote: {selectedPackage?.probe_classes.join(', ') || 'nenhuma'}.
            </p>
          ) : (
            <>
              <p className="modal-hint">
                Sem seleção → default seguro P0. P1+ pedem allowlist explícita.
              </p>
              <div className="run-config-probes">
                {probesByPriority.map((probe) => (
                  <label key={probe.id} className="run-config-probe">
                    <input
                      type="checkbox"
                      checked={value.probeClasses.includes(probe.id)}
                      onChange={() => toggleProbe(probe.id)}
                      disabled={disabled}
                    />
                    <span className="run-config-probe-badge">{probe.priority}</span>
                    <span className="run-config-probe-name">{probe.class_label}</span>
                  </label>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      {value.preset && (
        <p className="modal-hint">
          O preset é autoritativo para as cartas e traz seu pacote de política.
        </p>
      )}
      {managed && (
        <p className="modal-hint">
          O pacote governa também o devil_mode (os pacotes atuais são devil_mode=false); o
          modo Death no menu é ignorado enquanto um pacote estiver ativo.
        </p>
      )}
    </section>
  );
}

export default RunConfig;