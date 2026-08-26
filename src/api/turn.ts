import { CARD_AGENT_IDS, DEFAULT_SECTIONS } from '../data/agents';

export interface TargetInfo {
  name: string;
  url: string;
  notes: string;
}

const AGENT_NAMES: string[] = (() => {
  const namesById = new Map(
    DEFAULT_SECTIONS.flatMap((section) => section.models).map((model) => [model.id, model.name]),
  );
  return CARD_AGENT_IDS.map((id) => namesById.get(id) ?? id);
})();

export function buildTurnPayload(target: TargetInfo, playedCards: number[]) {
  const agentes: Record<string, boolean> = {};

  AGENT_NAMES.forEach((name, cardId) => {
    agentes[name] = playedCards.includes(cardId);
  });

  return {
    alvo: {
      nome: target.name,
      url: target.url,
      informacoes: target.notes,
    },
    agentes,
  };
}

const API_URL = import.meta.env.VITE_API_URL ?? '/api/turno';

export async function sendTurn(payload: unknown): Promise<void> {
  const response = await fetch(API_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`Erro ao enviar turno: ${response.status}`);
  }
}
