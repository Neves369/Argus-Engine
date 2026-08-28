import { useEffect, useState } from "react";
import { useEdgesState, useNodesState, type Edge } from "@xyflow/react";
import backgroundImage from "./assets/backgrounds/Background1.png";
import deathImg from "./assets/cards/death.jpg";
import CharacterPanel from "./components/CharacterPanel";
import DeathOverlay from "./components/DeathOverlay";
import EndTurnButton from "./components/EndTurnButton";
import EnemyForm from "./components/EnemyForm";
import Hand from "./components/Hand";
import Login from "./components/Login";
import Modal from "./components/Modal";
import PlayedArea from "./components/PlayedArea";
import Sessions from "./components/Sessions";
import Settings from "./components/Settings";
import {
  createComposition,
  getRun,
  streamRun,
  type Composition,
} from "./api/client";
import type { CardNodeType } from "./components/CardNode";
import { CARD_ARCHETYPES } from "./data/agents";
import "./App.css";

function App() {
  const [loggedIn, setLoggedIn] = useState(false);
  const [enemyModalOpen, setEnemyModalOpen] = useState(false);
  const [playerModalOpen, setPlayerModalOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [sessionsOpen, setSessionsOpen] = useState(false);
  const [connectionsOn, setConnectionsOn] = useState(false);
  const [deathMode, setDeathMode] = useState(false);
  const [enemyInfo, setEnemyInfo] = useState({ name: '', url: '', notes: '' });
  const [returnedCard, setReturnedCard] = useState<number | undefined>(undefined);
  const [runResult, setRunResult] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [activeArchetype, setActiveArchetype] = useState<string | null>(null);
  const [runEnded, setRunEnded] = useState(false);

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

  async function handleRun() {
    const archetypes = currentArchetypes();
    if (archetypes.length === 0) {
      setRunResult('Adicione cartas ao grafo antes de executar.');
      return;
    }
    setBusy(true);
    setRunResult('Salvando composição e iniciando execução…');
    setConnectionsOn(true);
    setActiveArchetype(null);
    setRunEnded(false);
    try {
      await createComposition({
        name: `Composição ${new Date().toLocaleTimeString('pt-BR')}`,
        archetypes,
        target: enemyInfo.name ? { name: enemyInfo.name, url: enemyInfo.url, notes: enemyInfo.notes } : null,
        devil_mode: deathMode,
      });

      const runId = await new Promise<number>((resolve, reject) => {
        let settled = false;
        let id = 0;
        const stop = streamRun(
          enemyInfo.name,
          deathMode,
          archetypes,
          (event) => {
            setActiveArchetype(event.node);
          },
          (rid, status) => {
            id = rid;
            settled = true;
            stop();
            if (status === 'failed') {
              reject(new Error('Run falhou'));
            } else {
              resolve(id);
            }
          },
        );
        window.setTimeout(() => {
          if (!settled) {
            stop();
            reject(new Error('Tempo esgotado ao executar o run'));
          }
        }, 60000);
      });

      setRunEnded(true);
      const run = await getRun(runId);
      const result = run.result as
        | { findings?: unknown[]; stop_reason?: string; next_agent?: string }
        | undefined;
      const findings = result?.findings?.length ?? 0;
      const stopReason = result?.stop_reason ?? run.status;
      const nextAgent = result?.next_agent ? ` · próximo: ${result.next_agent}` : '';
      setRunResult(`Run #${runId}: ${run.status} · achados ${findings} · parada: ${stopReason}${nextAgent}`);
    } catch (error) {
      setRunResult(
        error instanceof Error ? `Erro: ${error.message}` : 'Erro inesperado ao executar.',
      );
    } finally {
      setBusy(false);
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
      />
      <div className={`run-result${runResult ? ' is-visible' : ''}${busy ? ' is-busy' : ''}`}>
        {runResult ?? ''}
      </div>
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
        <Sessions onLoad={loadComposition} />
      </Modal>
    </div>
  );
}

export default App;
