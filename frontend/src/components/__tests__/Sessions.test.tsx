import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import Sessions from '../Sessions'
import * as client from '../../api/client'

vi.mock('../../api/client', () => ({
  listRuns: vi.fn(),
  listCompositions: vi.fn(),
  listTargets: vi.fn(),
}))

const runs = [
  {
    id: 7,
    status: 'completed',
    started_at: null,
    finished_at: null,
    created_at: null,
    target_id: null,
    result: { target: { name: 'ex.com' } },
  },
]

const compositions = [
  { id: 3, name: 'Comp A', status: 'done', config: { archetypes: ['hermit', 'justica'] } },
]

const targets = [{ id: 1, name: 'api.ex.com', url: 'https://api.ex.com', notes: '', created_at: 'x' }]

beforeEach(() => {
  vi.clearAllMocks()
  client.listRuns.mockResolvedValue(runs)
  client.listCompositions.mockResolvedValue(compositions)
  client.listTargets.mockResolvedValue(targets)
})

describe('Sessions', () => {
  it('abre na aba Composições', async () => {
    render(<Sessions onLoad={() => {}} onExecute={async () => {}} onOpenReport={() => {}} onSelectTarget={() => {}} />)

    expect(await screen.findByText('Comp A')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Composições' }).getAttribute('aria-selected')).toBe('true')
  })

  it('troca para a aba Alvos e usa o alvo selecionado', async () => {
    const onSelectTarget = vi.fn()
    render(<Sessions onLoad={() => {}} onExecute={async () => {}} onOpenReport={() => {}} onSelectTarget={onSelectTarget} />)

    fireEvent.click(screen.getByRole('tab', { name: 'Alvos' }))

    expect(await screen.findByText('api.ex.com')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Usar' }))

    expect(onSelectTarget).toHaveBeenCalledWith(targets[0])
  })

  it('troca para a aba Execuções e mostra o histórico', async () => {
    render(<Sessions onLoad={() => {}} onExecute={async () => {}} onOpenReport={() => {}} onSelectTarget={() => {}} />)

    fireEvent.click(screen.getByRole('tab', { name: 'Execuções' }))

    expect(await screen.findByText('ex.com')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ver' })).toBeInTheDocument()
  })
})