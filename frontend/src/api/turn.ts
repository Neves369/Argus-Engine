import { streamRun } from './client';

export interface TargetInfo {
  name: string;
  url: string;
  notes: string;
}

export function sendTurn(
  target: TargetInfo,
  devilMode: boolean,
  archetypes: string[] = [],
): Promise<void> {
  const name = target.name.trim();
  if (!name) {
    return Promise.reject(new Error('Nome do alvo é obrigatório'));
  }

  return new Promise<void>((resolve, reject) => {
    let settled = false;

    const stop = streamRun(
      name,
      devilMode,
      archetypes,
      (event) => {
        console.info(`[${event.node}]`, event.update);
      },
      (_runId, status) => {
        settled = true;
        stop();
        if (status === 'failed') {
          reject(new Error('Run falhou'));
        } else {
          resolve();
        }
      },
    );

    window.setTimeout(() => {
      if (!settled) {
        stop();
        reject(new Error('Tempo esgotado ao executar o run'));
      }
    }, 60000);
  });
}
