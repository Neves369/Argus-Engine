import { useState } from "react";
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
import { buildTurnPayload, sendTurn } from "./api/turn";

function App() {
  const [loggedIn, setLoggedIn] = useState(false);
  const [enemyModalOpen, setEnemyModalOpen] = useState(false);
  const [playerModalOpen, setPlayerModalOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [sessionsOpen, setSessionsOpen] = useState(false);
  const [connectionsOn, setConnectionsOn] = useState(false);
  const [deathMode, setDeathMode] = useState(false);
  const [enemyInfo, setEnemyInfo] = useState({ name: '', url: '', notes: '' });
  const [playedCards, setPlayedCards] = useState<number[]>([]);
  const [returnedCard, setReturnedCard] = useState<number | undefined>(undefined);

  function handleCardReturn(id: number) {
    setPlayedCards((prev) => prev.filter((cardId) => cardId !== id));
    setReturnedCard(id);
    window.setTimeout(() => setReturnedCard(undefined), 100);
  }

  function handleEndTurn() {
    setConnectionsOn((prev) => !prev);
    const payload = buildTurnPayload(enemyInfo, playedCards);
    void sendTurn(payload).catch((error) => {
      console.error(error);
    });
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
        onCardPlayed={(id) => setPlayedCards((prev) => [...prev, id])}
        returnedCard={returnedCard}
      />
      <PlayedArea
        cards={playedCards}
        connected={connectionsOn}
        onCardReturn={handleCardReturn}
      />
      <DeathOverlay intensity={deathMode ? 'full' : 'light'} />
      <EndTurnButton
        active={connectionsOn}
        onClick={handleEndTurn}
      />
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
