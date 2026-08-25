import './CharacterPanel.css';

interface CharacterPanelProps {
  name?: string;
  health?: number;
  mana?: number;
  side?: 'ally' | 'enemy';
  onPhotoClick?: () => void;
}

function CharacterPanel({
  name = 'Nome do Personagem',
  health = 100,
  mana = 100,
  side = 'ally',
  onPhotoClick,
}: CharacterPanelProps) {
  return (
    <div className={`character-panel character-panel--${side}`}>
      <div
        className={`character-photo${onPhotoClick ? ' is-clickable' : ''}`}
        onClick={onPhotoClick}
      />
      <div className="character-info">
        <div className="character-name">{name}</div>
        <div className="character-bars">
          <div className="bar bar-health">
            <div className="bar-fill" style={{ width: `${health}%` }} />
          </div>
          <div className="bar bar-mana">
            <div className="bar-fill" style={{ width: `${mana}%` }} />
          </div>
        </div>
      </div>
    </div>
  );
}

export default CharacterPanel;
