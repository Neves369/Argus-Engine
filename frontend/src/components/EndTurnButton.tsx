import './EndTurnButton.css';

interface EndTurnButtonProps {
  onClick?: () => void;
  active?: boolean;
  disabled?: boolean;
  hint?: string;
}

function EndTurnButton({ onClick, active = false, disabled = false, hint }: EndTurnButtonProps) {
  return (
    <button
      type="button"
      className={`end-turn-button${active ? ' is-active' : ''}${disabled ? ' is-disabled' : ''}`}
      onClick={onClick}
      disabled={disabled}
      title={hint}
    >
      <span className="end-turn-ornament" aria-hidden="true">
        ✦
      </span>
      Finalizar Turno
      <span className="end-turn-ornament" aria-hidden="true">
        ✦
      </span>
    </button>
  );
}

export default EndTurnButton;