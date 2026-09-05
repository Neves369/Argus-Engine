import { create } from 'zustand'

/**
 * Estado de UI global (Zustand — stack opcional de estado).
 *
 * Slice selecionado a dedo para não competir com o estado de execução (runId,
 * log, chat etc.), que continua local no App: aqui mora o que é transversal
 * e de interesse de vários componentes — modais, busy e o toast de resultado.
 * O App reage com `useUIStore` no lugar de seus `useState` desses campos.
 */
interface UIState {
  playerModalOpen: boolean
  enemyModalOpen: boolean
  settingsOpen: boolean
  sessionsOpen: boolean
  dashboardOpen: boolean
  runResult: string | null
  busy: boolean

  openPlayer: () => void
  closePlayer: () => void
  setEnemyModalOpen: (open: boolean) => void
  setSettingsOpen: (open: boolean) => void
  setSessionsOpen: (open: boolean) => void
  setDashboardOpen: (open: boolean) => void
  setRunResult: (result: string | null) => void
  setBusy: (busy: boolean) => void
}

export const useUIStore = create<UIState>((set) => ({
  playerModalOpen: false,
  enemyModalOpen: false,
  settingsOpen: false,
  sessionsOpen: false,
  dashboardOpen: false,
  runResult: null,
  busy: false,

  openPlayer: () => set({ playerModalOpen: true }),
  closePlayer: () => set({ playerModalOpen: false }),
  setEnemyModalOpen: (open) => set({ enemyModalOpen: open }),
  setSettingsOpen: (open) => set({ settingsOpen: open }),
  setSessionsOpen: (open) => set({ sessionsOpen: open }),
  setDashboardOpen: (open) => set({ dashboardOpen: open }),
  setRunResult: (result) => set({ runResult: result }),
  setBusy: (busy) => set({ busy }),
}))