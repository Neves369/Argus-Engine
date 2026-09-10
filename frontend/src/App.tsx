import { useEffect, useRef, useState } from "react";
import { useEdgesState, useNodesState, type Edge } from "@xyflow/react";
import { AnimatePresence, motion } from "framer-motion";
import backgroundImage from "./assets/backgrounds/Background1.png";
import deathImg from "./assets/cards/death.jpg";
import CharacterPanel from "./components/CharacterPanel";
import Dashboard from "./components/Dashboard";
import DeathOverlay from "./components/DeathOverlay";
import EndTurnButton from "./components/EndTurnButton";
import NewSessionButton from "./components/NewSessionButton";
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
  logout,
  reviewRun,
  runStream,
  type ActiveRunInfo,
  type Composition,
  type HistoryEntry,
  type PendingReview,
  type ReviewPayload,
  type RunDecision,
  type RunFinding,
  type RunLogLine,
  type RunMeta,
  type StreamEvent,
  type RunEndSignal,
  type Report,
} from "./api/client";
import type { CardNodeType } from "./components/CardNode";
import { CARD_AGENT_IDS } from "./data/agents";
import { useUIStore, type UIModal } from "./store/ui";
import "./App.css";

const IMPERIAL_TEAM_CARDS: ReadonlyArray<{ id: number; key: string }> = [
  { id: 0, key: "fool" },
  { id: 1, key: "hermit" },
  { id: 4, key: "magician" },
  { id: 3, key: "justice" },
];
const IMPERIAL_TEAM_ARCHETYPES = IMPERIAL_TEAM_CARDS.map((card) => card.key);

function formatLogEntry(entry: HistoryEntry): string {
  const parts: string[] = [];
  if (entry.action) parts.push(String(entry.action));
  if (entry.reasoning != null && String(entry.reasoning).trim() !== "") {
    parts.push(String(entry.reasoning));
  }
  return parts.join(" — ");
}

