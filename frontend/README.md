# React + TypeScript + Vite

## Integração com o backend (Argus Engine)

O frontend consome a API real do backend via proxy de desenvolvimento (`/api` →
`http://localhost:8000`). O cliente tipado fica em `src/api/client.ts`:

- `listTargets`, `createTarget`, `createRun`, `listRuns`, `getRun`, `listFindings`
- `streamRun` — acompanha a execução do grafo via SSE (`EventSource`).
- `listCompositions`, `getComposition`, `createComposition`, `deleteComposition`,
  `executeComposition` — composição do grafo (Etapa 8).

`src/components/Sessions.tsx` lista os runs reais (`GET /api/v1/runs`) e o
`EndTurnButton` dispara um run real (`Modo Death` → `devil_mode`).

## Composição do grafo (Etapa 8)

- A **mão** (`Hand`) vira a paleta: clicar numa carta adiciona o nó ao canvas
  (`PlayedArea`, React Flow) em modo composição (nós arrastáveis).
- A **sequência** é a posição X dos nós (esquerda→direita); `justice` deve ficar à
  direita (regra de `validate_sequence` no backend). `App.tsx` deriva
  `CARD_ARCHETYPES` (id → chave de arquétipo) para montar a lista.
- **Salvar** → `createComposition` (persiste em `sessions.config`), garantindo que a
  cena fique salva e recarregável.
- **Executar** → `createComposition` + `streamRun` (SSE `/runs/stream`): o canvas
  destaca o **nó ativo** a cada evento `node` (arquétipos passados como
  `?archetypes=...`) e marca o nó final como concluído ao receber `done`; o resumo é
  exibido no toast e as composições salvas ficam listadas (executáveis e carregáveis
  para edição) no modal Sessões.

---

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend updating the configuration to enable type-aware lint rules:

```js
export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...

      // Remove tseslint.configs.recommended and replace with this
      tseslint.configs.recommendedTypeChecked,
      // Alternatively, use this for stricter rules
      tseslint.configs.strictTypeChecked,
      // Optionally, add this for stylistic rules
      tseslint.configs.stylisticTypeChecked,

      // Other configs...
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])

```

You can also install [eslint-plugin-react-x](https://npmx.dev/package/eslint-plugin-react-x) and [eslint-plugin-react-dom](https://npmx.dev/package/eslint-plugin-react-dom) for React-specific lint rules:

```js
// eslint.config.js
import reactX from 'eslint-plugin-react-x'
import reactDom from 'eslint-plugin-react-dom'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...
      // Enable lint rules for React
      reactX.configs['recommended-typescript'],
      // Enable lint rules for React DOM
      reactDom.configs.recommended,
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])

```
