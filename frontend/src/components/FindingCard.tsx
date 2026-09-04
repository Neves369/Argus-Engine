import type { RunFinding } from '../api/client';
import './FindingCard.css';

function formatConfidence(conf?: number): string {
  if (conf === undefined || conf === null) return '—';
  return `${Math.round(conf * 100)}%`;
}

function formatCvss(score?: number | null, vector?: string | null): string | null {
  if (score === undefined || score === null) return null;
  return vector ? `${score} ${vector}` : String(score);
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
  const cvss = formatCvss(finding.cvss_score, finding.cvss_vector);
  const cves = finding.cves?.filter(Boolean) ?? [];
  const exploits = finding.known_exploits?.filter(Boolean) ?? [];
  const references = finding.references?.filter(Boolean) ?? [];

  return (
    <div className="finding-card">
      <div className="finding-card-head">
        <span className="finding-card-title">{title}</span>
        <span className="finding-card-badge finding-card-badge--confidence">
          {formatConfidence(finding.confidence)}
        </span>
      </div>

      <div className="finding-card-meta">
        {severity && (
          <span className={`finding-card-badge finding-card-badge--severity finding-card-badge--sev-${severity}`}>
            {severity}
          </span>
        )}
        {finding.category && (
          <span className="finding-card-badge finding-card-badge--category">{finding.category}</span>
        )}
        {cvss && (
          <span className="finding-card-badge finding-card-badge--cvss">CVSS {cvss}</span>
        )}
        {finding.status && (
          <span className="finding-card-badge">{finding.status}</span>
        )}
        {finding.requires_human_review && (
          <span className="finding-card-badge finding-card-badge--review">requer revisão</span>
        )}
      </div>

      {cves.length > 0 && (
        <div className="finding-card-chips">
          {cves.map((cve) => (
            <span key={cve} className="finding-card-chip finding-card-chip--cve">{cve}</span>
          ))}
        </div>
      )}

      {exploits.length > 0 && (
        <div className="finding-card-exploits">
          <span className="finding-card-exploit-label">Exploit público:</span>{' '}
          {exploits.join('; ')}
        </div>
      )}

      {finding.description && (
        <div className="finding-card-description">{finding.description}</div>
      )}

      {finding.evidence && (
        <div className="finding-card-evidence">
          <span className="finding-card-evidence-label">Evidência (dado real consultado):</span>
          <span className="finding-card-evidence-text">{finding.evidence}</span>
        </div>
      )}

      {finding.remediation && (
        <div className="finding-card-remediation">
          <span className="finding-card-remediation-label">Remediação:</span>{' '}
          {finding.remediation}
        </div>
      )}

      {references.length > 0 && (
        <div className="finding-card-references">
          {references.map((ref) => (
            <div key={ref} className="finding-card-reference">{ref}</div>
          ))}
        </div>
      )}
    </div>
  );
}

export default FindingCard;