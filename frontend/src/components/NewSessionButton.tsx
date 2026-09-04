import './NewSessionButton.css';

interface NewSessionButtonProps {
  onClick?: () => void;
  disabled?: boolean;
  hint?: string;
}

function NewSessionButton({ onClick, disabled = false, hint }: NewSessionButtonProps) {
  return (
    <button
      type="button"
      className={`new-session-button${disabled ? ' is-disabled' : ''}`}
      onClick={onClick}
      disabled={disabled}
      title={hint ?? 'Limpar alvo, cartas e relatório atual para começar do zero'}
    >
      <span className="new-session-ornament" aria-hidden="true">
        ↺
      </span>
      Nova Sessão
    </button>
  );
}

export default NewSessionButton;
