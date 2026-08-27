import { useState, useEffect } from 'react';
import { CARD_IMAGES } from './cardImages';
import Card from './Card';
import './Hand.css';

const CARD_COUNT = 5;
const ARC_ANGLE = 8;
const ARC_LIFT = 16;
const TILT_ANGLE = 6;
const BURN_DURATION = 2000;

interface Particle {
  id: number;
  type: 'flame' | 'soot';
  x: number;
  size: number;
  delay: number;
  duration: number;
}

interface HandProps {
  onCardPlayed?: (id: number) => void;
  returnedCard?: number;
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

function Hand({ onCardPlayed, returnedCard }: HandProps) {
  const [focused, setFocused] = useState<number | null>(null);
  const [cards, setCards] = useState<number[]>(
    Array.from({ length: CARD_COUNT }, (_, i) => i),
  );
  const [burning, setBurning] = useState<Map<number, Particle[]>>(new Map());
  const [appearing, setAppearing] = useState<Set<number>>(new Set());

  useEffect(() => {
    if (returnedCard === undefined || cards.includes(returnedCard)) {
      return;
    }

    const appearTimer = window.setTimeout(() => {
      setCards((prev) => [...prev, returnedCard].sort((a, b) => a - b));
      setAppearing((prev) => new Set(prev).add(returnedCard));
    }, 0);

    const clearTimer = window.setTimeout(() => {
      setAppearing((prev) => {
        const next = new Set(prev);
        next.delete(returnedCard);
        return next;
      });
    }, BURN_DURATION);

    return () => {
      window.clearTimeout(appearTimer);
      window.clearTimeout(clearTimer);
    };
  }, [returnedCard, cards]);

  function handleSelect(id: number) {
    setBurning((prev) => {
      if (prev.has(id)) {
        return prev;
      }
      const next = new Map(prev);
      next.set(id, makeParticles());
      return next;
    });

    window.setTimeout(() => {
      setCards((prev) => prev.filter((cardId) => cardId !== id));
      setBurning((prev) => {
        const next = new Map(prev);
        next.delete(id);
        return next;
      });
      onCardPlayed?.(id);
    }, BURN_DURATION);
  }

  return (
    <div
      className="hand"
      onMouseLeave={() => setFocused(null)}
    >
      {cards.map((id) => {
        const offset = id - (CARD_COUNT - 1) / 2;
        const rotation = offset * ARC_ANGLE;
        const tilt = offset * TILT_ANGLE;
        const lift = Math.abs(offset) * ARC_LIFT;
        const isBurning = burning.has(id);
        const isAppearing = appearing.has(id);
        const particles = burning.get(id);
        const burnSide = offset < 0 ? 'left' : offset > 0 ? 'right' : 'center';

        return (
          <div
            key={id}
            className={`hand-card${focused === id ? ' is-focused' : ''}${isBurning ? ' is-burning' : ''}`}
            style={
              {
                '--rotation': `${rotation}deg`,
                '--lift': `${lift}px`,
                '--tilt': `${tilt}deg`,
              } as React.CSSProperties
            }
            onMouseEnter={() => setFocused(id)}
            onClick={() => handleSelect(id)}
          >
            <Card burning={isBurning} burnSide={burnSide} appearing={isAppearing} image={CARD_IMAGES[id]} />
            {isBurning &&
              particles?.map((particle) => (
                <span
                  key={particle.id}
                  className={`particle particle--${particle.type}`}
                  style={
                    {
                      '--x': `${particle.x}px`,
                      '--size': `${particle.size}px`,
                      '--delay': `${particle.delay}ms`,
                      '--duration': `${particle.duration}ms`,
                    } as React.CSSProperties
                  }
                />
              ))}
          </div>
        );
      })}
    </div>
  );
}

export default Hand;
