import { DEFAULT_SESSIONS, type SessionStatus } from '../data/sessions';
import './Sessions.css';

const STATUS_LABELS: Record<SessionStatus, string> = {
  in_progress: 'Em andamento',
  completed: 'Concluída',
  failed: 'Falha',
};

function Sessions() {
  return (
    <div className="sessions">
      <div className="sessions-header">
        <span className="sessions-col">Alvo</span>
        <span className="sessions-col">Início</span>
        <span className="sessions-col">Término</span>
        <span className="sessions-col">Status</span>
      </div>
      <div className="sessions-list">
        {DEFAULT_SESSIONS.map((session) => (
          <div key={session.id} className="sessions-row">
            <span className="sessions-target">{session.target}</span>
            <span className="sessions-time">{session.startTime}</span>
            <span className="sessions-time">{session.endTime}</span>
            <span className={`sessions-status sessions-status--${session.status}`}>
              {STATUS_LABELS[session.status]}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default Sessions;
