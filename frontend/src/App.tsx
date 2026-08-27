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
import { createComposition, executeComposition, getRun } from "./api/client";
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

  function handleCardPlayed(id: number) {
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
    setNodes((prev) => prev.filter((node) => node.id !== `card-${id}`));
    setEdges((prev) => prev.filter((e) => e.source !== `card-${id}` && e.target !== `card-${id}`));
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
    try {
      const composition = await createComposition({
        name: `Composição ${new Date().toLocaleTimeString('pt-BR')}`,
        archetypes,
        target: enemyInfo.name ? { name: enemyInfo.name, url: enemyInfo.url, notes: enemyInfo.notes } : null,
        devil_mode: deathMode,
      });
      const exec = await executeComposition(composition.id);
      const run = await getRun(exec.run_id);
      const result = run.result as
        | { findings?: unknown[]; stop_reason?: string; next_agent?: string }
        | undefined;
      const findings = result?.findings?.length ?? 0;
      const stopReason = result?.stop_reason ?? run.status;
      const nextAgent = result?.next_agent ? ` · próximo: ${result.next_agent}` : '';
      setRunResult(`Run #${exec.run_id}: ${run.status} · achados ${findings} · parada: ${stopReason}${nextAgent}`);
    } catch (error) {
      setRunResult(
        error instanceof Error ? `Erro: ${error.message}` : 'Erro inesperado ao executar.',
      );
    } finally {
      setBusy(false);
    }
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
        <Sessions />
      </Modal>
    </div>
  );
}

export default App;
