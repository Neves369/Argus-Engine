import emperrorImg from '../assets/cards/emperror.jpg';
import towerImg from '../assets/cards/tower.jpg';
import deathImg from '../assets/cards/death.jpg';
import './CharacterPanel.css';

interface CharacterPanelProps {
  name?: string;
  health?: number;
  mana?: number;
  side?: 'ally' | 'enemy';
  onPhotoClick?: () => void;
  image?: string;
}

function CharacterPanel({
  name = 'Nome do Personagem',
  health = 100,
  mana = 100,
  side = 'ally',
  onPhotoClick,
  image,
}: CharacterPanelProps) {
  const defaultImg = side === 'ally' ? emperrorImg : towerImg;

  return (
    <div className={`character-panel character-panel--${side}`}>
      <div
        className={`character-photo${onPhotoClick ? ' is-clickable' : ''}`}
        style={{ backgroundImage: `url(${image ?? defaultImg})` }}
        onClick={onPhotoClick}
      />
    </div>
  );
}

export default CharacterPanel;
