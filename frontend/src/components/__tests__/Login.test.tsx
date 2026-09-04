import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import Login from '../Login'
import * as client from '../../api/client'
import { ApiError } from '../../api/client'

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('Login', () => {
  it('entra direto em modo aberto (ui_enabled=false)', async () => {
    vi.spyOn(client, 'getMe').mockResolvedValue({ authenticated: false, ui_enabled: false })
    const onLogin = vi.fn()
    render(<Login onLogin={onLogin} />)
    await waitFor(() => expect(onLogin).toHaveBeenCalled())
    expect(screen.queryByText('Argus Engine')).not.toBeInTheDocument()
  })

  it('mostra o formulário em modo protegido', async () => {
    vi.spyOn(client, 'getMe').mockResolvedValue({ authenticated: false, ui_enabled: true })
    render(<Login onLogin={vi.fn()} />)
    expect(await screen.findByText('Argus Engine')).toBeInTheDocument()
    expect(screen.getByLabelText('Senha')).toBeInTheDocument()
  })

  it('loga com senha correta', async () => {
    vi.spyOn(client, 'getMe').mockResolvedValue({ authenticated: false, ui_enabled: true })
    vi.spyOn(client, 'login').mockResolvedValue({ authenticated: true })
    const onLogin = vi.fn()
    render(<Login onLogin={onLogin} />)
    const input = await screen.findByLabelText('Senha')
    fireEvent.change(input, { target: { value: 'secret' } })
    fireEvent.click(screen.getByText('Entrar'))
    await waitFor(() => expect(client.login).toHaveBeenCalledWith('secret'))
    expect(onLogin).toHaveBeenCalled()
  })

  it('mostra "Senha inválida." em 401', async () => {
    vi.spyOn(client, 'getMe').mockResolvedValue({ authenticated: false, ui_enabled: true })
    vi.spyOn(client, 'login').mockRejectedValue(new ApiError(401, 'invalid'))
    render(<Login onLogin={vi.fn()} />)
    const input = await screen.findByLabelText('Senha')
    fireEvent.change(input, { target: { value: 'wrong' } })
    fireEvent.click(screen.getByText('Entrar'))
    expect(await screen.findByText('Senha inválida.')).toBeInTheDocument()
  })

  it('mostra aviso de modo aberto em 409', async () => {
    vi.spyOn(client, 'getMe').mockResolvedValue({ authenticated: false, ui_enabled: true })
    vi.spyOn(client, 'login').mockRejectedValue(new ApiError(409, 'open'))
    render(<Login onLogin={vi.fn()} />)
    const input = await screen.findByLabelText('Senha')
    fireEvent.change(input, { target: { value: 'x' } })
    fireEvent.click(screen.getByText('Entrar'))
    expect(await screen.findByText(/modo aberto/i)).toBeInTheDocument()
  })

  it('mostra "Serviço indisponível." em erro de rede', async () => {
    vi.spyOn(client, 'getMe').mockResolvedValue({ authenticated: false, ui_enabled: true })
    vi.spyOn(client, 'login').mockRejectedValue(new Error('network'))
    render(<Login onLogin={vi.fn()} />)
    const input = await screen.findByLabelText('Senha')
    fireEvent.change(input, { target: { value: 'x' } })
    fireEvent.click(screen.getByText('Entrar'))
    expect(await screen.findByText('Serviço indisponível.')).toBeInTheDocument()
  })
})
