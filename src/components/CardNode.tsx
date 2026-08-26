import { memo, useState } from 'react';
import { Handle, Position, type Node, type NodeProps } from '@xyflow/react';
import Card from './Card';
import { CARD_IMAGES } from './cardImages';
import './CardNode.css';

const BURN_DURATION = 2000;
const PLAYED_TILT = 3;
const SLOT_COUNT = 5;

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

export type CardNodeData = {
  id: number;
  onReturn: (id: number) => void;
};

export type CardNodeType = Node<CardNodeData, 'card'>;

function CardNode({ data }: NodeProps<CardNodeType>) {
  const [burning, setBurning] = useState(false);
  const [particles, setParticles] = useState<Particle[]>([]);

  function handleClick() {
    if (burning) return;

    setBurning(true);
    setParticles(makeParticles());

    window.setTimeout(() => {
      setBurning(false);
      setParticles([]);
      data.onReturn(data.id);
    }, BURN_DURATION);
  }

  const offset = data.id - (SLOT_COUNT - 1) / 2;
  const tilt = offset * PLAYED_TILT;
  const burnSide = offset < 0 ? 'left' : offset > 0 ? 'right' : 'center';

  return (
    <>
      <Handle
        type="target"
        position={Position.Left}
        className="card-node-handle"
      />
      <div
        className={`card-node${burning ? ' is-burning' : ''}`}
        style={{ '--tilt': `${tilt}deg` } as React.CSSProperties}
      >
        <Card
          burning={burning}
          burnSide={burnSide}
          appearing={!burning}
          image={CARD_IMAGES[data.id]}
          onClick={handleClick}
        />
        {burning &&
          particles.map((particle) => (
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
      <Handle
        type="source"
        position={Position.Right}
        className="card-node-handle"
      />
    </>
  );
}

export default memo(CardNode);
