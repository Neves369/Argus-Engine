import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import Settings from '../Settings'
import * as client from '../../api/client'

vi.mock('../../api/client', () => ({
  listProviders: vi.fn(),
  setProviderApiKey: vi.fn(),
  setProviderEnabled: vi.fn(),
  getKillSwitchStatus: vi.fn(),
  activateKillSwitch: vi.fn(),
  changePassword: vi.fn(),
}))

const providerConfigs = [
  {
    provider: 'groq',
    models: ['llama-3.3-70b-versatile'],
    price_in: 0,
    price_out: 0,
    base_url: 'https://api.groq.com/openai/v1',
    has_api_key: false,
    key_source: null,
    enabled: true,
    usage_tokens: 0,
    usage_cost: 0,
  },
]

beforeEach(() => {
  vi.clearAllMocks()
  client.listProviders.mockResolvedValue({
    providers: providerConfigs,
    has_encryption_configured: true,
  } as client.ProvidersResponse)
})

async function openSecurityTab() {
  fireEvent.click(await screen.findByRole('tab', { name: 'Segurança' }))
}

describe('Settings — Segurança (kill-switch)', () => {
  it('mostra o status do kill-switch e ativa com motivo e confirmação', async () => {
    client.getKillSwitchStatus.mockResolvedValue({ active: false, source: 'none' })
    client.activateKillSwitch.mockResolvedValue({ active: true, source: 'runtime' })

    openSecurityTab()
    render(<Settings onClose={() => {}} />)
    await openSecurityTab()

    expect(await screen.findByText('Inativo')).toBeInTheDocument()

    const reasonInput = screen.getByLabelText(/Motivo/)
    await fireEvent.change(reasonInput, { target: { value: 'incidente em andamento' } })

    const armButton = screen.getByRole('button', { name: 'Ativar kill-switch' })
    expect(armButton).toBeEnabled()
    fireEvent.click(armButton)

    fireEvent.click(screen.getByRole('button', { name: 'Confirmar ativação' }))

    await waitFor(() => {
      expect(client.activateKillSwitch).toHaveBeenCalledWith('incidente em andamento')
    })
    expect(await screen.findByText('ATIVO (runtime)')).toBeInTheDocument()
  })

  it('não ativa o kill-switch sem motivo', async () => {
    client.getKillSwitchStatus.mockResolvedValue({ active: false, source: 'none' })

    openSecurityTab()
    render(<Settings onClose={() => {}} />)
    await openSecurityTab()
    await screen.findByText('Inativo')

    const armButton = screen.getByRole('button', { name: 'Ativar kill-switch' })
    expect(armButton).toBeDisabled()
  })

  it('mostra env ativo e bloqueia nova ativação', async () => {
    client.getKillSwitchStatus.mockResolvedValue({ active: true, source: 'env' })

    render(<Settings onClose={() => {}} />)
    await openSecurityTab()

    expect(
      await screen.findByText(/ATIVO \(via KILL_SWITCH no ambiente/)
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ativar kill-switch' })).toBeDisabled()
  })
})

describe('Settings — Segurança (troca de senha)', () => {
  it('troca a senha, valida confirmação e notifica logout após invalidar sessões', async () => {
    client.getKillSwitchStatus.mockResolvedValue({ active: false, source: 'none' })
    client.changePassword.mockResolvedValue({ ok: true, sessions_invalidated: true })
    const onSessionInvalidated = vi.fn()

    openSecurityTab()
    render(<Settings onClose={() => {}} onSessionInvalidated={onSessionInvalidated} />)
    await openSecurityTab()

    await screen.findByText('Inativo')

    const current = screen.getByLabelText(/Senha atual/)
    const next = screen.getByLabelText(/Nova senha/)
    const confirm = screen.getByLabelText(/Confirmar nova senha/)

    fireEvent.change(current, { target: { value: 'velha-senha' } })
    fireEvent.change(next, { target: { value: 'nova-forte-123' } })
    fireEvent.change(confirm, { target: { value: 'nova-forte-12' } }) // confirmação errada
    fireEvent.click(screen.getByRole('button', { name: 'Trocar senha' }))

    expect(await screen.findByText(/confirmação não confere/)).toBeInTheDocument()
    expect(client.changePassword).not.toHaveBeenCalled()

    fireEvent.change(confirm, { target: { value: 'nova-forte-123' } })
    fireEvent.click(screen.getByRole('button', { name: 'Trocar senha' }))

    await waitFor(() => {
      expect(client.changePassword).toHaveBeenCalledWith(
        'velha-senha',
        'nova-forte-123',
      )
    })
    await waitFor(() => {
      expect(onSessionInvalidated).toHaveBeenCalledTimes(1)
    })
  })

  it('bloqueia a troca quando a criptografia não está configurada', async () => {
    client.getKillSwitchStatus.mockResolvedValue({ active: false, source: 'none' })
    client.listProviders.mockResolvedValue({
      providers: providerConfigs,
      has_encryption_configured: false,
    } as client.ProvidersResponse)

    openSecurityTab()
    render(<Settings onClose={() => {}} />)
    await openSecurityTab()

    const mentions = await screen.findAllByText(/ARGUS_ENCRYPTION_KEY/)
    expect(mentions.length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: 'Trocar senha' })).toBeDisabled()
  })
})