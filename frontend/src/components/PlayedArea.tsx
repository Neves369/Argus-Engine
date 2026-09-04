import { useEffect, useState } from 'react';
import {
  ReactFlow,
  type Edge,
  type OnConnect,
  type OnEdgesChange,
  type OnNodesChange,
  type ReactFlowInstance,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import CardNode, { type CardNodeType } from './CardNode';
import './PlayedArea.css';

const nodeTypes = { card: CardNode };

interface PlayedAreaProps {
  nodes: CardNodeType[];
  edges: Edge[];
  composeMode: boolean;
  onNodesChange: OnNodesChange<CardNodeType>;
  onEdgesChange: OnEdgesChange;
  onConnect: OnConnect;
}

function PlayedArea({
  nodes,
  edges,
  composeMode,
  onNodesChange,
  onEdgesChange,
  onConnect,
}: PlayedAreaProps) {
  const [instance, setInstance] = useState<ReactFlowInstance<CardNodeType, Edge> | null>(null);

  useEffect(() => {
    if (instance && nodes.length > 0) {
      void instance.fitView({ padding: 0.4, maxZoom: 1 });
    }
  }, [nodes, instance]);

  return (
    <div className="played-area-flow">
      <ReactFlow<CardNodeType, Edge>
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onInit={setInstance}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        nodesDraggable={composeMode}
        nodesConnectable={composeMode}
        nodesFocusable={composeMode}
        edgesFocusable={composeMode}
        elementsSelectable={composeMode}
        panOnDrag={composeMode}
        zoomOnScroll={composeMode}
        zoomOnPinch={composeMode}
        zoomOnDoubleClick={composeMode}
        preventScrolling
        fitView={!composeMode}
        fitViewOptions={{ padding: 0.4, maxZoom: 1 }}
        proOptions={{ hideAttribution: true }}
      />
    </div>
  );
}

export default PlayedArea;
