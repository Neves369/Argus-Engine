import { useEffect, useState } from 'react';
import {
  getDashboardRuns,
  getDashboardSummary,
  type DashboardRun,
  type DashboardSummary,
} from '../api/client';
import './Dashboard.css';

function formatNumber(value: number): string {
  return new Intl.NumberFormat('en-US').format(value);
}

function statusLabel(status: string): string {
  if (status === 'pending_review') return 'Em revisão (HITL)';
  if (status === 'completed') return 'Concluído';
  if (status === 'failed') return 'Falha';
  if (status === 'running') return 'Executando';
  return status;
}

interface DashboardProps {
  onOpenReport: (runId: number) => void;
}

const SEVERITY_ORDER = ['critical', 'high', 'medium', 'low', 'info', 'unknown'];
const SEVERITY_LABELS: Record<string, string> = {
  critical: 'crit',
  high: 'high',
  medium: 'med',
  low: 'low',
  info: 'info',
  unknown: '?',
};

function SeverityChips({ bySeverity }: { bySeverity?: Record<string, number> }) {
  if (!bySeverity) return null;
  const entries = SEVERITY_ORDER.filter(
    (key) => key === 'critical' && (bySeverity[key] ?? 0) > 0,
  );
  if (entries.length === 0) return null;
  return (
    <span className="dashboard-sev-chips">
      {entries.map((key) => (
        <span key={key} className={`dashboard-sev-chip dashboard-sev-chip--${key}`}>
          {SEVERITY_LABELS[key] ?? key} {bySeverity[key]}
        </span>
      ))}
    </span>
  );
}

function Dashboard({ onOpenReport }: DashboardProps) {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [runs, setRuns] = useState<DashboardRun[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getDashboardSummary()
      .then(setSummary)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
    getDashboardRuns()
      .then(setRuns)
      .catch(() => undefined);
  }, []);

  if (error) {
    return <div className="dashboard">Erro ao carregar dashboard: {error}</div>;
  }

  return (
    <div className="dashboard">
      <div className="dashboard-cards">
        <div className="dashboard-card">
          <div className="dashboard-card-value">{summary ? formatNumber(summary.runs.total) : '—'}</div>
          <div className="dashboard-card-label">Runs totais</div>
        </div>
        <div className="dashboard-card">
          <div className="dashboard-card-value">
            {summary ? formatNumber(summary.pending_reviews) : '—'}
          </div>
          <div className="dashboard-card-label">Em revisão (HITL)</div>
        </div>
        <div className="dashboard-card">
          <div className="dashboard-card-value">
            {summary ? formatNumber(summary.findings.total) : '—'}
          </div>
          <div className="dashboard-card-label">Findings</div>
        </div>
        <div className="dashboard-card">
          <div className="dashboard-card-value">
            {summary ? formatNumber(summary.costs.total_tokens) : '—'}
          </div>
          <div className="dashboard-card-label">Tokens</div>
        </div>
      </div>

      <div className="dashboard-section">
        <div className="dashboard-title">Runs</div>
        {runs.length === 0 ? (
          <div className="dashboard-empty">Nenhum run ainda.</div>
        ) : (
          <div className="dashboard-table">
            <div className="dashboard-tr dashboard-tr--head">
              <span>Run</span>
              <span>Alvo</span>
              <span>Findings</span>
              <span>Tokens</span>
              <span>Status</span>
              <span>Ações</span>
            </div>
            {runs.map((run) => (
              <div key={run.id} className="dashboard-tr">
                <span>#{run.id}</span>
                <span className="dashboard-target">{run.target ?? '—'}</span>
                <span className="dashboard-findings">
                  {run.findings}
                  <SeverityChips bySeverity={run.by_severity} />
                </span>
                <span className="dashboard-mono">{formatNumber(run.tokens)}</span>
                <span className={`dashboard-status dashboard-status--${run.status}`}>
                  {statusLabel(run.status)}
                </span>
                <span>
                  <button
                    type="button"
                    className="dashboard-action"
                    onClick={() => onOpenReport(run.id)}
                  >
                    {run.status === 'pending_review' ? 'Revisar' : 'Ver'}
                  </button>
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default Dashboard;
