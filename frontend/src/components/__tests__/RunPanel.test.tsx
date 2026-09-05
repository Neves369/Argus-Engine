import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import RunPanel from '../RunPanel'
import type { ChatMessage, PendingReview, RunFinding } from '../../api/client'
import { getReportExport } from '../../api/client'

vi.mock('../../api/client')

const baseProps = {
  runId: 1,
  status: 'completed' as const,
  running: false,
  log: [],
  chat: [],
  meta: {},
  findings: [] as RunFinding[],
  trace: [],
  pendingReview: null,
  reviewing: false,
  readonly: false,
  onReview: vi.fn(),
  onCancel: vi.fn(),
  onClose: vi.fn(),
}

const finding: RunFinding = {
  id: 1,
  title: 'Apache exposto (CVE-2021-41773)',
  severity: 'critical',
  category: 'A06',
  affected: 'Apache 2.4.49',
  cvss_score: 7.5,
  cves: ['CVE-2021-41773'],
  known_exploits: ['Exploit-DB 50383'],
  description: 'Versão desatualizada.',
  remediation: 'Atualize.',
  references: ['https://example.com'],
  confidence: 0.9,
  status: 'candidate',
  requires_human_review: false,
  created_at: '',
  updated_at: '',
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('RunPanel', () => {
  it('renderiza os achados na aba de resultados', () => {
    render(<RunPanel {...baseProps} findings={[finding]} />)
    expect(screen.getByText('Apache exposto (CVE-2021-41773)')).toBeInTheDocument()
    expect(screen.getByText('critical')).toBeInTheDocument()
  })

  it('mostra a revisão humana quando pendente e aciona onReview', () => {
    const pending: PendingReview = {
      id: 'review-1',
      kind: 'destructive_action',
      context: 'Executar ação destrutiva?',
      proposal: { tool: 'nmap' },
    }
    render(<RunPanel {...baseProps} status="pending_review" pendingReview={pending} />)

    expect(screen.getByText('Revisão humana exigida')).toBeInTheDocument()
    expect(screen.getByText('Executar ação destrutiva?')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Aprovar'))
    expect(baseProps.onReview).toHaveBeenCalledWith(true, '')

    fireEvent.click(screen.getByText('Rejeitar'))
    expect(baseProps.onReview).toHaveBeenCalledWith(false, '')
  })

  it('exporta o relatório no formato escolhido pelo select', async () => {
    vi.mocked(getReportExport).mockResolvedValue('conteúdo-exportado')
    // jsdom não implementa createObjectURL/revokeObjectURL.
    const createObjectURL = vi.fn().mockReturnValue('blob:mock')
    const revokeObjectURL = vi.fn()
    Object.assign(URL, { createObjectURL, revokeObjectURL })

    render(<RunPanel {...baseProps} />)

    const select = screen.getByLabelText('Exportar') as HTMLSelectElement
    fireEvent.change(select, { target: { value: 'sarif' } })

    await waitFor(() => expect(getReportExport).toHaveBeenCalledWith(1, 'sarif'))
    expect(createObjectURL).toHaveBeenCalled()
    // o select volta para o placeholder — permite exportar o mesmo formato de novo
    await waitFor(() => expect(select.value).toBe(''))
  })

  it('mostra os metadados do entry (correlações CVE, achados, fontes, scan) no chat', () => {
    const messages: ChatMessage[] = [
      {
        agent: 'hermit',
        action: 'simulate',
        reasoning: 'Resumo da investigação.',
        findings: 3,
        sources: 2,
        scanned: true,
        pages: 5,
        cve_correlations: 2,
      },
      {
        agent: 'justice',
        action: 'validate',
        reasoning: 'Avaliação final.',
      },
    ]
    const { container } = render(<RunPanel {...baseProps} chat={messages} />)

    fireEvent.click(screen.getByRole('button', { name: /^Chat/ }))
    expect(screen.getByText('2 correlações CVE')).toBeInTheDocument()
    expect(screen.getByText('3 achados')).toBeInTheDocument()
    expect(screen.getByText('2 fontes')).toBeInTheDocument()
    expect(screen.getByText(/scan ativo/)).toBeInTheDocument()
    expect(screen.getByText(/5 páginas/)).toBeInTheDocument()
    // entry sem metadados não renderiza a linha de chips
    const chips = container.querySelectorAll('.run-panel-chat-chip')
    expect(chips.length).toBe(4)
  })
})
