import { useEffect, useMemo, useState } from 'react';
import {
  ReactFlow,
  type Edge,
  type ReactFlowInstance,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import CardNode, { type CardNodeType } from './CardNode';
import './PlayedArea.css';

const CARD_WIDTH = 110;
const CARD_HEIGHT = 200;
const GAP = 60;
const STEP = CARD_WIDTH + GAP;

const nodeTypes = { card: CardNode };

interface PlayedAreaProps {
  cards: number[];
  connected: boolean;
  onCardReturn?: (id: number) => void;
}

function PlayedArea({ cards, connected, onCardReturn }: PlayedAreaProps) {
  const [instance, setInstance] = useState<ReactFlowInstance | null>(null);

  const nodes: CardNodeType[] = useMemo(() => {
    return cards.map((id, index) => ({
      id: `card-${id}`,
      type: 'card',
      position: {
        x: (index - (cards.length - 1) / 2) * STEP,
        y: -CARD_HEIGHT / 2,
      },
      data: { id, onReturn: onCardReturn ?? (() => {}) },
    }));
  }, [cards, onCardReturn]);

  const edges: Edge[] = useMemo(() => {
    if (!connected) return [];

    const sorted = [...cards].sort((a, b) => a - b);
    const result: Edge[] = [];

    for (let i = 0; i < sorted.length - 1; i++) {
      result.push({
        id: `edge-${sorted[i]}-${sorted[i + 1]}`,
        source: `card-${sorted[i]}`,
        target: `card-${sorted[i + 1]}`,
        type: 'smoothstep',
        animated: true,
        style: { stroke: '#c084fc', strokeWidth: 3 },
      });
    }

    return result;
  }, [cards, connected]);

  useEffect(() => {
    if (instance) {
      void instance.fitView({ padding: 0.4, maxZoom: 1 });
    }
  }, [cards, instance]);

  return (
    <div className="played-area-flow">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onInit={setInstance}
        nodesDraggable={false}
        nodesConnectable={false}
        nodesFocusable={false}
        edgesFocusable={false}
        elementsSelectable={false}
        panOnDrag={false}
        zoomOnScroll={false}
        zoomOnPinch={false}
        zoomOnDoubleClick={false}
        preventScrolling
        fitView
        fitViewOptions={{ padding: 0.4, maxZoom: 1 }}
        proOptions={{ hideAttribution: true }}
      />
    </div>
  );
}

export default PlayedArea;
