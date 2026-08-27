import './EndTurnButton.css';

interface EndTurnButtonProps {
  onClick?: () => void;
  active?: boolean;
}

function EndTurnButton({ onClick, active = false }: EndTurnButtonProps) {
  return (
    <button
      type="button"
      className={`end-turn-button${active ? ' is-active' : ''}`}
      onClick={onClick}
    >
      <span className="end-turn-ornament" aria-hidden="true">✦</span>
      Finalizar Turno
      <span className="end-turn-ornament" aria-hidden="true">✦</span>
    </button>
  );
}

export default EndTurnButton;
