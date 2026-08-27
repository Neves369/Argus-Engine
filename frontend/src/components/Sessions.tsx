import { useEffect, useState } from 'react';
import { listRuns, type Run } from '../api/client';
import './Sessions.css';

type SessionStatus = 'in_progress' | 'completed' | 'failed';

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

function Sessions() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listRuns()
      .then(setRuns)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  if (error) {
    return <div className="sessions">Erro ao carregar sessões: {error}</div>;
  }

  return (
    <div className="sessions">
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
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default Sessions;
