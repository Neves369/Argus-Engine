import { useState } from "react";
import backgroundImage from "./assets/backgrounds/Background1.png";
import CharacterPanel from "./components/CharacterPanel";
import EnemyForm from "./components/EnemyForm";
import Hand from "./components/Hand";
import Modal from "./components/Modal";
import PlayedArea from "./components/PlayedArea";

function App() {
  const [enemyModalOpen, setEnemyModalOpen] = useState(false);
  const [playedCards, setPlayedCards] = useState<number[]>([]);

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
      <CharacterPanel />
      <CharacterPanel
        side="enemy"
        name="Alvo"
        onPhotoClick={() => setEnemyModalOpen(true)}
      />
      <Hand onCardPlayed={(id) => setPlayedCards((prev) => [...prev, id])} />
      <PlayedArea cards={playedCards} />
      <Modal
        open={enemyModalOpen}
        title="Informações do Alvo"
        onClose={() => setEnemyModalOpen(false)}
      >
        <EnemyForm />
      </Modal>
    </div>
  );
}

export default App;
