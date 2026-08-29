import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import Dashboard from '../Dashboard'
import * as client from '../../api/client'

vi.mock('../../api/client', () => ({
  getDashboardSummary: vi.fn(),
  getDashboardRuns: vi.fn(),
}))

const summary = {
  runs: { total: 2, by_status: { completed: 1, pending_review: 1 } },
  pending_reviews: 1,
  findings: { total: 3, by_severity: { critical: 1, low: 2 }, by_status: {} },
  costs: { total_cost: 0, total_tokens: 0, trace_tokens: 0, trace_cost: 0 },
}

beforeEach(() => {
  vi.clearAllMocks()
  client.getDashboardSummary.mockResolvedValue(summary)
})

describe('Dashboard', () => {
  it('renderiza runs com chips de severidade', async () => {
    client.getDashboardRuns.mockResolvedValue([
      {
        id: 1,
        status: 'completed',
        target: 'ex.com',
        findings: 3,
        by_severity: { critical: 1, low: 2 },
        cost: 0,
        tokens: 0,
        stop_reason: null,
        created_at: null,
        finished_at: null,
      },
    ])

    render(<Dashboard onOpenReport={() => {}} />)

    expect(await screen.findByText('ex.com')).toBeInTheDocument()
    expect(await screen.findByText(/crit 1/)).toBeInTheDocument()
    expect(await screen.findByText(/low 2/)).toBeInTheDocument()
    expect(screen.getByText('Ver')).toBeInTheDocument()
  })

  it('usa o rótulo "Revisar" para runs pendentes', async () => {
    client.getDashboardRuns.mockResolvedValue([
      {
        id: 2,
        status: 'pending_review',
        target: 'pending.com',
        findings: 1,
        by_severity: { high: 1 },
        cost: 0,
        tokens: 0,
        stop_reason: null,
        created_at: null,
        finished_at: null,
      },
    ])

    render(<Dashboard onOpenReport={() => {}} />)

    expect(await screen.findByText('pending.com')).toBeInTheDocument()
    expect(screen.getByText('Revisar')).toBeInTheDocument()
  })
})
