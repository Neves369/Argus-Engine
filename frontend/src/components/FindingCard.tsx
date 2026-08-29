import type { RunFinding } from '../api/client';
import './FindingCard.css';

function formatConfidence(conf?: number): string {
  if (conf === undefined || conf === null) return '—';
  return `${Math.round(conf * 100)}%`;
}

function FindingCard({
  finding,
  index,
}: {
  finding: RunFinding;
  index?: number;
}) {
  const title = finding.title ?? finding.id ?? `Achado ${(index ?? 0) + 1}`;
  const severity = finding.severity ?? undefined;
  return (
    <div className="finding-card">
      <div className="finding-card-head">
        <span className="finding-card-title">{title}</span>
        <span className="finding-card-badge finding-card-badge--confidence">
          {formatConfidence(finding.confidence)}
        </span>
      </div>
      {finding.description && (
        <div className="finding-card-description">{finding.description}</div>
      )}
      <div className="finding-card-meta">
        {severity && (
          <span className={`finding-card-badge finding-card-badge--severity finding-card-badge--sev-${severity}`}>
            {severity}
          </span>
        )}
        {finding.status && (
          <span className="finding-card-badge">{finding.status}</span>
        )}
        {finding.requires_human_review && (
          <span className="finding-card-badge finding-card-badge--review">requer revisão</span>
        )}
      </div>
    </div>
  );
}

export default FindingCard;