function App() {
  const [loggedIn, setLoggedIn] = useState(false);
  const playerModalOpen = useUIStore((s) => s.playerModalOpen);
  const enemyModalOpen = useUIStore((s) => s.enemyModalOpen);
  const settingsOpen = useUIStore((s) => s.settingsOpen);
  const sessionsOpen = useUIStore((s) => s.sessionsOpen);
  const dashboardOpen = useUIStore((s) => s.dashboardOpen);
  const runResult = useUIStore((s) => s.runResult);
  const busy = useUIStore((s) => s.busy);
  const {
    openModal,
    closeAllModals,
    closePlayer,
    setEnemyModalOpen,
    setSettingsOpen,
    setSessionsOpen,
    setDashboardOpen,
    setRunResult,
    setBusy,
  } = useUIStore.getState();

  function openModalExclusive(name: UIModal) {
    setRunPanelOpen(false);
    openModal(name);
  }
  const [connectionsOn, setConnectionsOn] = useState(false);
  const [deathMode, setDeathMode] = useState(false);
  const [enemyInfo, setEnemyInfo] = useState({ name: '', url: '', notes: '' });
  const [returnedCard, setReturnedCard] = useState<number | undefined>(undefined);
  const [activeArchetype, setActiveArchetype] = useState<string | null>(null);
  const [runEnded, setRunEnded] = useState(false);
  const [runPanelOpen, setRunPanelOpen] = useState(false);
  const [activeRun, setActiveRun] = useState<ActiveRunInfo>({
    active: false,
    run_id: null,
    status: null,
  });
  const [runId, setRunId] = useState<number | null>(null);
  const [historyRunId, setHistoryRunId] = useState<number | null>(null);
  const [runStatus, setRunStatus] = useState<string | null>(null);
  const [runLog, setRunLog] = useState<RunLogLine[]>([]);
  const [runDecisions, setRunDecisions] = useState<RunDecision[]>([]);
  const [runMeta, setRunMeta] = useState<RunMeta>({});
  const [runFindings, setRunFindings] = useState<RunFinding[]>([]);
  const [runPendingReview, setRunPendingReview] = useState<PendingReview | null>(null);
  const [runReviewing, setRunReviewing] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

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
        const isActive = CARD_AGENT_IDS[node.data.id] === activeArchetype;
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

  useEffect(() => {
    let saved: string | null = null;
    try {
      saved = localStorage.getItem('argus.lastRunId');
    } catch {
      // localStorage indisponível; ignora
    }
    if (saved && /^\d+$/.test(saved)) {
      void openReport(Number(saved));
    }
    // Restaura o último run exibido ao recarregar a página (F5).
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

  function handleNewSession() {
    const hasSomethingToLose =
      nodes.length > 0 || runId !== null || historyRunId !== null || enemyInfo.name.trim() !== '';
    if (hasSomethingToLose) {
      const confirmed = window.confirm(
        'Iniciar uma nova sessão? Isso limpa o alvo, as cartas jogadas e o relatório atual.',
      );
      if (!confirmed) return;
    }

    setNodes([]);
    setEdges([]);
    setActiveArchetype(null);
    setRunEnded(false);
    setEnemyInfo({ name: '', url: '', notes: '' });
    setRunId(null);
    setHistoryRunId(null);
    setRunPanelOpen(false);
    setRunStatus(null);
    setRunLog([]);
    setRunDecisions([]);
    setRunMeta({});
    setRunFindings([]);
    setRunPendingReview(null);
    setRunError(null);
    setRunResult(null);
    lastHistoryLenRef.current = 0;
    try {
      localStorage.removeItem('argus.lastRunId');
    } catch {
      // localStorage indisponível; ignora
    }
  }

  function currentArchetypes(): string[] {
    const sorted = [...nodes].sort((a, b) => a.position.x - b.position.x);
    return sorted.map((node) => CARD_AGENT_IDS[node.data.id]);
  }

  function ingestEvent(event: StreamEvent): void {
    const update = event.update ?? {};
    const history = (update.history as HistoryEntry[] | undefined) ?? [];
    if (history.length > lastHistoryLenRef.current) {
      history.slice(lastHistoryLenRef.current).forEach((entry) => {
        setRunLog((prev) => [
          ...prev,
          { node: entry.agent ?? event.node, text: formatLogEntry(entry) },
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
    setRunPanelOpen(true);
    setRunId(null);
    setHistoryRunId(null);
    setRunLog([]);
    setRunDecisions([]);
    setRunMeta({});
    setRunFindings([]);
    setRunPendingReview(null);
    setRunReviewing(false);
    setRunError(null);
    setRunResult(null);
    setConnectionsOn(true);
    setActiveArchetype(null);
    setRunEnded(false);
    lastHistoryLenRef.current = 0;
  }

  async function finishRun({ run_id, status }: RunEndSignal) {
    setRunId(run_id);
    setRunStatus(status);
    setRunEnded(true);
    try {
      localStorage.setItem('argus.lastRunId', String(run_id));
    } catch {
      // localStorage pode ser indisponível; ignora
    }
    try {
      const report = await getReport(run_id);
      applyReport(report);
    } catch {
      // painel segue mostrando os dados ao vivo
    }
  }

  function applyReport(report: Report) {
    setRunFindings(report.findings);
    setRunError(null);
    setRunStatus(report.status);
    setRunPendingReview(report.pending_review ?? null);
    setRunMeta((prev) => ({
      ...prev,
      tokens: report.observability.tokens_used ?? prev.tokens,
      cost: report.observability.cost ?? prev.cost,
      target: report.target || prev.target,
      durationMs: report.duration_ms ?? prev.durationMs,
      stopReason: report.observability.stop_reason ?? prev.stopReason,
    }));
  }
function seedReport(report: Report) {
    setRunLog(
      (report.history ?? []).map((entry) => ({
        node: entry.agent ?? '?',
        text: formatLogEntry(entry),
      })),
    );
    lastHistoryLenRef.current = (report.history ?? []).length;
  }

  async function openReport(runNumber: number) {
    closeAllModals();
    setHistoryRunId(runNumber);
    setRunPanelOpen(true);
    try {
      localStorage.setItem('argus.lastRunId', String(runNumber));
    } catch {
      // localStorage pode ser indisponível; ignora
    }
    setRunStatus(null);
    setRunLog([]);
    setRunDecisions([]);
    setRunMeta({});
    setRunFindings([]);
    setRunPendingReview(null);
    setRunError(null);
    setRunResult(null);
    setRunEnded(true);
    try {
      const report = await getReport(runNumber);
      seedReport(report);
      applyReport(report);
    } catch (error) {
      setRunError(error instanceof Error ? error.message : String(error));
    }
  }
  async function handleReview(approved: boolean, note: string) {
    if (runId == null || runPendingReview == null) return;
    setRunReviewing(true);
    try {
      const payload: ReviewPayload = {
        approval_id: runPendingReview.id,
        approved,
        note: note || undefined,
      };
      await reviewRun(runId, payload);
      setRunDecisions((prev) => [
        ...prev,
        {
          id: runPendingReview.id,
          kind: runPendingReview.kind,
          context: runPendingReview.context ?? undefined,
          approved,
          note: note || '',
        },
      ]);
      const report = await getReport(runId);
      applyReport(report);
    } catch (error) {
      setRunError(error instanceof Error ? error.message : String(error));
    } finally {
      setRunReviewing(false);
    }
  }

  function placeImperialTeam() {
    setActiveArchetype(null);
    setRunEnded(false);
    setNodes(
      IMPERIAL_TEAM_CARDS.map((card, index): CardNodeType => ({
        id: `card-${card.id}`,
        type: 'card',
        position: { x: 80 + index * 60, y: -100 + (card.id % 3) * 20 },
        data: { id: card.id, onReturn: handleCardReturn },
      })),
    );
  }

  async function handleRun() {
    const archetypes = currentArchetypes();
    const imperialTurn = archetypes.length === 0;
    if (activeRun.active) {
      setRunResult(
        `Aguarde o run #${activeRun.run_id} (${activeRun.status}) concluir antes de iniciar outro.`,
      );
      return;
    }
    beginRun();
    try {
      // Supervisor universal: sem cartas o Imperador escala o time padrão —
      // as cartas vão ao tabuleiro como se ele as tivesse jogado. Com cartas
      // ele escala apenas as escolhidas (a composição é salva).
      if (imperialTurn) {
        placeImperialTeam();
        setRunResult("O Imperador escalou o time padrão para este turno.");
      } else {
        await createComposition({
          name: `Composição ${new Date().toLocaleTimeString('pt-BR')}`,
          archetypes,
          target: enemyInfo.name
            ? { name: enemyInfo.name, url: enemyInfo.url, notes: enemyInfo.notes }
            : null,
          devil_mode: deathMode,
        });
      }

      const params = new URLSearchParams({
        target: enemyInfo.name,
        devil_mode: String(deathMode),
      });
      params.set(
        'archetypes',
        (imperialTurn ? IMPERIAL_TEAM_ARCHETYPES : archetypes).join(','),
      );

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
    closeAllModals();
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

  async function handleLogout() {
    try {
      await logout();
    } catch {
      // ignora falha de logout; encerra a sessão local mesmo assim
    }
    setLoggedIn(false);
  }

  function loadComposition(composition: Composition) {
    setActiveArchetype(null);
    setRunEnded(false);
    const archetypes = composition.config?.archetypes ?? [];
    const idByArchetype: Record<string, number> = {};
    for (const [strId, key] of Object.entries(CARD_AGENT_IDS)) {
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
  const showRunPanel = busy || (runPanelOpen && activeRunId !== null);
  const readOnlyReport = runId === null && historyRunId !== null;
  const runLocked =
    !busy && activeRun.active && runId === null;

  return (
    <div
      className="select-none"
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
        onPhotoClick={() => openModalExclusive('player')}
        image={deathMode ? deathImg : undefined}
      />
      <CharacterPanel
        side="enemy"
        name="Alvo"
        onPhotoClick={() => openModalExclusive('enemy')}
      />
      <Hand
        palette
        onCardPlayed={handleCardPlayed}
        returnedCard={returnedCard}
        playedCards={nodes.map((node) => node.data.id)}
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
      <button
        type="button"
        className={`run-panel-toggle${showRunPanel ? ' is-open' : ''}`}
        aria-pressed={showRunPanel}
        title="Resultados e logs do run"
        onClick={() => {
          if (showRunPanel) {
            setRunPanelOpen(false);
            return;
          }
          if (activeRunId !== null) {
            closeAllModals();
            setRunPanelOpen(true);
            return;
          }
          let last: string | null = null;
          try {
            last = localStorage.getItem('argus.lastRunId');
          } catch {
            // localStorage indisponível; ignora
          }
          if (last && /^\d+$/.test(last)) {
            void openReport(Number(last));
          }
        }}
      >
        ☰ Resultados
      </button>
      <NewSessionButton
        onClick={handleNewSession}
        disabled={busy || runLocked}
        hint={
          runLocked
            ? `Há um run ativo (#${activeRun.run_id}, ${activeRun.status}) — aguarde para iniciar uma nova sessão.`
            : undefined
        }
      />
      <EndTurnButton
        active={connectionsOn}
        onClick={handleRun}
        disabled={busy || runLocked}
        hint={runLocked ? `Há um run ativo (#${activeRun.run_id}, ${activeRun.status}) — aguarde.` : undefined}
      />
      <AnimatePresence>
        {runResult && (
          <motion.div
            key="run-result"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 12 }}
            transition={{ duration: 0.18 }}
            className={`run-result is-visible${busy ? ' is-busy' : ''}`}
          >
            {runResult}
          </motion.div>
        )}
      </AnimatePresence>
      <AnimatePresence>
        {showRunPanel && (
          <motion.div
            key="run-panel"
            initial={{ opacity: 0, x: 40 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 40 }}
            transition={{ duration: 0.22, ease: 'easeOut' }}
          >
            <RunPanel
              runId={activeRunId}
              status={runStatus}
              running={busy}
              log={runLog}
              decisions={runDecisions}
              meta={runMeta}
              findings={runFindings}
              error={runError}
              pendingReview={runPendingReview}
              reviewing={runReviewing}
              readonly={readOnlyReport}
              onReview={(approved, note) => void handleReview(approved, note)}
              onCancel={() => void handleCancel()}
              onClose={() => setRunPanelOpen(false)}
            />
          </motion.div>
        )}
      </AnimatePresence>
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
        onClose={() => closePlayer()}
      >
        <div className="modal-menu">
          <button className="modal-menu-item" type="button" onClick={() => openModalExclusive('sessions')}>
            Sessões</button>
          <button className="modal-menu-item" type="button" onClick={() => openModalExclusive('dashboard')}>
            Dashboard</button>
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
            onClick={() => openModalExclusive('settings')}
          >
            Configurações
          </button>
          <button className="modal-menu-item" type="button" onClick={() => void handleLogout()}>
            Sair
          </button>
        </div>
      </Modal>
      <Modal
        open={settingsOpen}
        title="Configurações"
        onClose={() => setSettingsOpen(false)}
        size="wide"
      >
        <Settings
          onClose={() => setSettingsOpen(false)}
          onSessionInvalidated={() => {
            setSettingsOpen(false);
            void handleLogout();
          }}
        />
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
          onSelectTarget={(target) => {
            setEnemyInfo({ name: target.name, url: target.url ?? '', notes: target.notes ?? '' });
            setSessionsOpen(false);
          }}
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