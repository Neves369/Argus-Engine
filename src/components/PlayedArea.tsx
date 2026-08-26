import { useState } from 'react';
import { CARD_IMAGES } from './cardImages';
import Card from './Card';
import './PlayedArea.css';

const SLOT_COUNT = 5;
const PLAYED_TILT = 3;
const BURN_DURATION = 2000;

interface Particle {
  id: number;
  type: 'flame' | 'soot';
  x: number;
  size: number;
  delay: number;
  duration: number;
}

let particleId = 0;

function random(min: number, max: number) {
  return min + Math.random() * (max - min);
}

function makeParticles(): Particle[] {
  const flames = Array.from({ length: 28 }, () => ({
    id: particleId++,
    type: 'flame' as const,
    x: random(-55, 55),
    size: random(3, 7),
    delay: random(0, 700),
    duration: random(900, 1600),
  }));

  const soot = Array.from({ length: 20 }, () => ({
    id: particleId++,
    type: 'soot' as const,
    x: random(-65, 65),
    size: random(2, 5),
    delay: random(0, 900),
    duration: random(1500, 2300),
  }));

  return [...flames, ...soot];
}

interface PlayedAreaProps {
  cards: number[];
  onCardReturn?: (id: number) => void;
}

function PlayedArea({ cards, onCardReturn }: PlayedAreaProps) {
  const [burningSlot, setBurningSlot] = useState<number | null>(null);
  const [particles, setParticles] = useState<Particle[]>([]);

  function handleClick(slot: number) {
    if (burningSlot !== null) return;

    setBurningSlot(slot);
    setParticles(makeParticles());

    window.setTimeout(() => {
      setBurningSlot(null);
      setParticles([]);
      onCardReturn?.(slot);
    }, BURN_DURATION);
  }

  return (
    <div className="played-area">
      {Array.from({ length: SLOT_COUNT }, (_, slot) => {
        const played = cards.includes(slot);
        const offset = slot - (SLOT_COUNT - 1) / 2;
        const tilt = offset * PLAYED_TILT;
        const isBurning = burningSlot === slot;
        const burnSide = offset < 0 ? 'left' : offset > 0 ? 'right' : 'center';

        return (
          <div
            key={slot}
            className={`played-slot${isBurning ? ' is-burning' : ''}`}
            style={{ '--tilt': `${tilt}deg` } as React.CSSProperties}
          >
            {played && (
              <>
                <Card
                  appearing={!isBurning}
                  burning={isBurning}
                  burnSide={burnSide}
                  image={CARD_IMAGES[slot]}
                  onClick={() => handleClick(slot)}
                />
                {isBurning &&
                  particles.map((p) => (
                    <span
                      key={p.id}
                      className={`particle particle--${p.type}`}
                      style={
                        {
                          '--x': `${p.x}px`,
                          '--size': `${p.size}px`,
                          '--delay': `${p.delay}ms`,
                          '--duration': `${p.duration}ms`,
                        } as React.CSSProperties
                      }
                    />
                  ))}
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default PlayedArea;
