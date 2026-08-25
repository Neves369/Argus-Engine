import Card from './Card';
import './PlayedArea.css';

const SLOT_COUNT = 5;
const PLAYED_TILT = 9;

interface PlayedAreaProps {
  cards: number[];
}

function PlayedArea({ cards }: PlayedAreaProps) {
  return (
    <div className="played-area">
      {Array.from({ length: SLOT_COUNT }, (_, slot) => {
        const played = cards.includes(slot);
        const offset = slot - (SLOT_COUNT - 1) / 2;
        const tilt = offset * PLAYED_TILT;

        return (
          <div
            key={slot}
            className="played-slot"
            style={{ '--tilt': `${tilt}deg` } as React.CSSProperties}
          >
            {played && <Card appearing />}
          </div>
        );
      })}
    </div>
  );
}

export default PlayedArea;
