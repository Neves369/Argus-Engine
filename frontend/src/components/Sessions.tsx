import { useEffect, useState } from 'react';
import {
  listCompositions,
  listRuns,
  listTargets,
  type Composition,
  type Run,
  type Target,
} from '../api/client';
import './Sessions.css';

type SessionStatus = 'in_progress' | 'completed' | 'failed';
type SessionsTab = 'compositions' | 'targets' | 'executions';

const STATUS_LABELS: Record<SessionStatus, string> = {
  in_progress: 'Em andamento',
  completed: 'Concluída',
  failed: 'Falha',
};

function normalizeStatus(status: string): SessionStatus {
  if (status === 'completed') return 'completed';
  if (status === 'failed') return 'failed';
  return 'in_progress';
}

function formatTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
}

function targetName(run: Run): string {
  return run.result?.target?.name ?? run.target_id?.toString() ?? `#${run.id}`;
}

interface SessionsProps {
  onLoad: (composition: Composition) => void;
  onExecute: (compositionId: number) => Promise<void>;
  onOpenReport: (runId: number) => void;
  onSelectTarget: (target: Target) => void;
  locked?: boolean;
}

function Sessions({ onLoad, onExecute, onOpenReport, onSelectTarget, locked = false }: SessionsProps) {
  const [tab, setTab] = useState<SessionsTab>('compositions');
  const [runs, setRuns] = useState<Run[]>([]);
  const [compositions, setCompositions] = useState<Composition[]>([]);
  const [targets, setTargets] = useState<Target[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [executing, setExecuting] = useState<number | null>(null);

  useEffect(() => {
    listRuns()
      .then(setRuns)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
    listCompositions()
      .then(setCompositions)
      .catch(() => undefined);
    listTargets()
      .then(setTargets)
      .catch(() => undefined);
  }, []);

  async function handleExecute(compositionId: number) {
    setExecuting(compositionId);
    try {
      await onExecute(compositionId);
      const updatedRuns = await listRuns();
      setRuns(updatedRuns);
    } catch (err) {
      window.alert(err instanceof Error ? err.message : String(err));
      const updatedRuns = await listRuns();
      setRuns(updatedRuns);
    } finally {
      setExecuting(null);
    }
  }

  if (error) {
    return <div className="sessions">Erro ao carregar sessões: {error}</div>;
  }

  return (
    <div className="sessions">
      <div className="sessions-tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'compositions'}
          className={`sessions-tab${tab === 'compositions' ? ' sessions-tab--active' : ''}`}
          onClick={() => setTab('compositions')}
        >
          Composições
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'targets'}
          className={`sessions-tab${tab === 'targets' ? ' sessions-tab--active' : ''}`}
          onClick={() => setTab('targets')}
        >
          Alvos
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'executions'}
          className={`sessions-tab${tab === 'executions' ? ' sessions-tab--active' : ''}`}
          onClick={() => setTab('executions')}
        >
          Execuções
        </button>
      </div>

      {tab === 'compositions' && (
        <div className="sessions-block">
          <div className="sessions-title">
            Composições
            {locked && (
              <span className="sessions-lock-hint">
                Há um run ativo — execute apenas depois que ele concluir.
              </span>
            )}
          </div>
          {compositions.length === 0 ? (
            <div className="sessions-empty">Nenhuma composição salva.</div>
          ) : (
            <div className="sessions-list">
              {compositions.map((comp) => (
                <div key={comp.id} className="sessions-row">
                  <span className="sessions-target">{comp.name}</span>
                  <span className="sessions-time">
                    {comp.config?.archetypes?.join(' → ') ?? '—'}
                  </span>
                  <span className={`sessions-status sessions-status--${comp.status === 'done' ? 'completed' : 'in_progress'}`}>
                    {comp.status}
                  </span>
                  <div className="sessions-actions">
                    <button
                      type="button"
                      className="sessions-exec"
                      onClick={() => onLoad(comp)}
                    >
                      Carregar
                    </button>
                    <button
                      type="button"
                      className="sessions-exec"
                      disabled={executing === comp.id || locked}
                      onClick={() => handleExecute(comp.id)}
                    >
                      {executing === comp.id ? 'Executando…' : 'Executar'}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === 'targets' && (
        <div className="sessions-block">
          <div className="sessions-title">Alvos</div>
          {targets.length === 0 ? (
            <div className="sessions-empty">Nenhum alvo salvo.</div>
          ) : (
            <div className="sessions-list">
              {targets.map((target) => (
                <div key={target.id} className="sessions-row sessions-row--target">
                  <span className="sessions-target">{target.name}</span>
                  <span className="sessions-time">{target.url ?? '—'}</span>
                  <div className="sessions-actions">
                    <button
                      type="button"
                      className="sessions-exec"
                      onClick={() => onSelectTarget(target)}
                    >
                      Usar
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === 'executions' && (
        <div className="sessions-block">
          <div className="sessions-header">
            <span className="sessions-col">Alvo</span>
            <span className="sessions-col">Início</span>
            <span className="sessions-col">Término</span>
            <span className="sessions-col">Status</span>
          </div>
          <div className="sessions-list">
            {runs.map((run) => {
              const status = normalizeStatus(run.status);
              return (
                <div key={run.id} className="sessions-row">
                  <span className="sessions-target">{targetName(run)}</span>
                  <span className="sessions-time">{formatTime(run.started_at ?? run.created_at)}</span>
                  <span className="sessions-time">{formatTime(run.finished_at)}</span>
                  <span className={`sessions-status sessions-status--${status}`}>
                    {STATUS_LABELS[status]}
                  </span>
                  <div className="sessions-actions">
                    <button
                      type="button"
                      className="sessions-exec"
                      onClick={() => onOpenReport(run.id)}
                    >
                      Ver
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

export default Sessions;