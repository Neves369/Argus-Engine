import { mkdir } from 'node:fs/promises';

// Garante que o diretório de estado E2E existe. A limpeza é feita pelo script
// `npm run e2e` ANTES do Playwright subir os webServers: o backend muda para um
// banco novo em cada execução e o globalSetup roda DEPOIS dos webServers
// iniciarem (se isto apagasse o diretório aqui, o backend ficaria com conexões
// órfãs para um sqlite desvinculado e os endpoints agregados responderiam 500).
const E2E_DIR = '/tmp/argus-e2e';

export default async function globalSetup() {
  await mkdir(E2E_DIR, { recursive: true });
}