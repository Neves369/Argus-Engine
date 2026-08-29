import { useEffect, useRef, useState } from 'react';
import type {
  ChatMessage,
  RunFinding,
  RunLogLine,
  RunMeta,
  TraceStep,
} from '../api/client';
import FindingCard from './FindingCard';
import './RunPanel.css';

type Tab = 'log' | 'chat' | 'results';

interface RunPanelProps {
  runId: number | null;
  status: string | null;
  running: boolean;
  log: RunLogLine[];
  chat: ChatMessage[];
  meta: RunMeta;
  findings: RunFinding[];
  trace: TraceStep[];
  error?: string | null;
  readonly?: boolean;
  onCancel: () => void;
  onClose: () => void;
}

const STATUS_LABELS: Record<string, string> = {
  running: 'Em execução',
  completed: 'Concluído',
  failed: 'Falha',
  cancelled: 'Cancelado',
  pending_review: 'Aguardando revisão',
};

function formatDuration(ms?: number): string {
  if (ms === undefined || Number.isNaN(ms)) return '—';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function formatCost(cost?: number): string {
  if (cost === undefined || cost === null) return '—';
  return `$${cost.toFixed(4)}`;
}

function RunPanel({
  runId,
  status,
  running,
  log,
  chat,
  meta,
  findings,
  trace,
  error,
  readonly = false,
  onCancel,
  onClose,
}: RunPanelProps) {
  const [tab, setTab] = useState<Tab>('results');
  const scrollRef = useRef<HTMLDivElement>(null);
  const prevRunningRef = useRef(running);

  useEffect(() => {
    if (prevRunningRef.current && !running) {
      setTab('results');
    }
    prevRunningRef.current = running;
  }, [running]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [log, chat]);

  const statusClass = status ?? '';
  const statusLabel = status ? (STATUS_LABELS[status] ?? status) : '';

  return (
    <div className="run-panel">
      <div className="run-panel-header">
        <span className="run-panel-title">
          Run #{runId ?? '—'}
          {status && <span className={`run-panel-status run-panel-status--${statusClass}`}>{statusLabel}</span>}
        </span>
        <div className="run-panel-actions">
          {running && !readonly && (
            <button type="button" className="run-panel-cancel" onClick={onCancel}>
              Cancelar
            </button>
          )}
          <button type="button" className="run-panel-close" onClick={onClose} aria-label="Fechar">
            ✕
          </button>
        </div>
      </div>

      <div className="run-panel-tabs" role="tablist">
        <button
          type="button"
          className={`run-panel-tab${tab === 'log' ? ' is-active' : ''}`}
          onClick={() => setTab('log')}
        >
          Log
        </button>
        <button
          type="button"
          className={`run-panel-tab${tab === 'chat' ? ' is-active' : ''}`}
          onClick={() => setTab('chat')}
        >
          Chat{chat.length > 0 ? ` (${chat.length})` : ''}
        </button>
        <button
          type="button"
          className={`run-panel-tab${tab === 'results' ? ' is-active' : ''}`}
          onClick={() => setTab('results')}
        >
          Resultados
        </button>
      </div>

      <div className="run-panel-body">
        {tab === 'log' && (
          <div className="run-panel-scroll" ref={scrollRef}>
            {log.length === 0 ? (
              <div className="run-panel-empty">Nenhuma atividade registrada ainda.</div>
            ) : (
              log.map((line, index) => (
                <div key={index} className="run-panel-log-line">
                  <span className="run-panel-log-node">{line.node}</span>
                  <span className="run-panel-log-text">{line.text}</span>
                </div>
              ))
            )}
          </div>
        )}

        {tab === 'chat' && (
          <div className="run-panel-scroll" ref={scrollRef}>
            {chat.length === 0 ? (
              <div className="run-panel-empty">O raciocínio dos arquétipos aparecerá aqui.</div>
            ) : (
              chat.map((message, index) => (
                <div key={index} className="run-panel-chat-bubble">
                  <div className="run-panel-chat-head">
                    <span className="run-panel-chat-agent">{message.agent}</span>
                    <span className="run-panel-chat-action">{message.action}</span>
                  </div>
                  {message.reasoning && (
                    <div className="run-panel-chat-text">{message.reasoning}</div>
                  )}
                </div>
              ))
            )}
          </div>
        )}

        {tab === 'results' && (
          <div className="run-panel-results">
            <div className="run-panel-meta">
              <span className="run-panel-meta-item">Tokens: <b>{meta.tokens ?? '—'}</b></span>
              <span className="run-panel-meta-item">Custo: <b>{formatCost(meta.cost)}</b></span>
              {meta.durationMs !== undefined && meta.durationMs !== null && (
                <span className="run-panel-meta-item">Duração: <b>{formatDuration(meta.durationMs)}</b></span>
              )}
              {meta.stopReason && (
                <span className="run-panel-meta-item">Motivo: <b>{meta.stopReason}</b></span>
              )}
              {meta.target && (
                <span className="run-panel-meta-item">Alvo: <b>{meta.target}</b></span>
              )}
            </div>

            {error && <div className="run-panel-error">{error}</div>}

            <div className="run-panel-section-title">Achados ({findings.length})</div>
            {findings.length === 0 ? (
              <div className="run-panel-empty">
                {running ? 'Buscando achados…' : 'Nenhum achado registrado.'}
              </div>
            ) : (
              <div className="run-panel-table">
                {findings.map((finding, index) => (
                  <FindingCard key={finding.id ?? index} finding={finding} index={index} />
                ))}
              </div>
            )}

            <div className="run-panel-section-title">Trace ({trace.length})</div>
            {trace.length === 0 ? (
              <div className="run-panel-empty">Nenhuma etapa registrada.</div>
            ) : (
              <div className="run-panel-table">
                {trace.map((step, index) => (
                  <div key={index} className="run-panel-trace-row">
                    <span className="run-panel-trace-node">{step.node ?? '?'}</span>
                    <span className="run-panel-trace-model">
                      {[step.provider, step.model].filter(Boolean).join('/') || '—'}
                    </span>
                    <span className="run-panel-trace-num">{formatDuration(step.duration_ms)}</span>
                    <span className="run-panel-trace-num">{step.tokens ?? 0} tok</span>
                    <span className="run-panel-trace-num">{formatCost(step.cost)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default RunPanel;