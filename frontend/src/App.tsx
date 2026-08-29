import { useEffect, useRef, useState } from "react";
import { useEdgesState, useNodesState, type Edge } from "@xyflow/react";
import backgroundImage from "./assets/backgrounds/Background1.png";
import deathImg from "./assets/cards/death.jpg";
import CharacterPanel from "./components/CharacterPanel";
import Dashboard from "./components/Dashboard";
import DeathOverlay from "./components/DeathOverlay";
import EndTurnButton from "./components/EndTurnButton";
import EnemyForm from "./components/EnemyForm";
import Hand from "./components/Hand";
import Login from "./components/Login";
import Modal from "./components/Modal";
import PlayedArea from "./components/PlayedArea";
import RunPanel from "./components/RunPanel";
import Sessions from "./components/Sessions";
import Settings from "./components/Settings";
import {
  cancelRun,
  createComposition,
  getActiveRun,
  getReport,
  runStream,
  type ActiveRunInfo,
  type ChatMessage,
  type Composition,
  type HistoryEntry,
  type RunFinding,
  type RunLogLine,
  type RunMeta,
  type StreamEvent,
  type RunEndSignal,
  type TraceStep,
} from "./api/client";
import type { CardNodeType } from "./components/CardNode";
import { CARD_ARCHETYPES } from "./data/agents";
import "./App.css";

