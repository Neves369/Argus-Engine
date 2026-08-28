import { useEffect, useState } from 'react';
import {
  getDashboardRuns,
  getDashboardSummary,
  type DashboardRun,
  type DashboardSummary,
} from '../api/client';
import './Dashboard.css';

function formatCost(cost: number): string {
  return `$${cost.toFixed(4)}`;
}

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

function Dashboard() {
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

  const statuses = summary?.runs.by_status ?? {};
  const severities = summary?.findings.by_severity ?? {};
  const order = ['critical', 'high', 'medium', 'low', 'info', 'unknown'];

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
            {summary ? formatCost(summary.costs.total_cost) : '—'}
          </div>
          <div className="dashboard-card-label">Custo total</div>
        </div>
        <div className="dashboard-card">
          <div className="dashboard-card-value">
            {summary ? formatNumber(summary.costs.total_tokens) : '—'}
          </div>
          <div className="dashboard-card-label">Tokens</div>
        </div>
      </div>

      <div className="dashboard-section">
        <div className="dashboard-title">Runs por status</div>
        <div className="dashboard-chips">
          {Object.entries(statuses).length === 0 && <span className="dashboard-empty">Sem dados.</span>}
          {Object.entries(statuses).map(([key, value]) => (
            <span key={key} className="dashboard-chip">{key}: {value}</span>
          ))}
        </div>
      </div>

      <div className="dashboard-section">
        <div className="dashboard-title">Findings por severidade</div>
        <div className="dashboard-chips">
          {Object.entries(severities).length === 0 && <span className="dashboard-empty">Sem dados.</span>}
          {order
            .filter((key) => key in severities)
            .map((key) => (
              <span key={key} className="dashboard-chip">{key}: {severities[key]}</span>
            ))}
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
              <span>Custo</span>
              <span>Tokens</span>
              <span>Status</span>
            </div>
            {runs.map((run) => (
              <div key={run.id} className="dashboard-tr">
                <span>#{run.id}</span>
                <span className="dashboard-target">{run.target ?? '—'}</span>
                <span>{run.findings}</span>
                <span className="dashboard-mono">{formatCost(run.cost)}</span>
                <span className="dashboard-mono">{formatNumber(run.tokens)}</span>
                <span className={`dashboard-status dashboard-status--${run.status}`}>
                  {statusLabel(run.status)}
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
