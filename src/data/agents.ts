export interface ModelConfig {
  id: string;
  name: string;
  model: string;
  apiKey: string;
  tokensUsed: number;
  tokensLimit: number;
  cost: number;
  enabled: boolean;
}

export interface SettingsSection {
  id: string;
  title: string;
  description?: string;
  models: ModelConfig[];
}

export const CARD_AGENT_IDS = [
  'fool',
  'hermit',
  'chariot',
  'justice',
  'mage',
] as const;

export const DEFAULT_SECTIONS: SettingsSection[] = [
  {
    id: 'agents',
    title: 'Agentes',
    models: [
      {
        id: 'fool',
        name: 'O Louco',
        model: 'gpt-4o',
        apiKey: 'sk-proj-louco-0000',
        tokensUsed: 124_800,
        tokensLimit: 1_000_000,
        cost: 1.87,
        enabled: true,
      },
      {
        id: 'hermit',
        name: 'O Eremita',
        model: 'claude-3-5-sonnet',
        apiKey: 'sk-ant-eremita-1111',
        tokensUsed: 512_300,
        tokensLimit: 1_000_000,
        cost: 7.68,
        enabled: true,
      },
      {
        id: 'chariot',
        name: 'O Carro',
        model: 'gemini-1.5-pro',
        apiKey: 'AIza-carro-2222',
        tokensUsed: 43_120,
        tokensLimit: 500_000,
        cost: 0.54,
        enabled: false,
      },
      {
        id: 'justice',
        name: 'A Justiça',
        model: 'gpt-4o-mini',
        apiKey: 'sk-proj-justica-3333',
        tokensUsed: 98_760,
        tokensLimit: 2_000_000,
        cost: 0.74,
        enabled: true,
      },
      {
        id: 'mage',
        name: 'O Mago',
        model: 'claude-3-opus',
        apiKey: 'sk-ant-mago-4444',
        tokensUsed: 765_410,
        tokensLimit: 1_500_000,
        cost: 22.96,
        enabled: true,
      },
    ],
  },
  {
    id: 'auxiliary',
    title: 'Modelos de auxílio',
    description: 'Modelos abliterados e com menos restrições',
    models: [
      {
        id: 'dolphin',
        name: 'Dolphin',
        model: 'dolphin-mixtral-8x7b',
        apiKey: 'sk-dolphin-aaaa',
        tokensUsed: 210_500,
        tokensLimit: 1_000_000,
        cost: 3.15,
        enabled: true,
      },
      {
        id: 'abliterated',
        name: 'Llama Abliterated',
        model: 'llama-3.1-8b-abliterated',
        apiKey: 'sk-abliterated-bbbb',
        tokensUsed: 89_240,
        tokensLimit: 1_000_000,
        cost: 1.11,
        enabled: true,
      },
      {
        id: 'hermes',
        name: 'Hermes',
        model: 'hermes-2-pro',
        apiKey: 'sk-hermes-cccc',
        tokensUsed: 341_870,
        tokensLimit: 1_000_000,
        cost: 4.62,
        enabled: false,
      },
    ],
  },
];