function formatDuration(ms?: number): string {
  if (ms === undefined || Number.isNaN(ms)) return "—";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function formatTraceStep(step: TraceStep): string {
  const model = [step.provider, step.model].filter(Boolean).join("/");
  const parts: string[] = [];
  if (model) parts.push(model);
  if (step.duration_ms !== undefined) parts.push(formatDuration(step.duration_ms));
  if (typeof step.tokens === "number") parts.push(`${step.tokens} tok`);
  if (typeof step.cost === "number") parts.push(`$${step.cost.toFixed(4)}`);
  return parts.join(" · ");
}

function App() {
  const [loggedIn, setLoggedIn] = useState(false);
  const [enemyModalOpen, setEnemyModalOpen] = useState(false);
  const [playerModalOpen, setPlayerModalOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [sessionsOpen, setSessionsOpen] = useState(false);
  const [dashboardOpen, setDashboardOpen] = useState(false);
  const [connectionsOn, setConnectionsOn] = useState(false);
  const [deathMode, setDeathMode] = useState(false);
  const [enemyInfo, setEnemyInfo] = useState({ name: '', url: '', notes: '' });
  const [returnedCard, setReturnedCard] = useState<number | undefined>(undefined);
  const [runResult, setRunResult] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [activeArchetype, setActiveArchetype] = useState<string | null>(null);
  const [runEnded, setRunEnded] = useState(false);
  const [activeRun, setActiveRun] = useState<ActiveRunInfo>({
    active: false,
    run_id: null,
    status: null,
  });
  const [runId, setRunId] = useState<number | null>(null);
  const [historyRunId, setHistoryRunId] = useState<number | null>(null);
  const [runStatus, setRunStatus] = useState<string | null>(null);
  const [runLog, setRunLog] = useState<RunLogLine[]>([]);
  const [chat, setChat] = useState<ChatMessage[]>([]);
  const [runMeta, setRunMeta] = useState<RunMeta>({});
  const [runFindings, setRunFindings] = useState<RunFinding[]>([]);
  const [runTrace, setRunTrace] = useState<TraceStep[]>([]);
  const [runError, setRunError] = useState<string | null>(null);

  const lastTraceLenRef = useRef(0);
  const lastHistoryLenRef = useRef(0);

  const [nodes, setNodes, onNodesChange] = useNodesState<CardNodeType>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  useEffect(() => {
    const sorted = [...nodes].sort((a, b) => a.position.x - b.position.x);
    const next: Edge[] = [];
    for (let i = 0; i < sorted.length - 1; i += 1) {
      next.push({
        id: `edge-${i}`,
        source: sorted[i].id,
        target: sorted[i + 1].id,
        type: 'smoothstep',
        animated: true,
        style: { stroke: '#c084fc', strokeWidth: 3 },
      });
    }
    setEdges(next);
  }, [nodes, setEdges]);

  useEffect(() => {
    setNodes((prev) =>
      prev.map((node) => {
        const isActive = CARD_ARCHETYPES[node.data.id] === activeArchetype;
        return {
          ...node,
          data: {
            ...node.data,
            active: isActive,
            ended: runEnded && isActive,
          },
        };
      }),
    );
  }, [activeArchetype, runEnded, setNodes]);

  async function refreshActiveRun() {
    try {
      setActiveRun(await getActiveRun());
    } catch {
      // polling em segundo plano; falha pontual é ignorada
    }
  }

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const info = await getActiveRun();
        if (!cancelled) setActiveRun(info);
      } catch {
        // ignore
      }
    };
    tick();
    const intervalId = window.setInterval(tick, 3000);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, []);

  function handleCardPlayed(id: number) {
    setActiveArchetype(null);
    setRunEnded(false);
    setNodes((prev) => {
      if (prev.some((node) => node.id === `card-${id}`)) {
        return prev;
      }
      const node: CardNodeType = {
        id: `card-${id}`,
        type: 'card',
        position: { x: 80 + prev.length * 60, y: -100 + (id % 3) * 20 },
        data: { id, onReturn: handleCardReturn },
      };
      return [...prev, node];
    });
    setReturnedCard(id);
    window.setTimeout(() => setReturnedCard(undefined), 100);
  }

  function handleCardReturn(id: number) {
    setActiveArchetype(null);
    setRunEnded(false);
    setNodes((prev) => prev.filter((node) => node.id !== `card-${id}`));
    setEdges((prev) => prev.filter((e) => e.source !== `card-${id}` && e.target !== `card-${id}`));
    setReturnedCard(id);
    window.setTimeout(() => setReturnedCard(undefined), 100);
  }

  function currentArchetypes(): string[] {
    const sorted = [...nodes].sort((a, b) => a.position.x - b.position.x);
    return sorted.map((node) => CARD_ARCHETYPES[node.data.id]);
  }

  function ingestEvent(event: StreamEvent): void {
    const update = event.update ?? {};
    const trace = (update.trace as TraceStep[] | undefined) ?? [];
    if (trace.length > lastTraceLenRef.current) {
      trace.slice(lastTraceLenRef.current).forEach((step) => {
        setRunLog((prev) => [
          ...prev,
          { node: step.node ?? event.node, text: formatTraceStep(step) },
        ]);
      });
      lastTraceLenRef.current = trace.length;
    }
    const history = (update.history as HistoryEntry[] | undefined) ?? [];
    if (history.length > lastHistoryLenRef.current) {
      history.slice(lastHistoryLenRef.current).forEach((entry) => {
        const agent = entry.agent;
        if (!agent) return;
        setChat((prev) => [
          ...prev,
          {
            agent,
            action: entry.action ?? '',
            reasoning: String(entry.reasoning ?? ''),
          },
        ]);
      });
      lastHistoryLenRef.current = history.length;
    }
    setRunMeta((prev) => ({
      ...prev,
      tokens: typeof update.tokens_used === 'number' ? update.tokens_used : prev.tokens,
      cost: typeof update.cost === 'number' ? update.cost : prev.cost,
    }));

    const liveFindings = update.findings;
    if (Array.isArray(liveFindings) && liveFindings.length > 0) {
      setRunFindings(liveFindings as RunFinding[]);
    }
  }

  function beginRun() {
    setBusy(true);
    setRunStatus('running');
    setRunId(null);
    setHistoryRunId(null);
    setRunLog([]);
    setChat([]);
    setRunMeta({});
    setRunFindings([]);
    setRunTrace([]);
    setRunError(null);
    setRunResult(null);
    setConnectionsOn(true);
    setActiveArchetype(null);
    setRunEnded(false);
    lastTraceLenRef.current = 0;
    lastHistoryLenRef.current = 0;
  }

  async function finishRun({ run_id, status }: RunEndSignal) {
    setRunId(run_id);
    setRunStatus(status);
    setRunEnded(true);
    try {
      const report = await getReport(run_id);
      setRunFindings(report.findings);
      setRunTrace(report.trace ?? []);
      setRunError(null);
      setRunMeta((prev) => ({
        ...prev,
        tokens: report.observability.tokens_used ?? prev.tokens,
        cost: report.observability.cost ?? prev.cost,
        target: report.target || prev.target,
        durationMs: report.duration_ms ?? prev.durationMs,
        stopReason: report.observability.stop_reason ?? prev.stopReason,
      }));
    } catch {
      // painel segue mostrando os dados ao vivo
    }
  }

  async function openReport(runNumber: number) {
    setPlayerModalOpen(false);
    setSessionsOpen(false);
    setDashboardOpen(false);
    setHistoryRunId(runNumber);
    setRunStatus(null);
    setRunLog([]);
    setChat([]);
    setRunMeta({});
    setRunFindings([]);
    setRunTrace([]);
    setRunError(null);
    setRunResult(null);
    setRunEnded(true);
    try {
      const report = await getReport(runNumber);
      const trace = report.trace ?? [];
      const history = report.history ?? [];
      setRunStatus(report.status);
      setRunError(null);
      setRunTrace(trace);
      setRunLog(
        trace.map((step) => ({ node: step.node ?? '?', text: formatTraceStep(step) })),
      );
      setChat(
        history.map((entry) => ({
          agent: entry.agent ?? '?',
          action: entry.action ?? '',
          reasoning: String(entry.reasoning ?? ''),
        })),
      );
      setRunFindings(report.findings);
      setRunMeta({
        tokens: report.observability.tokens_used,
        cost: report.observability.cost,
        target: report.target,
        durationMs: report.duration_ms ?? undefined,
        stopReason: report.observability.stop_reason,
      });
    } catch (error) {
      setRunError(error instanceof Error ? error.message : String(error));
    }
  }

  async function handleRun() {
    const archetypes = currentArchetypes();
    if (archetypes.length === 0) {
      setRunResult('Adicione cartas ao grafo antes de executar.');
      return;
    }
    if (activeRun.active) {
      setRunResult(
        `Aguarde o run #${activeRun.run_id} (${activeRun.status}) concluir antes de iniciar outro.`,
      );
      return;
    }
    beginRun();
    try {
      await createComposition({
        name: `Composição ${new Date().toLocaleTimeString('pt-BR')}`,
        archetypes,
        target: enemyInfo.name
          ? { name: enemyInfo.name, url: enemyInfo.url, notes: enemyInfo.notes }
          : null,
        devil_mode: deathMode,
      });

      const params = new URLSearchParams({
        target: enemyInfo.name,
        devil_mode: String(deathMode),
      });
      params.set('archetypes', archetypes.join(','));

      const signal = await runStream(`/runs/stream?${params.toString()}`, ingestEvent, {
        onStart: setRunId,
      });
      await finishRun(signal);
      setRunResult(`Run #${signal.run_id}: ${signal.status}`);
    } catch (error) {
      setRunResult(
        error instanceof Error ? `Erro: ${error.message}` : 'Erro inesperado ao executar.',
      );
    } finally {
      setBusy(false);
      void refreshActiveRun();
    }
  }

  async function executeSession(sessionId: number) {
    if (activeRun.active) {
      throw new Error(
        `Já existe um run ativo (#${activeRun.run_id}, status '${activeRun.status}').`,
      );
    }
    beginRun();
    setPlayerModalOpen(false);
    setSessionsOpen(false);
    try {
      const signal = await runStream(`/runs/stream?session_id=${sessionId}`, ingestEvent, {
        onStart: setRunId,
      });
      await finishRun(signal);
      setRunResult(`Run #${signal.run_id}: ${signal.status}`);
    } catch (error) {
      setRunResult(
        error instanceof Error ? `Erro: ${error.message}` : 'Erro inesperado ao executar.',
      );
      throw error;
    } finally {
      setBusy(false);
      void refreshActiveRun();
    }
  }

  async function handleCancel() {
    if (!runId) return;
    setRunResult(`Cancelando run #${runId}…`);
    try {
      await cancelRun(runId);
    } catch (error) {
      setRunResult(
        error instanceof Error ? `Falha ao cancelar: ${error.message}` : 'Falha ao cancelar.',
      );
    }
  }

  function loadComposition(composition: Composition) {
    setActiveArchetype(null);
    setRunEnded(false);
    const archetypes = composition.config?.archetypes ?? [];
    const idByArchetype: Record<string, number> = {};
    for (const [strId, key] of Object.entries(CARD_ARCHETYPES)) {
      idByArchetype[key] = Number(strId);
    }

    const loaded: CardNodeType[] = archetypes.map((key, index) => {
      const id = idByArchetype[key] ?? index;
      return {
        id: `card-${id}`,
        type: 'card',
        position: { x: 80 + index * 60, y: -80 + (id % 3) * 20 },
        data: { id, onReturn: handleCardReturn },
      };
    });

    setNodes(loaded);
    setEdges([]);
    const target = composition.config?.target;
    setEnemyInfo({
      name: target?.name ?? '',
      url: target?.url ?? '',
      notes: target?.notes ?? '',
    });
    if (composition.config?.devil_mode) {
      setDeathMode(true);
    }
    setRunResult(`Composição "${composition.name}" carregada no grafo.`);
    setSessionsOpen(false);
  }

  if (!loggedIn) {
    return <Login onLogin={() => setLoggedIn(true)} />;
  }

  const activeRunId = runId ?? historyRunId;
  const showRunPanel = busy || activeRunId !== null;
  const readOnlyReport = runId === null && historyRunId !== null;
  const runLocked =
    !busy && activeRun.active && runId === null;

  return (
    <div
      style={{
        backgroundImage: `url(${backgroundImage})`,
        backgroundSize: "cover",
        backgroundPosition: "center",
        backgroundRepeat: "no-repeat",
        backgroundColor: "#000",
        minHeight: "100vh",
        width: "100%",
        position: "relative",
        overflow: "hidden",
      }}
    >
      <CharacterPanel
        onPhotoClick={() => setPlayerModalOpen(true)}
        image={deathMode ? deathImg : undefined}
      />
      <CharacterPanel
        side="enemy"
        name="Alvo"
        onPhotoClick={() => setEnemyModalOpen(true)}
      />
      <Hand
        palette
        onCardPlayed={handleCardPlayed}
        returnedCard={returnedCard}
      />
      <PlayedArea
        nodes={nodes}
        edges={edges}
        composeMode
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={() => undefined}
      />
      <DeathOverlay intensity={deathMode ? 'full' : 'light'} />
      <EndTurnButton
        active={connectionsOn}
        onClick={handleRun}
        disabled={busy || runLocked}
        hint={runLocked ? `Há um run ativo (#${activeRun.run_id}, ${activeRun.status}) — aguarde.` : undefined}
      />
      <div className={`run-result${runResult ? ' is-visible' : ''}${busy ? ' is-busy' : ''}`}>
        {runResult ?? ''}
      </div>
      {showRunPanel && (
        <RunPanel
          runId={activeRunId}
          status={runStatus}
          running={busy}
          log={runLog}
          chat={chat}
          meta={runMeta}
          findings={runFindings}
          trace={runTrace}
          error={runError}
          readonly={readOnlyReport}
          onCancel={() => void handleCancel()}
          onClose={() => {
            setRunId(null);
            setHistoryRunId(null);
          }}
        />
      )}
      <Modal
        open={enemyModalOpen}
        title="Informações do Alvo"
        onClose={() => setEnemyModalOpen(false)}
      >
        <EnemyForm value={enemyInfo} onSave={setEnemyInfo} onClose={() => setEnemyModalOpen(false)} />
      </Modal>
      <Modal
        open={playerModalOpen}
        title="Menu"
        onClose={() => setPlayerModalOpen(false)}
      >
        <div className="modal-menu">
          <button className="modal-menu-item" type="button" onClick={() => {
            setPlayerModalOpen(false);
            setSessionsOpen(true);
          }}>Sessões</button>
          <button className="modal-menu-item" type="button" onClick={() => {
            setPlayerModalOpen(false);
            setDashboardOpen(true);
          }}>Dashboard</button>
          <button
            className="modal-menu-item"
            type="button"
            onClick={() => setDeathMode((prev) => !prev)}
          >
            {deathMode ? 'Modo Normal' : 'Modo Death'}
          </button>
          <button
            className="modal-menu-item"
            type="button"
            onClick={() => {
              setPlayerModalOpen(false);
              setSettingsOpen(true);
            }}
          >
            Configurações
          </button>
          <button className="modal-menu-item" type="button" onClick={() => setLoggedIn(false)}>Sair</button>
        </div>
      </Modal>
      <Modal
        open={settingsOpen}
        title="Configurações"
        onClose={() => setSettingsOpen(false)}
        size="wide"
      >
        <Settings onClose={() => setSettingsOpen(false)} />
      </Modal>
      <Modal
        open={sessionsOpen}
        title="Sessões"
        onClose={() => setSessionsOpen(false)}
        size="wide"
      >
        <Sessions
          onLoad={loadComposition}
          onExecute={executeSession}
          onOpenReport={(runNumber) => void openReport(runNumber)}
        />
      </Modal>
      <Modal
        open={dashboardOpen}
        title="Dashboard"
        onClose={() => setDashboardOpen(false)}
        size="wide"
      >
        <Dashboard onOpenReport={(runNumber) => void openReport(runNumber)} />
      </Modal>
    </div>
  );
}

export default App;